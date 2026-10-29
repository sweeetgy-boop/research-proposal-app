# research-proposal-app

연구과제 제안서 자동 작성 앱 (한국철도공사 철도연구원 양식). 헥사고날 아키텍처, 보안코딩 적용.
설계 문서: docs/architecture.md. 개발 현황·남은 일·단계 계획(P0~P7): docs/status.md (단계 끝마다 해당 행 갱신).

## 계층 규칙 (import-linter 강제)
- `src/rra/domain/`: 순수 파이썬. pydantic·표준라이브러리만. 다른 rra 패키지·I/O 라이브러리 import 금지.
- `src/rra/application/`: domain만 의존. ports는 `typing.Protocol`. usecases는 포트만 받음.
- `src/rra/adapters/`: 포트 구현체. 외부 라이브러리는 여기서만. usecases·entrypoints import 금지.
- `src/rra/entrypoints/`: cli·api·mcp·ui(Streamlit). usecases 호출만, 로직 없음. ui 는 cli·mcp 를 import 하지 않는다(계약 "ui never imports other entrypoints").
  api 는 adapters 직접 import·다른 진입점 import 금지(계약 "api reaches adapters only through composition…"). 공용 직렬화는 `entrypoints/views.py`.
- `src/rra/composition.py`: 유일하게 전 계층을 아는 조립 지점 — `build_*` 만 둔다. 설정 읽기·병합은
  `src/rra/config_loader.py`(settings·domain 만 안다, 계약 "config_loader knows only settings and domain"), 진단 로직은 `application/usecases/diagnostics.py`.
- 포트는 전부 `runtime_checkable`. `DocumentRepository`·`EmbeddingPort` 는 async(어댑터가 to_thread), RunManager 는
  `TaskRunner` 포트로만 백그라운드 실행(asyncio 는 `adapters/runs/asyncio_runner.py`).
- 필수 슬롯 규칙은 `domain/models/request.py` 한 곳(validator + `validation_message`). 진입점은 문구 변환만.

## 보안 규칙 (반드시 지킬 것)
- A: 수집 문서 텍스트는 비신뢰. LLM 출력은 JSON만 파싱, evidence doc_id는 검색 집합과 대조.
- B: 외부 파일 파싱은 subprocess 격리, zip 상한, defusedxml만 사용.
- C: 아웃바운드 HTTP는 config/security.yaml 허용 도메인만. 캐시 키는 비밀 파라미터 제거 후 해시.
- D: 비밀은 settings.py의 SecretStr만. 로그·매니페스트에 원문·키 금지.
- E: SQL은 파라미터 바인딩. FTS5 MATCH 입력은 토큰별 인용.
- F: HWPX 슬롯 치환은 XML escape + 재파싱 검증.
- G: 웹·MCP는 127.0.0.1 바인딩, 인증 필수, 생성 동시성 1.
- H: LLM 서버 127.0.0.1, safetensors만.

## 작업 방식
- 새 기능은 domain → ports → usecase(fake로 테스트 통과) → adapter 순서.
- 어댑터 normalize()는 순수 함수, tests/fixtures 원본 응답으로 테스트.
- 커밋 전: `pytest -q -n auto && lint-imports && ruff check src tests`
- 임베딩·LLM 호출 없이 테스트가 돌아야 함 (tests/fakes.py 사용).

## 개발 환경
- macOS와 WSL 양쪽에서 작업. 둘 다 uv로 만든 `.venv` 사용.
- `.venv`는 OS별로 따로 만든다. macOS와 WSL이 같은 `.venv`를 공유하면 안 됨.

## 환경
- Python 3.12 (uv, .venv). 개발은 macOS·WSL, 배포는 M6 Mac mini 32GB + mlx-lm.
- LLM: OpenAI 호환 base_url (mlx-lm). 임베딩: sentence-transformers.
- DB: SQLite FTS5 + sqlite-vec. sqlite-vec 미설치 시 파이썬 코사인 브루트포스로 자동 폴백.

