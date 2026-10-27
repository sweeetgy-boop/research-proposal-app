# 레인 G — feat/rnd-notice (2026-10-27, P2-7 국토교통 분야 정부 R&D 공고·RFP) 전달 사항

## 전달한 것
- **탐색** `docs/korail-web-crawl.md` §5 표 — KAIA 사업공고(robots Allow, GET, 공고기간, PDF 공고문·안내서), IRIS 사업공고(공개 POST
  검색 폼 → JSON, 국토교통부 필터 AR4004, 인라인 공고문, 담당자 이름·전화 있음), NTIS(robots `Disallow: /` → 보류), 공공데이터포털
  (국토교통 R&D 공고 API 없음). ADR 0023.
- **어댑터** `src/rra/adapters/sources/rnd_notice/`(`_html` KAIA·IRIS 해석, `crawler` 스냅샷 수집: robots·2초 간격·백오프 2→5→10s·연속 3회
  보류·끝에 1회 재시도·최근 2년·상한 500·중복 합침·PII 제거, `source` SourcePort: 스냅샷 → 공고 1건 = Document 1건, 첨부는 샌드박스),
  `GuardedClient.post_form`(공개 검색 폼 POST, 허용목록·상한·재시도 동일), `domain/rules/notices.py`(notice_key·parse_period·is_open),
  `domain/models/notice.py`(NoticeMatch). SourceType·DocType `rnd_notice`, visibility public, `valid_until` = 접수 마감일(저장소 만료 규칙
  `sqlite_repo._VALID` 로 마감 지난 공고는 검색·precheck 제외 — 스크래치 DB 로 확인), `raw.notice{agency, ministry, program, deadline,
  start, period, status, notice_no, site, also_in, attachments, parsed_attachments}`.
- **배선** `config/rnd_notice.yaml`, `config_loader.rnd_notice_config`, `build_rnd_notice_crawler`·`build_rnd_notice_source`·
  `build_notice_match`, `_SOURCE_BUILDERS["rnd_notice"]`, `rra ingest --source rnd_notice`, `rra crawl rnd-notice --explore|--download
  [--limit N] [--incremental]`, `rra sources status` 행 + "정부 R&D 공고: <날짜> 기준 스냅샷" 줄, `SOURCE_LABELS`·`NON_OVERLAP_SOURCES`,
  `security.yaml allowed_domains` 에 `www.kaia.re.kr`·`www.iris.go.kr`.
- **검색 범위** `retrieval_scope.OVERLAP_EXCLUDED_DOC_TYPES` 에 `rnd_notice`(유사과제 판정 제외, 테스트), `POLICY_DOC_TYPES`·
  `policy_suggest.POLICY_SOURCES` 에 추가(정책 근거 추천 후보), 새 `NOTICE_DOC_TYPES`. 기술적 중요도 근거로는 쓰지 않는다(retrieval_mix
  `technical_importance` allow 에 없음 — 통합 세션 확인).
- **#13 선행 훅** `application/usecases/notice_match.py`(NoticeMatcher: rnd_notice 만 hybrid_search, 접수 중(마감 ≥ 오늘) 상위 3건, LLM
  없음, 자동 삽입 없음), `rra notices match [--file]`, `POST /v1/ideas/notices`, `views.notice_matches_payload`. #13 은 열어 둔다.
- **테스트** 20건 추가(`tests/adapters/rnd_notice`, `tests/domain/test_notices.py`, `tests/application/test_notice_match.py`,
  `tests/entrypoints/test_notices_entrypoints.py`; fixture `tests/fixtures/rnd_notice/` 는 담당자 이름·전화를 가짜 값으로 바꿈):
  `pytest -q` 1,515 통과·17 skip, `lint-imports` 8 kept, `ruff` 통과.
