# 개발 연표 (2026-09-08 ~ 2026-10-27)

근거: `git log`(커밋 107건), GitHub PR #1~#19·이슈 #2·#10~#14, `docs/architecture.md §10`, `docs/status.md`,
`docs/llm-bench-2026-10-26.md`, `docs/external-apis.md`. 저장소 밖에서 있었던 일(기획서·팀 구성·대화 결정)은
"(대화 기록 기준, 미검증)" 으로 표시한다. 수치 변화는 `metrics.md`.

커밋 수(날짜별): 09-08 6 · 09-18 11 · 09-21 5 · 10-13 6 · 10-23 10 · 10-26 69.

## 0. 배경 (대화 기록 기준, 미검증)

- 목적: 한국철도공사 철도연구원의 연구과제 제안서(「연구개발 규정 시행세칙」 별지 제2호서식, 개정 2024.02.19.) 작성 부담과
  중복 과제 위험을 줄이는 근거 기반 작성 지원 도구. "2026 한국철도 AI 거점 리더 양성과정" 팀 프로젝트(팀 "철도R&D 플러스").
  프로젝트명 "근거 기반 연구과제 제안서 작성 지원 Agent (Rail Research Assistant, RRA)".
- 저장소 안에서 확인되는 것: 양식 이름·개정일(`ac55782`, `config/templates/proposal_korail.rules.yaml`), 기획서 파일명
  (`docs/status.md` 머리, 최종 수정 2026-10-15), 팀원 이름은 저장소에 없다(개인정보라 기록하지 않는다).

## 1. 설계 (2026-09-08)

| 무엇 | 왜 | 결과 | 근거 |
|---|---|---|---|
| 헥사고날 구조(domain / application / adapters / entrypoints)와 보안 규칙 A~J 를 설계 문서 v4 로 확정 | 외부 자료·LLM 출력을 비신뢰로 다루고, 어댑터(SQLite·mlx·HWPX)를 바꿔 끼울 수 있어야 함 | `docs/architecture.md`, `CLAUDE.md`(계층 규칙·보안 규칙), import-linter 계약 | `609e2e4`, `aad374c` |
| Step 1 domain·ports·usecases·fakes | LLM·DB 없이 도는 테스트가 먼저 | `tests/fakes.py` 로 유스케이스 테스트 | `aad374c` |
| Step 2 SQLite 저장소(FTS5 + sqlite-vec, RRF 융합), 임베딩 어댑터, 보안 E(바인딩·토큰 인용) | 단일 Mac mini 에서 운영·백업이 가장 단순 | `adapters/persistence/`, `domain/rules/fusion.py` | `4c23b52` |
| Step 3 LLM 어댑터·프롬프트·MCP stdio·composition | 로컬 mlx-lm(OpenAI 호환)으로 작성, MCP 로 외부 에이전트에 제공 | `adapters/llm/`, `entrypoints/mcp/` | `981e295` |

## 2. 핵심 기능 (2026-09-18 ~ 09-21)

| 무엇 | 왜 | 결과 | 근거 |
|---|---|---|---|
| Step 4 OpenAlex 자료원·GuardedClient(허용 도메인)·ingest | 논문 근거 적재. 아웃바운드 HTTP 는 허용 도메인만(보안 C) | `rra ingest`, 20건 적재 | `f19b974` |
| Step 5 알리오 catalog·filedrop·샌드박스 파싱 | 공시 문서는 비신뢰 파일 → subprocess 격리·zip 상한·defusedxml(보안 B) | `adapters/sources/alio/`, `_sandbox.py` | `d305174`, 보강 `c3ac454` |
| Step 6 RunManager(재개 가능한 생성)·CLI generate/runs·MCP 쓰기 도구 | 섹션 단위 저장·재개, 생성 동시성 1(보안 G) | `application/services/run_manager.py` | `90f46bc` |
| 엄격한 LLM 출력 파서(JSON 만, 실패 사유), `<doc id>` 근거 정규화 | LLM 출력은 JSON 만 파싱하고 근거 id 는 검색 집합과 대조(보안 A) | `domain/rules/llm_output.py` | `fad5f91` |
| ScienceON·NTIS 어댑터, 기관 태그, `rra sources check`, fixture 녹화 도구 | 국내 R&D 과제 검색(키 대기) | `428ed2c` | |
| 제안서 섹션을 별지 제2호서식(2024.02.19.)에 맞춰 재구성 — 섹션 12개·선택형 확정 | 실제 양식 순서·칸에 맞춰야 렌더가 가능 | `ac55782`, architecture §4.1 | |

## 3. 화면·모델 전환 (2026-10-13)

