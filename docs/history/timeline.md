# 개발 연표 (2026-09-08 ~ 2026-10-29)

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
| 2026-10-27 | [P3] 첨부 속 내장 이미지 — HWPX·HWP(BinData)·PDF·PPTX(media)·XLSX 내장 이미지를 격리 워커로 꺼내 같은 해시는 하나로, 로고·장식 거르기 공용, 원본 위치(첨부 파일명·쪽·슬라이드) 메타, 순서 그룹 brochure 추가, `rra vision extract` | 크롤 스냅샷 1,396 첨부에 비해 페이지 이미지는 196장뿐 — 전략체계도·통계 표는 첨부 안에 있음 | #34 | 추출 결과·판독 장수는 overnight 기록 |
| 2026-10-27 | NTIS 실연결 [N] — 4개 서비스 실호출(과제·성과·연구보고서·연관콘텐츠) 모두 HTTP 200 `<error>접근 허용 IP가 아닙니다.</error>`(키 수락, 서버 IP 미등록) → 공개 매뉴얼로 형식 확정(record_tag HIT, FIELDS), 합성 fixture 5종·skip 2건 해제, `<error>` 본문을 ok 로 올리던 결함 수정, 연구보고서 소스(`ntis_reports`, report), 성과·연관콘텐츠 유스케이스 + `POST /v1/precheck/ntis-outcomes` + 파일 캐시, 유사과제 티어 `national_rnd`(0.80, "국가R&D 과제"), 보고서 교차 중복 규칙(과제번호+제목+연도), 질의 13개·적재 명령(26회/소스) 준비 | 키 승인 뒤 첫 실호출로 IP·형식·결함을 확정하고 ② 화면용 성과·추천을 붙이려고 | (레인 N, PR 미생성) | 사람: 서버 IP 를 현재 공인 IP 로 변경 뒤 통합 세션 재시도 |
| 2026-10-27 | 표 구조화 table_facts(P2-8): 스냅샷 xlsx·xls 시트·pdf 쪽·이미지 판독 structure → (항목·연도·단위·값) 사실, migration 005, `rra facts extract|search`, `GET /v1/facts`, 수치 lint 가 인용 문서의 표 칸을 근거로 인정(`RetrievalSnapshot.facts`); 용어 후보 추출(P2-9) `rra terms candidates` → `config/*.candidates.yaml`(자동 반영 없음) | 표의 숫자는 청크에 흩어져 "지어낸 수치" 로 보이고, 용어사전은 손으로만 자랐다 — 보수적 규칙(못 읽으면 내지 않음) + 사람 승인(ADR 0022) | #36 | scratch 측정: 표 2,094장 → 사실 48,253건/문서 32건(59초), pdf 사실 2건, 테스트 1,572 통과·계약 8 |
| 2026-10-27 | [P2] 보류 자료원 처리 — 나라장터 발주 용역 공고 `g2b`(키 대기, "발주 용역" 티어·"용역으로 진행 중/예정"), 감사원 감사결과 `bai`(Playwright 공개 화면 조작 스냅샷, 전문 PDF·HWP), 기재부 경영평가 결과 `mofe`, 공공데이터포털 철도 안전·수송 통계 파일 `datago`(키 없음), 판 추적 모호 처리(P2-10), DocType statistics·audit·procurement | 안전·수송 수치, 감사·평가 지적, 발주 중인 용역을 근거·판정에 쓸 수 있게 — ebid 는 로그인·POST 라 공개 API 로, 키 필요 통계는 키 없는 파일데이터로 대체 | #37 | 감사원 "철도" 55항목·파일 40개(pdf 20·hwp 20)·82.5MB, 데이터셋 16개, 테스트 1,519 통과·계약 8 |
| 2026-10-27 | 국토교통 분야 정부 R&D 공고·RFP 자료원 `rnd_notice`(P2-7): KAIA 사업공고(GET·PDF 공고문)·IRIS 사업공고(국토교통부 필터, 공개 POST 검색 폼·인라인 공고문) 스냅샷 크롤러 `rra crawl rnd-notice`, 중복 합침(제목+기관+공고일 키), 마감일 → `valid_until`, 담당자 개인정보 제거, `rra ingest --source rnd_notice`, 공고문 대조 `rra notices match`·`POST /v1/ideas/notices`(접수 중 상위 3건, LLM 없음), 정책 근거 추천 후보 추가, 유사과제 판정 제외. NTIS 는 robots 전면 금지로 보류 | 접수 중인 정부 공고를 입력과 대조해 보여 주고(#13 선행), 공고문을 정책 근거 후보로 — 공고가 유사과제·기술 근거를 오염하지 않게 | #38 | KAIA 1,224건·IRIS 국토교통부 945건(전 기간) 탐색, 스냅샷 공고 99건(KAIA 83 + IRIS 16, 두 사이트에 함께 실린 63건은 한 문서로 합침), 첨부 229개 808MB(KAIA pdf·hwp; IRIS 첨부 40건은 이름만), 등록일 2024-10-30~2026-08-20 (완료, 2년 범위), 테스트 1,515 통과(+20)·계약 8 |
| 2026-10-27 | 웹 ② NTIS 과제 카드 [W] — 유사과제 알림에 `national_rnd`(국가R&D 과제) 티어가 있으면 `POST /v1/precheck/ntis-outcomes` 를 같은 본문으로 1회 호출해 과제 카드 "주요 성과 (참고용)"(논문·특허 종류·제목·연도·학술지/기관, 5건 초과는 더 보기)과 "NTIS 추천"(점수·순위·외부 링크 `rel="noopener noreferrer"`, 외부 링크·미검증 표시, notice 캡션) 을 그린다. 503·오류는 "NTIS 성과 조회 불가" 한 줄만(흐름 차단 없음). 알림 표·비교표의 티어 라벨은 `lib/tiers.ts` 로 보충. 가짜 모드: `adapters/fake/ntis.py`(ScriptedNtisInsights) + 청크 없는 NTIS 시드 문서(`ntis:fake-1`, precheck 에만 잡힘) | 레인 N(PR #35) 의 성과검색·연관콘텐츠 응답을 ② 화면에서 보이게 — 근거가 아닌 참고 정보임을 라벨로 분명히 | feat/web-ntis | Vitest 56(+5)·Playwright 11(+1)·backend 1,530 통과·계약 8, 캡처 `docs/history/screens/2026-10-27-web-ntis-01-precheck.png` |
| 2026-10-27 | 공사 홈페이지 첨부 xlsx·xls 를 본문으로 적재 — 워커의 시트 구조를 `[시트]` + " \| " 행 텍스트로 바꿔 `ExtractResult` 에 넣는다(`korail_web/_sheets.py`) | [P] 적재에서 ValidationError 61건(xlsx 59·xls 2)이 전부 시트 구조만 돌아온 스프레드시트 — 광역수송 통계 등 표 문서가 검색 집합에 없었다(레인 F 발견) | #40 | 재적재 뒤 건수는 overnight 기록 |
| 2026-10-27 | reranker 모델 호출 직렬화 — `CrossEncoderReranker._scores` 에 threading.Lock(적재·추론) | 웹 e2e 에서 `/precheck/comparison` 과 `/precheck/ntis-outcomes` 가 동시에 reranker 를 돌리자 Metal 단언으로 API 프로세스가 죽음(웹 레인 발견, 보안 G 생성 동시성 1 과 같은 취지) | #41 | 가짜 모델로 동시 4요청 겹침 0 검증 |
| 2026-10-27 | Argon 판독 전 OCR 결과로 사진 거르기 — `domain/rules/photo_filter`(글자 < 20·숫자/도형 기호 없음·줄 ≤ 2, 전략·ESG·통계 그룹 제외), 판독 계획 `photos`, status photo(적재 안 함, alt·캡션·제목만 vision_log 메타), `config/vision.yaml photo` | 첨부 내장 이미지로 판독 대상이 4,003장이 되자 사진이 Argon 상한 2,000 을 잡아먹음 — OCR 표본 2,062장에서 글자 0 이 46% | #43 | 기준값은 표본 분포로, 사진 표본 30장은 docs/ocr-sample/excluded/ |
| 2026-10-27 | 데이터 위치 고정 — `RRA_DATA_DIR`·`config_loader.resolve_data_dir`(원 저장소 = git common dir 의 부모)/`data_path`/`_DATA_LOCATIONS` 표, composition 이 DB·스냅샷·캐시·inbox·eval·bench·backups 를 데이터 폴더 절대 경로로 조립, 어댑터 cwd 기준 `data/` 기본값 제거, worktree 보호·정적 테스트, CONTRIBUTING "데이터 위치" | 합쳐진 브랜치의 worktree 를 지우면서 그 안 `data/` 의 미커밋 크롤 스냅샷이 사라짐 — 레인 worktree 가 데이터를 갖지 않게 | #42 | 테스트 +15(1,670 통과), 계약 8 유지 |
| 2026-10-27 | 이미지 판독 병렬 처리 — `read_images` 에 asyncio.Semaphore(`config/vision.yaml concurrency: 4`), 결과 순서 유지, 공용 Gemini 제한기(동시 4·분당 60) 안에서 순차 분당 8장 → 29장 | 첨부 내장 이미지로 Argon 대상이 2,000장이 되자 순차 판독이 4시간 넘게 걸림 | #44 | 실측 분당 29장(16:20~17:40, 2,000장), 실패 166(8%) |
| 2026-10-27 | 브라우저 접속 준비(레인 W) — `config/api.yaml`(`public_origin`·`trust_cf_connecting_ip`, `config_loader.api_config`), 세션 쿠키 Secure(공개 Host)·Origin 검사(쿠키 인증 상태 변경·로그인), `adapters/security/client_ip.py`(`client_ip`·`access_user_hash`, CF-Connecting-IP 는 peer 127.0.0.1 일 때만, 이메일은 sha256 앞 12자), 거부 로그 `rra.api.auth`, `deploy/cloudflared/config.example.yml`·`com.rra.tunnel.plist`, deploy-exposure §5(결정·막힌 점·절차·Tailscale 대체), ADR 0024 | 동료가 설치 없이 브라우저로 `https://rra.ai-edu-lab.co.kr` 접속(Cloudflare Access 이메일 OTP + 앱 로그인 이중 인증). DNS 가 Gabia·cloudflared 미설치라 터널은 만들지 않고 코드·절차만 | #45 | 테스트 +18(1,696 통과), 계약 8 유지, 터널 미기동·Access 미확인 |
| 2026-10-27 | 자료원 IP 확인 [I] — `sources.yaml` 자료원별 `ip_restricted`·`registered_ips`(NTIS 59.0.166.199·59.0.251.250), `rra sources check` 가 공인 IP(api.ipify.org, allowed_domains) 를 1회 조회해 대조하고 "현재 IP <값> 가 <자료원> 등록 IP 에 없습니다. 활용신청에 추가하세요" 안내, IP 거부 응답(`NtisIpBlocked` ⊂ `SourceIpBlocked`)은 그 자료원만 건너뜀(ingest `--skip-unavailable`·사전 점검 NTIS 성과) + 로그·웹 자료원 상태(`GET /v1/sources/status` `notice`, `/sources` 경고)·`rra sources status` 에 같은 안내(`cache/source_availability.json`), `ntis_insights` 연결 확인 추가 | NTIS 가 IP 로 막히는 상황을 설정·진단·건너뜀으로 다루고 운영 전 공인 IP 고정 과제를 드러내려고 | #46 | 실호출: ScienceON ok, NTIS 4개 서비스 IP 거부(현재 IP 59.0.251.250 는 등록 목록에 있음 → 활용신청 반영 확인) |
| 2026-10-27 | 로그인 방식 변경(레인 A) — 직원은 사번(HMAC-SHA256, `data/auth/`·700/600·원문 없음), 그 외는 공용 아이디·비밀번호(scrypt), 관리 토큰 유지(관리자는 모든 run). run 소유자 가명 ID 격리(남의 run 404), 공용 계정 internal 제외(`PublicOnlyRepository`·`generate_public`), 사용자별 일일 상한(공용 10·직원 20), 잠금(계정 5회·IP 20회/10분·전체 50회 지연, 문구 하나), 외부 검토 LLM 일일 300회 상한(소진 시 검토 없이 진행·알림), `rra auth` CLI(getpass), 웹 로그인 두 탭 + 상단 종류 라벨, e2e 두 경로 | 시범 사용자를 사번·공용 계정으로 구분하면서 저장소(공개)에 사번·비밀번호·해시를 두지 않고, run·자료 범위·비용을 사용자별로 보호 | #48 | 테스트 +26(1,723 통과), 계약 8 유지, Vitest 57·Playwright 13, axe 0 |
| 2026-10-27 | DB migration 006 — `documents.text_basis` CHECK 에 `image_vision` 추가(표 재생성: FK OFF → 새 표 → INSERT SELECT rowid 보존 → DROP → RENAME → 인덱스 5개 복원 → FK ON). 005 까지의 옛 DB 로 행·청크·FTS·hybrid_search 보존 + image_vision upsert + 새 DB 001→006 테스트 3건 | `rra vision ingest` 가 운영 DB(user_version 5, 8,406건)에서 `CHECK constraint failed: text_basis IN ('full_text','summary','abstract')` 로 실패 — 도메인 `TextBasis` 만 넓히고 002 의 CHECK 는 그대로였고, 테스트는 새 DB 에서 image_vision 을 upsert 한 적이 없었다 | #47 | 운영 DB 사본 검증: 행·rowid 합·청크·orgs 동일, integrity ok, FK 검사 0건, 0.15초. 저장소 open 시 자동 적용 |
| 2026-10-27 | NTIS 실응답 확정 [R-NTIS](#50) — 서버 IP 등록 뒤 4개 서비스 실호출(총 17회: 녹화 12·sources check 5). `sources check` 의 `XmlResponseError (ParseError)` 원인 = Accept 에 application/json 이 있으면 서버가 XML 전체를 JSON 문자열로 감싸 보냄(content-type application/json) → `ntis/client.py unwrap_json_string`(한글 오류 문구 때문에 json Accept 유지); 연구보고서 DocUrl 의 맨 `&` → `_xml.repair_bare_ampersands`. 합성 fixture 5종 삭제 → 실응답 6종(과제 `철도 궤도`·`전차선` 10건씩, 보고서 10건, 성과 논문 10·특허 2, 연관 10; 사람 이름 NAME-REMOVED). FIELDS 확정(과제 매뉴얼과 동일 + 사업명·전문기관·ScienceClass 중복 제거, 보고서 SpecializedAgency·AgencyDetailProjectNumber, 성과 과제번호 `ProjectID`·DOI·RegistType, 연관 JSON 안의 JSON + NaN). probe 에 `hits`·`record_tag_matches`(자동 탐지는 NAVIGATIONENTRY 를 고른다), `ntis_reports` 힌트가 ntis 설정을 보도록, `build_ntis_source` 에 per_query_limit 전달(없으면 질의당 11페이지 → 예산 초과), 녹화 도구 `ntis_insights`·`--label`. `rra sources check --source ntis,ntis_reports,ntis_insights` 셋 다 ok(1,087/202/성과 12·연관 10) | 실응답으로 매핑을 확정하고 적재 전 파서 결함을 없애려고 | PR #(본문) | 통합 세션: `rra ingest --source ntis --limit 2000`·`ntis_reports --limit 1500` 뒤 골든셋 임계치(0.80) 확인 |
| 2026-10-27 | NTIS 연구보고서 파싱 수정 2건 — 정의되지 않은 명명 엔티티(`R&DB;`)와 공백 앞의 맨 `<` 를 이스케이프(`_xml._BARE_AMP`·`_BARE_LT`) | `rra ingest --source ntis_reports` 가 0건(100건 응답 3쪽에서 ParseError) | #51 #53 | 테스트 +2(1,772), 적재는 병합 뒤 |
| 2026-10-27 | 시범 운영 준비 [D] — `max_queued_runs` 6(사용자별), 동료 안내 `docs/pilot-guide.md`, launchd 4종 등록·점검, 시범 흐름 1회 실측 227초 | 2026-10-28 3명 시범 | #52 | 외부 주소는 DNS(Gabia) 때문에 미기동, 사번·공용 계정은 사람 등록 |
| 2026-10-28 | 공용 계정 비밀번호 최소 길이 설정화 — `auth.yaml guest.min_password_length`(기본 8, 시범 한정 4), `auth_policy.valid_password` | 시범 지시 | #54 | 시범 뒤 8 로 복원 |
| 2026-10-28 | [F1] 빈 초안 금지 — 일부 섹션의 로컬 작성이 실패해도 run 은 drafted(실패 섹션은 빈칸 + `failed_sections` 목록·사유, `generation_failed` 경고), 전부 실패일 때만 invalid. REST·render/submit-check·웹 "이 섹션 다시 생성" 버튼(U3 재사용)·Streamlit 목록 | 저녁 골든셋 측정 01·02·06·10 두 번 모두 invalid(빈 초안) — 원인 표: JSON 깨짐 11·펜스 2·**빈 문장 목록이 ok 로 통과 10**(02·05·10), 코퍼스 증가로 섹션 [자료] 글자 2.1× | #55 | 내일 시범에 빈 초안을 주지 않기 위한 안전한 변경 먼저 |
| 2026-10-28 | [F1] 원인 수정·대체 작성 — 필수 섹션 빈 목록은 실패로 보고 교정 재요청, 섹션 [자료] 상한(청크 500자·기본 집합 10청크), finish_reason=length 집계, 로컬 2회 실패 섹션만 Gemini 대체 작성(`compose.fallback: gemini`, 검토와 같은 전송 범위·일일 예산·보여 준 청크 기준 근거 검증, manifest `fallback_sections`, 웹 "대체 작성" 배지) | 원인 표: 빈 목록 ok 통과 10·JSON 깨짐 11·청크 길이 2.1× | #57 | 골든셋 10건 재측정 결과는 docs/eval-2026-10-28.md |
| 2026-10-28 | [F2] 유사과제 판정 후보 = 과제형 자료원만(own·alio·NTIS 과제·g2b, `overlap.yaml candidates`), 논문·보고서·특허는 `related_research`(관련 연구, 참고)로 분리 — `find_similar(sources=)` sqlite-vec 사전 필터, 자료원별 풀 7/28, `judge()` reranker 순서 유지, REST `related_research[]`, 웹 ② "관련 연구" 목록 | ScienceON 2,045·NTIS 3,084 적재 뒤 골든셋 precheck 적중 9/10 → 6/10 (논문 0.886~0.903 이 사내 기록 0.84~0.88 을 밀어냄, NTIS 과제 2,000건이 상위 80 을 메움) | #56 | 적중 5/10 → 9/10, 지연 on 1.84~2.09s(중앙값 2.06s), Gemini 0회 (docs/eval-2026-10-28-precheck.md, ADR 0028) |
| 2026-10-28 | [A2] 사번 일괄 등록 `rra auth staff import --file <xlsx|csv> [--sheet] [--column] [--pad N] [--replace] [--dry-run]` — 샌드박스 자식이 "사번" 열만 반환(`adapters/auth/_roster_worker`·`RosterReader`, 포트 `RosterReaderPort`), 정규화·검증·중복 합침 `domain/rules/staff_roster`(공백·하이픈·숫자 셀·0 채움), `AuthStorePort.import_staff`(HMAC 만, replace/dry_run), 출력은 개수·오류 행 번호·길이별 분포뿐, 원본 미복사. 로그인 입력도 같은 정규화 | 시범 직원 전원을 한 명씩 getpass 로 넣기 어려움, 엑셀 숫자 셀의 앞자리 0 빠짐 | #TBD | 테스트 +12(가짜 사번 xlsx·csv, 출력·로그에 값 없음, dry-run 무저장, replace, 로그인 일치), API 재시작 불필요(로그인마다 파일 읽음), `docs/pilot-guide.md` §6 |
| 2026-10-28 | [D2] 시범 배포 규칙 — `tools/deploy.sh`(main 최신 확인 → web 변경 시 빌드 → `rra runs active` 생성 중 run 확인·`--wait`/`--force` → `data/deploy/version.json` → `launchctl kickstart -k com.rra.api` → healthz·/login·외부 주소 확인 → `docs/history/deploys/<시각>.md`), 반영 대기 목록 `pending.md`(합쳐도 자동 재시작 없음, 보안·접속 오류는 즉시), `GET /healthz version` + 웹 하단 "버전 · 배포" 표시 | 시범 중 동료가 생성하는 도중 재시작되면 run 이 끊기고, 어떤 버전을 쓰는지 알 수 없음 | #62 | 테스트 +9(버전 읽기 2·healthz 1·runs active 1·스크립트 3·web 3) |
| 2026-10-28 | [G] 제안서 그림(인포그래픽) — 명세(JSON, 본문·입력·근거·table_facts 글자만) → 템플릿 SVG 밑그림 6종 → Nano Banana Pro(`gemini-3-pro-image`) 1회 채택, 실패면 기본 그림. 자동 검증 대신 제안자 확인(카드 배지·제출 전 점검·마무리 확인 창), 말로 고치기·글자 고치기·기본 그림으로·빼기·추가(새 버전·복원·비교), 1차 검토 불일치 지적, HWPX 본문 뒤 삽입(+별첨) | 글만 있는 제안서에 개념도·체계도·일정표 등을 넣되 지어낸 글자·수치·외부 전송을 막기 | #63 | 실측 6/6·장당 29~39초·말로 고치기 27~28초(글자 변형 2~3곳 → 확인 절차), 테스트 +48·vitest +11·e2e +2 |
| 2026-10-28 | [2] 그림 [말로 고치기] = 명세 변경(Argon, 실패면 로컬; 생성과 같은 검사) → 밑그림 → Nano Banana 새로 그림, 현재 그림은 보내지 않는다(편집 호출 없음). 모양만 바꾸는 요청은 명세 그대로 밑그림 + 모양 요청. 카드 "바뀐 내용"(`Figure.last_change`), 초안 그림 명세도 Argon 먼저(`Figure.spec_model`) | 오전 실측: 현재 그림을 다시 그리는 편집 호출이 글자를 바꿈(목록 없이 3곳, 목록 넣어도 2곳 + 테두리 끊김), 로컬 7B 명세가 근거 밖 글자를 지어내 그림 1~2장 | #70 | 한글 글자 변형(눈) 오전 편집 1회 3·2 → 새 경로 6회 합계 1, OCR 같은 잣대 4·3 → 0~1, 1회 31~41초 (docs/eval-2026-10-28-figure-edit.md, ADR 0030) |
| 2026-10-28 | [3] 초안 작성 순서 변경 — Argon 먼저 작성(섹션 4개 동시)·실패 섹션만 로컬(error·rate_limit·budget·invalid)·섹션별 작성 기록·1차 검토 끔(self_review)·local_check(기본 끔)·동시 run 3(FlockPool, 로컬 단계만 슬롯)·Gemini 일일 600 | 소유자 승인 정책. 7B 로컬 작성 155초·JSON 실패 4/10 대응, ADR 0032 | #71 | 실측 섹션당 6.6~11.8초, 3섹션 동시 11.8초, Gemini 3회 |
| 2026-10-28 | [4] 실시간 자료 검색 — 입력 확인 때 Argon 키워드(→로컬→규칙)로 ScienceON·NTIS·OpenAlex 동시 검색(자료원 10초·전체 15초, 상위 30), 이름 제거·public·raw.live 로 DB 에 넣고 평소 판정·검색이 함께 본다. 24시간 캐시, NTIS IP 거부는 건너뜀, REST live_search·live 배지 | 야간 적재 질의 밖 주제는 ②·브리핑·③ 근거가 비었다 | #72 | 실호출: 키워드 4초, ScienceON 30건 7.3초, OpenAlex 30건 1.2초, NTIS ip_blocked, 캐시 재사용 0.00초, e5 60청크 1.07초 (ADR 0031) |
| 2026-10-28 | [3]·[4] 화면 — 섹션 "로컬 작성" 배지(Argon 실패 사유)·근거 대조(로컬) 불일치 건수·run 작성자 칩, ② "실시간 검색" 배지·자료원별 상태(완료/시간 초과/IP 차단/오류/꺼짐, NTIS 안내)·검색어 접기, 인용·근거 패널 실시간 배지 | Argon 우선 작성·실시간 검색 백엔드 레인과 병렬 — 새 필드는 전부 선택, 없으면 화면 그대로 | #69 | vitest 86·e2e 17 통과 |
| 2026-10-28 | 그림 명세·말로 고치기의 로컬 대체 호출만 로컬 슬롯(`runs/.generate.lock`, RunManager 와 같은 FlockSlot) 안에서 — `MakeFigures.local_slot`, 로컬 작성 run 의 그림 단계는 `local_held` 로 다시 잡지 않음. Argon·Nano Banana 는 슬롯 밖 | [3](#71) 뒤 Argon 작성 run 3건이 동시에 돌 때 그림 단계는 전역 슬롯 밖 → Argon 실패 시 로컬 7B 대체가 슬롯 없이 겹칠 수 있었다 | #73 | 가짜 동시 run 3건: 그림 로컬 대체 동시 1(슬롯 없으면 6), Argon·이미지 호출은 겹침 |
| 2026-10-28 | [G] 그림 v2 — 기본 그림 = As-Is/To-Be + 분석 기법 추천 0~2(+ 수치 그래프·일정표, 최대 4장), 개념도·체계도·로드맵은 [다른 그림 추가]에서만. 기법 20종을 Argon 이 고르고 제안 내용으로 분석(정성 상·중·하, 비교 +/0/−, 경제성은 근거 수치만·없으면 "산출 필요", 항목 출처, 예비 평가), 추천 카드 [넣기 확정]·[필요 없음]·[다른 기법으로 바꾸기], 빈 결과도 사유. 그림 프롬프트를 "밑그림 배치 그대로" → "인포그래픽 새로 디자인"으로, 비율은 내용 양으로 | 시범 의견: 자동 개념도·체계도·로드맵은 글자가 작고 본문을 되풀이, Nano Banana 그림이 회색 밑그림을 베껴 빈 곳이 큼 | #81 | 같은 명세 6종 기존/v2 나란히(성공 13/13, 장당 27~35초), Argon 추천 1회 64초(텍스트 3·그림 2), 첫 v2 에서 지어낸 제목 1건 → 프롬프트 보완 (docs/eval-2026-10-28-figures-v2.md, ADR 0033) |
| 2026-10-28 | [D] HWPX 서식·화면 편의 — 단계별 단락 모양(왼쪽 여백+내어쓰기)·본문 12pt/장 제목 13pt·표 칸 서식 통일·그림 캡션 12pt 가운데·앞 공백 제거를 HWPX 만들 때마다 점검·고침(`hwpx_format`, manifest 건수), 과제 제목 머리·목록·`<제목>_v<n>.hwpx` 파일 이름, 알림 코드 한국어 설명 표(백엔드·웹 같은 표), 근거 "확인 필요"는 불일치·부분·이미지 판독만 + 근거 일괄 승인, 선택형 제안값 바로 확정, 섹션 작성 벽시계, 위쪽 단계 표시 이동 + run 안 ①·② + 입력 변경 시 관련 섹션만/전체 다시 쓰기(새 버전) | 시범 HWPX 둘째 줄이 왼쪽 끝으로 돌아가고 글자 크기가 섞임, 제출 전 점검의 영문 코드·"0/61 승인 필요", 초안 뒤 아이디어를 고치려면 새 run | #82 | 골든 10/10·시범 run 19/19 남은 서식 불일치 0, 섹션 작성 실측 합 73초 → 벽시계 20초 표시 (docs/eval-2026-10-28-hwpx-format.md, ADR 0034·0035) |
| 2026-10-28 | ② 유사과제 흐름 — reranker 점수 중심 판정(0.5)·아이디어 핵심 키워드(실시간 검색 Argon 키워드)·일반어 40여 개, 같은 제목 행 합치기, 상위 10 Argon "대상·문제·방법이 같은가" 판정(같다만 차단, 한 줄 이유, 실패면 로컬 → 규칙 + [다시 시도]), 행별 [유사함]/[관련 없음]·차단 해제·선택 기록, [유사함] 행만 비교표(원문 추출)·활용 제안·과제안·5. 특이사항, 과제안 카드(목표·방법·범위)·직접 고치기·[AI로 다듬기]·idea_versions, 추천 검증 완화·제외 사유·1회 재생성, 다음 버튼 사유 | 시범: 폐역사 아이디어가 일반어("부족·정책·상황·인식·필요한")로 조달정책·터널 여굴 과제에 차단, 엉뚱한 활용 제안, 추천 0건("검증에서 제외됨 2건") | #83 | 상위 5 적중 10/10 + 유사하지 않음 2/2, 거짓 차단 0/3(종전 1/3), 규칙 2.1초·AI 판정 중앙 10.7초, Gemini 39회 (docs/eval-2026-10-28-precheck-v2.md, ADR 0036) |
| 2026-10-28 | 작성·편집 AI 버튼 — 정책적 중요도 작성안 4개(방향별·근거 겹침 없음·인용 구간 안·원문 재대조), 보강 질문 켬(Argon 먼저·사유 off/enough/failed), AI 다시 쓰기 0후보 사유·새로 쓰기·Argon, 보완 질문 Argon·모든 섹션 체크리스트·[답 반영해 다시 쓰기], 변경 n건 종류별·저장 버튼 항상 켬·최종 검토 팝업, 근거 판단 500 수정. ADR 0037 | 시범 다시 쓰기 4건이 모두 정책 근거 빈 2-가-(1) 에서 사유 없이 0후보, 정책적 중요도 빈칸, 보강 질문 꺼짐, 보완 질문 늘 "없음", "변경 0건" 으로 저장 불가 | #84 | 백엔드 2084·웹 112·e2e 20 통과, 실호출은 PR 본문 표 |
| 2026-10-28 | AI 응답 대기 공용 부품 — 응답 시간 제한 없음(앱 제한 제거, 통신 10분 무응답만 연결 오류), 화면 "응답 기다리는 중 · 경과 n초" + [취소](`useAiCall`·`AiWaiting`), 서버는 브라우저가 끊으면 작업 코루틴 취소(`cancel_on_disconnect`, 499), 로컬 대체는 오류 응답일 때만(규칙에 걸러진 답은 로컬에 다시 묻지 않음). ADR 0038 | 시범: Argon 이 가끔 수 분 걸릴 때 판정 40초·로컬 검토 20초·읽기 180초 제한에 걸려 로컬 답으로 바뀌거나 건너뜀, 기다리는 동안 끊을 방법 없음 | #88 | uvicorn 실측: 1초 뒤 끊은 3초 작업 취소 1·완료 0 |
| 2026-10-28 | 그림 확인·추천 그림 결정·근거 승인/제외·선택형 확정은 버전을 만들지 않고 현재 버전의 표시 파일(`versions/marks_vN.json`)에 쌓는다 — 읽을 때 합침(화면·제출 전 점검·마무리), "변경 n건"과 "확인 n건" 분리, 예전 상태만 바뀐 버전은 "확인 기록"으로 접기, 바뀐 섹션은 실제 차이로·그림은 이름으로, v1 실제 작성자 배지. 단계 화면 아래 이동 막대(이전·다음·남은 일), 초안 보기 [수정 없이 최종 검토로], ⑤ 최종 검토·브리핑 대기 경과 초+[취소], 화면 "run" → 제안서·작성 번호·내 제안서 (ADR 0042) | 시범 run 에서 그림 확인 3번 = 버전 3개, "바뀐 섹션"에 안 바뀐 섹션, 메모 "그림 confirm", 단계 이동·남은 확인이 안 보임, 내부 용어 "run" | #89 | 시범 run 36건·버전 63개: 상태만 바뀐 버전 12개 접음, 잘못된 "바뀐 섹션" 11→0; 가짜 모드 그림 확인 ×3 뒤 버전 수 그대로 |
| 2026-10-28 | [23] 그림 모양 — 모두 가로(16:9·21:9, 일정표·로드맵 21:9·4:1), 가로 배치(As-Is/To-Be 좌우 두 단, SWOT 네 칸 한 줄, 기법별 row·split·flow·grid·table), HWPX 그림 폭 = 양식 본문 안쪽 폭(153.8mm, 양식에서 읽음)·높이 상한 쪽 1/3, 글자 9pt 하한(밑그림 SVG 계산·Nano Banana 는 OCR 상대 어림) → 덜 넓은 비율·글자 줄이기·"글자를 더 크게" 다시 그림, manifest `figure_fit`, 카드 가로 비율·한국어 `display_name`, 그림 AI 버튼 대기·[취소] | 시범 의견: 그림이 세로로 길고 본문 폭보다 좁으며, 넣고 나면 글자가 5~8pt | #91 | 실물 양식 미리보기(한/글 Quick Look) 9/9 본문 폭·높이 상한 안, 밑그림 최소 글자 9.3pt (docs/eval-2026-10-28-figures-wide.md) |
| 2026-10-28 | ② 유사과제 v3 — 표 먼저(stage=rule, 규칙 판정까지) 뒤 AI 판정·과제안을 이어서(같은 판정 작업 공유·취소), 제한 시간 제거(판정·다듬기·원문 추출), 판정 칸 같다→차단·일부 겹침→근접·다르다→관련 낮음, 관련도 높음/보통/낮음(유사도 숫자 숨김), "다르다" 만 [관련 없음] 미리 고름, 선택 요약 막대 [선택 적용]·[차별화 과제안 더 만들기], 카드 근거 제목·자료원(상위 3 + 더 보기), 카드 겹침 재판정(② 같은 기준 → 겹친 카드만 한 번 다시)·차별성 순 정렬, 일반어 37개 | 시범: ② 36~76초 대기, 행 클릭마다 비교표 재생성, 유사도 0.86 일색, 카드 근거가 내부 번호, 거의 모든 카드에 "기존 과제와 가깝다" | #92 | 표 중앙 2.4초(종전엔 판정·과제안 뒤 36~76초), AI 판정 중앙 25.3초·첫 카드 중앙 100초(제한 시간 없음, 12건 모두 Argon), 상위 5 적중 10/10 + 유사하지 않음 2/2, 거짓 차단 0/3, 카드 경고 14/25 → 0/27, Gemini 61회 (docs/eval-2026-10-28-precheck-v3.md, ADR 0039) |
| 2026-10-28 | 레인 B `feat/policy-l2` — 자료 분류(사전정보공표 연구용역 = 연구용역(사내 발주), procurement + raw.doc_class)·운영 DB 이주(`rra db reclassify`, korail_web 702건 바뀜·정책 근거 후보 702→52)·정책 근거 추천과 작성안 같은 범위(`policy_passage`)·인용 정리(URL·글머리·통문장)·문서 표시 공용 도우미(docRefs·DocRef, 내부 번호 숨김)·L2 로컬 2차 검토(시간 상한 제거·우선 순서·문장별 판정·규칙 불일치·Argon 제안 [반영]/[무시]) | 정책 근거 추천에 수송수요 예측 같은 연구용역이 정책으로 나오고, 로컬 대조는 7B 배열 응답을 버려 불일치 0건이던 것 | #90 | 연구용역 287·행정 공시 270·현황 70·통계 23·정책 52, ADR 0040 |
| 2026-10-29 | 시범 의견 2차 통합 — 그림 글자 9pt 밑이면 칸 글자를 줄여(22→16자·이름표 두 글자) 최대 2번 다시 그림, 밑그림 작은 글자 10pt, 분석 기법 그림의 "제안 내용 기반 예비 평가" 표시는 그림 밖 HWPX 캡션 줄로, 설정 사본도 번들 글꼴을 찾음(없으면 경고), 브리핑·자료 검색 내부 번호 → 제목·자료원, 서버 문구 "run" → 제안서, Argon 호출 응답 시간 기록 | 1차 측정에서 그림 글자 9pt 이상 21/36(긴 칸 글자를 Nano Banana 가 줄여 그림·회색 예비 평가 표시), 측정 설정 사본의 밑그림 글자 없음, CI e2e 에서 브리핑 근거 내부 번호 | #93 | 골든셋 적중 9/10 + 2/2, 거짓 차단 0, 정책 빈칸 0(철도 9/9), HWPX 10/10, 그림 본문 폭 37/37·9pt 37/37, L2 지지 187·부분 19·불일치 5, 생성 중앙 217초(3건 동시 259~316초), Argon 중앙 9.1초·p90 27.2초 (docs/eval-2026-10-28-pilot2.md) |
| 2026-10-29 | 근거 범위(ADR 0046): 공사 홈페이지 행정 공시 → `admin_notice`, 사업 현황 → `status_report`, 통계 `statistics` (분류 규칙·`rra db reclassify` 공용). `retrieval_mix` `only_in`(세 종류는 기술적 중요도·연구목적, 통계는 경영혁신도)·`strict`(2-가-(3) 은 policy 만, 되돌리기·보탬 청크 없음) | 행정 공시·현황이 doc_type policy 로 남아 2-가-(3) 경영전략 정합성 근거에 들어갔고(02 「자산개발 규정」), 유사과제 보탬 청크로 연구용역도 섞였다(08·10) | #95 | 운영 DB 사본: 바뀔 행 340(270+70), 다시 점검 0. 골든셋 6건: 2-가-(3) 정책 아닌 청크 5→0, 작성안·추천 출처 6/6 같음 |
| 2026-10-29 | ② 유사과제 표 같은 연작 한 줄(ADR 0043, 레인 A): 제목이 연도·차수만 다른 과제를 "광역철도 수송수요 예측(연작 n건)" 한 줄로, [펼치기] 연도별 목록(제목 · 자료원, 근거 패널). 후보 풀은 묶음 수를 세고(검색 4배), reranker 는 연작마다 상위 2판만(30건 유지). AI 같음 판정은 연작 행 한 번. 공시용 요약문 머리("요 약 문 1. 연구 제목 …") 화면·적재 정리 | 시범 측정 08 의 ② 상위 10칸이 모두 연도만 다른 「수송수요 예측」 보고서라 다른 과제가 표에 못 들었다 | #96 | 골든셋 12건 ② 만: 08 상위 10 서로 다른 과제 7 → 10(연작 줄 6), 08 원래 정답 상위 5 적중 미적중 → 적중, 거짓 차단 0 유지 — docs/eval-2026-10-29-precheck-series.md |
| 2026-10-29 | 그림 칸 글자는 잘라 줄이지 않는다 — 명세 프롬프트에 칸별 글자 수 상한(`figure_phrases.FIELD_LIMITS`)과 완결 구절 규칙, 끊긴 구절(조사·연결어미·말줄임·낱말 중간)은 교정 재요청 → 온전한 낱말 묶음, 9pt 미달은 Argon 이 상한 −25% 로 칸 글자를 다시 써서(`rewrite_texts`) 1회 다시 그림(`max_image_redraws` 2 → 1), `shorten_spec`·`clip_text` 삭제 | 시범 의견 3차 항목 2: "신설역 수요를 별도 가정으로" 처럼 띄어쓰기 자리에서 잘린 구절이 그림에 남았다(10-28 측정 그림 47장 중 29장을 잘라 줄였다) | #98 (ADR 0044) | 측정은 docs/eval-2026-10-29-figure-phrases.md |
| 2026-10-29 | 초안 글 먼저(ADR 0045): v1 저장 즉시 drafted·편집 열림, 그림은 백그라운드 작업(`figures_job.json`·`.figures.lock`, 읽을 때 합치기·끝나면 버전 파일에 채움 — 그림 때문에 새 버전 없음), 자리 카드 "그림 준비 중"·실패 사유 + [다시 그리기], 그리는 동안 ⑤·⑥ 은 "그림 준비 중 — 끝나면 진행할 수 있습니다", 재시작 → failed, `rra runs active` 가 그리는 run 도 셈, 진행 화면에 다 쓴 섹션 먼저(`/sections-progress`), `draft_visible_seconds`·`figures_done_seconds` | 시범 의견 3차 항목 3: 생성 중앙 217초 중 그림 단계 123초 — 초안 글이 그림을 기다림 | #97 | 레인 실측(다른 레인과 겹침) 초안 보임 117·206초, 그림까지 198·335초 (docs/eval-2026-10-29-draft-first.md) |
| 2026-10-29 | 시범 의견 3차 통합(#99): 08 정답에 수송수요 예측 연작 추가(8 → 175), 측정 도구 실시간 상태·초안/그림 시간 분리, openapi 70 경로. 09:30 배포 546f244 → 운영 DB 재분류 340행(policy→admin_notice 270·status_report 70, 배포 전 백업) | 3차 측정 대신 배포 먼저(소유자 지시) — 동료 사용 시간에 골든셋 전체 측정을 돌리지 않으려고 | #99 | 배포 확인: 초안 글 보임 75초·그림까지 187초·② 표 16.0초(첫 요청)·외부 3곳 200, 시험 pytest 2,406·vitest 159·e2e 29 |
| 2026-10-29 | 문서 최신화 [D]: md 244개 목록·분류(`docs/final-docs-inventory.md`), 이전 방식 표시(로컬 7B 주 작성·③ 1차 검토·Cloudflare 계획·"run" 표기), ADR 0047 Tailscale Funnel(사후 기록)·ADR 목록 0029~0047, 최종보고서 재료(`docs/final-report-materials.md`) | 문서마다 작성 방식·공개 방식·수치가 서로 달랐다(예: deploy-exposure "funnel 쓰지 않음" ↔ 실제 Funnel 운영) | docs/final-docs | 고친 파일 수는 PR 본문 |
| 2026-10-29 | [UI] Research Studio 화면 — 디자인 토큰·공용 조각(#101, ADR 0051), 화면 안 로그인(#102)·사이드바·위쪽 막대·접는 메뉴(#106, ADR 0048), 연구 작업실 홈·작성 가이드·내 제안서 줄(#104, ADR 0049), ⌘K 통합 검색·`GET /v1/search/docs`·자료 검색 거르기·자료 현황(#105, ADR 0050), ①~⑥ 안쪽 화면 스타일(#107), 통합 #108(로그인 전 검색칸 창 다시 열림·360px 넘침 수정) | 동료 UI 캡처("Research Studio") 틀로 — 로그인 페이지가 첫 화면이고 위쪽 메뉴로는 흐름·목록을 함께 보기 어려웠다. 기능·흐름은 그대로 | #101·#102·#104~#108 | 10:48 배포 c277253. 실제 화면 axe 위반 5 → 0, Lighthouse 100·100·100, pytest 2,418 · vitest 201 · e2e 40(+3 skip). 배포 확인: 초안 글 92초·그림 202초 |
| 2026-10-29 | ① 정책 근거 추천 팝업 — 네 칸이 채워지면(또는 정책 근거가 빈 채 [다음]) 자동으로 열려 바로 추천, 관련도 1순위 미리 체크("기본 추천")·추가 체크·직접 입력·[다시 받기](이미 본 문서 제외)·[적용]/[나중에 넣기], 정책 근거 칸을 접지 않음. 다시 넣는 길: ③ 작성안 처음부터 펼침, ④ 2-가-(1) 머리 [정책 근거 넣기·바꾸기] 늘 보임(빈칸 안내 줄·직접 입력·`?policy=1`), ③ 초안 보기 바로가기, ⑥ "정책 근거" 항목 [정책 근거 넣기]. 서버는 추천 `rank`·`exclude_doc_ids` 만(ADR 0052). DocRef·제출 전 점검 단추 접근 이름을 보이는 글자에 맞춤 | 시범 의견: 추천 버튼을 누르지 않으면 2-가-(1) 이 빈칸으로 생성되고 다시 넣는 길을 못 찾음(시범 11건 중 정책 근거 없이 만든 7건의 6건이 빈칸, 2건은 그대로 마무리). ④ 단추는 그려졌지만 초안 보기에 길이 없고, 빈 섹션 본문 자리에 안내가 없고, 이름이 "고르기"였고, 편집 불가 상태에서는 숨었음 | #110 | pytest 2,419 · vitest 214 · e2e 43(+3 skip) · import 계약 8, 실제 브라우저 axe 위반 0(팝업·④·⑥) |