- **스냅샷** `data/rnd_notice/snapshots/2026-10-27/` — 공고 99건(KAIA 83 + IRIS 16, 두 사이트에 함께 실린 63건은 한 문서로 합침), 첨부 229개 808MB(KAIA pdf·hwp; IRIS 첨부 40건은 이름만), 등록일 2024-10-30~2026-08-20 (완료, 2년 범위) (커밋 안 함). 스크래치 DB 적재 3건·청크 293 확인.

## 프론트엔드 영향 (docs/openapi.json 은 통합 세션이 `rra api schema` 로 갱신)
- `POST /v1/ideas/notices` (본문 ProposalRequest) → `{notice, count, items:[{doc_id,title,agency,program,posted,deadline,days_left,url,
  similarity}]}`; 503 = 기능 꺼짐. 공고는 제안서에 자동으로 들어가지 않는다(선택 UI 는 #13 과 함께).
- `GET /v1/sources/status` 행에 `rnd_notice` 추가, 그 행에 `snapshot`·`snapshot_items`·`snapshot_label`("정부 R&D 공고: <날짜> 기준 스냅샷").
- `rra sources status --json` 에 `rnd_notice_snapshot`.

## 통합 세션이 돌릴 것 (무거운 작업)
```bash
# 1) 스냅샷 마저/다시 받기 (같은 날이면 받은 공고는 건너뜀; 다음 날부터는 --incremental)
PYTHONPATH=src .venv/bin/python -m rra.entrypoints.cli crawl rnd-notice --download --incremental
# 2) 적재 (PDF 샌드박스 파싱 + 임베딩 — DB 작업)
PYTHONPATH=src .venv/bin/python -m rra.entrypoints.cli ingest --source rnd_notice --limit 600
PYTHONPATH=src .venv/bin/python -m rra.entrypoints.cli sources status
# 3) 골든셋 01·02 로 공고문 대조·정책 근거 추천 확인 (적재 뒤)
for g in tests/golden/01*.yaml tests/golden/02*.yaml; do PYTHONPATH=src .venv/bin/python -m rra.entrypoints.cli notices match --file "$g"; done
```

## retrieval_mix.yaml 규칙 (의도 — 통합 세션이 행을 모은다)
- `rnd_notice`: 정책 근거 추천 후보(`policy_importance` allow 에 이미 있음)·공고문 대조(#13). **기술적 중요도 근거·유사과제 판정 금지**
  (`overlap_exclude` 에 이미 있음, 코드 `retrieval_scope` 도 제외). 섹션 프롬프트 `[자료]` 에는 정책적 중요도·필요성 보조로만.

## 내가 할 일 (키가 필요한 API — 사람)
- **NTIS OpenAPI** (제공: 한국과학기술정보연구원 NTIS, 신청 https://www.ntis.go.kr/rndopen/api/ … "Open API 신청") — 기존 과제검색 키와 같은
  키로 "사업공고" 서비스 제공 여부 확인. robots 가 전면 금지라 공개 페이지는 수집하지 않는다.
- (선택) **공공데이터포털 "과학기술정보통신부_사업공고"** (제공: 과기정통부, 신청 https://www.data.go.kr/data/15074634/openapi.do,
  `apis.data.go.kr` 키) — 국토교통 밖이라 보류. 필요해지면 어댑터 추가.
- IRIS 첨부(세션 POST 다운로드)는 받지 않는다 — 필요하면 KAIA PDF 로 대신(같은 공고는 합쳐짐).

## 남은 것 / 보류
- IRIS 첨부 보류(post_download), KAIA zip 서식(33MB) 미수집. 2년 이전 공고 없음(설정 `since_days`).
- NTIS 공고(robots)·data.go.kr(국토교통 R&D 공고 API 없음) 보류.
- #13 본체(공고 요건 추출·render_check 대조·notice_id)는 미착수 — `rnd_notice:<key>` 를 notice_id 로 이어 쓸 수 있다.
- Streamlit·MCP 에 공고문 대조 없음(CLI·REST 만).
