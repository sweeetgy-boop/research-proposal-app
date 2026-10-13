"""`python -m rra.entrypoints.ui` → streamlit run app.py (127.0.0.1 고정)."""

from __future__ import annotations

import sys
from pathlib import Path

APP = Path(__file__).with_name("app.py")
BIND = ["--server.address", "127.0.0.1", "--server.headless", "true"]


def main(extra: list[str] | None = None) -> int:
    from streamlit.web import cli as stcli

    sys.argv = ["streamlit", "run", str(APP), *BIND, *(extra or [])]
    try:
        stcli.main()
    except SystemExit as exc:  # click 이 종료 코드를 SystemExit 로 올린다
        return int(exc.code or 0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
