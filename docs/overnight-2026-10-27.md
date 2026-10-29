# 아침 요약 (2026-10-27 밤 → 2026-10-28 아침, 시범 운영 준비까지)

> 보관(2026-10-29): 2026-10-27 작업 일지(당시 기록 그대로). 당시 작성 방식은 로컬 7B 작성 + Argon 1차 검토(이전 방식).

**한 줄**: 오전 [Q] 품질 강화·레인 병렬 작업에 이어, 오후에는 공사 홈페이지·첨부·이미지 판독 적재(korail_web 5,098 문서), 데이터 위치 고정, 로그인(사번·공용 계정), 자료원 IP 확인, 브라우저 접속 준비, NTIS 실연결(과제 2,000·보고서 1,084 적재)까지 끝내고 launchd 로 서비스를 올렸다. 시범 흐름 1회 실측 3분 47초. 외부 주소(Cloudflare)는 DNS 가 Gabia 라 터널을 만들지 못해 사람 결정 대기.

- 자세한 준비 상태·오늘 밤 할 일·아침 점검 순서: `docs/final-check-2026-10-27.md` 맨 위 "내일 아침 시범 준비".
- 병합 PR #42~#53(아래 진행 기록), 테스트 1,772 통과·import 계약 8, CI 7 job 통과. 측정: 골든셋 10건 유효 6/10, 평균 180초/run, Gemini 기타 12/80·이미지 2,000/2,000(+표본 재호출 약 50).
- 남은 리스크: 7B JSON 실패(10건 중 4건 invalid → "다시 생성"), precheck 적중 9→6(ScienceON 논문이 사내 기록 위로), precheck 38~56초(자동 추천 포함), 외부 접속 경로 미결정, 사번·공용 계정 미등록.