| 무엇 | 왜 | 결과 | 근거 |
|---|---|---|---|
| Qwen2.5-3B → 7B 전환, 본문 속 자료 태그 조각 제거, 지어낸 수치 lint, grounding 관형형 예외 | 3B 가 JSON 형식을 지키지 못함(대화 기록 기준, 미검증 — 커밋 메시지 "7B 전환 보정" 으로 간접 확인) | `e5c59b5`, `ba3e600`, `3e9a89b` | |
| 유사과제 차단에 공유 키워드 조건 추가 | e5 코사인만으로는 무관한 한국어 문서도 0.80 을 넘어 거짓 양성 | `70dad36`, `domain/rules/keywords.py` | |
| Streamlit 화면(규칙 기반 Agent, 토큰 게이트, 워커 스레드 폴링) | 기획서 Ⅱ 흐름 시연. LLM 은 판단에 쓰지 않는다 | `9170790`, `entrypoints/ui/`, architecture §4.2 | |
| 12개 섹션 생성 실측 54초 | (대화 기록 기준, 미검증 — 저장소에 기록 없음. 10-26 벤치는 골든셋 1건 97초) | | |

## 4. 구조 검토·리팩터링·Step 8~10 (2026-10-23)

| 무엇 | 왜 | 결과 | 근거 |
|---|---|---|---|
| 구조 검토 6항목: 필수 슬롯 규칙 단일화, composition 분해(config_loader·diagnostics), `_Lazy` 제거, 포트 async 통일, TaskRunner 포트 | 진입점에 로직이 새고, 조립 지점이 설정까지 읽고 있었음. 마이크로서비스는 미채택(단일 장비·사용자 수 명) | `b20deb6`, `6b31f35`, `edac5f7`, `17b6e30`, `0bcac95`, architecture §4.3, ADR 0002 | |
| Step 8 HWPX 렌더러(XML escape + defusedxml 재파싱, 보안 F) | 양식 파일 출력 | `aa4be7c` | |
| Step 9 run_log 를 adapters/logging 으로, manifest 허용목록, `rra runs purge` | 로그·매니페스트에 비밀·본문 금지(보안 D·I) | `3dcb081` | |
| Step 10 REST API(FastAPI)·보안 미들웨어·`rra api`·launchd plist | 웹 프론트엔드·외부 연동 | `2b169f8` | |
| 사내 과제 압축본이 DRM 표식으로 보였으나 원본 폴더는 정상(878개) | (대화 기록 기준, 미검증) | lessons.md | |

## 5. 양식 연동·작성→검토 구조·DB 정비 (2026-10-26 오전)

| 무엇 | 왜 | 결과 | 근거 |
|---|---|---|---|
| 실물 양식 템플릿 모드 1~4: slots.yaml 영문 키·체크 칸 `( ○ )`·문장별 단락 복제·`tools/build_form_template.py`·render_check·줄 배치 캐시 제거 | 실제 hwpx 양식을 그대로 채워야 함. 연구과제명 길이 제한 없음 | `aa7b977`, `df3de98`, `aee3163`, `6fea01f` | |
| [1] clean_sentence·foreign_script lint, [2] migration 003·004(valid_until·visibility·ingested_at)·`rra reindex`·`rra db backup`, [3] 저장소 계약 테스트 | 중국어 조각·만료 문서·외부 전송 범위 | `463139e`, `42c2eaf`, `42d071a` | |
| [4] Gemini 4 Argon 연결(providers 표, 단계별 provider, 401 비재시도) | 외부 강한 모델은 검토에만 — 로컬 작성 + 외부 검토 2중화 | `9cb311f`, ADR 0007 | |
| [5] 검토 흐름(review_flow 상태 전이·review_draft·버전·revert·finalize·reopen) [6] 세션·CSRF·SSE·problem+json·정적 SPA·가짜 모드 [7] Streamlit 최종 마무리 | 프론트엔드가 쓸 API 와 검토 루프 | `4b22913`, `b979fd0`, `71d860c`, `dec519e`, `67baf29` | |
| 웹은 React SPA 로 결정 | (대화 기록 기준, 미검증 — `dec519e` 의 정적 SPA 서빙·`web/dist` 로 간접 확인) | ADR 0008 | |

## 6. 로컬 모델 비교 (2026-10-26, PR #1)

| 무엇 | 왜 | 결과 | 근거 |
|---|---|---|---|
| model_profiles(qwen·midm·ax_light), `rra llm-bench`, 골든셋 3건, 형식 보완(교정 재요청·선택형 예시) | 한국어 특화 모델이 더 나은지 확인 | JSON (b) Qwen 93.1→96.5% / Mi:dm 3.5% / A.X 79.3%, 근거 폐기 Qwen 0 / A.X 7 → **Qwen 유지**. EXAONE 4.5(비상업 라이선스·메모리)·Solar Open(메모리)은 후보에서 제외(대화 기록 기준, 미검증) | `3a98056`~`3f208c8`, `docs/llm-bench-2026-10-26.md`, ADR 0006 | |

## 7. 사내 자료·P0~P7 (2026-10-26, PR #3~#9·#15·#16)

