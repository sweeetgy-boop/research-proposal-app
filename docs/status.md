# 개발 현황 (2026-10-26)

기획서(`AI_Agent_프로젝트_기획서_연구과제제안서작성지원_20251015_rev_2.hwpx`, 최종 수정 2026-10-15) 기준으로
개발된 것과 남은 것을 적는다. 항목마다 근거(파일·테스트·커밋)를 붙인다. 설계는 `architecture.md`,
단계 계획은 맨 아래 "진행 계획" 표. 각 단계가 끝날 때 이 문서의 해당 행을 갱신한다.

규모(main 43ff8d8 + PR #1 기준): 커밋 58, `src/rra` 파일 134, 테스트 67파일(2026-10-26 `pytest -q` 1,027 통과·10 skip), import-linter 계약 8.

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
| ④ | 국내외 논문·특허·R&D 사전 적재·갱신 | 부분 | OpenAlex(f19b974)·알리오 catalog/filedrop/공개 요약(d305174, c3ac454)·ScienceON·NTIS 과제검색(428ed2c)·KIPRIS 특허(P4, `adapters/sources/kipris/`) 코드 완료. ScienceON·NTIS·KIPRIS 는 키·실응답 fixture 대기(skip 3). 야간 적재 launchd 없음 → P6 |
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
| 사내 자료 적재 (P2) | `own_projects`(엑셀 4개 → 과제 1,119건, status·과제명 병합·이름 열 제외)·`own_docs`(공시완료 107개 폴더 → 요약문 129파일, 공시용 > 일반, hwpx > hwp > pdf, 묶음 분리). 샌드박스 hwp·xlsx·xls 파서. `OverlapAlert.status` | `adapters/sources/own/`, `alio/extract/hwp.py`·`spreadsheet.py`, `config/sources.yaml own`; `tests/adapters/own/`, `tests/adapters/alio/test_extract.py`; architecture §4.8 |
| 외부 자료원 점검 (P4) | `external-apis.md` 전수 표(신청처·필요 정보·한도·검증 명령), KIPRIS Plus 어댑터(발명자 제외·출원인 기관만), `rra sources check` kipris·record_tag 진단, ScienceON MAC 안내, NTIS 연구보고서 가능 여부 | `adapters/sources/kipris/`, `config/sources.yaml kipris`; `tests/adapters/test_kipris.py`, `tests/test_composition.py`; architecture §4.10 |
| 생성 근거 관련도 하한 (P1) | 검색 청크가 근거로 남으려면 코사인 ≥ 0.79, 한글 청크는 질의 키워드 ≥ 1. 통과 0 이면 근거 필수 섹션 빈칸 + `no_relevant_evidence`. 골든셋 측정 fixture 로 임계치 고정 | `domain/rules/relevance.py`, `config/overlap.yaml evidence_floor`, `tests/fixtures/relevance_golden.json`; `tests/domain/test_relevance.py`, `tests/application/test_generate_proposal.py`, `tests/adapters/test_sqlite_repo.py`; architecture §4.7, 이슈 #2 |
| 계층·검증 | 헥사고날 4계층, import-linter 계약 8건, 포트 전부 runtime_checkable·비동기 저장소/임베딩, TaskRunner 포트 | `pyproject.toml`, `composition.py`·`config_loader.py`; `tests/test_composition.py`·`test_config_loader.py`, `tests/adapters/test_port_conformance.py`; 0ecbe46, 6b31f35~0bcac95 |
| 보안 A~J | 근거 id 대조·JSON 전용 파싱, subprocess 파싱 격리·zip 상한·defusedxml, 허용 도메인·리다이렉트 재검사·사설 IP 거부, SecretStr, SQL 바인딩·FTS5 토큰 인용, HWPX escape·재파싱, 127.0.0.1·토큰·동시성 1, 로그 허용목록 | `adapters/sources/_base.py`·`_sandbox.py`, `adapters/security/`, `adapters/llm/_endpoint.py`; `tests/adapters/test_base_security.py`·`test_guarded_client.py`·`test_sandbox.py`·`test_llm_endpoint.py`, `tests/entrypoints/test_api.py` |
| DB 정비 | migration 001~004(schema_version·valid_until·visibility·ingested_at), 만료 문서 검색 제외, `rra reindex`, `rra db backup`(VACUUM INTO·보관 회전), 일일 백업 plist | `adapters/persistence/migrations/`, `usecases/maintain_db.py`; `tests/application/test_maintain_db.py`; 42c2eaf |
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
| ScienceON·NTIS·KIPRIS API 키 → 실응답 녹화 → FIELDS 매핑·record_tag 확정 (`external-apis.md` 신청처) | 대기 (skip 3건) |
| 알리오 원문 공시 파일·카탈로그 CSV 샘플 | 대기 (skip 2건). 공시용 요약문은 P2 에서 own_docs 로 적재됨 |
| `config/templates/korail_strategy.yaml` 전략체계 목록 | 비어 있음 → 2-가-(3) 빈칸 |
| 연구과제 공고문 (`data/inbox/notice/`) | 파일 대기 ([11]) |
| 웹 프론트엔드 `web/dist` | 동료가 별도 진행. API 변경 시 `openapi.json` 갱신·PR 에 "프론트엔드 영향" 기재 |
| 운영 공개 방식(Tailscale/Cloudflare) 결정 | `docs/deploy-exposure.md` 비교 완료 — 권장 Tailscale. 결정 대기 |

### 3.3 나중 (P7, 이슈만)

골든셋 피드백 루프(채택·반려 결과 → 골든셋 갱신), 용어사전 반자동 확장(rail_terms 후보 → 사람 승인),
reranker·유사과제 임계치 재조정(표본 축적 후), 공고문 반영, 운영 공개 방식 결정.

## 4. 진행 계획 (2026-10-26 지시)

단계마다 브랜치 → `pytest -q && lint-imports && ruff check src tests` → 커밋 → PR. PR 은 사용자가 확인·병합.

| 단계 | 브랜치 | 내용 | 상태 | PR |
|---|---|---|---|---|
| P0 | `chore/status-sync` | 이 문서, Gemini 모델 목록 `models/` 접두어, `own_unit.departments`(연구계획처·차량기술센터) | 완료 2026-10-26 | #3 |
| P1 | `fix/retrieval-relevance-floor` | 검색 관련도 하한 (이슈 #2): 03 궤도 인용 0건, 01 관련 논문 16건 유지 (`llm-bench-2026-10-26.md` P1 절) | 완료 2026-10-26 | #4 |
| P2 | `feat/own-ingest` | 사내 자료 적재: 엑셀 1,119건·공시 요약문 121건, precheck 예시 3건 (PR 본문) | 완료 2026-10-26 | #5 |
| P3 | `feat/differentiation` | 기능 2 차별화 제안: 실례 2건(미채택 재제안 2건·완료 근접 4건, 폐기 0) | 완료 2026-10-26 | #6 |
| P4 | `feat/external-apis` | 전수 점검 표(`external-apis.md`), KIPRIS 어댑터, record_tag 진단, ScienceON MAC 안내 | 완료 2026-10-26 | #7 |
| P5 | `feat/review-scoring` | 심사 기준 4개 채점·2점 이하 의견 연결·수치 정책(알림 유지 + 검토 지적 + render_check 맨 위)·양식 밖 산출물 결정 | 완료 2026-10-26 | #8 |
| P6 | `chore/ops` | `com.rra.ingest.plist`·`--skip-unavailable`, plist·백업 7벌 테스트, `deploy/README` 설치 순서, `deploy-exposure.md` 비교 | 완료 2026-10-26 | #9 |
| P7 | — | 이슈 등록만 | 대기 | — |
