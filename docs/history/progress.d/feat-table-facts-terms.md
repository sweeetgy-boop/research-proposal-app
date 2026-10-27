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