| 단계 | 무엇 | 결과 | PR |
|---|---|---|---|
| P0 | `docs/status.md` 현황표, Gemini 모델 목록, 부서 추가 | | #3 |
| P1 | 생성 근거 관련도 하한(코사인 ≥ 0.79, 한글 청크는 키워드 ≥ 1) | 03 무관 입력 인용 0건, 01 관련 논문 16건 유지 | #4 |
| P2 | 사내 자료 적재(엑셀 1,119건·공시용 요약문 121건, 샌드박스 hwp·xlsx·xls) | own 1,119 / alio 115+5 | #5 |
| P3 | 기능 2 차별화 제안(후보 = 차단 또는 임계치×0.9, LLM 항목 검증) | 실례 2건, 폐기 0 | #6 |
| P4 | 외부 자료원 전수 점검, KIPRIS 어댑터, record_tag 진단 | `docs/external-apis.md` | #7 |
| P5 | Argon 검토 4개 기준 채점·2점 이하 의견 연결·수치 정책 | 실측 3/2/2/3 (run 17d5e269) | #8 |
| P6 | 야간 적재 plist·백업 회전 테스트·설치 순서·공개 방식 비교 | | #9 |
| P7 | 이슈 #10~#14 등록 | | 이슈 |
| A | own 티어 전부(세부 institute/company)·visibility public 정정·generic_terms·차별화 자동 실행 규칙 | 사내 과제 목록·공시자료는 공개 자료로 정정 | #15 |
| D | status.md 병합 결과 | | #16 |

## 8. 협업·자동화 (2026-10-26, PR #17)

GitHub Actions CI(backend: uv·pytest·lint-imports·ruff / web: `web/` 있을 때만 / detect), CODEOWNERS, PR 템플릿, CONTRIBUTING.
샌드박스 자식의 RLIMIT_AS 를 제거(리눅스에서 pymupdf import 실패) — `1d5fa87`. 이후 PR 은 CI 통과 뒤 자동 병합.

## 9. 근거 확충 (2026-10-26, PR #18·#19)

OpenAlex 철도 분야 영문 질의 13개(초록 있음·10년·질의당 200) → 2,482건(청크 3,465, 78초). cursor 페이징이 API 키를
요구(401)해 page 페이징으로. 적재 뒤 한국어 질의가 사내 기록만 앞세워 논문이 근거 0건 → 넓은 검색(k×4)·부족 자료원
재검색(`hybrid_search sources` 필터)·출처별 최소 보장 6(`balance_sources`, 초과 시 라운드 로빈). 골든셋 01 근거 구성
alio 15/own 5/openalex 0 → alio 9/own 6/openalex 6, 같은 입력 Argon 점수 3/2/2/3 → 3/2/3/3(run 간 편차 안). ADR 0010.

## 10. 2026-10-27 (야간 작업, 이 문서 작성 시점)

흐름 확정: ① 아이디어 입력 → ② 유사과제 확인·과제 추천 → ③ 초안 생성(로컬 작성 + Argon 1차 검토, v1→v2) → ④ 직접 수정·보완
(버전 관리) → ⑤ Argon 최종 검토 1회 → ⑥ 최종 마무리. "재검토 무제한" 흐름을 대체(ADR 0011, 대화 기록 기준).
차별화 과제 추천(0~5건, ADR 0012), 초안 품질 강화 8가지(효과가 확인된 것만 기본 켬, ADR 0013), 웹 프론트엔드.
진행 상황은 `docs/overnight-2026-10-27.md`.

| 날짜 | 무엇 | 왜 | PR | 핵심 수치 |
|---|---|---|---|---|
| 2026-10-27 | 2중 작성·직접 수정·최종 검토·버전 관리 [E] — 흐름 ③~⑥ 상태 재정의, 1차 검토 자동 반영 v2(Argon 보완)+문장 메모, 문장·섹션 편집(근거 이어받기)·임시 저장·복원·비교·동시 편집 보호, 최종 검토 1회(stale·다시 받기)·마무리 조건, REST/CLI/MCP/Streamlit, pipeline.yaml | 재검토 무제한 흐름의 호출 비용·책임 불명확(ADR 0011) | #22 | 테스트 1,239 |
| 2026-10-27 | 차별화 과제 추천 [R] — 유사과제 확인 직후 기존 과제와 다른 과제 0~5건(검증·자기 중복 검사·미리보기 반영), CLI·REST·MCP·Streamlit, run 복사·manifest | 차단만 알리면 제안자가 방향을 바꿀 재료가 없음(ADR 0012) | #21 | 골든셋 01·02·03 실측은 overnight 기록·ADR 0012 |
| 2026-10-27 | 개발 경과 기록 `docs/history/`(연표·수치·ADR 14건·교훈·구조도 7장·그래프 5장·Streamlit 화면 캡처 5장), `tools/history_charts.py`, CONTRIBUTING·PR 템플릿에 경과 기록 규칙 | 발표 자료 원천을 저장소 안에 두고 PR 마다 갱신하게 | #20 | 커밋 107, 테스트 1,178, 자료원 3,721건 |
