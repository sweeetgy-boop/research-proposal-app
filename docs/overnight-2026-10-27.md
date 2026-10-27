# 야간 작업 기록 (2026-10-27)

(아침 보고 요약은 작업이 끝나면 이 자리에 쓴다.)

## 진행 기록

| 시각 | 단계 | 내용 |
|---|---|---|
| 00:18 | 시작 | main e10466e+#19(20eaafc). 작업 트리 깨끗. mlx_lm.server(Qwen2.5-7B-Instruct-4bit, 127.0.0.1:8080) 이미 떠 있음(한 개, PID 60209) — 재시작하지 않음 |
| 00:19 | [0] | `rra llm-check --stage compose` 0.4s 통과, `--provider gemini` 3.6s 통과(Gemini 1회) |
| 00:20~00:40 | [H] | 브랜치 docs/history. git log 107건·PR 19·이슈 6 대조. docs/history/(README·timeline·metrics.csv/md·lessons·decisions 14건·diagrams 7 .mmd+.svg·charts 5·screens 5), tools/history_charts.py, pyproject `history` extra(matplotlib), CONTRIBUTING·PR 템플릿 규칙. Streamlit 캡처는 가짜 부품 래퍼(scratch)로 8501 에 띄워 Playwright 로 찍고 내림 |

| 00:45 | [H] 완료 | PR #20 CI(backend·detect pass, web skip) → 병합 201b751. main 검사 1178/8/통과 |
| 00:46 | [R] 시작 | 브랜치 feat/project-recommendations |
| ~01:30 | 중단 | 맥 절전으로 세션 끊김. [R] 코드(domain·usecase·prompt·config·composition·assistant·REST·CLI·MCP·UI)와 테스트 3개 파일은 작업 트리에 남음(미커밋) |
| 06:28 | 재개 | 이 기록·git status·열린 PR(0건) 확인. [R] 의 남은 일: 진입점 테스트·전체 검사·openapi·문서·골든셋 실측·PR 부터 이어서 |

| 06:30~07:20 | [R] | 진입점 테스트(REST·CLI·MCP·Streamlit·Agent·저장소·manifest·설정·조립) 작성, 전체 검사 1,215 통과·8 kept·ruff 통과, openapi 갱신(경로 21개), architecture §4.14·CLAUDE.md·timeline. 커밋 5c039ef |
| 07:20 | [R] 실측 1차 | 골든셋 01·02·03 `rra recommend`(Gemini 3회): 03 은 추천 0 + 정확한 사유(철도 무관). 01·02 는 모델이 2건씩 냈으나 전부 검증 제외 — compared_with 에 검색 근거 id 를 쓴 것(규칙이 알림 id 만 허용)·자기 중복(probe 가 원래 입력 4칸을 섞어 원래 아이디어가 차단되면 추천도 전부 차단)·정책명 1건 |
| 07:25 | [R] 수정 | compared_with 도 검색 근거 id 허용(지시서 "검색·precheck 결과 안의 doc_id"), 자기 중복 probe 는 추천 글(가제·요약·차별점·위험)만으로. 테스트 갱신, 2차 실측(Gemini 3회) 진행 |

| 07:10 | [R] 실측 2차 | 03 은 1차와 같이 0건+정확한 사유. 01·02 는 모델 추천 2건씩이 전부 자기 중복으로 제외 — probe 를 추천 글만으로 바꿔도 e5 가 같은 분야 한국어 글을 모두 0.80 위로 올리고 키워드도 겹쳐 "차단" 이 됨 |
| 07:15 | [R] 수정 2 | 자기 중복을 상대 기준으로(`self_overlaps`): 원래 아이디어보다 기존 과제에 가깝거나 같으면(같은 문서 유사도 ≥ 원래, 또는 새 차단 문서) 제외, 멀어졌으면 통과. 테스트 1,217 통과 |
| 07:20 | [R] 실측 3차 | 1회 실패 — 네트워크 끊김(DNS, Gemini·HF ConnectError, Gemini 호출 0회 소모). 07:27 복구 확인 후 HF_HUB_OFFLINE=1 로 재실행 |

| 07:35 | [R] 실측 3차 | 상대 기준으로도 01·02 추천 전부 self_overlap — probe(짧은 추천 글)가 다른 사내 기록을 0.85~0.87 로 새로 차단(e5 분포 압축). 02 의 1건은 정책명 ungrounded(정당) |
| 07:45 | [R] 수정 3 | 자기 중복 결과를 기본 경고로(`recommend.self_overlap: warn|exclude`, `overlap_warning` 카드·CLI·API 표시). 테스트 1,218 통과. 커밋 da8eba2 |
| 07:55 | [R] 실측 4차 | 01 추천 2건(비교 3·근거 3~4·위험·겹칠 수 있음 8·9), 02 추천 1건(+1 ungrounded 폐기), 03 0건+사유. ADR 0012 갱신 → PR #21 |

