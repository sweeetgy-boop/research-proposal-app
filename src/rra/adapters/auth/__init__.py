"""로그인 저장소 어댑터 (레인 A) — data/auth/ 파일. 사번은 HMAC-SHA256, 비밀번호는 scrypt.
사번 명부 파일(xlsx·csv) 읽기는 `roster.RosterReader`(샌드박스, 사번 열만)."""

from rra.adapters.auth.file_store import FileAuthStore
from rra.adapters.auth.roster import RosterReader

__all__ = ["FileAuthStore", "RosterReader"]
