"""LLM 응답 캐시 재생 (계약 §4 L0) — 프롬프트 sha256 키 → 응답 파일.

`CacheReplayLLM` 은 LLMPort 를 감싼다. 키 = sha256(JSON{system, prompt, json_mode}). 캐시 폴더
(`tests/eval/l0_cache/<key>.json` = {"response": …})에 있으면 호출 없이 응답을 돌려주고(적중),
없으면
- `inner` 가 있으면(녹화 모드, `rra eval run --suite l0 --record`) 안쪽 LLM 을 부르고 응답을 저장,
- 없으면 `CacheMiss` 를 던진다 → SameJudge 는 실패로 보고 규칙 판정으로 간다.
응답 본문은 합성 코퍼스에 대한 판정 JSON 뿐이다(사내 본문 없음) — 캐시는 커밋한다.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from rra.application.ports.eval_store import CacheMiss


def cache_key(prompt: str, *, system: str | None, json_mode: bool) -> str:
    body = json.dumps(
        {"system": system or "", "prompt": prompt, "json_mode": bool(json_mode)},
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


class CacheReplayLLM:
    provider = "cache"
    model_name = "cache-replay"

    def __init__(self, cache_dir: str | Path, *, inner: Any | None = None):
        self.cache_dir = Path(cache_dir)
        self.inner = inner
        self.hits = 0
        self.misses = 0
        self.recorded = 0

    def __repr__(self) -> str:
        return f"CacheReplayLLM({self.cache_dir}, hits={self.hits}, misses={self.misses})"

    def _path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    async def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str:
        key = cache_key(prompt, system=system, json_mode=json_mode)
        path = self._path(key)
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            self.hits += 1
            return str(data.get("response") or "")
        self.misses += 1
        if self.inner is None:
            raise CacheMiss(key[:12])
        response = await self.inner.complete(
            prompt, system=system, max_tokens=max_tokens, json_mode=json_mode
        )
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"response": response}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self.recorded += 1
        return response

    async def aclose(self) -> None:
        close = getattr(self.inner, "aclose", None)
        if close is not None:
            await close()
