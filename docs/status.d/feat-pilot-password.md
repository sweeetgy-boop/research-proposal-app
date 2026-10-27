# feat/pilot-password (2026-10-28) — 공용 계정 비밀번호 최소 길이 설정화

- `config/auth.yaml guest.min_password_length` (기본 8). **시범 운영(2026-10-28) 한정 4** 로 둠 — 시범 뒤 8 로 되돌릴 것(final-check "내가 할 일").
- 규칙은 `domain/rules/auth_policy.valid_password(value, min_length)`, CLI `rra auth guest set` 이 `auth_config` 값을 쓴다(문구도 설정값으로).