| 08:05 | [R] 완료 | PR #21 CI 통과 → 병합 691c99d. main 검사 1,218/8/통과 |
| 08:10 | [E] 시작 | 브랜치 feat/draft-pipeline. review_flow·run_manager·review_draft·진입점·테스트 읽고 설계 |

| 08:10~10:40 | [E] 구현 | review_flow 재정의·run 상태·PipelineConfig·pipeline.yaml·versions 규칙·저장소(working, review_draft/final 파일명)·RunManager(1차 자동 반영 v2·annotations·final_review·stale·working·diff·restore·finalize version)·review_draft(kind final)·agent_policy·manifest·REST(8 경로·SSE 이름 이벤트)·CLI(clarify·diff·restore·final-review·outline·edit --memo)·MCP(6 도구)·Streamlit(stepper·버전·편집·최종 검토). 기존 테스트 36건을 새 흐름으로 옮기고 새 테스트 추가 → 1,239 통과·8 kept·ruff 통과. openapi 경로 28개 |

| 10:45 | [E] PR | 커밋 b25c052, PR #22 생성 → CI 대기 |

| 11:05 | [E] 완료 | PR #22 CI 통과 → 병합 1102b72. main 검사 1,245/8/통과. 실제 흐름 확인(골든셋 01, Gemini 1회): v1 18문장·알림 1 → 1차 검토 의견 24·통과 수정안 14 자동 반영(폐기 0) → v2(argon 14·llm 4, 메모 10), 점수 3/2/2/3 |
| 11:10 | [Q] 시작 | 브랜치 feat/draft-quality. Q6 규칙(style.py)·Q1 clarify·Q2 outline 유스케이스·프롬프트·체크리스트 yaml·포트/저장소(outline·candidates)·reranker 설정 뼈대 |
| (중단) | 세션 | 크레딧 소진으로 멈춤 → 사용자 구입 뒤 재개 |
| 08:43~09:40 | [Q] 배선 | Q1~Q8 백엔드 배선 완료(GenerateProposal reranker·섹션별 검색·본보기·규칙 검사, ReviewDraft 체크리스트·추가 문장·후보 선택, RunManager outline 단계·두 후보·자동 반영, composition build_reranker/outliner/clarifier, Assistant·Streamlit clarify·후보 표시, 프롬프트). 테스트 25건 추가 → 1,273 통과·8 kept·ruff 통과. 커밋 296749a |

| 10:03~10:08 | [Q] Q8 | bge-reranker-v2-m3 내려받음(~/models, 2.1GB, safetensors). 라이선스는 지시서의 MIT 가 아니라 **Apache-2.0**(HF 모델 카드 확인) — 업무 이용 허용이라 진행. MPS 측정: 적재 6.1s, 80쌍 0.67s, 32쌍 0.28s, RSS 900MB → 지연 2초 이내 조건 충족 |
| 10:10~10:25 | [Q] Q9 도구 | `rra eval`(EvaluateQuality, --pipeline none/all/default, --on/--off, --no-review, --report 비교표). 테스트 1,277 통과. 커밋 |
| 10:26 | [Q] Q9 측정 1 | baseline(모두 끔)·all(모두 켬) × 골든셋 3, Argon 1차 검토 포함(Gemini 6회 예정) 백그라운드 시작 |

| 10:33 | [Q] Q9 측정 1 결과 | baseline(모두 끔): 01 v1 알림 1→v2 1·점수 4/2/3/3·193s, 03 알림 8→5·점수 3/2/2/2, 02 는 tech_importance JSON 형식 오류 2회로 invalid(품질 단계와 무관). all(모두 켬): 01 알림 5→2·점수 4/3/3/3·반영 10+추가 3·238s, 03 알림 7→4·후보 B 선택 1, 02 는 title 형식 오류로 invalid. **발견한 결함 2건**: 본보기(Q4)가 0건(공시 요약의 "■ 연구목적 ◦" 꼴을 파서가 못 읽음), 섹션별 검색(Q3)이 한국어 질의로 논문을 전부 밀어내 논문 인용 6→0. 둘 다 고침(파서 확장, 섹션 근거에도 자료원 섞임 유지) → all 재측정(all2)을 2단계에 넣음 |
| 10:40 | [Q] Q8 precheck 적중 | 골든셋 10건(기존 3 + [4] 초안 7) precheck 정답 적중: reranker 없이 9/10, 있이 9/10(03 은 둘 다 주차 안내 과제에 차단 — 기존 판정 특성). 평균 정답 순위 1.7 → 1.4(10 은 3위 → 1위, 01·05·10 의 상위 5 가 전부 같은 주제로 바뀜). 지연: k×4(40건) 2.0~2.4s 로 상한 초과 → k×3(30건) 1.5~1.95s. 정답 목록은 두 모드의 상위 5 제목을 보고 같은 주제의 사내 기록을 더해 넓혔다(기록: data/eval/precheck_hits*.json) |
| 10:45 | [Q] Q9 측정 2 시작 | baseline-02 재시도, all2, minus-additions·minus-two_candidates(Argon 포함, 골든셋 3), local-none/local-all/local-minus-{outline,section_search,exemplars,rule_check,reranker}(01·02, Argon 없이). Gemini 예정 10회 |

