# research-proposal-app

연구과제 제안서 자동 작성 앱 (한국철도공사 철도연구원 양식). 헥사고날 아키텍처, 보안코딩 적용.
설계 문서: docs/architecture.md

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
- 커밋 전: `pytest -q && lint-imports && ruff check src tests`
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
  sanitize→escape→defusedxml 재파싱. 진입점: `rra runs render`, UI 5번 패널, MCP `rra_render`, REST `/v1/runs/{id}/file`.
- 실물 양식 연결(2026-10-26): 원본 `data/templates/proposal_form_original.hwpx` → `tools/build_form_template.py` →
  `config/templates/proposal_korail.hwpx`(둘 다 미커밋, .gitignore). 자리표시자는 slots.yaml 영문 키(`{{title}}`,
  `{{task_type:basic}}`, `{{utilization:software}}` …). 체크 칸은 양식 괄호 안 `( ○ )`/`(   )`(slots.yaml marks),
  여러 문장 섹션은 문장마다 `○ ` 단락 복제(`expand_paragraphs`), 한 줄 칸은 인라인. 제안일자 비면 렌더 날짜.
  렌더 전 점검 `usecases/render_check.py`(미해결 lint·max_chars·line_limits 초과·전략 빈칸) — CLI 출력, UI 버튼 위,
  REST `GET /v1/runs/{id}/render-check`. 알림은 렌더를 막지 않는다. 양식이 바뀌면 스크립트가 앵커 불일치로 멈춘다.
- 대기(사람 입력): 자체과제 내역 파일(data/inbox/own/), 연구과제 공고문(data/inbox/notice/).
- 후속: critique_draft·예산표·차별성 매트릭스(Step 9), MCP streamable-http·Tailscale 공개(Step 10), reranker.

## MCP
- `.mcp.json`(프로젝트 루트, stdio, `.venv/bin/python -m rra.entrypoints.mcp.server`). 등록·보안은 docs/mcp.md.
- 도구 로직은 `entrypoints/mcp/tools.py`(읽기)·`run_tools.py`(쓰기, mcp SDK import 없음), 등록만 `server.py`.
  쓰기 도구(generate·get_draft·confirm·render)는 `--enable-generate` 일 때만 등록. tools.py 는 RunManager 를 import 할 수 없다(계약 "read-only MCP tools never reach the run manager"). 계약은 모두 8건.
- 도구 결과는 항상 비신뢰: `domain/rules/trust.untrusted_block()` / `UNTRUSTED_NOTICE` 를 거쳐 나간다.
