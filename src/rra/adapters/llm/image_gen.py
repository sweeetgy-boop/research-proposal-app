"""ImageGeneratorPort 구현 — Gemini 이미지 생성(Nano Banana Pro, `generateContent` 이미지 출력) [G].

- 엔드포인트: `<native_base>/models/<image_model>:generateContent`. native_base 는 llm.yaml
  providers.gemini base_url 에서 `/openai/` 를 뗀 것(`…googleapis.com/v1beta`). 보안 C·H:
  `guard_base_url` 로 https·허용 도메인 검사.
- 보안 D: 키는 `x-goog-api-key` 헤더로만. 로그·예외 메시지에 키·프롬프트·이미지가 들어가지 않는다.
- 외부로 나가는 것: 프롬프트(명세 글자 목록)와 참고 이미지(밑그림 또는 현재 그림)뿐.
- 공용 제한기 `limiter_for("gemini")` 를 거치고, 일일 상한 카운터(`DailyBudgetPort`)를 넘으면
  `ImageBudgetExhausted`. 같은 (모델, 프롬프트, 참고 이미지 해시, 비율, 크기)는 캐시 디렉터리에서
  돌려준다(호출·상한 소비 없음).
- 429/5xx/타임아웃은 RetryPolicy 로 재시도, 401/403·키 무효 400 은 즉시 실패.
- 오류 분류(ADR 0055 덧붙임, 2026-11-04): 텍스트 호출(openai_compat)과 같은 `_payload` 분류 —
  400 API_KEY_INVALID·401·403 → LLMAuthError, 429 할당량 → LLMQuotaExceeded(그 밖 429 는
  LLMRateLimited), 타임아웃 → LLMTimeout, 연결 실패 code=connection, 5xx code=server. 실패 1건마다
  같은 `llm.failed provider=gemini stage=figure_image …` 경고 한 줄(열거값만).
- 상태(status, LLMStatusPort): 그림 결과는 `gemini_image` 에 적는다(/healthz 에 내지 않는다).
  키 무효는 `gemini`(텍스트·띠) 에도 올리고, 그림 성공은 `gemini` 가 key_invalid 일 때만 ok 로
  되돌린다. 그림의 할당량·응답 없음은 `gemini` 를 바꾸지 않는다
  (domain/rules/llm_status.text_status_from_image).
- 응답 시간 기록(`*.latency.jsonl`)은 그림 경로에 없다 — 일일 상한 카운터만 쓴다.
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

from rra.adapters.llm import _payload
from rra.adapters.llm._endpoint import USER_AGENT, guard_base_url
from rra.adapters.llm.errors import (
    LLMAuthError,
    LLMError,
    LLMQuotaExceeded,
    LLMRateLimited,
    LLMResponseInvalid,
    LLMTimeout,
)
from rra.adapters.llm.rate_limiter import RateLimiter, limiter_for, parse_retry_after
from rra.adapters.runs._fs import ensure_dir, write_bytes
from rra.application.ports.auth import DailyBudgetPort
from rra.application.ports.figures import ImageBudgetExhausted, ImageResult
from rra.application.ports.llm_status import LLMStatusPort
from rra.domain.rules import llm_status

logger = logging.getLogger("rra.llm.image")

DEFAULT_MODEL = "gemini-3-pro-image"
ALLOWED_MIME = frozenset({"image/png", "image/jpeg", "image/webp"})
MAX_REFERENCE_BYTES = 6 * 1024 * 1024
MAX_PROMPT_CHARS = 6000
MAX_RESPONSE_BYTES = 12 * 1024 * 1024
_RETRY_STATUS = frozenset({408, 429, 500, 502, 503, 504})
_HASH = re.compile(r"^[0-9a-f]{32}$")
STAGE = "figure_image"  # 실패 경고 줄의 단계 이름


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
        status: LLMStatusPort | None = None,
        stage: str = STAGE,
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
        # 연결 상태 기록(ADR 0055 덧붙임) — 조립이 텍스트와 같은 상태 파일을 넘긴다
        self.status = status
        self.stage = stage
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
            raise LLMError(f"지원하지 않는 이미지 형식입니다: {mime}", code="not_sent")
        if not image or len(image) > MAX_REFERENCE_BYTES:
            raise LLMError("참고 이미지가 비었거나 상한을 넘습니다.", code="not_sent")
        if len(prompt) > MAX_PROMPT_CHARS:
            raise LLMError("프롬프트가 상한을 넘습니다.", code="not_sent")
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
        """요청 1건(재시도 포함). 끝나면 연결 상태를 기록하고, 실패면 경고 한 줄을 남긴다
        (텍스트 호출과 같은 분류·같은 줄, ADR 0055 덧붙임)."""
        try:
            data = await self._post_with_retry(url, body)
        except LLMError as exc:
            logger.warning(
                _payload.FAILURE_LOG, *_payload.failure_args(self.provider, self.stage, exc)
            )
            self._note_status(llm_status.status_for_code(exc.code))
            raise
        self._note_status(llm_status.OK)
        return data

    def _note_status(self, image_status: str | None) -> None:
        """그림 결과는 gemini_image 에, 텍스트(gemini) 상태에는 규칙이 정한 것만
        (domain/rules/llm_status.text_status_from_image). 기록 실패는 호출 결과를 바꾸지 않는다."""
        if image_status is None or self.status is None:
            return
        try:
            self.status.record(llm_status.IMAGE_PROVIDER, image_status)
            text = self.status.snapshot(llm_status.TEXT_PROVIDER) or {}
            to_text = llm_status.text_status_from_image(image_status, text.get("status"))
            if to_text is not None:
                self.status.record(llm_status.TEXT_PROVIDER, to_text)
        except (OSError, ValueError) as exc:
            logger.debug("figure.status_failed err=%s", type(exc).__name__)

    async def _post_with_retry(self, url: str, body: dict[str, Any]) -> dict[str, Any]:
        last: LLMError | None = None
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
                if isinstance(exc, httpx.TimeoutException):
                    last = LLMTimeout(f"이미지 생성 응답 시간 초과 ({type(exc).__name__})")
                else:
                    last = LLMError(
                        f"이미지 생성 요청 실패: {type(exc).__name__}", code="connection"
                    )
                self.limiter.release()
                await asyncio.sleep(self._backoff(attempt))
                continue
            try:
                status = resp.status_code
                if status == 200:
                    if len(resp.content) > MAX_RESPONSE_BYTES:
                        raise LLMResponseInvalid(
                            "이미지 응답이 상한을 넘습니다.", http_status=status
                        )
                    try:
                        return resp.json()
                    except ValueError as exc:
                        raise LLMResponseInvalid(
                            "이미지 응답이 JSON 이 아닙니다.", http_status=status
                        ) from exc
                codes = _payload.error_codes(resp.text, [self._key])
                where: dict[str, Any] = {
                    "http_status": status,
                    "api_status": codes.status,
                    "api_reason": codes.reason,
                }
                # 401/403·키 무효 400(Google API_KEY_INVALID): 재시도 없음, 본문·키 노출 없음
                if status in (401, 403) or _payload.is_key_invalid(status, resp.text, codes):
                    raise LLMAuthError(f"이미지 생성 인증 실패 ({status}).", **where)
                if status in _RETRY_STATUS:
                    wait = parse_retry_after(resp.headers.get("retry-after"))
                    if status == 429:
                        self.limiter.note_429(wait)
                        if _payload.is_quota_exhausted(resp.text, codes):
                            last = LLMQuotaExceeded(f"이미지 생성 할당량 소진 ({status}).", **where)
                        else:
                            last = LLMRateLimited(
                                f"이미지 생성 호출 한도 초과 ({status}).", **where
                            )
                    else:
                        last = LLMError(
                            f"이미지 생성 일시 실패 ({status}).",
                            code="server" if status >= 500 else "http",
                            **where,
                        )
                    await asyncio.sleep(wait if wait is not None else self._backoff(attempt))
                    continue
                raise LLMError(f"이미지 생성 실패 ({status}).", code="http", **where)
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
