"""로그인 저장소 어댑터 (레인 A) — data/auth/ 파일. 사번은 HMAC-SHA256, 비밀번호는 scrypt."""

from rra.adapters.auth.file_store import FileAuthStore

__all__ = ["FileAuthStore"]
