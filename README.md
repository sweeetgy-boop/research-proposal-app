# 연구제안서 작성 앱 (research-proposal-app)

한국철도공사 철도연구원 양식(별지 제2호서식, 2024.02.19.) 연구과제 제안서 초안을 근거 기반으로 만드는 앱.
초안은 Argon(Gemini)이 먼저 쓰고 오류 섹션만 로컬 LLM(Qwen2.5-7B, mlx)이 대신 쓴다(2026-10-28, ADR 0032 — 그 전에는 로컬 작성이 기본이었다).
헥사고날 구조(domain → application(ports·usecases) → adapters, 진입점 웹(REST + `web/` SPA)·CLI·MCP·Streamlit 은 같은
application 을 호출), 보안코딩 A~J 반영. 설계는 `docs/architecture.md`, 개발 현황·남은 일은 `docs/status.md`, 동료 안내는
`docs/pilot-guide.md`, MCP 는 `docs/mcp.md`, 배포는 `deploy/README.md`, 최종보고서 재료는 `docs/final-report-materials.md`.

## 설치

```bash
uv venv --python 3.12 && source .venv/bin/activate
uv pip install -e ".[dev]"   # persistence·llm·mcp·sources·ui·render·api + 검사 도구
pytest -q && lint-imports && ruff check src tests
```

임베딩 모델까지 쓰려면 `uv pip install -e ".[adapters]"` (sentence-transformers·torch, 무겁다).
macOS 와 WSL 은 `.venv` 를 따로 만든다. `.env` 는 `.env.example` 을 복사해 권한 600 으로 둔다(없으면 기동 거부).

## 구성

| 계층 | 위치 | 내용 |
|---|---|---|
| domain | `src/rra/domain/` | 모델(ProposalRequest·Draft·RunState…)·규칙(근거 검증·lint·유사과제 판정·Agent 정책). pydantic·표준 라이브러리만 |
| application | `src/rra/application/` | 포트(`typing.Protocol`, 전부 비동기 저장소·임베딩·TaskRunner·Renderer…)·유즈케이스(ingest·precheck·generate·list_missing·diagnostics·purge_runs)·서비스(RunManager·ProposalAssistant) |
| adapters | `src/rra/adapters/` | SQLite FTS5+sqlite-vec, sentence-transformers, OpenAI 호환 LLM, 자료원(OpenAlex·알리오·ScienceON·NTIS·사내 엑셀/공시 요약문), runs 파일 저장소·락·asyncio 실행기, logging(manifest), rendering(HWPX), security(ASGI 미들웨어) |
| entrypoints | `src/rra/entrypoints/` | `cli.py`, `mcp/`, `ui/`(Streamlit), `api/`(FastAPI). 유즈케이스 호출만 |
| 조립 | `src/rra/composition.py`, `src/rra/config_loader.py` | `build_*` 만 / yaml·환경변수 병합 |

`import-linter` 계약 8건이 계층 방향을 강제한다 (`pyproject.toml`).

## 실행

```bash
rra precheck --current-state "..." --root-cause "..." --limitation "..." --goal "..."   # 유사과제 사전 점검
rra differentiate --current-state ... --goal ...   # 차단·근접 유사과제별 활용·차별화 방향 (기능 2, Gemini — 키 없으면 로컬)
rra search "궤도 틀림 자동 감지" -k 5                                                # 하이브리드 검색
rra llm-check --stage compose                                                        # mlx-lm 왕복 1회 + served_model 확인
rra ingest --source openalex,alio,alio_summary [--query ...]                          # 수집 → 적재
rra ingest --source own_projects,own_docs      # 사내 과제 현황 엑셀(data/inbox/own)·공시용 요약문(data/inbox/own_docs)
rra ingest --source kipris                      # KIPRIS Plus 특허 (RRA_KIPRIS_KEY, docs/external-apis.md)
rra sources check                                                                    # ScienceON·NTIS·KIPRIS 키 유무(값 미표시)·왕복·record_tag 진단
rra alio catalog [--fetch] | rra alio missing | rra alio status                       # 알리오 카탈로그·filedrop
rra generate --current-state ... --goal ... [--differentiation "고른 방향"] [--file in.yaml] [--resume RUN] [--reuse-input RUN]
rra runs list | rra runs show RUN [--json]
rra runs confirm RUN --task-type applied --utilization software,manual [--strategy D1-1]
rra runs review RUN [--wait]                 # Argon 검토 n차 (RRA_GEMINI_API_KEY 없으면 건너뜀 기록)
rra runs edit RUN --from edits.json          # 제안자 편집 반영 → 새 버전 (수정안 사용 | 원문 유지 | 직접 수정)
rra runs versions RUN | rra runs revert RUN --to v2 | rra runs reopen RUN
rra runs finalize RUN --out out/proposal.hwpx [--task-type ...] [--department ... --proposer-name ...]  # 유일한 HWPX 경로
rra reindex | rra db backup --out data/backups --keep 7                              # 임베딩 재색인 / VACUUM INTO 백업
rra llm-check --provider gemini | rra api schema                                     # Argon 왕복 / docs/openapi.json
rra runs purge [--dry-run]                                                           # 보존기간(180일) 지난 run 삭제
rra ui  [--port 8501]      # Streamlit, 127.0.0.1, RRA_API_TOKEN 필요
rra api [--port 8000]      # REST, 127.0.0.1, RRA_API_TOKEN 필요 (deploy/README.md)
rra mcp [--enable-generate]  # MCP stdio — 읽기 2개 / 쓰기 포함 11개 (docs/mcp.md)
```

