"""실제 fixture 의 추출 결과 요약을 출력해 expected.yaml 작성을 돕는다 (샌드박스 경유).

python -m tests.adapters.alio.dump_fixture tests/fixtures/alio/real/<파일>
"""

import asyncio
import sys
from pathlib import Path

import yaml

from rra.adapters.sources._sandbox import SandboxLimits, run_parser
from rra.adapters.sources.alio.filecheck import open_validated
from rra.adapters.sources.alio.filedrop import FILE_FORMATS


async def dump(path: Path) -> None:
    security = yaml.safe_load(Path("config/security.yaml").read_text(encoding="utf-8"))
    limits = SandboxLimits.from_security_config(security)
    max_bytes = int(limits.max_input_mb * 1024 * 1024)
    with open_validated(path, max_bytes=max_bytes, allowed=FILE_FORMATS) as vf:
        result = await run_parser(vf.fd, vf.fmt, limits)
        entry = {
            "file": path.name,
            "fmt": vf.fmt,
            "sha256": vf.sha256,
            "pages": result.get("pages"),
            "meta_title": result.get("meta_title"),
            "chars": len(result["text"]),
            "toc_count": len(result.get("toc") or []),
            "toc_head": (result.get("toc") or [])[:10],
            "text_head": result["text"][:800],
        }
    print(yaml.safe_dump(entry, allow_unicode=True, sort_keys=False))


if __name__ == "__main__":
    asyncio.run(dump(Path(sys.argv[1])))
