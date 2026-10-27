# 개발 현황 (2026-10-26)

기획서(`AI_Agent_프로젝트_기획서_연구과제제안서작성지원_20251015_rev_2.hwpx`, 최종 수정 2026-10-15) 기준으로
개발된 것과 남은 것을 적는다. 항목마다 근거(파일·테스트·커밋)를 붙인다. 설계는 `architecture.md`,
단계 계획은 맨 아래 "진행 계획" 표. 각 단계가 끝날 때 이 문서의 해당 행을 갱신한다.

규모(main e10466e, 2026-10-26 PR #1~#9·#15~#18 병합 뒤): 커밋 105, `src/rra` 파일 146, 테스트 76파일(`pytest -q` 1,178 통과·12 skip — skip 은 실응답 fixture·실물 양식), import-linter 계약 8 kept, ruff 통과. CI(`.github/workflows/ci.yml`): backend 통과, web 은 `web/` 이 없어 skip.

## 1. 기획서 기준표

### 1.1 Ⅱ 핵심 기능 7개

| No. | 핵심 기능 | 우선순위 | 상태 | 근거 |
|---|---|---|---|---|
| 1 | 유사과제 사전 알림 (기관별 기준 + 공유 키워드 2개 이상일 때만 차단, 겹친 키워드·공개 요약 기반 표시) | 필수 | 완료 | `domain/rules/overlap.py`·`keywords.py`, `usecases/precheck_overlap.py`, `config/overlap.yaml`; `tests/domain/test_overlap.py`·`test_keywords.py`, `tests/application/test_precheck.py`; 70dad36 |
| 2 | 유사과제 활용·차별화 제안 | 필수 | 완료 (P3) | `domain/rules/differentiation.py`, `usecases/differentiate.py`, `prompts/differentiate.md`, `agent_policy.on_differentiate`; `tests/domain/test_differentiation.py`, `tests/application/test_differentiate.py`; CLI·REST·MCP·Streamlit; architecture §4.9 |
| 3 | 근거 자료 RAG 검색 (FTS5 + 벡터, RRF) | 필수 | 완료 | `adapters/persistence/sqlite_repo.py`, `domain/rules/fusion.py`; `tests/adapters/test_sqlite_repo.py`·`test_fts_query.py`, `tests/contracts/test_document_repository.py`; 4c23b52, 42d071a |
| 4 | 제안서 초안 생성 (12섹션, 문장마다 근거 id, 검색 밖 id 폐기) | 필수 | 완료 | `usecases/generate_proposal.py`, `domain/rules/grounding.py`·`llm_output.py`·`numbers.py`; `tests/application/test_generate_proposal.py`, `tests/domain/test_grounding.py`·`test_llm_output.py`; ac55782, ba3e600, df70852. 검색 관련도 하한은 이슈 #2 → P1 |
| 5 | 선택형 항목 제안·확정 (과제유형·활용계획·경영전략) | 필수 | 완료 (전략체계 목록은 빈 파일) | `domain/models/draft.py` choices, `rra runs confirm`, UI 확정 폼; `tests/entrypoints/test_cli.py`·`ui/test_app.py`; ac55782. `config/templates/korail_strategy.yaml` 이 비어 있어 2-가-(3) 은 빈칸 + 경고 |
| 6 | 생성 이력·재개 (실행별 저장, 섹션 단위 재개, 성명·연락처 미저장) | 필수 | 완료 | `application/services/run_manager.py`, `adapters/runs/`, `adapters/logging/file_run_log.py`(허용목록); `tests/application/test_run_manager.py`, `tests/adapters/test_file_run_store.py`; 90f46bc, 3dcb081 |
| 7 | Streamlit 화면 (토큰 → 입력 → 유사과제 표 → 진행 → 초안·알림 → 확정 → HWPX, 사이드바 Agent 기록·자료 질의) | 선택 | 완료 | `entrypoints/ui/`, `domain/rules/agent_policy.py`, `application/services/assistant.py`; `tests/entrypoints/ui/test_app.py`·`test_server.py`·`test_worker.py`, `tests/domain/test_agent_policy.py`; 9170790, 71d860c |

### 1.2 Ⅰ 프로젝트 범위 12개

| No. | 범위 | 상태 | 근거 |
|---|---|---|---|
| ① | 과제 아이디어 입력 | 완료 | `domain/models/request.py`(필수 4 + 선택, validator 한 곳); `tests/domain/test_request.py`; b20deb6 |
| ② | 유사과제 중복성 검토·사전 알림 | 완료 | 기능 1 과 같음 |
| ③ | 유사과제 활용·차별화 제안 | 완료 (P3) | 기능 2 와 같음 |
| ④ | 국내외 논문·특허·R&D 사전 적재·갱신 | 부분 | OpenAlex 철도 코퍼스 2,482건(13개 분야 질의, #18, architecture §4.13)·알리오 catalog/filedrop/공개 요약(d305174, c3ac454)·ScienceON·NTIS 과제검색(428ed2c)·KIPRIS 특허(P4, `adapters/sources/kipris/`) 코드 완료. ScienceON·NTIS·KIPRIS 는 키·실응답 fixture 대기(skip 3). 야간 적재는 `com.rra.ingest.plist`(P6, `--limit 5000`, 증분 7일) |
| ⑤ | RAG 근거 검색·자료 질의 | 완료 | 기능 3, `rra search`, MCP `rra_search`, UI 사이드바 질의 |
| ⑥ | 섹션별 초안 생성·출처 표시·수치 검사 | 완료 | 기능 4, `numbers.py`(지어낸 수치 알림), `foreign_script.py`; `tests/domain/test_numbers.py`; 463139e |
| ⑦ | 과제유형·활용계획·경영전략 제안·확정 | 완료 (전략 목록 대기) | 기능 5 |
| ⑧ | 생성 이력 저장·중단 시 재개 | 완료 | 기능 6. 보존기간 삭제 `rra runs purge`; `tests/application/test_purge_runs.py` |
| ⑨ | Streamlit 화면·접속 통제 | 완료 | 기능 7, `entrypoints/ui/auth.py`(RRA_API_TOKEN 게이트) |
| ⑩ | HWPX 서식 자동 출력 | 완료 | `adapters/rendering/hwpx.py`(템플릿·생성 모드), `tools/build_form_template.py`, `usecases/render_check.py`; `tests/adapters/test_hwpx_renderer.py`·`test_form_template.py`, `tests/application/test_render_check.py`; aa4be7c, aa7b977~6fea01f |
| ⑪ | 운영 서버(Mac mini) 배포·시연 | 부분 | `deploy/launchd/com.rra.{api,mlx,backup,ingest}.plist`, `deploy/README.md` 설치 순서(P6), `tests/deploy/`. 공개 방식은 `deploy-exposure.md` 비교 뒤 결정 대기. Mac mini 실제 등록·타 제안자 시연은 미실시 |
| ⑫ | 소요예산 입력 반영 | 완료 | `ProposalRequest.budget` 은 LLM 에 보내지 않고 1-나 칸에만 기록(`slots.yaml`, 예산 표기 헬퍼); `tests/adapters/test_form_template.py`; aa7b977 |

## 2. 기획서 밖에서 개발된 것

| 영역 | 내용 | 근거 |
|---|---|---|
| 판단 반영 (A, 2026-10-26) | 하한 0.79 유지. 엑셀 4개 과제 = own 티어(철도연구원/공사 구분 표시), 경고 제외, generic_terms 14개 추가. visibility: 엑셀·공시용 요약문 public, 일반 요약문만 있는 5건 internal (dev DB 재적재: own 1,119 public / alio 115 public·5 internal / openalex 20 public). 차별화 자동 실행은 차단 알림만, REST 전송 기록 → manifest | `domain/rules/overlap.py`, `adapters/sources/own/`, `config/overlap.yaml`, `entrypoints/api/schemas.py RunIn`; `tests/adapters/own`, `tests/entrypoints/test_api.py`·`test_cli.py`; architecture §4.8·§4.9 |
| 사내 자료 적재 (P2) | `own_projects`(엑셀 4개 → 과제 1,119건, status·과제명 병합·이름 열 제외, 전부 public·own 티어)·`own_docs`(공시완료 107개 폴더 → 요약문 129파일, 공시용 > 일반, hwpx > hwp > pdf, 묶음 분리, 공시용 public). 샌드박스 hwp·xlsx·xls 파서. `OverlapAlert.status`·`own_detail` | `adapters/sources/own/`, `alio/extract/hwp.py`·`spreadsheet.py`, `config/sources.yaml own`; `tests/adapters/own/`, `tests/adapters/alio/test_extract.py`; architecture §4.8 |
| 외부 자료원 점검 (P4) | `external-apis.md` 전수 표(신청처·필요 정보·한도·검증 명령), KIPRIS Plus 어댑터(발명자 제외·출원인 기관만), `rra sources check` kipris·record_tag 진단, ScienceON MAC 안내, NTIS 연구보고서 가능 여부 | `adapters/sources/kipris/`, `config/sources.yaml kipris`; `tests/adapters/test_kipris.py`, `tests/test_composition.py`; architecture §4.10 |
| 생성 근거 관련도 하한 (P1) | 검색 청크가 근거로 남으려면 코사인 ≥ 0.79, 한글 청크는 질의 키워드 ≥ 1. 통과 0 이면 근거 필수 섹션 빈칸 + `no_relevant_evidence`. 골든셋 측정 fixture 로 임계치 고정 | `domain/rules/relevance.py`, `config/overlap.yaml evidence_floor`, `tests/fixtures/relevance_golden.json`; `tests/domain/test_relevance.py`, `tests/application/test_generate_proposal.py`, `tests/adapters/test_sqlite_repo.py`; architecture §4.7, 이슈 #2 |
| 계층·검증 | 헥사고날 4계층, import-linter 계약 8건, 포트 전부 runtime_checkable·비동기 저장소/임베딩, TaskRunner 포트 | `pyproject.toml`, `composition.py`·`config_loader.py`; `tests/test_composition.py`·`test_config_loader.py`, `tests/adapters/test_port_conformance.py`; 0ecbe46, 6b31f35~0bcac95 |
| 보안 A~J | 근거 id 대조·JSON 전용 파싱, subprocess 파싱 격리·zip 상한·defusedxml, 허용 도메인·리다이렉트 재검사·사설 IP 거부, SecretStr, SQL 바인딩·FTS5 토큰 인용, HWPX escape·재파싱, 127.0.0.1·토큰·동시성 1, 로그 허용목록 | `adapters/sources/_base.py`·`_sandbox.py`, `adapters/security/`, `adapters/llm/_endpoint.py`; `tests/adapters/test_base_security.py`·`test_guarded_client.py`·`test_sandbox.py`·`test_llm_endpoint.py`, `tests/entrypoints/test_api.py` |
| DB 정비 | migration 001~004(schema_version·valid_until·visibility·ingested_at), 만료 문서 검색 제외, `rra reindex`, `rra db backup`(VACUUM INTO·보관 회전), 일일 백업 plist | `adapters/persistence/migrations/`, `usecases/maintain_db.py`; `tests/application/test_maintain_db.py`; 42c2eaf |
| 협업 준비 (2026-10-26, #17) | GitHub Actions CI(backend: uv·pytest·lint-imports·ruff / web: `web/` 있을 때만 npm lint·typecheck·test / detect), CODEOWNERS(`web/` 동료 TODO), PR 템플릿, CONTRIBUTING. 비밀 키 없이 돌고 실물 양식·사내 데이터 테스트는 skip. 샌드박스 RLIMIT_AS 제거(리눅스 pymupdf import 실패) | `.github/workflows/ci.yml`, `.github/CODEOWNERS`, `.github/pull_request_template.md`, `CONTRIBUTING.md`, `adapters/sources/_worker.py` |
| OpenAlex 코퍼스·근거 출처 다양성 (2026-10-26, #18) | 철도 분야 영문 질의 13개(초록 있음·10년·질의당 200), page 페이징(cursor 는 API 키 필요), `RRA_OPENALEX_MAILTO`·`RRA_OPENALEX_API_KEY` 선택. 적재 뒤 한국어 질의가 사내 기록만 앞세워 논문이 근거 0건 → 넓은 검색(k×4)·부족 자료원 재검색(`hybrid_search sources` 필터)·출처별 최소 6건 보장. `rra generate` 가 자동 검토 뒤 종료 코드 1 이던 것 수정 | `adapters/sources/openalex.py`, `config/sources.yaml`, `domain/rules/relevance.py`, `usecases/generate_proposal.py`, `adapters/persistence/sqlite_repo.py`, `config/overlap.yaml evidence_floor`; `tests/adapters/test_openalex.py`·`test_sqlite_repo.py`, `tests/application/test_generate_proposal.py`; architecture §4.13 |
| 운영 준비 (P6) | 야간 적재 plist(키 없는 자료원 건너뜀·소스별 격리), plist 4종·백업 7벌 테스트, 설치 순서 문서, 공개 방식 비교 | `deploy/launchd/com.rra.ingest.plist`, `composition.build_available_sources`, `deploy/README.md`, `docs/deploy-exposure.md`; `tests/deploy/test_launchd_plists.py`; architecture §4.12 |
| 검토 채점 (P5) | Argon 검토에 필요성·차별성·실현가능성·기대효과 1~5점 + 근거 문장. 2점 이하 → 문장·섹션 의견. 수치는 알림 유지 + 검토 지적 의무 + 마무리 점검 맨 위 건수 | `domain/models/review.py`(CriterionScore·score_comments), `usecases/review_draft.parse_scores`, `prompts/review.md`, `usecases/render_check.py`; `tests/domain/test_review_scores.py`, `tests/application/test_review_draft.py`·`test_render_check.py`; architecture §4.11 |
| 검토·수정·마무리 흐름 | 작성 → Argon(Gemini) 검토 → 제안자 수정 → 재검토 → finalize → reopen. 버전(versions·revert)·검토 라운드 파일·manifest 검토 요약. 양식 파일은 finalize 로만 | `domain/rules/review_flow.py`, `usecases/review_draft.py`, `run_manager.py`; `tests/domain/test_review_flow.py`, `tests/application/test_review_draft.py`·`test_review_manager.py`; 4b22913~71d860c |
| 외부 LLM provider | `llm.yaml providers`(mlx·gemini·openai)·단계별 provider(review=gemini)·`RRA_GEMINI_API_KEY`·allowed_domains·reasoning_effort·401/403 비재시도. **`.env` 에 키가 있고 `rra llm-check --provider gemini` 왕복 성공(Argon 연결됨)** | `config_loader.py`, `adapters/llm/openai_compat.py`; `tests/adapters/test_openai_compat.py`, `tests/adapters/test_gemini_live.py`(키 있을 때만); 9cb311f. 모델 목록의 `models/` 접두어 비교는 P0 에서 수정 |
| 로컬 모델 프로필·벤치 | `model_profiles`(qwen·midm·ax_light), `rra llm-bench`, 골든셋 3건, 스키마 오류 1회 교정 재요청. Qwen2.5-7B-Instruct-4bit 유지 결정 | `usecases/bench.py`, `tests/golden/`, `llm-bench-2026-10-26.md`; `tests/application/test_bench.py`; 3a98056~3f208c8 (PR #1) |
| REST API | 세션 쿠키 + CSRF, problem+json, SSE, 전 흐름(precheck·search·runs·draft·versions·revert·review·edits·confirm·render-check·finalize·reopen), 정적 SPA fallback, `RRA_FAKE_LLM` 가짜 모드, `openapi.json` | `entrypoints/api/`, `adapters/fake/`; `tests/entrypoints/test_api.py`; 2b169f8, dec519e |
| MCP | stdio, 읽기 2 + 쓰기 8(`--enable-generate`), 결과는 비신뢰 블록 | `entrypoints/mcp/`, `domain/rules/trust.py`; `tests/entrypoints/test_mcp_server.py`·`test_mcp_tools.py`; `mcp.md` |
| CLI | precheck·search·ingest·generate·runs(list·show·confirm·review·edit·versions·revert·finalize·reopen·purge)·alio·sources check·llm-check·llm-bench·reindex·db backup·mcp·api·ui | `entrypoints/cli.py`; `tests/entrypoints/test_cli.py` |

## 3. 남은 일

### 3.1 코드로 할 일 (진행 계획 P1~P6)

| 항목 | 내용 | 단계 |
|---|---|---|

### 3.2 사람 입력 대기

| 항목 | 상태 |
|---|---|
| ScienceON 키 | **.env 의 `RRA_SCIENCEON_CLIENT_ID`(64자)·`RRA_SCIENCEON_KEY`(32자) 값이 서로 바뀌어 있음** — 맞바꿔 넣을 것(Mac mini 포함). 실호출·fixture·적재 2,045건은 worktree 사본으로 완료(#25) |
| NTIS·KIPRIS API 키 → 실응답 녹화 → FIELDS 매핑·record_tag 확정 (`external-apis.md` 신청처) | 대기 (skip 2건). 특허는 ScienceON PATENT 가 기본(ADR 0016)이라 KIPRIS 는 선택 |
| 전략체계 초안 → 확정 (`rra strategy promote`, `config/strategy.yaml source: draft`) | 초안 `korail_strategy.draft.yaml`(5 방향·15 과제, 출처 주석) 확인 뒤 사람이 실행 |
| 알리오 원문 공시 파일·카탈로그 CSV 샘플 | 대기 (skip 2건). 공시용 요약문은 P2 에서 own_docs 로 적재됨 |
| `config/templates/korail_strategy.yaml` 전략체계 목록(확정본) | 비어 있음 — 확정 전까지 앱은 초안을 쓰고 "전략체계 초안(확인 전)" 라벨 표시 |
| 연구과제 공고문 (`data/inbox/notice/`) | 파일 대기 ([11]) |
| 웹 프론트엔드 `web/` | 2026-10-27 구현 완료(#23·#30). 동료 GitHub 아이디를 CODEOWNERS `web/` 에 추가할 것. 로그인 뒤 화면 Lighthouse 는 세션 게이트 때문에 미측정 |
| `.env RRA_OPENALEX_MAILTO` (OpenAlex polite pool 이메일) | 값 대기 — 없어도 적재는 되지만 공용 풀(느림) |
| 운영 공개 방식(Tailscale/Cloudflare) 결정 | 보류(#14 댓글): 시범(팀 3명) Tailscale / 확대(사내·산학연) Cloudflare Access 검토, 공사 정보보안 규정 확인 후 결정 |

### 3.3 나중 (P7, 이슈만)

골든셋 피드백 루프(#10), 용어사전 반자동 확장(#11), reranker·유사과제 임계치 재조정(#12, 표본 축적 후),
공고문 반영(#13, 파일 준비 후), 운영 공개 방식 결정(#14, `deploy-exposure.md`).

## 4. 진행 계획 (2026-10-26 지시)

단계마다 main 에서 브랜치 → `pytest -q && lint-imports && ruff check src tests` → 커밋 → PR. 2026-10-26 [1] 이후 PR 은
CI(`gh pr checks --watch`) 통과 뒤 자동 병합(`--merge --delete-branch`), 병합 뒤 main 에서 같은 검사를 한 번 더. 동료 PR 은
자동 병합하지 않는다.

| 단계 | 브랜치 | 내용 | 상태 | PR |
|---|---|---|---|---|
| P0 | `chore/status-sync` | 이 문서, Gemini 모델 목록 `models/` 접두어, `own_unit.departments`(연구계획처·차량기술센터) | 완료 2026-10-26 | #3 |
| P1 | `fix/retrieval-relevance-floor` | 검색 관련도 하한 (이슈 #2): 03 궤도 인용 0건, 01 관련 논문 16건 유지 (`llm-bench-2026-10-26.md` P1 절) | 완료 2026-10-26 | #4 |
| P2 | `feat/own-ingest` | 사내 자료 적재: 엑셀 1,119건·공시 요약문 121건, precheck 예시 3건 (PR 본문) | 완료 2026-10-26 | #5 |
| P3 | `feat/differentiation` | 기능 2 차별화 제안: 실례 2건(미채택 재제안 2건·완료 근접 4건, 폐기 0) | 완료 2026-10-26 | #6 |
| P4 | `feat/external-apis` | 전수 점검 표(`external-apis.md`), KIPRIS 어댑터, record_tag 진단, ScienceON MAC 안내 | 완료 2026-10-26 | #7 |
| P5 | `feat/review-scoring` | 심사 기준 4개 채점·2점 이하 의견 연결·수치 정책(알림 유지 + 검토 지적 + render_check 맨 위)·양식 밖 산출물 결정 | 완료 2026-10-26 | #8 |
| P6 | `chore/ops` | `com.rra.ingest.plist`·`--skip-unavailable`, plist·백업 7벌 테스트, `deploy/README` 설치 순서, `deploy-exposure.md` 비교 | 완료 2026-10-26 | #9 |
| P7 | — | 이슈 등록: 골든셋 피드백 루프 #10, 용어사전 반자동 확장 #11, reranker·임계치 재조정 #12, 공고문 반영 #13, 공개 방식 결정 #14 | 완료 2026-10-26 | 이슈 |
| A | `fix/post-p7-decisions` | 판단 반영: own 티어 전부·세부 구분, visibility 정정, generic_terms, 차별화 자동 실행 규칙, REST 전송 기록 | 완료 2026-10-26 | #15 |
| D | `docs/status-after-p7` | 이 문서 §5 병합 결과·실제 확인 | 완료 2026-10-26 | #16 |
| [1] | `chore/collab` | CI 워크플로·CODEOWNERS·PR 템플릿·CONTRIBUTING | 완료 2026-10-26 | #17 |
| [2] | `feat/openalex-rail-corpus` | OpenAlex 철도 코퍼스 2,482건·근거 출처 다양성·generate 종료 코드 | 완료 2026-10-26 | #18 |
| [3] | `docs/status-corpus-ci` | 이 문서 갱신([1]·[2] 결과, CI, 보호 규칙) | 완료 2026-10-26 | #19 |
| [H] | `docs/history` | 개발 경과 기록(연표·수치·ADR·교훈·구조도·그래프·캡처), CONTRIBUTING 규칙 | 완료 2026-10-27 | #20 |
| [R] | `feat/project-recommendations` | 차별화 과제 추천(0~5건, 검증·자기 중복 경고·미리보기), ADR 0012 | 완료 2026-10-27 | #21 |
| [E] | `feat/draft-pipeline` | 2중 작성·직접 수정·최종 검토·버전 관리(ADR 0011), pipeline.yaml | 완료 2026-10-27 | #22 |
| [W] | `feat/web` | 웹 프론트엔드 11화면·DraftEditor·e2e·Lighthouse 100·axe 0 (ADR 0015) | 완료 2026-10-27 | #23 |
| 병렬 | `chore/parallel-ci` | pytest-xdist, CI 분할(backend-unit/api·web-check/e2e + 모음 job), 무거운 작업 락, 조각 파일 규칙 | 완료 2026-10-27 | #24 |
| [S] | `feat/scienceon-live` | ScienceON 실호출·fixture·매핑, 특허 기본 자료원(ADR 0016); 3단계 적재 2,045건 | 완료 2026-10-27 | #25 |
| 수정 | `fix/ci-e2e-path` | CI web-e2e 백엔드 경로 | 완료 2026-10-27 | #26 |
| [U] | `feat/usability` | 사용 편의성 U1~U8 백엔드(REST 14경로, usability.yaml, ADR 0017) | 완료 2026-10-27 | #27 |
| [P3] | `feat/policy-vision` | 웹 이미지 판독(거르기·OCR·Argon·캐시·신뢰도 규칙·공용 Gemini 제한기, ADR 0018) — 코드; 판독·적재는 대기열 | 완료 2026-10-27 | #28 |
| [C]·[P]·[P2-1] | `feat/policy-crawl` | 공사 홈페이지·국토부 크롤러·스냅샷·적재 어댑터·전략체계 초안·정책 근거 추천(ADR 0019) | 완료 2026-10-27 | #29 |
| U9 | `feat/web-u9` | 사용 편의성 웹 반영(간편 입력·정책 근거·비교표·브리핑·근거 패널·다시 쓰기·제출 전 점검·만족도) | 완료 2026-10-27 | #30 |
| [Q] | `feat/draft-quality` | 초안 품질 강화 8가지 + `rra eval` 측정 + 기본값 결정(ADR 0013), retrieval_mix.yaml, 골든셋 10건, acknowledged 게이트 | 완료 2026-10-27 | #31 |
| [5] | `fix/eval-findings` | 측정 결함 수정(JSON 찌꺼기 관용 파싱) | 완료 2026-10-27 | #32 |
| [6] | `docs/presentation-kit` | 발표 자료 원천 묶음 | 완료 2026-10-27 | #33 |
| [Z] | `docs/final-2026-10-27` | 이 문서·history·presentation-kit 갱신, 최종 점검 | 진행 2026-10-27 | — |

## 5. 병합 결과·실제 확인 (2026-10-26)

**병합** (순서대로, 매번 main 에서 `pytest -q && lint-imports && ruff check` 통과): #1 → #3 → #4 → #5 → #6 → #7 → #8 → #9 → #15
→ #16 → #17 → #18 → #19. GitHub 가 #4 이후를 충돌로 표시해 각 브랜치에 main 을 먼저 합쳐(충돌 없음) 푸시한 뒤 병합했다.
#17 부터는 CI(backend·detect 통과, web skip) 확인 뒤 자동 병합.

**검사** (main e10466e): pytest 1,178 passed·12 skipped / import-linter 8 kept, 0 broken / ruff All checks passed /
CI backend pass(1분), detect pass, web skipping. 깨끗한 클론(.env·data 없음, HF 오프라인)에서도 1,157 passed·18 skipped.

**자료원별 적재 (dev DB)**

| source | public | internal | 비고 |
|---|---|---|---|
| own (엑셀 4개 과제 기록) | 1,119 | 0 | 전부 own 티어, 공개 자료 |
| alio (공시용 요약문 + 알리오 페이지 요약) | 115 | 5 | internal 5 = 공시용 없이 일반 요약문만 있는 과제 |
| openalex | 2,482 | 0 | 13개 분야 질의(궤도 200·궤도검측 196·차량 197·신호 155·전력 199·유지보수 183·안전 191·수송수요 200·역사 197·자산관리 167·탄소중립 196·화물 200·운영 187) + 기존 14, 2009-04~2026-10, 청크 3,465 |
| scienceon·ntis·kipris | 0 | 0 | 키 대기 |

**실제 확인**
- Argon 검토(`rra runs review 20261026072125-17d5e269 --wait`, 2차, 36초): 채점 필요성 3·차별성 2·실현가능성 2·기대효과 3.
  의견 22건 = 근거 불일치 7·일관성 4·서식요건 3·수치 3·중복·차별화 3·논리 2. 수정안 사용 가능 13, 폐기 0.
  2점 기준은 tech_importance 문장 3건·method 문장 2건에 의견으로 연결됐다. 이 run 은 P1 이전 생성분이라 무관한
  자산개발 요약을 인용했고 검토가 그것을 정확히 지적했다(근거 불일치 7건).
- 차단 입력(자산개발 아이디어) precheck: 알림 10건·차단 2건, own:institute(사내 철도연구원)·own:company(사내 공사) 구분
  표시, 차단 알림으로 차별화 제안 자동 실행 → 3건(폐기 0, Gemini). 전송 public 5·internal 0.
- 공개 방식(#14): 보류 댓글 남김.
- OpenAlex 적재 뒤 골든셋(k=20, 하한 0.79 통과·출처): 01 궤도 — 적재 전 16(openalex 16) → 적재 직후 20(alio 15/own 5/openalex 0)
  → 다양성 규칙 뒤 20(+overlap 1)(alio 9/own 6/openalex 6). 02 자산개발 — 6 → 17(alio 8/own 9) → 20(alio 7/own 7/openalex 6).
  골든셋 01 새 초안 Argon 점수(필요성·차별성·실현가능성·기대효과): 이전 run 17d5e269 3/2/2/3 → min_per_source 4 run 9381fdcd
  4/2/2/3(논문 인용 0) → min_per_source 6 run eb7290ee 3/2/3/3(논문 인용 6, 채택). 차이는 7B run 간 편차 안이고 차별성 2 의 이유는
  세 번 모두 "무관한 사내 과제 인용·해외 연구와의 차별성 서술 부족"(e5 가 사내 한국어 청크를 0.85 이상으로 올림 → reranker #12).

**main 보호 규칙** — 켤 수 있는 상태. 권장 설정: "Require a pull request before merging"(승인 0 — 협업자가 본인뿐이면 본인 PR 을
승인할 수 없다; 동료가 들어오면 1), "Require status checks to pass" 에 검사 이름 **`backend`**·**`detect`** (CI job 이름.
`web` 은 `web/` 이 없으면 skipping 이라 `web/` 이 생긴 뒤 추가), "Require branches to be up to date" 켬, "Do not allow bypassing"
은 자동 병합 흐름이 관리자 권한으로 돌지 않으므로 켜도 된다. 보호 규칙이 자동 병합을 거부하면 어떤 규칙인지 보고하고 멈춘다.

**남은 사람 입력**: API 키(KIPRIS Plus·NTIS 소속기관 등록 뒤 과제검색/연구보고서·ScienceON client_id/키/기기별 MAC),
`.env RRA_OPENALEX_MAILTO` 값(polite pool), `config/templates/korail_strategy.yaml` 전략체계 목록, 연구과제 공고문
(`data/inbox/notice/`), Mac mini 에 launchd 4종 실제 등록(`deploy/README.md` 설치 순서) + 첫 `rra ingest --source openalex --full`,
main 보호 규칙 켜기(위 설정), 공개 방식 결정(#14), `web/` 생기면 CODEOWNERS 의 동료 TODO 채우기.

## 6. 2026-10-27 추가 작업 결과 (레인 병렬, 조각은 `docs/status.d/`·`docs/history/*.d/`)

| 영역 | 결과 | 상세 |
|---|---|---|
| 초안 품질 강화 [Q] | 8가지를 `config/pipeline.yaml` 로 켜고 끄며 측정(`rra eval`, 구성 16개) 뒤 기본값: section_search·additions·reranker·rule_check 켬 / clarify·outline·exemplars·two_candidates 끔. 결정 조합은 같은 코퍼스 기준 대비 점수 +1.5/run·충족률 +0.06·시간 +13%. precheck reranker 적중 9/10·순위 1.7→1.4 | `docs/eval-2026-10-27.md`, ADR 0013, `docs/status.d/feat-draft-quality.md` |
| 근거 구성 규칙 | `config/retrieval_mix.yaml` — 섹션별 허용 doc_type·논문·보고서·특허 최소 보장·유사과제 판정 제외(정책·보도·통계) | architecture §4.16 |
| ScienceON [S] | 실호출 검증·fixture·매핑, 적재 2,045건(논문 888·보고서 588·특허 569). 특허 기본 자료원은 ScienceON(ADR 0016). **.env 의 client_id·인증키가 서로 바뀌어 있음(사람 확인)** | `docs/status.d/feat-scienceon-live.md` |
| 공사 홈페이지·국토부 [C]·[P]·[P2-1] | info.korail.com 50개 메뉴 스냅샷(www.korail.com 은 SPA·봇 보호라 제외, 보도자료 5년, 50MB 초과 13건 보류), 크롤러·적재 어댑터·전략체계 초안(5 방향·15 과제)·정책 근거 추천·국토부 판 추적. 적재·측정은 대기열 | `docs/korail-web-crawl.md`, ADR 0019, `docs/status.d/feat-policy-crawl.md` |
| 이미지 판독 [P3] | 거르기·macOS OCR(샌드박스)·Argon 이미지 입력·해시 캐시·신뢰도 규칙(OCR 교집합 수치만)·공용 Gemini 제한기·표본 도구 — 코드·fixture 83건. 실판독은 대기열 | ADR 0018, `docs/status.d/feat-policy-vision.md` |
| 사용 편의성 [U] | U1~U8 백엔드(REST 14경로·CLI 5·usability.yaml)와 U9 웹 반영(8화면 추가, vitest 51·e2e 9) | ADR 0017, `docs/status.d/feat-usability.md`·`feat-web-u9.md` |
| 웹 [W] | Vite+React+TS SPA 11화면 + U9, Lighthouse 100/100/100(/login), axe 0, 초기 JS 111.6KB gzip | ADR 0015, `web/README.md` |
| 병렬 검사 | pytest-xdist(1,495 테스트 ≈10s), CI backend-unit/api·web-check/e2e + 모음 job, heavy lock, 조각 파일 규칙 | CONTRIBUTING |

보류·미착수: P2-2 안전 통계(키 필요)·P2-4 감사원(JS·robots)·P2-6 발주 용역(POST 폼)·P2 우선순위 2 전부, 로그인 뒤 Lighthouse, Streamlit 의 새 패널·MCP 도구.