## 현재 단계
- Step 1~8 완료. Step 9 는 run_log(adapters/logging, manifest 허용목록)·`rra runs purge` 까지. Step 10 은
  REST(`entrypoints/api`, `adapters/security`, `rra api`, `deploy/launchd/com.rra.api.plist`)까지. 2026-10-23 구조 검토
  6항목 반영 — docs/architecture.md §4.3·§4.4·§10. `.gitignore` 는 `/runs/`·`/data/`(루트만).
- Step 5 (알리오) 완료 — catalog·filedrop·샌드박스 파싱 + 원문 비공개 보고서의 공개 요약 경로
  (`alio/summary.py`, `Document.text_basis`, `<doc basis=…>`, migration 002, 설계 docs/architecture.md §0.1).
  own 티어는 `sources.yaml own_unit` 부서 목록 기준. 요약 파서는 실물 fixture(korail_2026_asset.txt)로 확정.
- Step 7 (ScienceON·NTIS 과제검색) 코드 완료 — 토큰 인증·레이트리밋·요청 예산, 기관 태그(_orgs),
  `rra sources check`, fixture 녹화 도구(tests/tools/record_fixture.py).
- 대기 (skip 4건):
  - ScienceON·NTIS 키 투입 → 실응답 녹화 → FIELDS 매핑·ntis.project_path·record_tag 확정 (skip 2)
  - 알리오 원문 공시 파일·카탈로그 CSV 샘플 투입 (skip 2)
  - `own_unit.departments` 나머지 철도연구원 부서 추가 (현재 철도연구원·경영연구처·기술연구처)
- 양식 개정 반영 — 별지 제2호서식(2024.02.19.) 섹션 12개·선택형 확정(`rra runs confirm`/`rra_confirm`)·
  정책적 중요도 입력 근거 규칙·유사과제 앱 판정·legacy run 조회 전용 (docs/architecture.md §4.1).
