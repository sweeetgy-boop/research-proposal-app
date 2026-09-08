"""PromptLibraryPort 구현 — 프롬프트를 .md 파일로 보관한다.

- 파일 이름은 allowlist 정규식으로만 받는다 (경로 탈출 차단).
- 패키지 자원으로 읽으므로 설치본에서도 동작한다. 개발 중에는 디렉터리를 덮어쓸 수 있다.
"""

from __future__ import annotations

import re
from importlib import resources
from pathlib import Path

PROMPT_PACKAGE = "rra.adapters.llm.prompts"
SYSTEM_NAME = "system"
JSON_FALLBACK_NAME = "json_fallback"
SECTION_PREFIX = "section_"
_NAME = re.compile(r"^[a-z0-9_]+$")


class PromptNotFound(KeyError):
    """선언되지 않은 프롬프트 요청."""


class FilePromptLibrary:
    def __init__(self, directory: Path | str | None = None):
        self._dir = Path(directory) if directory else None
        self._cache: dict[str, str] = {}

    def _read(self, name: str) -> str:
        if not _NAME.fullmatch(name):
            raise PromptNotFound(f"허용되지 않는 프롬프트 이름입니다: {name!r}")
        if name in self._cache:
            return self._cache[name]
        filename = f"{name}.md"
        try:
            if self._dir is not None:
                text = (self._dir / filename).read_text(encoding="utf-8")
            else:
                text = (
                    resources.files(PROMPT_PACKAGE).joinpath(filename).read_text(encoding="utf-8")
                )
        except (FileNotFoundError, OSError) as exc:
            raise PromptNotFound(f"프롬프트 파일이 없습니다: {filename}") from exc
        text = text.strip()
        self._cache[name] = text
        return text

    # ── PromptLibraryPort ──────────────────────────────────
    def system(self) -> str:
        return self._read(SYSTEM_NAME)

    def section(self, key: str) -> str:
        return self._read(f"{SECTION_PREFIX}{key}")

    # ── 부가 ───────────────────────────────────────────────
    def json_fallback(self) -> str:
        return self._read(JSON_FALLBACK_NAME)

    def available_sections(self) -> list[str]:
        if self._dir is not None:
            names = [p.name for p in self._dir.iterdir()]
        else:
            names = [p.name for p in resources.files(PROMPT_PACKAGE).iterdir()]
        return sorted(
            n[len(SECTION_PREFIX) : -len(".md")]
            for n in names
            if n.startswith(SECTION_PREFIX) and n.endswith(".md")
        )
