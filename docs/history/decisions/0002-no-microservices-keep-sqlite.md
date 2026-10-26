# ADR 0002 — 마이크로서비스 미채택, SQLite 유지 (2026-10-23)

**배경** 구조 검토(6항목)에서 분리 배포·다른 DB 가 논의됐다.
**선택지** (a) 서비스 분리(검색·생성·검토), (b) 모놀리스 유지 + PostgreSQL/Supabase, (c) 모놀리스 + SQLite 유지.
**결정** (c). 리팩터링만 수행: 필수 슬롯 규칙 단일화, composition 분해, `_Lazy` 제거, 포트 async 통일, TaskRunner 포트.
**이유** 단일 Mac mini·사용자 수 명·수십만 청크까지는 SQLite(FTS5 + sqlite-vec, WAL)가 운영·백업·보안(파일 0600)에서 가장 단순.
전환 조건(동시 사용자 5명 초과, 100만 청크, 여러 PC 공유)을 §4.5 에 적어 두고, 저장소 계약 테스트로 2차 어댑터를 대비.
**결과** `tests/contracts/test_document_repository.py` 가 SQLite 두 백엔드·fake 를 같은 계약으로 검사. 근거 `b20deb6`~`0bcac95`, architecture §4.3·§4.5.