- 유사과제 차단 = 유사도 AND 공유 키워드(`domain/rules/keywords.py`, `config/overlap.yaml`; architecture §4.1).
- 생성 근거 관련도 하한(P1, 이슈 #2, architecture §4.7): `domain/rules/relevance.py` — 코사인 ≥ 0.79, 한글 청크는
  질의 키워드 ≥ 1(영어 청크는 키워드 조건 없음). `Chunk.similarity` 는 저장소가 검색 결과에만 채운다. 통과 청크 0 이면
  근거 필수 섹션은 빈칸 + `no_relevant_evidence` 경고. 임계치는 `tests/fixtures/relevance_golden.json` 측정값으로 고정.
  e5 유사도만으로는 무관한 한국어 문서도 own 0.80 을 넘는다. 임계치는 표본이 쌓인 뒤 조정. reranker 는 후속.
- 7B(Qwen2.5-7B-Instruct-4bit) 전환 반영 — 본문 속 자료 태그 조각 제거(`llm_output.strip_doc_fragments`),
  지어낸 수치 lint 경고(`numbers.py`, `rules.yaml number_checked`), grounding 관형형 예외. 실응답 fixture tests/fixtures/llm.
- Streamlit 화면 (`entrypoints/ui/`, `rra ui`, 127.0.0.1:8501, RRA_API_TOKEN 게이트) — 기획서 Ⅱ 흐름.
  Agent = 규칙 기반 오케스트레이터: 판단 `domain/rules/agent_policy.py`(기획서 Tool 호출 조건 표), 실행
  `application/services/assistant.py`(ProposalAssistant, trace → 화면 "Agent 활동 기록"). LLM 은 판단에 쓰지 않는다.
  생성은 워커 스레드(자체 이벤트 루프, `ui/worker.py`)에서 돌고 화면은 2초 fragment 로 state.json 을 폴링한다.
  모든 repo(sqlite)·LLM 호출은 워커 스레드에서만. 화면 테스트는 `streamlit.testing.v1.AppTest` + FakeLLM
  (tests/entrypoints/ui). docs/architecture.md §4.2.
- 대기: `config/templates/korail_strategy.yaml` 전략체계 목록 채우기 (비어 있으면 2-가-(3) 빈칸).
- HWPX 렌더(Step 8, `adapters/rendering/hwpx.py`): `config/templates/proposal_korail.hwpx` 가 있으면 템플릿 모드(자리표시자는
  한 run 안에), 없으면 생성 모드. 체크 칸은 confirmed 로만, ProposerInfo 는 render 인자로만(저장 금지). 보안 F 는
  sanitize→escape→defusedxml 재파싱. 진입점(양식 파일은 finalize 로만): `rra runs finalize`, UI [최종 마무리 및
  다운로드], MCP `rra_finalize`, REST `POST /v1/runs/{id}/finalize`.
- 실물 양식 연결(2026-10-26): 원본 `data/templates/proposal_form_original.hwpx` → `tools/build_form_template.py` →
  `config/templates/proposal_korail.hwpx`(둘 다 미커밋, .gitignore). 자리표시자는 slots.yaml 영문 키(`{{title}}`,
  `{{task_type:basic}}`, `{{utilization:software}}` …). 체크 칸은 양식 괄호 안 `( ○ )`/`(   )`(slots.yaml marks),
  여러 문장 섹션은 문장마다 `○ ` 단락 복제(`expand_paragraphs`), 한 줄 칸은 인라인. 제안일자 비면 렌더 날짜.
  렌더 전 점검 `usecases/render_check.py`(미해결 lint·max_chars·line_limits 초과·전략 빈칸) — CLI 출력, UI 버튼 위,
  REST `GET /v1/runs/{id}/render-check`. 알림은 렌더를 막지 않는다. 양식이 바뀌면 스크립트가 앵커 불일치로 멈춘다.
- 2026-10-26 백엔드 일괄: [1] clean_sentence(저장·조회·렌더)·foreign_script lint·연구과제명 무제한, [2] DB migration
  003·004(schema_version·valid_until·visibility·ingested_at)·만료 제외·`rra reindex`·`rra db backup`, [3] tests/contracts,
  [4] llm.yaml providers(mlx·gemini)·`RRA_GEMINI_API_KEY`·allowed_domains·reasoning_effort·401 비재시도,
  [5] 검토 흐름(domain/rules/review_flow, usecases/review_draft, RunManager review/apply_edits/versions/revert/finalize/
  reopen, runs/…/versions·reviews 파일, 양식 파일은 finalize 로만), [6] REST 세션·CSRF·SSE·problem+json·정적 SPA·
  RRA_FAKE_LLM 가짜 모드(adapters/fake)·`rra api schema`, [7] Streamlit [최종 마무리 및 다운로드]. 설계 architecture §4.5·§4.6·§9.2.
- Gemini 키는 .env 에 있고 Argon 왕복 확인됨. 대기(사람 입력): 연구과제 공고문(data/inbox/notice/).
- 운영(P6, architecture §4.12): launchd 4종(mlx·api·backup 03:30·ingest 02:30 `--skip-unavailable`), `deploy/README.md` 설치
  순서, 공개 방식은 `docs/deploy-exposure.md` 비교만(결정 전). plist 는 `tests/deploy` 가 검사한다.
- 검토 채점(P5, architecture §4.11): Argon 검토가 필요성·차별성·실현가능성·기대효과 1~5점(`ReviewRound.scores`)을 함께 내고,
  2점 이하는 `score_comments` 로 문장·섹션 의견에 붙는다(자동 재생성 없음). 수치는 막지 않고 알림 유지 + 검토 프롬프트
  지적 의무 + render_check 맨 위 건수. 차별성 매트릭스·예산표는 양식 밖(화면·API 표), HWPX 붙임은 설계만.
- 외부 자료원(P4, architecture §4.10, docs/external-apis.md): KIPRIS 어댑터 `adapters/sources/kipris/`(KIPRIS Plus
  freeSearchInfo, accessKey, 레코드 PatentUtilityInfo, 발명자 제외·출원인 기관만), `RRA_KIPRIS_KEY`, `rra sources check` 에
  kipris + record_tag 진단. NTIS 연구보고서는 가능 여부만 확인(키 뒤 구현).
- OpenAlex 코퍼스(architecture §4.13): `sources.yaml openalex.queries` 13개 분야 질의, 초록 필터, 증분(lookback_days)/전체(`--full`,
  backfill_years), 질의당 상한 200, page 페이징(cursor 는 API 키 필요), `RRA_OPENALEX_MAILTO`·`RRA_OPENALEX_API_KEY` 선택.
  CI: `.github/workflows/ci.yml` backend·web job, 샌드박스는 RLIMIT_DATA 만(RLIMIT_AS 는 리눅스 import 실패).
  근거 출처 다양성: `evidence_floor.min_per_source`(4)·`search_multiplier`(4) — 넓은 검색 → 부족 자료원만
  `hybrid_search(sources=[…])` 재검색(`_top_up_sources`) → `balance_sources`. 포트 `hybrid_search` 에 `sources` 필터.
- 전체 흐름 ③~⑥(2026-10-27, architecture §4.6, ADR 0011): 상태 running → draft_reviewing → drafted(v1→v2 Argon 보완) →
  editing → final_reviewing → final_reviewed → finalized (`domain/rules/review_flow`, 옛 done·reviewed 는 normalize). ③ 파이프라인은
  `config/pipeline.yaml`(`PipelineConfig`, 품질 단계는 [Q]). ④ 편집 규칙 `domain/rules/versions`(문장/섹션 편집·근거 이어받기·diff),
  임시 저장 `draft_working.json`, 같은 내용 저장은 버전 없음, base_version 불일치 `VersionConflict`. ⑤ `RunManager.final_review`
  (kind=final, review_final_rN.json, score_delta, stale_edits). ⑥ finalize 는 final_reviewed 또는 review_skipped, 임시 편집 없음.
- 차별화 과제 추천(2026-10-27, architecture §4.14, ADR 0012): precheck 뒤 자동 1회(`llm.yaml recommend.auto`) 기존 과제와
  다른 과제 0~5건(`usecases/recommend_projects`, 검증 `domain/rules/recommendation`: doc_id 범위·수치·정책명·중복·자기 중복
  precheck). 선택 → `apply_recommendation` 미리보기 → 확정 입력으로 생성. run 에 recommendations.json 복사, manifest 는 전송
  기록+chosen. 진입점 `rra recommend`·REST `/v1/precheck/recommendations(/{id}/apply)`·MCP `rra_recommend`·Streamlit 카드.
  경과 기록은 `docs/history/`(PR 마다 timeline·metrics·ADR·screens, CONTRIBUTING 규칙).
- 초안 품질 강화 [Q](2026-10-27, architecture §4.15, ADR 0013): `config/pipeline.yaml` 8 단계 — Q1 clarify(`usecases/clarify_input`,
  `request.supplement`), Q2 outline(`usecases/outline`, `domain/rules/outline`, step `outline`, outline.json), Q3 section_search
  (`domain/rules/section_search`, `retrieve_sections`, `snapshot.section_chunks/chunks_for`), Q4 exemplars(`domain/rules/exemplars`,
  인용·베끼기 폐기 `exemplar_cited`), Q5 additions(`section_checklists.yaml`, `ReviewComment.kind=addition`, `origin=argon_addition`),
  Q6 rule_check(`domain/rules/style`, finalize 자동 정리 + `STYLE_CODES` 경고 → 1차 검토 `[앱이 찾은 문제]`), Q7 two_candidates
  (`CORE_SECTIONS`, candidates.json, `candidate_choices`, B 선택 시 `candidate_replaced`), Q8 reranker(`ports/reranker`,
  `adapters/reranking`, `~/models/bge-reranker-v2-m3` Apache-2.0, 없으면 경고 후 생략). 측정 `rra eval`(`usecases/evaluate`,
  `build_eval`, `data/eval/`, `docs/eval-<날짜>.md`). 기본값은 측정 뒤 효과 있는 것만 켠다.
- 2026-10-27 추가(병렬 레인, PR #23~#33): 웹 SPA `web/`(Vite+React+TS, U9 포함; `web/README.md`), pytest-xdist(`pytest -q -n auto`)·CI 분할·
  `tools/with_heavy_lock.py`·조각 파일 규칙(CONTRIBUTING), ScienceON 실연결·적재(2,045건, 특허 기본 자료원 ADR 0016; `.env` client_id·key 가
  서로 바뀌어 있음 — 사람 확인), 사용 편의성 U1~U8(`config/usability.yaml`, ADR 0017), 이미지 판독(`rra vision`, ADR 0018, `config/vision.yaml`),
  공사 홈페이지·국토부 수집(`rra crawl korail`, `adapters/sources/korail_web/`·`molit/`, 전략체계 초안 `korail_strategy.draft.yaml` +
  `config/strategy.yaml source: draft`, `rra strategy promote`, `rra policy-suggest`, ADR 0019), 측정 결함 수정(JSON 관용 파싱). 현황 docs/status.md §6.
- 2026-10-26 판단 반영(A): 엑셀 4개 과제는 부서 무관 own 티어(`OWN_RECORD_SOURCES`, 알림 세부 institute/company,
  `tier_label`), 그 출처는 `unlisted_department` 경고 없음, visibility 는 엑셀·공시용 요약문 public(일반 요약만 internal),
  generic_terms 14개 추가. 차별화 제안 자동 실행은 차단 알림일 때만(근접은 요청 시), REST `RunIn.differentiation_transfer`.
- 사내 자료 적재(P2, architecture §4.8): `adapters/sources/own/` — `own_projects`(data/inbox/own 엑셀 4개, 시트 머리글로
  종류 판별, 이름 열 제외, status rejected/stopped/…, 과제명 병합)·`own_docs`(data/inbox/own_docs 공시완료 폴더, 공시용 >
  일반 요약, hwpx > hwp > pdf, 묶음 꼬리말 분리, alio.summary 정규화 공용, 이름 제거). 샌드박스 파서 hwp(olefile)·xlsx·xls.
  `OverlapAlert.status` 는 `Document.raw.status`. 실물 파일 테스트는 skipif.
- 기획서 기능 2 유사과제 활용·차별화 제안(P3, architecture §4.9): `domain/rules/differentiation.py`(후보 = 차단 또는
  임계치×0.9, LLM 항목 검증·폐기), `usecases/differentiate.py`(Gemini `stages.differentiate`, 키 없으면 compose 로컬 대체,
  전송 범위는 검토와 동일, `transfer()` → manifest `differentiation`), `ProposalRequest.differentiation` 은 목적·방법·
  특이사항 프롬프트에 `[제안자가 정한 차별화 방향]` 으로 들어간다. 진입점: `rra differentiate`, `POST /v1/precheck/differentiate`,
  MCP `rra_differentiate`(쓰기 서버), Streamlit [차별화 제안 받기]. `rra llm-check` 기본 프롬프트의 `[]` 응답은 의도된 출력.
- 2026-10-27 오후 일괄(레인 병렬, 조각 파일 규칙은 CONTRIBUTING): **데이터 위치** 모든 실행 데이터는 원 저장소 `data/` 절대 경로
  (`RRA_DATA_DIR`, `config_loader.resolve_data_dir`·`data_path`·`data_locations`, #42) — worktree 는 데이터를 갖지 않는다.
  공사 홈페이지 `korail_web`(크롤·첨부·xlsx 시트 본문·내장 이미지 #34·#40), 이미지 판독 `adapters/vision`(거르기·OCR·사진 거르기
  `domain/rules/photo_filter` #43·병렬 `concurrency` #44·신뢰도 규칙, `rra vision extract|read|sample|ingest`; `sample` 은
  `--cached-only` 로 — 아니면 캐시 없는 항목을 다시 호출한다), NTIS 4 서비스(`adapters/sources/ntis`, 티어 `national_rnd`, 서버 IP 등록 필요, #35; 실응답 확정 #50 — 응답은 Accept json 이면
  JSON 문자열로 감싼 XML(`unwrap_json_string`), record_tag HIT, fixture 는 실응답·이름 제거), [P2] g2b(키)·bai(Playwright)·datago·mofe(#37), `rnd_notice` KAIA·IRIS 공고(#38), `table_facts`·용어 후보(#36, migration 005),
  `config/retrieval_mix.yaml`(섹션별 doc_type·최소 보장), reranker 잠금(#41). **브라우저 접속**(#45, ADR 0024): `config/api.yaml`
  (`public_origin`·`trust_cf_connecting_ip`), `adapters/security/client_ip.py`(CF-Connecting-IP 는 peer 127.0.0.1 일 때만), Origin 검사,
  cloudflared 설정 초안·`com.rra.tunnel.plist` — 터널·Access 는 사람 작업(`docs/deploy-exposure.md` §5).
  **로그인**(#48, ADR 0026): `domain/models/principal.py`·`domain/rules/auth_policy.py`(가명 `staff:<HMAC 12자>`·`guest:<아이디>`, 잠금·일일 상한),
  `adapters/auth/file_store.py`(`data/auth/` 700/600, 사번 HMAC·비밀번호 scrypt, 원문 없음), `config/auth.yaml`, `POST /v1/session {kind: token|staff|guest}`,
  run 소유자 격리(남의 run 404, 관리자 토큰은 전부), 공용 계정은 `PublicOnlyRepository` 로 internal 제외, Gemini 일일 상한 `llm.yaml budget`
  (`adapters/llm/daily_budget.py`), `rra auth staff|guest|status`(getpass). 사번 일괄 등록(2026-10-28 A2): `rra auth staff import --file
  <xlsx|csv> [--sheet] [--column] [--pad N] [--replace] [--dry-run]` — 샌드박스 자식(`adapters/auth/_roster_worker`)이 "사번" 열만 반환,
  규칙 `domain/rules/staff_roster`(공백·하이픈 제거·숫자 셀·0 채움, 로그인도 같은 정규화), 포트 `RosterReaderPort`·`AuthStorePort.import_staff`,
  출력은 개수만·원본 미복사·API 재시작 불필요. **자료원 IP**(#46, ADR 0025): `sources.yaml registered_ips`,
  `domain/rules/source_ip.py`, IP 거부 응답은 그 자료원만 건너뜀 + `cache/source_availability.json` 안내.
- **제안서 그림 [G]**(2026-10-28, ADR 0029, architecture §4.20): 명세(JSON, `domain/models/figure.py` 6종, `rules/figures.validate_spec` — 본문·입력·근거·
  table_facts 글자만) → 밑그림(`adapters/figures` SVG→PNG, 번들 Pretendard, `config/figures.yaml` 팔레트) → Nano Banana Pro(`adapters/llm/image_gen.py`,
  `gemini-3-pro-image`) 1회 채택, 실패면 기본 그림. 자동 검증 없음 — 제안자가 카드에서 확인(`Figure.confirmed`). 그림은 `DraftVersion.figures`(파일은 run
  `figures/<sha>`), 동작 `RunManager.figure_action`(새 버전), REST `/v1/runs/{id}/figures…`, 1차 검토 `figures` 의견, 제출 전 점검 `figures_*`,
  HWPX `render_with_figures`(표식 단락 → 그림, 못 찾으면 별첨), 일일 상한 `figures.daily_image_cap` 150. 끄기 `figures.yaml enabled: false`.
  명세는 Argon 먼저·실패면 로컬(`Figure.spec_model`). [말로 고치기] = 명세 변경(`edit_by_words`→`change_spec`, 생성과 같은 검사) → 밑그림 → 새로 그림,
  현재 그림은 보내지 않는다(편집 호출 없음), 결과 `Figure.last_change`(카드 "바뀐 내용") — ADR 0030.
- **Argon 먼저 작성 [3]**(2026-10-28 오후, ADR 0032, #71): `llm.yaml compose.writer: gemini`(섹션 Argon 작성·`concurrency` 4), 실패 섹션만 로컬
  (`writers`·`local_sections`, 사유 error·rate_limit·budget·invalid), `review.first_pass: off`(self_review), `compose.local_check`, Gemini 일일 600,
  `config/runs.yaml max_concurrent` 3(run 은 FlockPool, 로컬 모델 단계만 `runs/.generate.lock`). 보안 G "생성 동시성 1" 은 Argon 작성 한정 완화.
  공용 계정 run 은 원격 프롬프트에서 internal 제외. 그림 명세·말로 고치기도 Argon→로컬(#70, 로컬 호출은 슬롯 안 #73).
- **실시간 검색 [4]**(2026-10-28 오후, ADR 0031, #72): `config/live_search.yaml`, ② precheck 때 키워드 → ScienceON·NTIS·OpenAlex 동시 검색 →
  public·`raw.live` 로 DB 저장(이름 제거, 24h 캐시), 응답 `live_search`·`live` 배지. 가짜 모드는 기본 꺼짐.
- **시범 배포 규칙**(2026-10-28, [D2]): PR 을 합쳐도 운영 API 를 자동 재시작하지 않는다 — `docs/history/deploys/pending.md` 에 PR 한 줄을
  쌓고, 사용자가 "배포해" 하면 `tools/deploy.sh --wait`(main 최신 확인·web 빌드·`rra runs active`·version.json·kickstart·healthz/login/
  외부 주소 확인·`docs/history/deploys/<시각>.md`). 보안 수정·로그인/접속 차단 오류 수정은 즉시 배포하고 알린다. 배포 버전은
  `GET /healthz version`(`adapters/deploy/version.py`)·웹 하단. 절차 `docs/pilot-guide.md` §6.3.
- 시범 운영(2026-10-28, 3명, [D]): launchd com.rra.{mlx,api,backup,ingest} 등록(`deploy/README.md` §2), `max_queued_runs` 6(사용자별),
  동료 안내 `docs/pilot-guide.md`, 준비 상태·사람 할 일은 `docs/final-check-2026-10-27.md` 맨 위. 외부 주소는 DNS 가 Gabia 라 터널 미기동
  (Tailscale 대체 가능). 실측: 한 건 227초(생성 155 + 최종 검토 15), precheck 38~56초(자동 추천 Gemini 포함), 7B JSON 실패 4/10.
- 2026-10-28 새벽 수정: **빈 초안 금지**(ADR 0027, #55·#57) — 일부 섹션 실패는 `failed_sections`(웹 "이 섹션 다시 생성"), 빈 목록은 실패로 보고
  교정 재요청, 섹션 [자료] 상한(청크 500자·10청크), 로컬 2회 실패 섹션만 Gemini 대체 작성(`llm.yaml compose.fallback: gemini`, manifest
  `fallback_sections`, 웹 "대체 작성" 배지). **유사과제 판정**(ADR 0028, #56) — 후보는 `config/overlap.yaml candidates` 의 과제형 자료원만
  (`domain/rules/overlap_candidates.py`, `find_similar(sources=)`), 논문·보고서·특허는 `related_research`(웹 ② 관련 연구). 공용 계정 비밀번호
  최소 길이는 `auth.yaml guest.min_password_length`(시범 한정 4, #54).
- **시범 오류·개선 17건**(2026-10-28 저녁, #81~#84): ② 판정 = reranker ≥ 0.5 + 핵심 키워드 ≥ 1, 상위 10건 Argon 같음 판정(→로컬→규칙),
  행별 [유사함]/[관련 없음](`ProposalRequest.similar_choices`, 선택 기록 JSONL) — 비교표·활용 제안·과제안·본문 차별성은 [유사함] 행만(ADR 0036).
  정책적 중요도 작성안 4개(`RunIn.policy_choice`, 원문 재대조, 없음 → `policy_basis_needed`), 보강 질문 켬, AI 다시 쓰기·보완 질문 Argon 먼저,
  공통 순서 `usecases/argon_first.py`(빈 결과 금지·사유 표시, ADR 0037), "변경 n건" `domain/rules/change_count.py`. 그림 v2: 기본 As-Is/To-Be +
  분석 기법 추천 0~2(`config/figures/techniques.yaml`, ADR 0033). HWPX 단계별 서식 점검 `adapters/rendering/hwpx_format.py`(ADR 0034), 알림 한국어
  설명 표 `domain/rules/problem_labels.py` = `web/src/lib/labels.ts`(새 알림 코드는 두 표에 함께), 입력 변경 다시 쓰기 `POST /v1/runs/{id}/regenerate`(ADR 0035).
  화면 문구에 내부 코드(input_missing·json·no_change 등)를 내보내지 않는다.
- **시범 의견 2차**(2026-10-28 밤, #88~#92): AI 응답은 시간 제한 없음 + "응답 기다리는 중 · 경과 n초" [취소](`web/src/lib/useAiCall.ts`·
  `components/AiWaiting.tsx`, 서버 `entrypoints/api/cancellable.cancel_on_disconnect` — 끊기면 작업 취소 499), 로컬 대체는 오류 응답일 때만
  (ADR 0038, `llm.yaml timeout.read` 600 = 10분 무응답 안전선). ② 표 먼저(`POST /v1/precheck?stage=rule` → `/judgment`·`/recommendations`,
  [선택 적용], `/recommendations/more`, ADR 0039). 연구용역 재분류(`domain/rules/doc_category.py`, `rra db reclassify`, 정책 근거 추천 =
  `policy_cards.policy_passage` 범위), 화면 내부 번호 금지(`DocRef`·`lib/docRefs.ts`·`entrypoints/views_refs.py`, e2e `helpers-text.expectNoInternalIds`),
  L2 로컬 2차 검토 켬(`compose.local_check: on`, 모델 판정 + 규칙, 불일치만 Argon 제안, `/v1/runs/{id}/local-review…`, ADR 0040). 그림 가로·본문 폭
  153.8mm·높이 쪽 1/3·글자 9pt(`domain/rules/figure_fit.py`, manifest `figure_fit`, ADR 0041). 상태 표시는 버전 없음(`versions/marks_vN.json`,
  `RunManager.record_mark`), 아래 이동 막대(`StepNavBar`, `--stepnav-h`), 화면에 "run" 단어 금지(e2e `expectNoRunWord`, ADR 0042).
  Argon 호출 응답 시간은 예산 카운터 옆 `*.latency.jsonl`(본문 없음). 설정 사본(RRA_CONFIG_DIR)도 번들 글꼴을 찾는다(`_figure_asset_dir`).
- **시범 의견 3차**(2026-10-29, #95~#98): ② 같은 연작(제목이 연도·차수만 다른 과제) 한 줄 "○○(연작 n건)" + 연도별 목록(`domain/rules/series.py`,
  묶은 뒤 상위 10·나머지 판은 `merged_ids`, `overlap.yaml series`, ADR 0043). 그림 칸 글자는 자르지 않는다 — 칸별 상한 + 완결 구절
  (`domain/rules/figure_phrases.py`), 9pt 미달은 Argon 이 상한 −25% 로 다시 써서 1회 다시 그림(`max_image_redraws` 1, ADR 0044). 초안 글 먼저
  (v1 즉시 drafted) + 그림 백그라운드(`application/services/figure_job.py`, run 의 `figures_job.json`·`.figures.lock`, 그리는 동안 ⑤⑥ 409
  "그림 준비 중", `rra runs active` 가 그리는 run 도 셈, `draft_visible_seconds`·`figures_done_seconds`, ADR 0045). 공사 홈페이지 행정 공시 →
  `admin_notice`·사업 현황 → `status_report`, `retrieval_mix` `only_in`·`strict`(2-가-(3) 은 정책만, ADR 0046) — 옛 코드는 새 doc_type 을 못 읽으므로
  운영 DB 이주(`rra db reclassify --apply`)는 새 코드 배포 뒤.
- 후속: 검토 채점은 별도 critique_draft 없이 Argon 검토에 합침(P5), 예산표·차별성 매트릭스는 양식 밖(화면·API 표만),
  MCP streamable-http·Tailscale/Cloudflare 공개는 비교 문서만(P6), reranker·골든셋 피드백 루프는 이슈(P7).

## MCP
- `.mcp.json`(프로젝트 루트, stdio, `.venv/bin/python -m rra.entrypoints.mcp.server`). 등록·보안은 docs/mcp.md.
- 도구 로직은 `entrypoints/mcp/tools.py`(읽기)·`run_tools.py`(쓰기, mcp SDK import 없음), 등록만 `server.py`.
  쓰기 도구(differentiate·generate·get_draft·confirm·review·get_review·edit·finalize·reopen)는 `--enable-generate` 일 때만 등록. tools.py 는 RunManager 를 import 할 수 없다(계약 "read-only MCP tools never reach the run manager"). 계약은 모두 8건.
- 도구 결과는 항상 비신뢰: `domain/rules/trust.untrusted_block()` / `UNTRUSTED_NOTICE` 를 거쳐 나간다.
