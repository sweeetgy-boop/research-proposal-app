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
| 2026-10-27 | 웹 프론트엔드 [W] — Vite+React+TS SPA 11화면(①~⑥ 흐름·run 목록·검색·자료원), 디자인 토큰·라이트/다크, DraftEditor(문장·섹션 편집·자동 임시 저장·409 충돌), 버전 글자 단위 diff·복원, 최종 검토·마무리(HWPX 내려받기, 제안자 정보 미저장), SSE 진행, 가짜 백엔드 e2e·녹화·화면 캡처, Lighthouse·axe | Streamlit 은 시연용이라 편집·비교·팝업·접근성 목표를 못 맞춤(ADR 0008·0015) | #23 | 번들 초기 JS 110.6 KB gzip(전체 ≈167 KB)·Lighthouse 100/100/100·CLS 0·axe 위반 0(7 화면)·vitest 33·e2e 8 |
| 2026-10-27 | ScienceON 실연결 [B] — 토큰·검색 실호출 ok(ARTI 1,858·REPORT 370·PATENT 911), fixture 3종(이름 제거)·FIELDS 확정·skip 3건 해제, GuardedClient Accept 헤더(406 수정)·refresh_token·XML 토큰 오류, PATENT target·per_query_limit·질의 13개, 적재 명령·예산(40회) 준비, 특허 기본 자료원 = ScienceON(ADR 0015) | 키 투입 뒤 첫 실응답으로 가정(키 길이·파라미터 이름·Accept)이 틀린 곳을 확정하려고 | (레인 B, PR 미생성) | .env 두 값 뒤바뀜 발견(원본 미수정), 질의 13개 총건수 조사 58회 |
| 2026-10-27 | 사용자 관점 검토 반영 [U1~U8] — 근거 원문 바로보기·Argon 적합성(support)·제안자 근거 판단(approve/replace/exclude → 버전), 간편 입력(자유 문장 → 4칸 + 보완 질문), 섹션별 AI 다시 쓰기(제안자 문장 보존)·체크리스트 보완 질문, 차별성 비교표, 선행연구 브리핑(우선 근거 → snapshot.priority_ids), 추진일정·성과지표 지시 + 일정 초과 경고, 제출 전 점검(target 포함), usage.json·만족도·`rra usage report`. `config/usability.yaml` 로 항목별 켜고 끔. REST 13경로·CLI 5명령 | 외부 사용성 검토 의견(10.15 기획서 대상) — 근거를 눈으로 확인하고, 입력 부담을 줄이고, 제출 전에 빠진 것을 한눈에 보게(ADR 0017) | feat/usability | 테스트 1,292(+53) |
| 2026-10-27 | 웹 이미지 판독 [P3] — 장식 거르기(크기·이름·alt·반복 해시), 순서·예산 계획(dry-run), macOS Vision OCR(격리 자식), Argon 이미지 입력 판독(JSON 만), 해시 캐시(실패 포함)·기록, 수치 OCR 대조("판독 확인 필요"), 개인정보 제거, image_vision 문서 적재 준비, 측정 harness, 공용 Gemini 제한기(동시 4·분당 60·429 백오프), `rra vision read/sample/ingest` | 경영목표·전략·통계가 이미지라 본문 크롤만으로는 정책 근거가 비고, LLM 판독 수치는 OCR 교집합만 근거로(ADR 0018) | #28 | 새 테스트 83·계약 8 유지, 실측은 통합 세션(`docs/ocr-sample/summary.md`) |
| 2026-10-27 | 공사 홈페이지(info.korail.com) 스냅샷 크롤러·`korail_web` 적재(policy·korail_news), 국토교통부 정책자료 `molit` 적재(판 추적), 전략체계 초안(5 방향·15 과제, basis text)·`strategy.yaml` 스위치·`rra strategy draft/promote`, 정책 근거 추천(`POST /v1/ideas/policy-suggestions`, `rra policy-suggest --pick`), 정책·보도자료는 유사과제 판정 제외 | 정책적 중요도·경영전략 정합성의 근거를 공사·정부 공개 자료에서 — 비어 있던 전략체계 목록을 문서 근거로 채우고, 보도자료·정책 문서가 유사과제 판정을 오염하지 않게 | #29 | 메뉴 50(보도자료 6,380건 중 최근 5년), 스냅샷 229항목·207파일·654MB(진행 중), 테스트 1,300 통과·계약 8 |
| 2026-10-27 | 웹 U9 [W] — U1~U8 화면: 간편 입력(네 칸 미리보기·보완 질문·503 대체)·정책 근거 추천(버튼 호출, 미개방 안내)·차별성 비교표·선행연구 브리핑(`/new/brief`, 우선 근거)·근거 패널(`<dialog>`, 승인/교체/제외 → 버전, 409)·섹션 AI 다시 쓰기·보완 질문·제출 전 점검(`/runs/:id/submit-check`, target 이동·사용 기록·만족도), stepper 연결, 가짜 LLM structure/brief 분기 | 사용자 검토 U1~U8 이 REST 까지만 있어 화면이 없었음; 간편 입력을 기본으로 둬 네 칸 부담을 줄임 | #30 | Vitest 50·Playwright 10·axe 0(새 8 화면)·초기 JS 111.6 KB gzip(전체 ≈184 KB)·Lighthouse /login 100/100/100 |
| 2026-10-27 | 초안 품질 강화 8가지 [Q] — Q1 보강 질문·Q2 설계도·Q3 섹션별 검색·Q4 본보기·Q5 Argon 보완 작성·Q6 규칙 검사·Q7 두 후보·Q8 reranker 를 `config/pipeline.yaml` 로 켜고 끄게 만들고, `rra eval` 로 골든셋 측정(5단계, 결함 4건 수정) 뒤 효과 있는 것만 기본 켬(section_search·additions·reranker). 근거 구성 규칙 `config/retrieval_mix.yaml`, 골든셋 10건, POST /v1/runs acknowledged 서버 게이트, 초안 문장 sentence_id, ScienceON 적재 내성 | 측정 없이 켜면 7B 가 JSON 을 못 지켜 invalid 가 늘고 시간만 는다(ADR 0013) | #31 | 테스트 1,494, 구성 16개 측정, Gemini 38회, precheck 적중 9/10·순위 1.7→1.4 |
| 2026-10-27 | 측정에서 드러난 결함 수정 [5] — 로컬 모델 JSON 응답 앞뒤의 짧은 찌꺼기(`]}` 꼬리·짧은 머리말)를 살리는 관용 파싱(lenient 표시, 긴 설명문은 그대로 실패) | Q9 재측정(final·baseline3·post-scienceon)에서 골든셋 01 이 섹션 하나의 JSON 꼬리 때문에 invalid — 재요청까지 같은 꼴 | #32 | 재현 raw 541자 `[…]}` |
| 2026-10-27 | 병렬 검사 — pytest-xdist(-n auto), CI 를 backend-unit/api·web-check/e2e 로 나누고 backend·web 모음 job, 무거운 작업 락(`tools/with_heavy_lock.py`), 조각 파일 규칙(CONTRIBUTING) | 레인 4개가 동시에 진행되어 공유 파일 충돌·검사 시간을 줄여야 함 | #24 | 1,239 테스트 7.5s(-n auto) |
| 2026-10-27 | CI web-e2e 백엔드 경로 수정(저장소 루트 기준) | 첫 e2e job 이 exit 127 | #26 | — |
| 2026-10-27 | 발표 자료 원천 묶음 `docs/presentation-kit/`(구성안 15장·한 장 요약·시연 대본·예상 질문·한계) [6] | 발표 준비를 저장소 안 원천에서 | #33 | — |
