"""REST API (FastAPI) — Step 10. 유스케이스 호출만, 로직 없음.

조립은 composition, 보안 미들웨어는 adapters/security.
"""

from rra.entrypoints.api.app import create_app

__all__ = ["create_app"]