Argon(Gemini, `config/llm.yaml providers.gemini`, `RRA_GEMINI_API_KEY`)이 초안 작성·판정·최종 검토를, Nano Banana Pro 가 그림을 맡는다.
로컬 LLM 은 `mlx_lm.server --host 127.0.0.1 --port 8080` (OpenAI 호환, launchd `deploy/launchd/com.rra.mlx.plist`) — Argon 오류 대체·L2 로컬 2차 검토.
로컬 모델은 `llm.yaml model_profiles`(qwen·midm·ax_light: served_model·json_mode·system_role·stop)로 고르고
`RRA_LLM_PROFILE` 로 바꿀 수 있다. 2026-10-26 비교(`rra llm-bench`, `docs/llm-bench-2026-10-26.md`)에서 Mi:dm 2.0 Base·
A.X 4.0 Light 는 JSON 형식 성공률 기준(95%)에 못 미쳐 **Qwen2.5-7B-Instruct-4bit 를 유지**한다. 테스트는 LLM·임베딩 없이
`tests/fakes.py` 로 돈다. 실응답 fixture 는 `tests/fixtures/`, 녹화 도구는 `tests/tools/`, 골든셋은 `tests/golden/`.

## 현재 상태 (2026-10-29)

- **시범 운영 중**(2026-10-28~, 동료 3명): 운영 맥 launchd(mlx·api·backup·ingest·awake), 외부 주소는 Tailscale Funnel
  `https://rra.taile5afcf.ts.net`(ADR 0047), 로그인은 직원 사번·공용 계정·관리 토큰(ADR 0026). 배포 버전 c277253(2026-10-29 10:48, 그 전 546f244 09:30,
  `docs/history/deploys/`). 합쳐도 자동 재시작하지 않고 `tools/deploy.sh` 로 배포한다(`docs/pilot-guide.md` §6.3).
- 흐름 ①~⑥: 아이디어 입력 → ② 유사과제 확인(표 먼저 → Argon 같음 판정 → [유사함]/[관련 없음], 같은 연작 한 줄, 실시간 검색
  ScienceON·NTIS·OpenAlex) → ③ 초안 생성(Argon 작성 → 규칙 검사 → L2 로컬 2차 검토, 그림은 백그라운드 Nano Banana Pro) →
  ④ 직접 수정 → ⑤ Argon 최종 검토 1회 → ⑥ HWPX. 자세한 것은 `docs/final-report-materials.md`.
- 검사: pytest 2,418 · vitest 201 · e2e 40(+3 skip), import 계약 8(2026-10-29 #108 기준).
- 화면: Research Studio — 배포됨 (c277253, 2026-10-29 10:48). 왼쪽 사이드바·화면 안 로그인·연구 작업실 홈·⌘K 통합 검색·작성 가이드(ADR 0048~0051).
- 대기(사람 입력): NTIS 서버 IP 반영 확인(실시간 검색 NTIS "IP 차단"), 고정 IP, `korail_strategy.yaml` 전략체계 확정,
  연구과제 공고문, g2b 키, Mac mini 이전. 목록은 `docs/status.md` §3.2.

<details><summary>이전 상태 (2026-10-26)</summary>

- Step 1~10 + 실물 양식 템플릿(`tools/build_form_template.py`) + 작성 → Argon 검토 → 제안자 수정 → 재검토 → 최종 마무리
  흐름(`docs/architecture.md` §4.6) + 프론트엔드용 REST(§9.2, `docs/openapi.json`) 까지. 양식 파일은 finalize 로만.
- 당시 대기: ScienceON·NTIS·KIPRIS 키, `korail_strategy.yaml` 전략체계, 연구과제 공고문, 프론트엔드 `web/dist` — 키·웹은 이후 해결.

</details>