## 레인 현황 (2026-10-27 10:56 추가 지시 — 통합 담당 = 메인 세션, 서브에이전트 최대 4)

| 레인 | 작업 | 브랜치 / 워크트리 | 상태 | 대기 중인 의존 |
|---|---|---|---|---|
| 통합 | [0] 정리(Q8 기본 켬·회귀 테스트·retrieval_mix.yaml), pytest-xdist·CI 분할(완료 #24), CONTRIBUTING 조각 규칙(완료 #24), Q9 결론, PR 합치기·공유 파일 반영 | feat/draft-quality, feat/retrieval-mix | 진행 | Q9 3단계(대기열) |
| 웹 | [3] 웹 프론트엔드 → U9(U1~U8 합침 뒤) | feat/web (../rra-web) | [3] 완료 → PR #23 CI 통과 → 병합 11:00. 화면 11·Vitest 33·e2e 8·Lighthouse 100/100/100·axe 0·초기 JS gzip 110.6KB | U9 ← U1~U8·[3] 합침 |
| A | [C] 공사 홈페이지 탐색·내려받기 → [P2] 수집처 확장 탐색·내려받기, [P] 코드·fixture | feat/policy-crawl (../rra-wt/feat-policy-crawl) | 시작 10:58 | [P] 적재·[P3] 판독은 내려받기 뒤(대기열) |
| B | [S] ScienceON 1~2단계(실호출 검증·fixture·매핑) | feat/scienceon-live (../rra-wt/feat-scienceon-live) | 시작 10:58 | 3단계 적재는 대기열 |
| C | [U] 백엔드 U1~U8(가짜 LLM 테스트까지) | feat/usability (../rra-wt/feat-usability) | 시작 10:58 | U9·U10 은 합친 뒤 |
| (미배정) | [P3] 이미지 판독 코드·fixture → 판독(Argon 2,000회 별도), [P] 적재, [P2] 적재, [Z] | feat/policy-vision | 대기 | 레인 A 내려받기 |

## 대기열 (무거운 작업, 한 번에 하나 — mlx·임베딩·재색인·대량 파싱·OCR·적재·측정)

| 순서 | 작업 | 상태 |
|---|---|---|
| 1 | Q9 2단계 → 결함으로 중단(11:07) → 3단계 재측정(all3·로컬 빼기 5·검토 빼기 2) | 진행 중 11:12~ |
| 2 | [S] 3단계 ScienceON 적재 1,000~2,000건 | 대기(레인 B 1~2단계 뒤) |
| 3 | [P] 공사 홈페이지 스냅샷 적재 | 대기(레인 A 내려받기 뒤) |
| 4 | [P3] 대조용 OCR | 대기 |
| 5 | [P2] 확장 수집처 적재 | 대기 |
| 6 | 재색인 | 대기 |
| 7 | U10·골든셋 측정(10건) | 대기([S]·[P]·[P2] 적재 뒤) |
| 8 | 보류 재시도분 적재·재측정 | 대기 |

Gemini 상한: 이미지 판독 2,000회(별도), 그 외 오늘 추가 작업 80회(사용 0). 이전 야간 지시분(Q9)은 120회 상한 안에서 계속(누계 아래 표).

| 11:05 | [3] 완료 | 서브에이전트 보고: 화면 11개·DraftEditor·Vitest 33·Playwright e2e 8·Lighthouse 100/100/100(/login)·axe 0(7화면)·초기 JS gzip 110.6KB. 미재현: 추천 ≥1·보강 질문 ≥1·키 없음 경로는 가짜 모드가 못 만듦(UI 는 구현). 백엔드 간극: main 의 build_api 가 clarify 를 안 넘김([Q] 에서 수정), POST /v1/runs 에 acknowledged 없음, 응답 스키마 없음, draft 문장 sentence_id 없음 → 통합 작업에서 처리. 검사 재확인 뒤 PR |

| 11:00 | [3] 병합 | PR #23 병합. 통합: chore/parallel-ci(pytest-xdist·CI 분할·heavy lock·조각 규칙) PR 생성 |

| 11:07 | [Q] Q9 2단계 중단 | all2·minus-additions 에서 골든셋 01·03 이 invalid(제목·기술적 중요도·활용계획 등 빈칸). 원인 2건: (1) Q4 "인용 금지" 가 검색 근거에도 든 본보기 doc 을 인용한 문장까지 폐기해 섹션이 통째로 사라짐, (2) 제목·선택형 프롬프트에 설계 요약이 들어가 Qwen 이 JSON 대신 긴 글을 씀(raw 1,597~2,689자). 수정: 본보기는 베끼기만 폐기(doc 인용 허용), 제목·선택형엔 설계 요약·본보기 제외, 요약 600자. 2단계 결과(baseline-02·all2·minus-additions)는 참고용으로만 남김 |
| 11:00~11:10 | 통합 | PR #24 병합(pytest-xdist·CI 분할 backend-unit/api·web-check/e2e + 모음 job·heavy lock·조각 규칙). xdist 수집 불일치 1건(zip 바이트 id) 수정. feat/draft-quality 에 main 병합 |
| 11:12 | [Q] Q9 3단계 시작 | all3(골든셋 3, Argon) → local-none/local-all/local-minus-{exemplars,outline,section_search,rule_check,reranker}(01·02, Argon 없이) → minus-additions/minus-two_candidates(Argon). heavy lock 사용. Gemini 예정 9회 |

## 판단 기록
- [H] 배경 메모 중 저장소에 근거가 없는 항목(팀 구성·54초·DRM·.env 흰 화면·8501 충돌·웹 React 결정)은 "(대화 기록 기준, 미검증)" 으로 표시. 팀원 이름은 개인정보라 기록하지 않음.
- [H] Mermaid SVG 는 `npx @mermaid-js/mermaid-cli`(puppeteer, 저장소 밖 캐시)로 렌더. 02 는 edge 라벨의 따옴표 때문에 실패 → 따옴표 제거.
- [H] 화면 캡처는 실제 DB·모델 대신 `composition.build_fake_parts` 로 띄워 Gemini·로컬 호출 0.
- [R] 지시서의 "자기 중복: 추천 글로 precheck 를 다시 돌려 blocking 이면 뺀다" 를 글자 그대로 쓰면 골든셋 01·02 의 추천이
  전부 떨어진다(e5 분포 압축). 기능 목적(기존 과제보다 차별성 있는 과제)을 지키는 가장 보수적인 완화로 **상대 기준**
  (원래 아이디어보다 멀어졌을 때만 통과)을 택했다. 절대 기준으로 되돌리려면 `self_overlaps` 호출을 `any(a.blocking)` 으로.
- [E] 상태 이름을 지시서 그대로(drafted·draft_reviewing·final_reviewing·final_reviewed)로 바꾸고 옛 이름(done·reviewed·reviewing)은
  읽을 때 변환했다(저장된 run 호환). 생성 단계 이름은 running 을 유지(generating 과 같은 뜻, 진입점 변경 최소화).
- [E] 1차 검토가 자동으로 붙으면서 run 의 step 계획에 `draft_review` 가 들어가 진행 수가 +1 — 기존 테스트의 (6,6)·"[2/4]" 를
  (7,7)·"[2/5]" 로 옮겼다(약화 아님). `review_skipped`(⑤ 없이 ⑥ 허용)는 검토 LLM 이 없을 때만; pipeline 으로 1차 검토를 끈 경우는
  최종 검토를 거쳐야 마무리.
- [E] 최종 검토 이후 수정(stale)은 지시서대로 마무리를 막지 않고 경고만 — can_finalize 가 final_reviews ≥ 1 이면 editing 도 허용.
- [R] compared_with 는 지시서 "이번 검색·precheck 결과 안의 doc_id" 대로 검색 근거(논문) id 도 허용 — 1차 실측에서 모델이
  논문을 비교 대상으로 든 것이 규칙 때문에 폐기됐다.

## Gemini 호출 집계 (상한 120)

| 단계 | 호출 | 누계 |
|---|---|---|
| [0] llm-check | 1 | 1 |
| [R] 실측 1차 (골든셋 3) | 3 | 4 |
| [R] 실측 2차 (골든셋 3) | 3 | 7 |
| [R] 실측 3차 (골든셋 3, 1회는 네트워크 실패로 0) | 3 | 10 |
| [R] 실측 4차 (골든셋 3, warn) | 3 | 13 |
| [E] 실제 흐름 확인 (골든셋 01 생성 + 1차 검토) | 1 | 14 |
| [Q] Q9 측정 1 (baseline 2 + all 2; 02 는 invalid 라 검토 없음) | 4 | 18 |
| [Q] Q9 측정 2 (baseline-02 1, all2 1, minus-additions 1, minus-two_candidates 중단 ≤1) | 4 | 22 |
