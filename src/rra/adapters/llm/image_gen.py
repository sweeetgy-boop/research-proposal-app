"""ImageGeneratorPort 구현 — Gemini 이미지 생성(Nano Banana Pro, `generateContent` 이미지 출력) [G].

- 엔드포인트: `<native_base>/models/<image_model>:generateContent`. native_base 는 llm.yaml
  providers.gemini base_url 에서 `/openai/` 를 뗀 것(`…googleapis.com/v1beta`). 보안 C·H:
  `guard_base_url` 로 https·허용 도메인 검사.
- 보안 D: 키는 `x-goog-api-key` 헤더로만. 로그·예외 메시지에 키·프롬프트·이미지가 들어가지 않는다.
- 외부로 나가는 것: 프롬프트(명세 글자 목록)와 참고 이미지(밑그림 또는 현재 그림)뿐.
- 공용 제한기 `limiter_for("gemini")` 를 거치고, 일일 상한 카운터(`DailyBudgetPort`)를 넘으면
  `ImageBudgetExhausted`. 같은 (모델, 프롬프트, 참고 이미지 해시, 비율, 크기)는 캐시 디렉터리에서
  돌려준다(호출·상한 소비 없음).
- 429/5xx/타임아웃은 RetryPolicy 로 재시도, 401/403 은 즉시 실패.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import httpx

from rra.adapters.llm._endpoint import USER_AGENT, guard_base_url
from rra.adapters.llm.errors import LLMError
from rra.adapters.llm.rate_limiter import RateLimiter, limiter_for, parse_retry_after
from rra.adapters.runs._fs import ensure_dir, write_bytes
from rra.application.ports.auth import DailyBudgetPort
from rra.application.ports.figures import ImageBudgetExhausted, ImageResult

logger = logging.getLogger("rra.llm.image")

DEFAULT_MODEL = "gemini-3-pro-image"
ALLOWED_MIME = frozenset({"image/png", "image/jpeg", "image/webp"})
MAX_REFERENCE_BYTES = 6 * 1024 * 1024
MAX_PROMPT_CHARS = 6000
MAX_RESPONSE_BYTES = 12 * 1024 * 1024
_RETRY_STATUS = frozenset({408, 429, 500, 502, 503, 504})
_HASH = re.compile(r"^[0-9a-f]{32}$")


def native_base_url(base_url: str) -> str:
    """OpenAI 호환 경로(`…/v1beta/openai/`) → 네이티브(`…/v1beta`)."""
    value = base_url.strip().rstrip("/")
    if value.endswith("/openai"):
        value = value[: -len("/openai")]
    return value


class GeminiImageGenerator:
    provider = "gemini"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str = DEFAULT_MODEL,
        allowed_hosts: Iterable[str] | None = None,
        timeout_sec: float = 180.0,
        attempts: int = 3,
        backoff_sec: float = 1.0,
        limiter: RateLimiter | None = None,
        budget: DailyBudgetPort | None = None,
        cache_dir: Path | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        if not api_key or not api_key.strip():
            raise LLMError("Gemini 키가 없습니다 (RRA_GEMINI_API_KEY).")
        self.base_url = guard_base_url("gemini", native_base_url(base_url), allowed_hosts)
        self.model = model
        self._key = api_key.strip()
        self.timeout_sec = timeout_sec
        self.attempts = max(1, int(attempts))
        self.backoff_sec = backoff_sec
        self.limiter = limiter or limiter_for("gemini")
        self.budget = budget
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_sec, connect=10.0),
            headers={"user-agent": USER_AGENT},
            transport=transport,
        )
        self.calls = 0  # 실제 전송 수 (캐시 적중 제외)

    def __repr__(self) -> str:
        return f"GeminiImageGenerator(model={self.model})"

    async def aclose(self) -> None:
        await self._client.aclose()

    # ── 포트 ─────────────────────────────────────────────
    async def generate(
        self,
        prompt: str,
        reference: bytes,
        *,
        mime: str = "image/png",
        aspect: str = "16:9",
        size: str = "2K",
    ) -> ImageResult:
        return await self._call(prompt, reference, mime, aspect, size)

    async def edit(
        self,
        prompt: str,
        image: bytes,
        *,
        mime: str,
        aspect: str = "16:9",
        size: str = "2K",
    ) -> ImageResult:
        return await self._call(prompt, image, mime, aspect, size)

    # ── 내부 ─────────────────────────────────────────────
    async def _call(
        self, prompt: str, image: bytes, mime: str, aspect: str, size: str
    ) -> ImageResult:
        if mime not in ALLOWED_MIME:
            raise LLMError(f"지원하지 않는 이미지 형식입니다: {mime}")
        if not image or len(image) > MAX_REFERENCE_BYTES:
            raise LLMError("참고 이미지가 비었거나 상한을 넘습니다.")
        if len(prompt) > MAX_PROMPT_CHARS:
            raise LLMError("프롬프트가 상한을 넘습니다.")
        key = self._cache_key(prompt, image, aspect, size)
        cached = self._cache_get(key)
        if cached is not None:
            return cached
        if self.budget is not None and not self.budget.try_spend():
            raise ImageBudgetExhausted("오늘 그림 호출 상한에 이르렀습니다.")
        body = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": mime,
                                "data": base64.b64encode(image).decode("ascii"),
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "responseModalities": ["IMAGE", "TEXT"],
                "imageConfig": {"aspectRatio": aspect, "imageSize": size},
            },
        }
        url = f"{self.base_url}/models/{self.model}:generateContent"
        data = await self._post(url, body)
        result = self._extract(data)
        self._cache_put(key, result)
        return result

    async def _post(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        last: Exception | None = None
        for attempt in range(self.attempts):
            await self.limiter.acquire()
            try:
                self.calls += 1
                resp = await self._client.post(
                    url,
                    json=body,
                    headers={"x-goog-api-key": self._key, "content-type": "application/json"},
                )
            except httpx.HTTPError as exc:
                last = LLMError(f"이미지 생성 요청 실패: {type(exc).__name__}")
                self.limiter.release()
                await asyncio.sleep(self._backoff(attempt))
                continue
            try:
                if resp.status_code in (401, 403):
                    raise LLMError(f"이미지 생성 인증 실패 ({resp.status_code}).")
                if resp.status_code in _RETRY_STATUS:
                    wait = parse_retry_after(resp.headers.get("retry-after"))
                    last = LLMError(f"이미지 생성 일시 실패 ({resp.status_code}).")
                    if resp.status_code == 429:
                        self.limiter.note_429(wait)
                    await asyncio.sleep(wait if wait is not None else self._backoff(attempt))
                    continue
                if resp.status_code != 200:
                    raise LLMError(f"이미지 생성 실패 ({resp.status_code}).")
                if len(resp.content) > MAX_RESPONSE_BYTES:
                    raise LLMError("이미지 응답이 상한을 넘습니다.")
                try:
                    return resp.json()
                except ValueError as exc:
                    raise LLMError("이미지 응답이 JSON 이 아닙니다.") from exc
            finally:
                self.limiter.release()
        raise last or LLMError("이미지 생성 실패.")

    def _backoff(self, attempt: int) -> float:
        return min(self.backoff_sec * (2**attempt), 16.0)

    def _extract(self, data: dict[str, Any]) -> ImageResult:
        try:
            parts = data["candidates"][0]["content"]["parts"]
        except (KeyError, IndexError, TypeError) as exc:
            reason = ""
            try:
                reason = str(data["candidates"][0].get("finishReason", ""))
            except Exception:  # noqa: BLE001 — 응답 구조 불명
                reason = ""
            raise LLMError(f"이미지 응답에 결과가 없습니다 ({reason or 'no_candidates'}).") from exc
        for part in parts:
            inline = part.get("inlineData") or part.get("inline_data")
            if isinstance(inline, dict) and inline.get("data"):
                mime = str(inline.get("mimeType") or inline.get("mime_type") or "image/png")
                try:
                    raw = base64.b64decode(inline["data"], validate=False)
                except (ValueError, TypeError) as exc:
                    raise LLMError("이미지 데이터를 풀 수 없습니다.") from exc
                if not raw:
                    raise LLMError("이미지 데이터가 비어 있습니다.")
                return ImageResult(raw, mime if mime in ALLOWED_MIME else "image/png", self.model)
        raise LLMError("이미지 응답에 그림이 없습니다 (텍스트만).")

    # ── 캐시 ─────────────────────────────────────────────
    def _cache_key(self, prompt: str, image: bytes, aspect: str, size: str) -> str:
        h = hashlib.sha256()
        for item in (self.model, prompt, aspect, size):
            h.update(item.encode("utf-8"))
            h.update(b"\x1f")
        h.update(hashlib.sha256(image).digest())
        return h.hexdigest()[:32]

    def _cache_get(self, key: str) -> ImageResult | None:
        if self.cache_dir is None or not _HASH.match(key):
            return None
        meta = self.cache_dir / f"{key}.json"
        if not meta.is_file():
            return None
        try:
            info = json.loads(meta.read_text(encoding="utf-8"))
            data = (self.cache_dir / f"{key}.{info['ext']}").read_bytes()
        except (OSError, ValueError, KeyError):
            return None
        return ImageResult(
            data, str(info.get("mime", "image/png")), str(info.get("model", self.model))
        )

    def _cache_put(self, key: str, result: ImageResult) -> None:
        if self.cache_dir is None:
            return
        try:
            ensure_dir(self.cache_dir)
            ext = "jpg" if result.mime == "image/jpeg" else "png"
            write_bytes(self.cache_dir / f"{key}.{ext}", result.data)
            write_bytes(
                self.cache_dir / f"{key}.json",
                json.dumps({"mime": result.mime, "model": result.model, "ext": ext}).encode(),
            )
        except OSError:
            logger.warning("figure.cache_write_failed")