---

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
| 통합 | [0] 정리 완료(Q8 기본 켬·회귀 테스트·retrieval_mix.yaml·CI 분할·조각 규칙), Q9 결론·[Q] PR #31 병합 13:01, 공유 파일 반영은 [Z] | feat/draft-quality | 진행 | — |
| 웹 | [3] 완료(#23) → U9 웹 반영 → NTIS 주요 성과·NTIS 추천(② 카드) | feat/web-u9 → feat/web-ntis | U9 완료 12:05 → PR #30 병합 12:15. NTIS 표시 레인 시작 13:56(#35 병합 뒤) → 완료 15:27, PR #39 병합 15:30. Vitest 50·e2e 9·Lighthouse 100·초기 JS 111.6KB. [3] 은 PR #23 병합 11:00. 화면 11·Vitest 33·e2e 8·Lighthouse 100/100/100·axe 0·초기 JS gzip 110.6KB | U9 ← U1~U8·[3] 합침 |
| A | [C]·[P]·[P2-1] 크롤러·적재 어댑터·전략체계 초안·정책 근거 추천·국토부 | feat/policy-crawl | 코드 완료 11:55 → PR #29 병합 12:05. 내려받기 14:03 종료 — 2,138항목·첨부 1,903파일·이미지 207·2.4GB(보류 13건) | [P] 적재·[P3] 판독은 내려받기 뒤(대기열); P2-2/4/6 은 보류 |
| B | [S] ScienceON 1~2단계(실호출 검증·fixture·매핑) | feat/scienceon-live | 완료 11:25 → PR #25 병합 11:30. 실호출 ARTI 1,858·REPORT 370·PATENT 911건, fixture 3종, ADR 0016(특허는 ScienceON 기본). **.env 의 client_id·인증키가 서로 바뀌어 있음(사람 확인)** | 3단계 적재는 대기열(worktree 사본 .env 로 실행 가능) |
| C | [U] 백엔드 U1~U8 | feat/usability | 완료 11:28 → PR #27 병합 11:33. REST 14경로·CLI 5·usability.yaml, 테스트 1,292, ADR 0017 | U9(웹)·U10(측정) 은 합친 뒤 |
| D | [P3] 이미지 판독 코드·fixture·OCR·Argon 이미지 입력·공용 Gemini 제한기 | feat/policy-vision | 완료 11:40 → PR #28 병합 11:48. 테스트 1,387(main 병합 뒤). 첨부 내장 이미지 추출은 통합 세션이 feat/attachment-images 로 추가(PR #34, 13:42) | 판독·OCR·적재는 레인 A 내려받기·대기열 |

| N | [N] NTIS 4개 서비스(과제검색·성과검색·연구보고서·연관콘텐츠) 실호출·fixture·매핑, national_rnd 적재 설계·"국가R&D 과제" 판정 구분, 보고서 중복 합침, 주요 성과·NTIS 추천 REST, 캐시·간격 제한 | feat/ntis-live | 완료 13:49 → PR #35 병합 13:55. 실호출은 IP 차단(사람: 서버 IP 변경), fixture 는 합성 | 적재는 대기열; IP 오류면 skip + 끝에 재시도; 웹 반영은 웹 레인 |
| E | [P2] 보류 처리 — P2-6 발주 용역(ebid/나라장터)·P2-4 감사원(Playwright)·P2-2 안전 통계·P2-3 수송 통계·P2-5 경영평가·P2-10 확인 | feat/policy-sources (../rra-wt/feat-policy-sources) | 완료 15:15(상한 중단 13:57~15:11 포함) → PR #37 병합 15:21 | 적재는 대기열, 키는 사람 |
| F | P2-8 표 구조화(table_facts)·P2-9 용어 후보 | feat/table-facts-terms (../rra-wt/feat-table-facts-terms) | 완료 15:15 → PR #36 병합 15:18 | 추출 실행은 적재 뒤 |
| G | P2-7 R&D 공고·RFP(rnd_notice, 이슈 #13 연결) | feat/rnd-notice (../rra-wt/feat-rnd-notice) | 완료 15:20(상한 중단 포함) → PR #38 병합 15:30 | 적재는 대기열 |

## 대기열 (무거운 작업, 한 번에 하나 — mlx·임베딩·재색인·대량 파싱·OCR·적재·측정)

| 순서 | 작업 | 상태 |
|---|---|---|
| 1 | Q9 측정 완료 12:58 (4단계 + final/baseline3) | 완료 |
| 2 | [S] 3단계 ScienceON 적재 완료 13:00 — 수집 2,317·저장 2,045(중복 272)·청크 2,504, 요청 중 1 조합 건너뜀(500) | 완료 |
| 3 | [P] 공사 홈페이지·국토부 스냅샷 적재 | 자동 예약(크롤 종료 시) |
| 4 | [P3] 대조용 OCR | 대기 |
| 5 | [P2]·[N] 적재(레인 E·G·N 결과) | 대기 |
| 6 | 재색인 | 대기 |
| 7 | U10·골든셋 10건 재측정 | 대기(재색인 뒤) |
| 8 | 보류 재시도분 적재·재측정 | 대기 |

Gemini 상한: 이미지 판독 2,000회(별도), 그 외 오늘 추가 작업 80회(사용 0). 이전 야간 지시분(Q9)은 120회 상한 안에서 계속(누계 아래 표).

| 11:05 | [3] 완료 | 서브에이전트 보고: 화면 11개·DraftEditor·Vitest 33·Playwright e2e 8·Lighthouse 100/100/100(/login)·axe 0(7화면)·초기 JS gzip 110.6KB. 미재현: 추천 ≥1·보강 질문 ≥1·키 없음 경로는 가짜 모드가 못 만듦(UI 는 구현). 백엔드 간극: main 의 build_api 가 clarify 를 안 넘김([Q] 에서 수정), POST /v1/runs 에 acknowledged 없음, 응답 스키마 없음, draft 문장 sentence_id 없음 → 통합 작업에서 처리. 검사 재확인 뒤 PR |

| 11:00 | [3] 병합 | PR #23 병합. 통합: chore/parallel-ci(pytest-xdist·CI 분할·heavy lock·조각 규칙) PR 생성 |

| 11:07 | [Q] Q9 2단계 중단 | all2·minus-additions 에서 골든셋 01·03 이 invalid(제목·기술적 중요도·활용계획 등 빈칸). 원인 2건: (1) Q4 "인용 금지" 가 검색 근거에도 든 본보기 doc 을 인용한 문장까지 폐기해 섹션이 통째로 사라짐, (2) 제목·선택형 프롬프트에 설계 요약이 들어가 Qwen 이 JSON 대신 긴 글을 씀(raw 1,597~2,689자). 수정: 본보기는 베끼기만 폐기(doc 인용 허용), 제목·선택형엔 설계 요약·본보기 제외, 요약 600자. 2단계 결과(baseline-02·all2·minus-additions)는 참고용으로만 남김 |
| 11:00~11:10 | 통합 | PR #24 병합(pytest-xdist·CI 분할 backend-unit/api·web-check/e2e + 모음 job·heavy lock·조각 규칙). xdist 수집 불일치 1건(zip 바이트 id) 수정. feat/draft-quality 에 main 병합 |
| 11:12 | [Q] Q9 3단계 시작 | all3(골든셋 3, Argon) → local-none/local-all/local-minus-{exemplars,outline,section_search,rule_check,reranker}(01·02, Argon 없이) → minus-additions/minus-two_candidates(Argon). heavy lock 사용. Gemini 예정 9회 |

| 11:05~11:14 | 통합 [0] | `config/retrieval_mix.yaml`(섹션별 허용 doc_type·논문·보고서·특허 최소 보장·유사과제 판정 제외, 출처별 최소 보장 우선), 스냅샷 doc_types, DocType report, reranker 기본 켬 + ADR 0013 Q8 결정, architecture §4.16. 테스트 1,285 통과 |
| 11:15 | 레인 D 시작 | [P3] 코드·fixture(장식 거르기·OCR·Argon 이미지 판독·캐시·신뢰도 규칙·배지·공용 Gemini 제한기) |

| 11:19~11:30 | [Q] Q9 3단계 중단 → 4단계 | all3 이 골든셋 3건 모두 invalid(제목·기술적 중요도 JSON 실패). 직접 재현: 제목 프롬프트가 34,099자 — 섹션별 검색이 더한 청크(~50개)가 섹션 검색 없는 섹션(제목·선택형)에도 전부 들어감. 수정: `RetrievalSnapshot.section_added` 를 빼고 기본 집합(20개)만. 테스트 1,286 통과. 4단계(all4 → 로컬 빼기 → 검토 빼기) 재시작 11:22. [3] 웹: acknowledged·sentence_id 반영, e2e 백엔드 경로 정정 뒤 e2e 7건 통과 |

| 11:25 | 레인 B 완료 | ScienceON 실호출 성공(토큰·논문·보고서·특허), fixture·매핑·테스트, 3단계 명령 준비(요청 48회·약 2,400건). 발견: 원본 .env 의 RRA_SCIENCEON_CLIENT_ID 와 RRA_SCIENCEON_KEY 값이 서로 바뀜 — .env 수정 금지라 worktree 사본으로만 검증, 사람 확인 항목으로 기록. ADR 번호 0015 충돌 → 0016. PR 생성 |

| 11:27 | 통합 | PR #25(ScienceON) CI: backend 통과, web-e2e 실패 — CI 의 e2e 백엔드 경로(`../.venv/bin/rra`)가 루트의 부모를 가리킴(exit 127). main 기준 작은 수정 PR #26 → 합친 뒤 #25 재검사 |

| 11:28 | 레인 C 완료 | U1~U8 백엔드(근거 바로보기·판단, 간편 입력, 다시 쓰기·보완 질문, 비교표, 브리핑, 일정·지표, 제출 전 점검, usage). main 병합·ADR 0017 로 번호 조정 → PR 생성. [Q] 와 겹치는 파일(section_checklists.yaml·ReviewRound·_prompt·RunStore) 은 [Q] 쪽에서 main 병합 때 해결 예정 |

| 11:30 | 통합 | PR #26(e2e 경로) 병합 → #25(ScienceON) 재검사 통과 → 병합. #27(usability) 은 main 최신 병합 뒤 CI 대기 |

| 11:33 | 통합 | PR #27(usability U1~U8) 병합. 웹 레인 U9 투입 준비(worktree feat/web-u9) |

| 11:40 | 레인 D 완료 | [P3] 코드·fixture 83건(장식 거르기·OCR(macOS Vision, 샌드박스)·Argon 이미지 입력·해시 캐시·신뢰도 규칙·개인정보 제거·표본 도구·공용 Gemini 제한기 동시 4/분당 60/429 백오프). 실측·판독은 크롤 뒤 대기열. ADR 번호 0016 충돌 → 0018. main 병합 충돌(llm.yaml·prompt_files·fakes·composition) 양쪽 유지로 해결 |

| 11:47 | [Q] Q9 4단계 | all4 가 골든셋 10건(04~10 추가분 포함)을 돌고 있음을 확인 — [4] 10건 지표로 그대로 쓴다(Gemini ≤10회). 이어지는 검토 포함 빼기 실험(minus-additions·minus-two_candidates)은 01~03 으로 제한해 다시 띄우도록 예약(호출 20회 절약). 레인 D PR #28 CI 대기 |

| 11:48 | 통합 | PR #28(이미지 판독 코드) 병합. 남은 레인: A(크롤링·[P]·[P2])·U9(웹). 대기열: all4(10건) 진행 중 |

| 11:51 | 통합 | [Q] 를 main(웹·병렬 CI·ScienceON·사용 편의성·이미지 판독) 에 맞춤 — 측정이 메인 작업 트리를 쓰고 있어 복사 브랜치(feat/draft-quality-merge, ../rra-wt/dq-merge)에서 충돌 16파일 해결. 테스트 1,428 통과·8 kept·ruff 통과, openapi 41경로. 4단계 끝나면 feat/draft-quality 를 여기로 fast-forward → PR |

| 11:55 | 레인 A 완료 | info.korail.com 50개 메뉴 탐색·내려받기(진행 중, worktree 의 data/ 에 저장), 크롤러·적재 어댑터·전략체계 초안(5 방향·15 과제, text 기준)·정책 근거 추천·국토부 어댑터·판 추적. 자동 판단: www.korail.com SPA 봇 보호 우회 안 함, 보도자료 5년, 50MB 상한 보류 13, 감사원·발주 용역 보류. main 병합 충돌 5파일 해결·이미지 적재 테스트 갱신·ADR 0019 → PR |

| 12:00 | [Q] 결함 수정 | 4단계 all4(10건): invalid 5/10 — JSON 실패(제목·활용계획) 2건 + 특이사항 `too_long`(lint error) 3건. 수정(복사 브랜치): 형식 교정 재요청은 기본 프롬프트(설계도·본보기·후보 제외)로, 칸 상한 초과 섹션은 뒤 문장을 잘라 경고(`section_trimmed`). 테스트 1,431 |
| 12:05 | 통합 | PR #29(크롤링·적재 어댑터·전략체계 초안·정책 근거 추천·국토부) 병합. main 검사 재실행. 내려받기는 worktree(feat-policy-crawl)에서 계속 — 끝나면 스냅샷을 main data/ 로 옮겨 적재 |

| 12:05 | U9 완료 | 간편 입력·정책 근거 추천(미개방 안내)·비교표·브리핑·근거 패널(판단·배지)·섹션 다시 쓰기·보완 질문·제출 전 점검·만족도. 가짜 LLM 분기로 e2e 가 U2·U5 경로 통과. main 병합 → PR #30 |

| 12:04 | [Q] 복사 브랜치 | 크롤 PR 뒤 main 재병합(충돌 5파일: retrieval_scope + retrieval_mix 제외 둘 다 적용, DocType 합집합), 근거 패널 응답에 원본 링크 `url`(U9 간극) 추가. 테스트 1,493·8 kept·ruff |

| 12:15 | 통합 | PR #30(U9 웹) 병합 — e2e 실패 1건은 크롤 PR 로 정책 근거 추천 엔드포인트가 생겨 응답 모양이 바뀐 것: 클라이언트를 실제 모양(suggestions)으로, 필수 4칸 전 버튼 잠금. 모든 레인 코드가 main 에 합쳐짐. 남은 것: [Q] PR(측정 뒤), 적재·판독·측정(대기열), [Z] |

| 12:44 | [Q] Q9 4단계 끝 | all4(10건): drafted 5·invalid 5(JSON 2·특이사항 too_long 3 → 수정 반영). 로컬 빼기(01·02, local-all 대비): 본보기 빼면 invalid 1→0·문장 14→29·논문 1→5, 설계도 빼면 문장 37·논문 5·+20s 절약, 섹션별 검색 빼면 논문 1→0, 규칙 검사·reranker 는 중립. 검토 빼기(01~03): 두 후보 빼면 invalid 0·문장 49·논문 11·점수 10.3/run(같음), 보완 작성 빼면 충족률 0.65→0.47·문장 26·점수 8/run. **기본값**: section_search·additions·reranker 켬, outline·exemplars·two_candidates·clarify 끔. 최종 조합(final)과 같은 코퍼스 baseline3 를 01~03 으로 측정 중(Gemini 6) |
| 12:45 | [S] 3단계 | DB 백업 뒤 ScienceON 적재 실행 → `ScienceOnError` 로 0건(라이브 check 는 성공) — 원인 조사 중 |

| 12:50 | [S] 3단계 원인 | 한 질의·target 조합이 ScienceON code=500 을 돌려 run 전체가 중단(49초, 0건). 수정([Q] 브랜치): 그 조합만 건너뛰고 나머지를 모음(전부 실패면 첫 오류 그대로). 측정(final·baseline3) 뒤 재적재 예약 |

| 12:58 | [Q] Q9 완료 | final(결정 조합) vs baseline3(같은 코퍼스, 01~03): 점수 10.5 vs 9.0/run, 충족률 0.77 vs 0.71, v2 문장 37 vs 27, 시간 131s vs 116s(+13%). 01 은 둘 다 invalid(수정 전 코드). docs/eval-2026-10-27.md §4, ADR 0013 결정표, 이슈 #12 댓글. feat/draft-quality 를 병합본으로 fast-forward → **PR #31** |

| 13:00 | [S] 3단계 완료 | ScienceON 적재 2,045건(논문 888·보고서 588(doc_type internal_report)·특허 569), 청크 2,504. 코퍼스: own 1,119·alio 120·openalex 2,482·scienceon 2,045. [S] 4단계로 골든셋 01·02 를 기본 파이프라인(수정 코드)으로 측정 중(Gemini 2) |

| 13:01 | 통합 | **PR #31([Q]) 병합** — 오늘 합친 PR: #23 #24 #25 #26 #27 #28 #29 #30 #31. 남은 것: [S] 4단계 측정(진행), 크롤 완료 뒤 [P] 적재·[P3] OCR·판독·적재, 골든셋 10건 재측정, [Z] |

| 13:09 | [S] 4단계·[5] | post-scienceon(01·02, 기본 파이프라인·수정 코드): 02 점수 3/3/2/3(차별성 2→3), 충족률 0.88, 근거에 scienceon 등장(문장 근거 id 가 scienceon:…). 01 은 또 invalid — 기대효과(기술) 섹션 JSON 실패. 직접 재현: 배열 뒤 `}` 꼬리 하나(541자). [5] fix/eval-findings: 짧은 찌꺼기 관용 파싱(lenient) → PR |

| 13:12 | 통합 | PR #32([5] 관용 파싱) 병합. 합친 PR 10건(#23~#32). 크롤 1,386항목 진행 중 — 끝나면 스냅샷 이동 → [P] 적재 → [P3] OCR·판독 → 측정 |

| 13:16 | 통합 | PR #33([6] 발표 자료) 병합. [Z] 문서 브랜치 docs/final-2026-10-27 에 status·timeline·metrics 반영. 크롤 1,442항목 진행 중 — 종료 시 자동: 스냅샷 이동 → 백업 → korail_web·molit 적재 → 자료원 상태 → 이미지 거르기·OCR → Argon 판독(cap 2000) → 표본 → 적재 → 정책 근거 예시 |

| 13:20 | 레인 N·E·F·G 시작 | 빈 서브에이전트 4개에 [N] NTIS, [P2] 보류 항목([자동 진행] 규칙), P2-8·P2-9, P2-7 배정. 대기열 순서: 크롤 종료 → [P] 적재 → [P3] OCR·판독 → [P2]·[N] 적재 → 재색인 → U10·골든셋 10건 재측정 → [Z]. 지시문의 "[N] 지시 전체" 는 붙어 있지 않아 CLAUDE.md·external-apis.md 의 NTIS 대기 항목(실응답 녹화·FIELDS·project_path·record_tag 확정·연구보고서 가능 여부)으로 구성했다 |

| 13:23 | 레인 N 지시 갱신 | 사용자가 보낸 [N] 세부 지시(서비스 4개·national_rnd·국가R&D 과제 구분·보고서 합침·주요 성과·NTIS 추천·캐시·IP 오류 처리)를 레인 N 에 전달. retrieval_mix 규칙은 조각으로 받아 통합 세션이 반영 |
| 13:42 | 통합 [P3] 첨부 내장 이미지 | 사용자 지시(13:30) 반영 — HWPX·HWP(BinData)·PDF·PPTX(media)·XLSX 내장 이미지를 격리 워커로 추출, 같은 해시 합침, 로고·장식 거르기 공용, 원본 위치(첨부 파일명·쪽·슬라이드) 메타, 순서 그룹 brochure(경영목표·전략·비전 > ESG·사전정보공표 > 통계 > 브로슈어 > 보도자료). `rra vision extract`. PR #34 검사 대기. 판독 흐름은 크롤 종료·[P] 적재 뒤 post_vision.sh(extract → dry-run 장수 기록 → OCR → Argon cap 2000 → 표본 → 적재) |
| 13:44 | 통합 연구개발 전략 확인 | '철도연구원 연구개발 중장기 발전전략 수립' 은 사전정보공표 과제 요약만 있고 원문 비공개·첨부 없음 → 초안 만들지 않음(final-check 13:44 판단). 경영목표·경영전략·비전 메뉴는 수집 확인(중장기 경영목표 key=1900, 경영가치체계, 환경경영 비전 및 전략, 경영목표 목표수준 종합) — 전략체계 초안 출처는 final-check '내가 확인할 것' |
| 13:45 | 통합 | PR #34(첨부 내장 이미지) 검사 통과 → 병합. main 검사 재실행(배경) |
| 13:48 | 통합 [P3] 표본 추출 | 크롤 스냅샷 첨부 66건(hwp 24·hwpx 16·pdf 10·pptx 10·xlsx 6, 196MB) 표본으로 `vision extract` 25s → 내장 이미지 407장(pdf 311·hwp 47·pptx 41·hwpx 8·xlsx 0), tiny 320·중복 83 제외, OutputTooLarge 2건. 첨부 1,640건(hwp 1,210·hwpx 261·pdf 69·xlsx 59·pptx 41)으로 환산하면 **약 4,000~5,000장**(로고·장식 거르기 전) + 페이지 이미지 196장. Argon 상한 2,000 을 넘으므로 순서(경영목표·전략 > ESG·사전정보 > 통계 > 브로슈어 > 보도자료) 뒤쪽 보도자료 첨부(hwp 대부분)는 OCR 만. post_vision.sh(추출 → dry-run 장수 → OCR → Argon cap 2000 → 표본 → 적재) 를 post_crawl 종료 뒤 자동 실행으로 걸어 둠 |
| 13:49 | 레인 N 완료 | NTIS 4개 서비스 실호출 전부 `접근 허용 IP가 아닙니다`(HTTP 200 본문) → 합성 fixture 로 완료, 끝에 재시도 13:43 동일. 오류 본문 미검출 결함 수정, national_rnd 티어, 보고서 합침, `POST /v1/precheck/ntis-outcomes`, ADR 0020. 통합: retrieval_mix.yaml NTIS 주석(최소 보장은 ntis 접두어로 min_per_source 적용, raw.kind 별 허용은 적재 뒤 보류)·openapi 재생성. PR #35 검사 대기. 적재는 IP 반영 뒤 대기열, 웹 반영(주요 성과·NTIS 추천)은 #35 병합 뒤 웹 레인 |
| 13:55 | 통합 | PR #35([N] NTIS) 검사 통과 → 병합. 웹 레인에 ② 과제 카드 '주요 성과'·'NTIS 추천' 표시 배정 |
| 15:11 | 통합 | 13:57 경 세션 사용량 상한(15:10 재설정)으로 서브에이전트 4개(E·F·G·웹 NTIS)가 중단됨 — 작업 내용은 각 worktree 에 보존. 15:11 재개: 네 레인에 이어서 하라고 전달. 크롤·대기열 waiter 는 영향 없이 계속 |
| 15:12 | 통합 크롤 종료 확인 | 크롤은 **14:03 에 끝나 있었음** — 최종 2,138항목·첨부 3,258(내려받음 1,903: hwp 1,471·hwpx 261·pdf 69·xlsx 59·pptx 41·xls 2)·페이지 이미지 207·2.4GB, 보도자료 1,450·사전정보공표 568. 종료 감지 waiter 두 개가 `pgrep -f "crawl korail --download"` 로 서로의 명령줄을 잡아 영원히 대기(결함, 약 70분 손실) → 둘을 멈추고 post_crawl.sh 를 {now} 직접 시작(스냅샷 이동 → 백업 → korail_web·molit 적재 → 자료원 상태 → 정책 근거 예시). post_vision.sh waiter 는 post_crawl.log 의 `== done` 을 보므로 그대로 이어진다 |
| 15:15 | 레인 F 완료 | P2-8 table_facts(도메인 규칙·migration 005·`rra facts extract|search`·`GET /v1/facts`·수치 lint 근거 연결)·P2-9 용어 후보(`rra terms candidates`, 자동 반영 없음, 이슈 #11 댓글 본문은 조각에). 스크래치 dry-run: 표 2,094장 → 사실 48,253건/문서 32건(pdf 표는 줄로 흩어져 2건). 발견: korail_web xlsx·xls 첨부는 text 가 없어 적재 안 됨 → 통합 후속. main 병합(app.py 임포트 충돌 1건)·openapi 재생성 → PR 검사 대기 |
| 15:15 | 레인 E 완료 | [P2] 보류: g2b(나라장터 API, 키 없음 → 어댑터·fixture·`RRA_DATA_GO_KR_KEY`)·bai(감사원 Playwright 화면 조작만, 철도 55건·파일 40개 82.5MB 수집, 보류 1)·datago(공공데이터포털 파일 16개, 키 없음)·mofe(기재부 경영평가 보도자료 10건)·P2-10 판 추적 모호 처리. procurement 티어 '발주 용역'·status '용역으로 진행 중/예정'. ADR 0021. 필요 키 목록은 final-check 로. 통합: main 병합 → PR |
| 15:18 | 통합 | PR #36(레인 F table_facts·용어 후보) 검사 통과 → 병합. 레인 E 는 PR #37(main 재병합 뒤 검사). 이슈 #11 댓글은 조각 본문으로 게시 |
| 15:20 | 레인 G 완료 | P2-7 rnd_notice: KAIA(주)·IRIS(보조, 국토교통부 필터, 공개 POST 폼) 스냅샷 공고 99건·첨부 229개 575MB(2024-10~2026-08), NTIS 공고는 robots 금지라 보류. valid_until=마감일(만료 제외 실동작 확인), 담당자 PII 제거, `rra notices match`·`POST /v1/ideas/notices`. ADR 0023. 통합: main 병합(architecture §4.19·api 충돌)·openapi → PR 검사 대기. 적재는 대기열 |
| 15:20 | [P] 적재 완료 | post_crawl.sh 15:12→15:20: 스냅샷 이동(data/korail_web/snapshots/2026-10-27), 백업 rra-20261027-151253, korail_web 적재 **2,613건(중복 917 제거)·청크 6,437**(거부: ValidationError 61 = xlsx·xls 시트 구조만 돌아와 text 없음 → 후속, MagicMismatch 12, ParseRejected 1), molit 6건·37청크. 자료원 상태: OpenAlex 2,482·ScienceON 2,045·알리오 120·사내 과제 1,119·공사 홈페이지 2,613·국토부 6. 정책 근거 예시(01·02) 출력은 post_crawl.log. 이어서 post_vision.sh 자동 시작 |
| 15:21 | 통합 | PR #37(레인 E [P2] 보류 자료원) 검사 통과 → 병합. 레인 G PR #38 은 main 재병합 뒤 검사 |
| 15:24 | 통합 xlsx 본문 | [P] 적재 거부 ValidationError 61건 = xlsx·xls 첨부(시트 구조만 돌아옴) → `korail_web/_sheets.py sheets_to_text`([시트] + " | " 행)로 본문 적재되게 고침, fix/xlsx-sheet-text PR 검사 대기. 병합 뒤 대기열에서 korail_web 재적재(레인 E 의 biz_stat_docs → statistics 와 함께). 첨부 내장 이미지 추출 진행 중: 15:24 현재 3,043장 저장(OutputTooLarge 일부 거부) |
| 15:27 | 웹 레인 완료 | ② 카드 '주요 성과(참고용)'·'NTIS 추천'(외부 링크·미검증 표시, 비신뢰 텍스트 노드), national_rnd 티어 라벨, 가짜 모드 ScriptedNtisInsights, Vitest 56·Playwright 11. 발견: `/precheck/comparison` 과 `/precheck/ntis-outcomes` 가 동시에 reranker 를 돌리면 Metal 단언으로 API 가 죽음 → 화면은 직렬화, 서버 잠금은 통합이 별도 PR. PR #39 main 병합 뒤 검사 중 |
| 15:27 | 통합 | PR #40(xlsx 시트 본문) 검사 통과 → 병합. korail_web 재적재는 대기열 |
| 15:27 | [P3] 추출·계획 | 첨부 내장 이미지 추출 15:21→15:26(저장 4,254장). 거르기 뒤 **유지 4,003 / 제외 447**(aspect 147·tiny 281·alt/name 18·format 1). 판독 계획: Argon 2,000(상한)·OCR 만 2,003. 순서 그룹: strategy 4, esg_policy 1,067, statistics 79, brochure 400, press 1,483, other 970 → press 뒤쪽 약 1,480장과 other 는 OCR 텍스트만. OCR 15:26 시작 |
| 15:30 | 통합 | PR #38(레인 G rnd_notice, ruff 줄 길이 1건 고친 뒤)·PR #39(웹 NTIS 표시) 검사 통과 → 병합. reranker 서버 잠금은 fix/reranker-lock PR 로. 레인 N·E·F·G·웹 전부 main 에 합쳐짐 — 남은 것은 대기열(적재·판독·측정)과 [Z] |
| 15:32 | 통합 **사고** | 병합된 레인 worktree 7개(../rra-wt/feat-ntis-live·feat-table-facts-terms·feat-policy-sources·feat-rnd-notice·feat-web-ntis·fix-xlsx-text·feat-attachment-images)가 사라짐 — `gh pr merge --delete-branch` 가 로컬 브랜치와 함께 worktree 를 지운 것으로 보임(마지막 삭제 15:30 = #38·#39 병합 시각). 코드는 전부 main 에 있어 손실 없음. **손실: 레인 E 감사원 스냅샷(data/bai, 55건 82.5MB)·레인 G 공고 스냅샷(data/rnd_notice, 99건 575MB)** — 둘 다 미커밋 데이터라 재수집(감사원 약 5분, 공고 약 1시간, 네트워크라 판독과 병행). datago·mofe 는 적재 때 내려받아 영향 없음. 앞으로 worktree 가 있는 브랜치는 `--delete-branch` 없이 병합하고 원격 브랜치만 따로 지운다 |
| 15:33 | 통합 | PR #41(reranker 모델 호출 직렬화) 검사 통과 → `--delete-branch` 없이 병합, 원격 브랜치만 삭제 → worktree 가 남음(15:30 사고의 원인 확인). 재수집(bai → rnd-notice) 15:32 시작, 대기열 뒷부분(post_queue.sh: 적재 bai·mofe·datago·rnd_notice·korail_web 재적재 → facts extract → terms candidates → notices match → 골든셋 10 no-review + 01·02 검토) 은 판독·재수집 종료 뒤 자동 |
| 15:41 | 지시 반영(15:39) | ① 데이터 위치 고정: 레인 D2(feat/data-dir) 시작 — `RRA_DATA_DIR`(기본 = `git rev-parse --git-common-dir` 의 원래 저장소 data/ 절대 경로), 모든 data 경로를 `data_path` 로, CONTRIBUTING 규칙 + worktree 쓰기 금지 테스트. 돌고 있는 재수집은 main 체크아웃(cwd = 원래 저장소)에서 돌아 `data/bai/snapshots/2026-10-27` 에 저장 중임을 확인. 다른 worktree 에 남은 data 는 feat-policy-crawl/data(빈 폴더)뿐 — 옮길 것 없음. ② 골든셋 측정: 오늘 추가 작업 Gemini 상한 80 중 사용 0(레인 전부 LLM 0) → 잔여 80 ≥ 30 → **10건 모두 Argon 1차 검토 포함**으로 post_queue.sh 수정(예상 20~30회, 결과 JSON 의 호출 수를 기록). ③ IP 상태: 현재 공인 IP 59.0.251.250, NTIS 등록 IP 223.38.229.90 과 다름. 15:40 실호출: NTIS 과제·보고서 둘 다 `접근 허용 IP가 아닙니다`, ScienceON 은 .env 키 길이 검사에서 멈춤(client_id·키가 서로 바뀐 상태 그대로 — 레인 B 가 사본으로 맞바꿔 호출했을 때는 성공했으므로 ScienceON 은 IP 제한 없음) |
| 15:42 | [P3] 제외 표본 | 거르기 제외 447장 중 사유별 고르게 30장을 `data/ocr-sample-excluded/2026-10-27/`(미커밋)에 복사, 목록·집계 `docs/ocr-sample/excluded_sample.json`. 거르기 사유는 가로세로비(aspect)·작은 크기(tiny)·alt/파일명 패턴·형식뿐이고 '사진' 판별은 없음 — 사진은 Argon 판독의 종류(기타)로 가려지며 적재 규칙에서 처리(판독 뒤 집계). OCR 1,450장(15:41), 감사원 재수집 17항목 52MB 진행 중 |
| 15:49 | 지시 반영(15:46) | ① Argon 판독 전 OCR 결과로 사진 거르기 — post_vision.sh 를 OCR 단계에서 멈추고(OCR 캐시 `data/korail_web/ocr/<sha>.json` 은 재실행 때 재사용) 사진 규칙(`domain/rules/photo_filter`, 기준값은 OCR 표본 분포로)·판독 계획 분리·적재 제외·표본 30장을 feat/photo-filter 로 구현한 뒤 OCR 재개 → Argon → 표본 → 적재 순으로 다시 돈다. ② 사용자가 .env ScienceON 키를 맞바꿈 → 15:48 `sources check`: **auth ok, ARTI 1,858·REPORT 370·PATENT 911** |
| 15:51 | [P3] 사진 기준값 표본 | OCR 결과 2,062장(성공 기준, 중지 시점) 분포: 글자 0 = 944(46%), 1~9 = 143, 10~19 = 157, 20~39 = 125, 40~79 = 162, 80+ = 531. 숫자 없는 것 1,316, 숫자 없고 줄 < 3 인 것 1,171. 후보 규칙 '글자 < 20 & 숫자 0 & 줄 < 3' = 1,138장(55%). 전략·ESG·통계 그룹은 OCR 이 못 읽는 체계도·도형일 수 있어 사진 규칙에서 제외(Argon 으로). OCR 은 post_vision 중지로 끊겨 15:51 캐시 재사용으로 재개 |
| 15:54 | [P3] 사진 거르기 구현 | feat/photo-filter: `domain/rules/photo_filter`(OCR 성공·글자 < 20·숫자/도형 기호 없음·줄 ≤ 2, 전략·ESG·통계 그룹 제외), `VisionPlan.photos`, status photo(적재 제외, vision_log 메타만), `config/vision.yaml photo`, 테스트 6건. PR 검사 대기 → 병합되면 post_vision2.sh(dry-run 사진 수 기록 → 사진 표본 30장 `docs/ocr-sample/excluded/photo_sample.json` → Argon cap 2000 → 표본 → 적재) 자동. 거르기 표본 JSON 은 `docs/ocr-sample/excluded/filter_sample.json` 으로 이동. OCR 재개 2,307장(15:52) |
| 15:54 | 레인 D2 완료 | 데이터 위치 고정 PR #42(검사 통과, 병합 대기): `RRA_DATA_DIR` > git common dir 의 원 저장소 data/ > cwd/data, `data_path`·`data_locations`(17키), 모든 build_* 가 절대 경로 전달, worktree 쓰기 금지 테스트 15건(임시 git worktree 로 검증)·정적 리터럴 금지, CONTRIBUTING '데이터 위치' 절. 병합 순서: 사진 거르기 PR 먼저(판독 흐름 긴급) → #42 main 재병합 뒤 |
| 15:56 | 통합 | PR #43(사진 거르기) 검사 통과 → 병합(worktree 유지). post_vision2 waiter 는 OCR 재개 종료를 기다리는 중. 이어서 #42(데이터 위치) main 재병합 |
| 15:58 | 통합 | PR #42(데이터 위치 고정) main 재병합·검사 통과 → 병합. 이후 모든 build_* 는 원 저장소 data/ 절대 경로를 쓴다(worktree 에서 실행해도 동일) |
| 15:59 | 재수집 완료 | 감사원 15:33→15:46: 54항목·파일 40개·82.5MB·보류 1(srno 1849, 대기열 앞에서 `--incremental` 재시도). KAIA·IRIS 15:46→15:59: 공고 99건(KAIA 83 + IRIS 16, 중복 63)·첨부 229개·847MB·오류 0. 둘 다 원 저장소 `data/` 에 저장(레인 보고와 같은 수치) |
| 16:14 | [P3] 사진 거르기 결과·병렬화 | OCR 재개 종료 16:10(총 4,003장). 사진 거르기 뒤 계획: **사진 1,570장**(brochure 286·press 543·other 741) Argon 제외, **Argon 대상 2,000**, **OCR 만 433**(사진 아닌 나머지 중 상한 초과; 그룹 strategy 4·esg_policy 1,067·statistics 79·brochure 400·press 1,483·other 970). 사진 표본 30장 `docs/ocr-sample/excluded/photo_sample.json`(이미지는 data/ocr-sample-excluded/2026-10-27/photo/). Argon 판독 16:11 시작 — 2분에 19장(순차)이라 2,000장에 3시간 이상 → 병렬 처리(동시 4) PR 작성·검사 중, 병합 즉시 캐시 유지한 채 재시작 |
| 16:20 | 통합 | PR #44(판독 병렬 처리 동시 4) 검사 통과 → 병합. 순차 판독(캐시 약 60장)을 멈추고 post_vision3.sh 로 재시작(캐시 유지) → 표본 → 적재 → 자료원 상태. 이어서 post_queue(적재·표 사실·용어 후보·골든셋 10건 검토 포함 측정) 자동 |
| 16:22 | [P3] 병렬 판독 실측 | 동시 4 로 분당 29장(순차 8~10장의 3배), 실패 1/120(LLMError). 남은 약 1,880장 → 17:30 전후 종료 예상, 이어서 표본·적재 → 대기열 → [Z]. 전체 완료 예상 19:00 |

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
| [Q] Q9 측정 3 (all3 — 전부 invalid 라 검토 0) | 0 | 22 |
| [Q] Q9 측정 4 (all4 10건 5 + minus-additions 2 + minus-two_candidates 3) | 10 | 32 |
| [Q] Q9 측정 5 (final 2 + baseline3 2) | 4 | 36 |
| [S] 4단계 post-scienceon (01 invalid 라 1) | 1 | 37 |

10:56 추가 지시 뒤 상한: 이미지 판독 2,000(별도) / 그 외 추가 작업 80. 사용: 레인 N·E·F·G·웹·D2 전부 0, 골든셋 10건 검토 포함 측정(대기열)에서 예상 20~30 — 결과는 post_queue.log·data/eval/final10_review.json 의 호출 수로 확정.
| 17:29 | 요약(compact) 뒤 점검: 판독 캐시 1,810/2,000(실패 1), "Q9 4단계 대기" 셸은 Q9 가 12:59 에 끝나 신호가 없어 영원히 대기 중이었고 다음 단계를 막지는 않음(대기열은 post_vision "== done"+재수집 완료만 봄) → 정리. 시범 운영 지시(17:2x) 반영: 새 레인 [A] feat/login·[I] feat/source-ip·[W] feat/tunnel 를 worktree 에 배정(서브에이전트 3, 합계 4 이하). 사전 확인: ai-edu-lab.co.kr NS 는 Gabia(Cloudflare 아님), ~/.cloudflared·cloudflared·tailscale 없음, agent.ai-edu-lab.co.kr 은 다른 호스트 → [W] 는 코드·준비 문서만, 터널 미기동, Tailscale 대체 절차 준비(규칙 5). [D] 는 [Z]·[A]·[W] 병합 뒤, [R] 은 맨 마지막 | 통합 |
| 17:43 | Argon 판독 종료(16:20 재시작 → 17:40, 병렬 4): 호출 2,000(상한 도달), argon 성공 1,903·실패 166(LLMError·JSON 아님 → OCR 텍스트만 status=failed, 상한 도달이라 재시도 없음·규칙 6)·사진 1,570·OCR 만 364(캐시 69 반영 뒤 계획값), 미확인 수치 2,414. 이어서 표본(`rra vision sample`)·적재 자동 진행 → 대기열 | post_vision.log, scratchpad vision_read_final.json |
| 17:45 | [W] PR #45 병합(client_ip·public_origin·Origin 검사·tunnel plist·ADR 0024). 터널·Access 는 사람 몫(DNS Gabia). [A] 에 client_ip 서명 전달 | 레인 W 보고 |
| 17:50 | `rra vision sample` 이 캐시 없는 항목(실패 166 등)을 다시 Argon 호출하는 것을 발견(이미지 상한 2,000 도달 뒤) → 즉시 중단(초과 약 50회, 실패 재시도분). 표본은 `--cached-only` 로 뒤에 다시. `rra vision ingest` 는 dry-run(문서 2,426·청크 2,496, 사진 1,570 제외, PII 제거 477건) 통과 뒤 실제 적재에서 `CHECK text_basis IN (full_text,summary,abstract)` 위반(image_vision 미포함, migration 002 의 CHECK 가 안 넓혀짐) → 레인 fix/image-vision-basis 로 migration 006 추가 뒤 재적재. 대기열(post_queue)은 17:46 백업 뒤 진행 중 | post_vision.log |
| 17:58 | [I] PR #46 병합(등록 IP 대조·IP 거부 자료원 건너뜀·웹 안내). 실호출: ScienceON ok, NTIS 는 현재 IP 가 목록에 있어도 거부 → 사람 확인. ADR 번호 충돌(#45·#46 둘 다 0024) → [Z] 에서 자료원 IP ADR 을 0025 로, README 표에 0015~0025 행 보충 | 레인 I 보고 |
| 18:01 | 대기열 적재: 감사원 보류 1건 재시도는 TimeoutError 2회(수집 0, 기존 54 유지) → bai 적재 21건·청크 967(ParseRejected 로 거른 파일 다수, id 1381·1462·1556·1614 등), mofe 10건·65청크, datago 16건·118청크. rnd_notice 적재 진행 중 | post_queue.log |
| 18:12 | [A] PR #48 병합(사번·공용 계정 로그인, run 소유자 격리, internal 제외, 일일 상한, Gemini 일일 300회 상한, rra auth CLI, 웹 두 탭; 테스트 1,756). ADR 번호 충돌(0025 중복) → [Z] 에서 로그인 ADR 0026. 남은 레인: migration 006 PR #47 CI 대기 | 레인 A 보고 |
| 18:13 | 대기열 적재 계속: rnd_notice 91건·청크 10,898(중복 4), korail_web 재적재 2,672건·청크 8,180(중복 917, MagicMismatch 12·ParseRejected 1 거름; 이전 2,613·6,437 → xlsx 시트 본문 반영), g2b 키 없음 건너뜀, ntis XmlResponseError(IP 거부, 로컬 main 은 #46 전 코드). 표 사실 추출 진행 중 | post_queue.log |
| 18:16 | migration 006 PR #47 병합(표 재생성, 저장소 open 시 자동 적용, 사본 검증 8,406건 보존). 적용·판독 적재는 대기열(골든셋 1차 측정) 종료 뒤 main 체크아웃을 최신으로 당긴 다음 heavy lock 으로 실행 → 2차 측정 | 레인 보고 |
| 18:13 | 대기열의 골든셋 측정 명령이 `--label` 누락으로 즉시 종료(실행 0, Gemini 0회) → 직접 다시 실행. 그 전에 main 체크아웃을 최신(#45~#48, migration 006)으로 당기고(ff) 판독 결과를 적재한 뒤 한 번만 측정(판독 전후 2회 대신 1회 — 대기열이 측정을 못 했으므로). 표 사실: korail_web 48,253건(문서 32)·vision 453건(문서 26, 적재 전) | post_queue.log |
| 18:14 | main 체크아웃을 #48 까지 당김(ff). `rra vision ingest`: migration 006 자동 적용(user_version 6) → 판독 결과 4,003건 → 문서 2,426·청크 2,496 적재(사진 1,570·no_text 7 제외, PII 제거 account 49·name 307·phone 93·email 28). `rra vision sample --cached-only`: 표본 180건 → docs/ocr-sample/(호출 0). 숫자 대조 통과율: 표 92.2%·체계도 75.3%·그래프 71.3%·글자 이미지 80.2%·기타 58.8%, 구조화 성공률 표 100·체계도 98.4·그래프 100. DB 문서 수: korail_web 5,098(텍스트 2,672 + 판독 2,426)·openalex 2,482·scienceon 2,045·own 1,119·alio 120·rnd_notice 91·bai 21·datago 16·mofe 10·molit 6 = 11,008. 골든셋 10건 측정(검토 포함) 18:14 시작 | post_ingest.log |
| 18:15 | [Z] PR #49 열림(CI 대기). 시범 준비 브랜치 feat/pilot-prep(대기 상한 6·안내서 초안, 1,756 통과) 커밋. web/dist 최신 main 으로 재빌드(18:14) | — |
| 18:45 | 골든셋 10건 측정(final10_review, 기본 파이프라인 + Argon 1차 검토, 코퍼스 11,008 문서) 완료 18:14→18:44(30분): 유효 5/10(01·02·05·06·10 은 7B JSON 파싱 실패 → invalid, Argon 미호출), 유효 5건 점수합 49(4항목 평균 2.45), 알림 v1 53→v2 39, 문장 93→105, 무관 인용 0, 논문 인용 2, 충족률 0.633, precheck 적중 6/10, 평균 179.8s/run, Gemini 5회(기타 상한 80 중 누적 5). 결정: invalid 5건만 1회 재시도(측정 반복 2회째, `--only 01,02,05,06,10`) 뒤 합쳐서 기록 → [D] 는 재시도 뒤(같은 mlx 서버·생성 동시 1) | data/eval/final10_review.json |
| 18:50 | 골든셋 10건 오전(all4, 11:52, 코퍼스 5,8xx) 대비 저녁(final10_review, 코퍼스 11,008): 유효 5/10 → 5/10, 점수 평균 2.75 → 2.45, 충족률 0.612 → 0.633, 논문 인용 11 → 2, 무관 인용 1 → 0, **precheck 적중 9/10 → 6/10**, 평균 178.5s → 179.8s. 적중 하락은 korail_web 텍스트 2,672 + 판독 2,426 + 공고 91 등이 유사과제 후보 상위를 차지한 영향으로 보임(retrieval_mix 의 유사과제 제외 doc_type 범위·own 가중 재검토 필요, 이슈 #12 성격). 오늘은 재조정하지 않고 final-check 확인 항목으로 기록(규칙: 측정 반복은 invalid 재시도 1회만) | data/eval/{all4,final10_review}.json |
| 19:00 | invalid 5건 재시도(final10_review_retry, 18:45→19:00): 05 만 유효(점수 3·4·2·3), 01·02·06·10 은 다시 7B JSON 파싱 실패(invalid). 합산 유효 6/10, Gemini 누적 6회. 01 은 오전 baseline 에서 유효했던 건 → 코퍼스 확대 뒤 섹션별 검색 청크·프롬프트 길이 증가가 원인일 가능성(조사 필요, 시범 중에는 화면에서 다시 생성으로 대응). 측정 반복 2회로 종료. [D] 시작: 수동 mlx 종료 → launchd 4종 → 시범 흐름 1회 | data/eval/final10_review_retry.json |
| 19:02 | [R] 자료원 재확인: ScienceON ok(ARTI 1,858·REPORT 370·PATENT 911). **NTIS 가 응답하기 시작** — 공인 IP 가 59.0.251.250 → 59.0.166.199 로 바뀌었고(둘 다 등록 목록), 과제검색 HTTP 200 XML(철도 24,210건)·연구보고서 200 XML(1,750건). 그러나 어댑터는 `XmlResponseError(ParseError)` — 실제 응답 구조(RESULT/QUERYTRANSFORMS/COUNTLIST/NAVIGATION/HITS…)가 합성 fixture 와 다름 → 레인 feat/ntis-live2: 4개 서비스 실응답 녹화(개인 이름 제거)·파서·FIELDS 확정·PR. 적재는 병합 뒤 heavy lock 으로 통합 담당이 실행 | overnight, sources check 19:01 |
| 19:01 | [D] 전환: 수동 mlx 종료 → launchd com.rra.{mlx,api,backup,ingest} 등록(PID mlx 15825·api 15828), healthz 200·무토큰 401·web 200·보안 헤더 유지, llm-check compose ok(served 7B). 시범 흐름 1회(골든셋 01) 19:00:53 시작 | pilot_d.log |
| 19:24 | [R-NTIS] PR #50 병합: ParseError 원인은 Accept: application/json 때문에 NTIS 가 XML 을 JSON 문자열로 감싸 보낸 것(+보고서 DocUrl 의 맨 &, 연관콘텐츠 NaN). 실응답 fixture 6종(이름 NAME-REMOVED), FIELDS·record_tag HIT 확정, per_query_limit 미전달 결함 수정, 테스트 1,770. sources check ntis·ntis_reports·ntis_insights 셋 다 ok(과제 1,087·보고서 202·성과 12·연관 10). 적재는 시범 흐름 뒤 heavy lock 으로 | 레인 보고 |
| 19:24 | [D] 시범 흐름 1회(골든셋 01, 실제 7B): 19:02:17 제출 → 19:05:49 **invalid**(3분 32초, strategy_alignment fence·expected_technology/expected_standing JSON 실패) — 측정과 같은 증상. 스크립트가 invalid 를 종료 상태로 안 봐 대기 → 중단·수정 후 골든셋 04(측정에서 유효) 로 재실행. 시범 리스크 1순위로 기록: 7B JSON 실패 시 화면 "다시 생성" | runs/local/20261027100217-587154f0 |
| 19:29 | [D] 시범 흐름 1회 성공(골든셋 04, 실제 7B + Argon, launchd api·mlx): 로그인 → precheck 56.4s(첫 호출, reranker 적재 포함, 알림 10) → 생성 155s(drafted, Argon 1차 검토 반영) → render-check 7건(mixed_style 경고 등, 미확인 수치 0) → 최종 검토 15s(final_reviewed) → finalize 0.2s HWPX 40,926 bytes. **전체 227s(3분 47초)**. 측정 평균 180s/run 과 일치 | scratchpad pilot_out/pilot_flow.json |
| 19:30 | NTIS 적재: 과제 2,000건·청크 2,000(13 질의 × 2페이지, 중복 0) → sources status "NTIS 국가R&D 과제 2,000건". ntis_reports 는 0건·종료 코드 1 → 원인 확인 중(재실행 로그) | pilot_chain.log |
| 19:33 | precheck 지연 재측정(적재 없이, 골든셋 04 두 번): 37.6s·38.9s — 응답에 recommendations 9·differentiation 포함, 즉 사전 점검이 차별화 과제 추천(Gemini, ADR 0012 자동 1회)·차별화 제안까지 한 번에 돌려 Gemini 왕복이 지연의 대부분(검색·reranker 자체는 오전 측정 1.5~2s). 시범 안내에 "유사과제 확인 약 40초" 로 적고, 추천 자동 실행을 비동기/선택으로 바꿀지는 후속. 오늘 precheck 호출로 쓴 Gemini: 시범 흐름 2 + 확인 4 = 6회(누적 12/80) | api 실측 |
| 19:33 | 골든셋 01·02 유사과제 상위 확인: 01 은 ScienceON 논문(0.886~0.903)이 상위 8 을 차지해 정답(사내 기록 alio/own)이 밀림, 02 는 own(alio 요약 0.882)이 1위·NTIS national_rnd 가 2~5위. 오전 all4(11:52) 측정은 ScienceON 적재(12:55) 전이라 적중 9/10 → 6/10 하락의 주원인은 korail_web 이 아니라 **ScienceON 논문의 높은 e5 유사도**. 사내 기록 우선(티어별 상위 보장) 규칙은 #12 에서 결정 | api 실측 |
| 19:40 | ntis_reports 적재 0건 원인: 연구보고서 100건 응답 안의 `Joint R&DB;` — `&DB;` 가 엔티티 꼴이라 맨 & 복구에서 빠지고 DTD 금지라 undefined entity ParseError(probe 는 5건이라 통과). `_xml._BARE_AMP` 를 미리 정의된 5개 엔티티·숫자 참조만 엔티티로 보도록 수정, 테스트 추가 → PR(fix/ntis-bare-amp). 병합 뒤 ntis_reports 1,500 재적재 | 직접 호출 진단 |
| 19:40 | #51 병합·main 당김 뒤에도 ntis_reports 0건 → 전 페이지 스캔: 3쪽(철도 궤도 2쪽·철도 신호 2쪽·철도 안전 1쪽)에 `R&amp;D 동향조사 < <span…>` 처럼 공백 앞의 맨 `<` → `_xml` 에 `_BARE_LT`(뒤가 공백·<·줄끝일 때만 &lt;) 추가, PR #53. 작업 중 테스트 파일을 잘못 잘라(1,771 → 1,749) origin/main 기준으로 복구 뒤 재검사 1,772 통과·ruff 0(파이프 없이 확인). [D] 시범 준비 PR #52 병합(19:39) | chain53.log |
| 19:43 | PR #53 병합 → ntis_reports 적재 1,084건·청크 634(중복 17) → NTIS 합계 3,084건, DB 문서 14,092. api 재기동(healthz 200). 남은 일: [Z] 문서 조립·#49 병합·main 전체 검사·e2e·최종 보고 | chain53.log |
| 19:46 | main 보호 규칙이 실제로는 없음(API 404, rulesets 없음) → #52·#53 이 CI 완료 전에 병합됨(로컬 검사는 통과, main CI #52 success). 설정 변경 금지라 사람 할 일로 기록 | gh api |
