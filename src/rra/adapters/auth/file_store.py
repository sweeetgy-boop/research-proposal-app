"""AuthStorePort 구현 — `<data_dir>/auth/` (폴더 700, 파일 600).

    auth/secret       무작위 32바이트(hex). 처음 실행 때 만든다. 사번 HMAC 의 키.
    auth/staff.json   {"hmacs": [hex …], "test_hmacs": [hex …]}  — HMAC-SHA256(secret, 사번) 만.
                      사번 원문 없음. test_hmacs 는 hmacs 의 부분집합 — 시험 계정(배포 확인용 임시
                      사번, `rra auth staff add --test`) 표시. 키가 없는 옛 파일은 시험 계정 0건.
    auth/guest.json   {"id", "salt", "hash", "n", "r", "p"} — scrypt. 비밀번호 원문 없음.

- 사번·비밀번호 원문은 메서드 인자로만 들어와 다이제스트를 만든 뒤 버린다. 로그 없음.
- 비교는 secrets.compare_digest. 등록 목록이 비면 직원 로그인은 항상 실패(비활성).
- 저장소가 공개라 이 폴더는 .gitignore(/data/) 아래에 있고 커밋되지 않는다.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import stat
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from rra.adapters.runs._fs import DIR_MODE, FILE_MODE, ensure_dir, read_json, write_json
from rra.application.ports.auth import StaffImportResult
from rra.domain.rules.staff_roster import normalize_staff_no

SECRET_BYTES = 32
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_LEN = 32
SALT_BYTES = 16
MAX_STAFF = 10_000


class FileAuthStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def __repr__(self) -> str:
        return f"FileAuthStore({self.root})"

    # ── 파일 ───────────────────────────────────────────
    def _ensure(self) -> Path:
        ensure_dir(self.root)
        return self.root

    def _secret(self) -> bytes:
        """비밀 키. 없으면 만든다(600). 값은 돌려주기만 하고 어디에도 기록하지 않는다."""
        path = self._ensure() / "secret"
        if not path.exists():
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, FILE_MODE)
            with os.fdopen(fd, "w", encoding="ascii") as f:
                f.write(secrets.token_hex(SECRET_BYTES))
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            os.chmod(path, FILE_MODE)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, "r", encoding="ascii") as f:
            value = f.read().strip()
        if len(value) < SECRET_BYTES * 2:
            raise ValueError(
                "auth/secret 이 손상되었습니다 — 파일을 지우고 사번을 다시 등록하십시오."
            )
        return bytes.fromhex(value)

    def _staff_file(self) -> Path:
        return self._ensure() / "staff.json"

    def _guest_file(self) -> Path:
        return self._ensure() / "guest.json"

    def _load_data(self) -> dict[str, Any]:
        path = self._staff_file()
        if not path.exists():
            return {}
        data = read_json(path)
        return data if isinstance(data, dict) else {}

    def _load_staff(self) -> list[str]:
        data = self._load_data()
        return [str(h) for h in (data.get("hmacs") or []) if isinstance(h, str)]

    def _load_test(self) -> set[str]:
        """시험 계정 표시 — 등록 목록에 있는 것만 (목록에서 빠진 표시는 무시)."""
        data = self._load_data()
        registered = {str(h) for h in (data.get("hmacs") or []) if isinstance(h, str)}
        return {str(h) for h in (data.get("test_hmacs") or []) if isinstance(h, str)} & registered

    def _save_staff(self, hmacs: list[str], test: set[str] | None = None) -> None:
        """test 가 None 이면 지금 표시를 이어 받는다. 표시는 늘 hmacs 의 부분집합."""
        kept = sorted(set(hmacs))[:MAX_STAFF]
        marks = self._load_test() if test is None else set(test)
        body: dict[str, Any] = {"hmacs": kept}
        test_hmacs = sorted(marks & set(kept))
        if test_hmacs:
            body["test_hmacs"] = test_hmacs
        write_json(self._staff_file(), body)

    def _digest(self, staff_no: str, secret: bytes | None = None) -> str:
        """정규화(공백·하이픈 제거) 뒤 HMAC. 등록·조회·일괄 등록·로그인이 같은 규칙을 쓴다."""
        message = normalize_staff_no(staff_no).encode("utf-8")
        return hmac.new(secret or self._secret(), message, hashlib.sha256).hexdigest()

    # ── 직원(사번) ──────────────────────────────────────
    def verify_staff(self, staff_no: str) -> str | None:
        registered = self._load_staff()
        if not registered or not (staff_no or "").strip():
            return None
        digest = self._digest(staff_no)
        found = False
        for h in registered:  # 전부 비교 — 위치에 따른 시간 차이를 줄인다
            if secrets.compare_digest(h, digest):
                found = True
        return digest if found else None

    def staff_enabled(self) -> bool:
        return bool(self._load_staff())

    def add_staff(self, staff_no: str, *, test: bool = False) -> bool:
        digest = self._digest(staff_no)
        current = self._load_staff()
        if digest in current:
            return False
        marks = self._load_test()
        if test:
            marks.add(digest)
        self._save_staff([*current, digest], marks)
        return True

    def remove_staff(self, staff_no: str) -> bool:
        digest = self._digest(staff_no)
        current = self._load_staff()
        if digest not in current:
            return False
        self._save_staff([h for h in current if h != digest], self._load_test() - {digest})
        return True

    def staff_count(self) -> int:
        return len(self._load_staff())

    def is_test_staff(self, digest: str) -> bool:
        if not digest:
            return False
        found = False
        for h in self._load_test():  # 전부 비교 — verify_staff 와 같은 방식
            if secrets.compare_digest(h, digest):
                found = True
        return found

    def test_staff_count(self) -> int:
        return len(self._load_test())

    def import_staff(
        self, staff_nos: Iterable[str], *, replace: bool = False, dry_run: bool = False
    ) -> StaffImportResult:
        """여러 사번을 한 번에 — 다이제스트만 만들어 합친다. 값은 여기서 버린다."""
        secret = self._secret()
        incoming: set[str] = set()
        for staff_no in staff_nos:
            value = normalize_staff_no(staff_no)
            if value:
                incoming.add(self._digest(value, secret))
        current = set(self._load_staff())
        added = len(incoming - current)
        existing = len(incoming & current)
        removed = len(current - incoming) if replace else 0
        merged = incoming if replace else current | incoming
        if len(merged) > MAX_STAFF:
            raise ValueError(f"등록 사번이 상한({MAX_STAFF}건)을 넘습니다.")
        if not dry_run:
            self._save_staff(sorted(merged))
        return StaffImportResult(added=added, existing=existing, removed=removed, saved=not dry_run)

    # ── 공용 계정 ───────────────────────────────────────
    def _load_guest(self) -> dict[str, Any] | None:
        path = self._guest_file()
        if not path.exists():
            return None
        data = read_json(path)
        return data if isinstance(data, dict) and data.get("id") and data.get("hash") else None

    def guest_id(self) -> str | None:
        guest = self._load_guest()
        return str(guest["id"]) if guest else None

    def set_guest(self, guest_id: str, password: str) -> None:
        if not password:
            raise ValueError("비밀번호가 비어 있습니다.")
        salt = secrets.token_bytes(SALT_BYTES)
        digest = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=SCRYPT_N,
            r=SCRYPT_R,
            p=SCRYPT_P,
            dklen=SCRYPT_LEN,
        )
        write_json(
            self._guest_file(),
            {
                "id": guest_id,
                "salt": salt.hex(),
                "hash": digest.hex(),
                "n": SCRYPT_N,
                "r": SCRYPT_R,
                "p": SCRYPT_P,
            },
        )

    def disable_guest(self) -> bool:
        path = self._guest_file()
        if not path.exists():
            return False
        path.unlink()
        return True

    def verify_guest(self, guest_id: str, password: str) -> bool:
        guest = self._load_guest()
        if guest is None or not password:
            return False
        try:
            digest = hashlib.scrypt(
                password.encode("utf-8"),
                salt=bytes.fromhex(guest["salt"]),
                n=int(guest.get("n", SCRYPT_N)),
                r=int(guest.get("r", SCRYPT_R)),
                p=int(guest.get("p", SCRYPT_P)),
                dklen=SCRYPT_LEN,
            )
        except (ValueError, TypeError):
            return False
        id_ok = secrets.compare_digest(str(guest["id"]), guest_id or "")
        pw_ok = secrets.compare_digest(digest.hex(), str(guest["hash"]))
        return id_ok and pw_ok

    # ── 진단 ────────────────────────────────────────────
    def status(self) -> dict[str, Any]:
        """설정 여부만 — 값·해시 없음."""
        secret_ok = (self.root / "secret").exists()
        return {
            "staff_count": self.staff_count() if self.root.exists() else 0,
            "test_staff_count": self.test_staff_count() if self.root.exists() else 0,
            "guest": self.guest_id() is not None,
            "secret": secret_ok,
            "dir_mode": oct(stat.S_IMODE(self.root.stat().st_mode)) if self.root.exists() else None,
        }

    def permissions_ok(self) -> bool:
        if not self.root.exists():
            return True
        if stat.S_IMODE(self.root.stat().st_mode) != DIR_MODE:
            return False
        return all(
            stat.S_IMODE(p.stat().st_mode) == FILE_MODE for p in self.root.iterdir() if p.is_file()
        )
