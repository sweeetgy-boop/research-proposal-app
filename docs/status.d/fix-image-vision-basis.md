## 긴급 수정 — text_basis CHECK 에 image_vision (fix/image-vision-basis, 2026-10-27)

- 증상: `rra vision ingest` → `sqlite3.IntegrityError: CHECK constraint failed: text_basis IN ('full_text', 'summary', 'abstract')`.
  `domain/models/document.py` 의 `TextBasis` 는 `image_vision` 을 허용했지만 `migrations/002_text_basis.sql` 의 CHECK 는 넓혀지지
  않았다. 테스트는 새 DB 를 만들어 돌고 image_vision 문서를 실제 저장소에 upsert 하는 경우가 없어 못 잡았다.
- 조치: `migrations/006_text_basis_image_vision.sql`. SQLite 는 CHECK 를 ALTER 로 못 바꾸므로 공식 12단계 표 재생성:
  `PRAGMA foreign_keys=OFF`(트랜잭션 밖) → `documents_new`(002~004 열·기본값·CHECK 전부, text_basis 에 image_vision) →
  `INSERT … SELECT rowid, …`(rowid 보존) → `DROP TABLE documents` → `RENAME` → 인덱스 5개(doi·appno·department·valid_until·ingested)
  복원 → `COMMIT` → `PRAGMA foreign_keys=ON`. documents 에는 트리거가 없고 FTS 는 chunks 외부 콘텐츠라 손대지 않는다.
  FK 를 끄지 않으면 DROP 의 암묵적 DELETE 가 chunks·document_orgs 를 CASCADE 로 지우므로 OFF 가 필수.
- 판단: CHECK 를 없애고 앱 검증만 두는 대안은 택하지 않았다 — 도메인 Literal 과 DB CHECK 가 이중으로 막는 현재 구조를 유지하는 쪽이
  외부 스크립트·수동 SQL 로 잘못된 basis 가 들어가는 것을 막는다. 앞으로 `TextBasis` 를 넓힐 때는 같은 방식의 migration 을 같이 낸다
  (ADR 없음 — 기본 선택).
- 적용 경로: `SQLiteDocumentRepository.__init__` → `runner.migrate` 이므로 저장소를 여는 모든 진입점(ingest·vision ingest·reindex·api·ui·mcp)
  에서 자동 적용. 별도 명령 불필요.
- 검증: 테스트 3건 추가(005 옛 DB 재생성 보존·hybrid_search/upsert·새 DB 001→006), 기존 버전 상수 5→6. 운영 DB 사본
  (`cp data/rra.sqlite /tmp/…`, 원본 미수정): documents 8,406·chunks 14,979·document_orgs 4,528 동일, rowid 합 동일, text_basis 분포
  abstract 5,646 / full_text 2,640 / summary 120 동일, `integrity_check` ok, `foreign_key_check` 0건, FTS MATCH 정상, image_vision INSERT 성공,
  0.15초. 사본 삭제.
- 남은 일: 운영 DB 는 다음 저장소 open 때 자동으로 6 이 된다. 그 뒤 `rra vision ingest` 재실행(무거운 작업 — heavy lock).
