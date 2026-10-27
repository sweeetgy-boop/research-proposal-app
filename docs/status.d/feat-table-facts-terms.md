## [P2-8·P2-9] 표 구조화(table_facts)·용어 후보 추출 (feat/table-facts-terms, 2026-10-27, ADR 0022, architecture §4.18)

- 코드·합성 fixture 테스트만. LLM 호출 0. 새 테스트 72(도메인 42·계약 6·응용 7·어댑터 10·진입점 5·조립 2), 전체 1,572 통과·17 skip,
  계약 8 유지, ruff 통과.
- P2-8: `domain/models/table_fact.py`(TableFact·ParsedTable), `domain/rules/table_facts.py`(격자·본문 줄·판독 structure → 사실;
  머리글 행·두 줄 병합·연도 열/행·단위 우선순위·연번/식별자 열 제외·긴 문장/날짜 셀 제외), `numbers.unsupported_numbers(facts=)`,
  `lint(facts=)`, `RetrievalSnapshot.facts`(retrieve 때 `GenerateProposal._fill_facts`: 문서당 300·전체 2,000, 연도·단위 우선),
  포트 `TableFactRepository`(replace_facts·search_facts·facts_for·fact_counts)·`TableSourcePort`·`CorpusAccessPort`,
  `usecases/extract_facts.py`, migration `005_table_facts.sql`(FK 없음), SQLite 구현(LIKE 토큰 AND, ESCAPE), `_worker pdf_pages`,
  어댑터 `adapters/tables/`(SnapshotTables=korail_web 첨부 xlsx·xls·pdf, VisionTables=판독 캐시 표(unconfirmed_numbers 있으면 제외),
  DocumentTables=DB 본문 줄 표(molit)), `composition.build_table_source/build_extract_facts`.
  진입점 `rra facts extract --source korail_web|molit|vision [--snapshot] [--dry-run] [--limit] [--json]`, `rra facts search "<항목>"`,
  REST `GET /v1/facts?q=&k=` → `{notice, facts[{item, year, unit, value, value_text, doc_id, page, sheet, basis, trust}]}`.
- P2-9: `domain/rules/term_candidates.py`(문서빈도: df/문서수 ≥ 0.15 & 자료원 ≥ 2 → 흔한 단어 후보, 나머지 → 철도 용어 후보,
  철도 어근 `hint=rail_seed`), `usecases/term_candidates.py`, `adapters/terms/writer.py`, `composition.build_term_candidates`,
  `rra terms candidates [--limit] [--sample 5000] [--out-dir]` → `config/rail_terms.candidates.yaml`·`config/generic_terms.candidates.yaml`
  (후보만: term·doc_freq·chunk_freq·doc_ratio·sources·examples(doc_id ≤3)·hint). **overlap.yaml 자동 반영 없음 — 사람 결정(이슈 #11).**
- scratch DB 측정(레인 A 스냅샷 2026-10-27, 샌드박스 실파싱, DeterministicEmbedding, 59초): 표 2,094장 → 사실 48,253건 / 문서 32건,
  사실 없는 표 2,035장(pdf 쪽 거의 전부 — pymupdf 가 셀을 줄로 흩어 정렬 줄 조건을 못 맞춤, pdf 사실 2건), 단위 있음 46%(명 22,000),
  연도 있음 23%, 샌드박스 거부 1건(ParseRejected). 실 DB 적재는 통합 세션.
- 발견(통합 결정 필요): `korail_web` 첨부 xlsx·xls 는 `_worker` 가 `{"sheets": …}` 를 돌려주고 `ExtractResult.text` 가 필수라 적재되지
  않는다(main·레인 A 동일) → 32개 표 문서가 전부 `missing_doc`. 사실은 doc_id(`korail_web:<sha16>`)로 저장되지만 검색 집합에
  들어올 문서가 없어 lint 효과는 xlsx 가 적재된 뒤에 난다. 시트→본문 변환(행을 " | " 로 이어 text) 1곳이면 된다 — 레인 A/통합.
- 통합 세션 실행 순서(저장소 루트): ① `rra ingest`(korail_web·molit) 뒤 ② `rra facts extract --source korail_web --dry-run` → 건수·
  missing_doc 확인 → `--dry-run` 없이 ③ `rra facts extract --source molit`(DB 본문) ④ `rra vision ingest` 뒤 `rra facts extract --source
  vision` ⑤ `rra facts search "승강설비"` 로 확인 ⑥ `rra terms candidates` → `config/*.candidates.yaml` 검토 → 이슈 #11 댓글.
- 프론트엔드 영향: 새 읽기 경로 `GET /v1/facts?q=<항목>&k=` (세션/토큰 인증, problem+json, 422 빈 질의, 503 저장소가 사실을 모를 때).
  응답은 `notice`(비신뢰 문구) + `facts[]`; `basis === "image_vision"` 이면 "이미지 판독" 배지, `page`/`sheet` 는 출처 표시용.
  초안 lint 메시지는 변화 없음(표 사실로 근거가 확인된 수치는 `unsupported_number` 경고가 나지 않을 뿐). 스키마는 `rra api schema`
  재생성 필요(docs/openapi.json 은 통합 세션).
- 이슈 #11 댓글 본문(통합 세션이 올림):
  > `rra terms candidates` 로 용어 후보 두 벌을 만들었습니다 — `config/rail_terms.candidates.yaml`(철도 용어 후보)·
  > `config/generic_terms.candidates.yaml`(흔한 단어 후보). 후보는 코퍼스 청크 표본(자료원별 고르게, 기본 5,000)의 문서빈도 통계로
  > 나눴고(`domain/rules/term_candidates.py`, ADR 0022) **config/overlap.yaml 에는 자동 반영하지 않습니다.**
  > 검토 방법: 각 항목의 `doc_freq`(문서 수)·`doc_ratio`·`sources`(자료원별 문서 수)·`examples`(doc_id ≤3, `rra search` 로 문맥 확인)를
  > 보고, (1) 흔한 단어 후보 중 "철도 과제라면 어디에나 있는 말" 만 `overlap.yaml keywords.generic_terms` 에 어간 형태로 옮기고
  > (`hint: rail_seed` 가 붙은 것은 철도 용어일 수 있으니 되돌려 보세요), (2) 철도 용어 후보는 유사과제 판정에서 "세는 말" 이므로 목록에
  > 넣을 필요는 없고 generic 에 잘못 들어간 것이 없는지만 확인하면 됩니다. 반영 뒤 골든셋 precheck 로 차단/근접 변화를 한 번 봐 주세요.
- 남은 일: pdf 표(쪽 텍스트가 셀 단위로 흩어짐 — pymupdf `find_tables()` 또는 words 좌표 묶기로 격자 복원, 샌드박스 자식에서),
  lint 시점 지연 조회(비동기 lint 경로가 생기면 스냅샷 상한 제거), 시트 적재(위 발견), 단위 없는 사실 54% 의 열 머리글 단위 보강,
  MCP 읽기 도구 `rra_facts`(선택), 용어 후보에 인접 2어절 복합어 추가(현재 단일 어절).
