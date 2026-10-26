# 연구제안서 작성 앱 (research-proposal-app)

한국철도공사 철도연구원 양식(별지 제2호서식, 2024.02.19.) 연구과제 제안서 초안을 로컬 LLM 으로 만드는 앱.
헥사고날 구조(domain → application(ports·usecases) → adapters, 진입점 CLI·MCP·Streamlit·REST 는 같은
application 을 호출), 보안코딩 A~J 반영. 설계는 `docs/architecture.md`, 개발 현황·남은 일·진행 계획은
`docs/status.md`, MCP 는 `docs/mcp.md`, 배포는 `deploy/README.md`.

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

LLM 은 `mlx_lm.server --host 127.0.0.1 --port 8080` (OpenAI 호환, `config/llm.yaml`, launchd `deploy/launchd/com.rra.mlx.plist`).
로컬 작성 모델은 `llm.yaml model_profiles`(qwen·midm·ax_light: served_model·json_mode·system_role·stop)로 고르고
`RRA_LLM_PROFILE` 로 바꿀 수 있다. 2026-10-26 비교(`rra llm-bench`, `docs/llm-bench-2026-10-26.md`)에서 Mi:dm 2.0 Base·
A.X 4.0 Light 는 JSON 형식 성공률 기준(95%)에 못 미쳐 **Qwen2.5-7B-Instruct-4bit 를 유지**한다. 테스트는 LLM·임베딩 없이
`tests/fakes.py` 로 돈다. 실응답 fixture 는 `tests/fixtures/`, 녹화 도구는 `tests/tools/`, 골든셋은 `tests/golden/`.

## 현재 상태 (2026-10-26)

- Step 1~10 + 실물 양식 템플릿(`tools/build_form_template.py`) + 작성 → Argon 검토 → 제안자 수정 → 재검토 → 최종 마무리
  흐름(`docs/architecture.md` §4.6) + 프론트엔드용 REST(§9.2, `docs/openapi.json`) 까지. 양식 파일은 finalize 로만.
- Argon 검토·차별화 제안은 `RRA_GEMINI_API_KEY` 로 연결돼 있다(없으면 검토 건너뜀·차별화는 로컬 모델). 기획서 기준
  외부 자료원 신청처·검증 명령은 `docs/external-apis.md`. 항목별 현황·근거·단계 계획(P0~P7)은 `docs/status.md`.
- 대기(사람 입력): ScienceON·NTIS·KIPRIS 키, `korail_strategy.yaml` 전략체계, 연구과제 공고문, 프론트엔드 `web/dist`.
