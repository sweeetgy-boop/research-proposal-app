# feat/table-facts-terms 진행 메모 (레인 F — P2-8 표 구조화 · P2-9 용어 후보)

- 2026-10-27 13:30 시작. main 1f3f3ab(PR #33) 기준 worktree `rra-wt/feat-table-facts-terms`. 읽은 것: CLAUDE.md, architecture §1·§4.16·§4.17,
  numbers.py·keywords.py·overlap.yaml, _sandbox·_worker·extract/spreadsheet·pdf, korail_web/snapshot·source, persistence(sqlite_repo·migrations),
  vision(models·store·link_image_readings), lint.py 수치 검사 경로, CLI/REST 패턴.
- 레인 A 스냅샷(2026-10-27) 확인: manifest 1,566줄, 첨부 hwp 888·hwpx 261·pdf 69·xlsx 59·xls 2(내려받음), 이미지 195.
  표본 3건(xlsx 2 "역별 승강설비 현황", pdf 1) scratch 로 복사해 모양만 봄 — xlsx 는 제목행 → 합계행 → 머리글행("연 번·노선명·역 명·엘리베이터…") →
  데이터행. pymupdf 텍스트는 표 셀이 줄 단위로 흩어져 "정렬된 숫자 행" 만 보수적으로 잡아야 한다.
- 발견: `korail_web` 첨부 xlsx/xls 는 `_worker` 가 `{"sheets": …}` 를 돌려주고 `ExtractResult` 는 `text` 필수라 ValidationError → 적재 안 됨
  (현재 main·레인 A 동일). 표 사실은 문서가 없어도 doc_id(`korail_web:<sha16>`) 로 저장하고 `missing_doc` 건수로 보고한다 — 시트→본문 변환은 통합 결정.
- molit 은 스냅샷이 없고(첨부는 store_dir 에 sha 이름으로만) 본문은 DB 에 있으므로 `--source molit` 은 DB 문서 본문의 줄 표 휴리스틱으로 간다(쪽 번호 없음).
- 설계: domain `TableFact`·`ParsedTable`·`rules/table_facts.py`(순수) → 포트 `TableFactRepository`·`TableSourcePort` → usecase
  `extract_facts`·`term_candidates`(fake 로 테스트) → 어댑터(migration 005, `_worker` `pdf_pages`, `adapters/tables/`) → CLI `rra facts`·`rra terms`, REST `GET /v1/facts`.
- 14:10 domain(TableFact·규칙·용어 후보)·application(포트·유스케이스)·numbers/lint facts·RetrievalSnapshot.facts 커밋(2f58a4b). 실물 xlsx 2건으로
  규칙 손봄: 연도 셀은 머리글 판정에서 값으로 세지 않음, "구분" 열은 데이터에 연도가 있을 때만 행 연도 열, 연번 열의 "합계" 는 라벨.
- 14:40 adapters(SQLite facts·코퍼스 표본, tables 3종, terms writer, pdf_pages 워커) + 계약·어댑터 테스트 커밋(966b405). schema 5.
- 14:55 진입점(CLI facts/terms, REST /v1/facts, composition) 커밋(1d28a8b). 전체 1,567 통과.
- 15:05 레인 A 스냅샷 실파싱 dry-run(scratch SQLite, DeterministicEmbedding) 1차: row_label 120자 초과 ValidationError(승차권 안내 URL 셀)
  → 긴 글자 셀·날짜 셀은 라벨 제외, 식별자 열(번호·코드·전화·일자·일시) 값 제외, 날짜 머리글 → (연도, "N월"). 2차·3차: 48,253건/32문서/59초.
  lint 스냅샷 상한을 문서 300·전체 2,000(연도·단위 우선)으로 — 큰 시트 전부를 넣으면 state.json 이 MB 단위. 커밋 bf722da + ADR 0022.
- 15:20 조각 파일(status·timeline·metrics)·architecture §4.18. 최종 검사 뒤 보고.
