# 2026-10-28 오후 작업 — 판단 기록과 사람 할 일

지시(13:0x): [0] 상태 확인 · [1] 맥 항상 켜짐 · [2] 그림 말로 고치기 = 명세 변경 · [3] Argon 먼저 작성 · [4] 실시간 검색 · [5] 통합 측정·배포 · [6] 보고.
레인 현황은 `docs/overnight-2026-10-28.md` "오후 레인" 표.

## 내가 할 일 (사람)

- **[급] Tailscale Funnel 다시 등록**(15:4x, 외부 접속 장애의 주원인): `funnel status` 는 on 인데 인터넷 쪽에서 TLS 가 끊긴다. 운영 맥 터미널에서 `/Applications/Tailscale.app/Contents/MacOS/Tailscale funnel --https=443 off` → `… funnel --bg --https=443 http://127.0.0.1:8000`, 안 되면 Tailscale 앱 재실행 → 관리 콘솔 nodeAttrs `funnel`·HTTPS 인증서 확인. 확인은 휴대폰 데이터망 또는 check-host.net(이 맥에서 하는 확인은 tailnet 경로라 소용없음). 절차 pilot-guide §1.5.
- **NTIS 활용신청 IP**: 13:05 현재 공인 IP `59.0.251.250` 은 등록돼 있다. 다만 이 회선은 IP 가 바뀌고(59.0.166.199↔59.0.251.250, 오전 한때 `106.101.9.45` 로그) 미등록 IP 일 때 NTIS 가 빠진다 → 고정 IP 확보 또는 바뀔 때마다 활용신청·`config/sources.yaml ntis.registered_ips` 갱신.
- **공용 계정 실제 로그인**: 비밀번호를 몰라 성공 경로는 확인하지 못했다(켜짐·틀린 비밀번호 통일 문구 401 은 확인). 외부 주소에서 한 번 로그인해 보기.
- **NTIS IP 반영 확인**: 레인 C 실호출(14:xx)에서 현재 IP `59.0.251.250` 이 `registered_ips` 에 있는데도 NTIS 가 "접근 허용 IP가 아닙니다" → 활용신청 페이지에서 등록 IP 가 실제 반영됐는지(서비스별: 과제·보고서·성과) 확인. 그 전까지 실시간 검색·② NTIS 는 건너뛰고 화면 자료원 상태에 "IP 차단"으로 보인다.
- 맥 덮개를 닫지 않기(외부 모니터 없이 닫으면 caffeinate 와 관계없이 잠들 수 있다). 수동으로 띄운 caffeinate 2개(PID 44521·44855)는 이제 launchd `com.rra.awake` 가 대신하므로 꺼도 된다.

## 판단 기록

| 시각 | 항목 | 판단 | 근거 |
|---|---|---|---|
| 13:05 | [0] 운영 버전 | api `a7c2e5f`(그림 #63 + 배포 시험 수정 #64~#66), main `8eced26` 은 문서만 → 최신과 같음. `figures.enabled: true`, 하단 "버전 a7c2e5f · 배포 10-28 12:02" (12:08 브라우저 확인) | healthz, `docs/history/deploys/2026-10-28-1202.md` |
| 13:05 | [0] NTIS IP | 현재 공인 IP `59.0.251.250` = 등록 IP 중 하나 → 이 시각 정상. 회선 IP 가 59.0.166.199↔59.0.251.250 로 바뀌고 오늘 오전 한때 `106.101.9.45`(미등록) 로 조회된 로그가 있다 → 고정 IP 확보 권장(아래 할 일) | api.ipify.org, rra-api.err.log `ntis_insights.ip_blocked 106.101.9.45` |
| 13:10 | [0] public_origin | `https://rra.ai-edu-lab.co.kr` → `https://rra.taile5afcf.ts.net` (외부 주소 실제 경로). Secure 쿠키·Origin 검사가 이 주소 기준이 된다. 반영 = PR 뒤 deploy | config/api.yaml |
| 13:10 | 레인 배정 | A `feat/figure-edit-spec`([2] + 그림 명세 생성을 Argon 으로 — 원래 [3] 항목이지만 그림 조립 함수 충돌을 피하려고 A 가 맡음), B `feat/argon-first`([3] 백엔드), C `feat/live-search`([4] 백엔드, B 병합 뒤 흐름 파일 통합), D `feat/web-argon-live`([3]·[4] 화면). B·C 응답 형태는 통합 담당이 미리 정해 D 와 공유 | 레인 지시 |
| 13:10 | 정책 | 외부 LLM 전송: Argon 작성도 검토와 같은 규칙(직원 public+internal, 공용 계정 internal 제외), manifest 섹션별 범위 기록, 안내 문구 없음. 실시간 검색 결과 visibility=public, 도메인은 ScienceON·NTIS·OpenAlex 만(이미 allowed_domains) | 지시 [공통 규칙] |
| 13:14 | [0] 반영 | PR #68 병합 → `tools/deploy.sh --wait`(대기 run 0) → `ab17faa`. 외부 주소: 로그인 화면 200, 직원 로그인 200(시험용 사번 등록→로그인·세션·자기 run·로그아웃→삭제, 82건 유지), 쿠키 Secure·HttpOnly·SameSite=Strict 확인(전에는 Secure 없음), 미등록 사번·공용 계정 틀린 비밀번호 401 통일 문구 | `docs/history/deploys/2026-10-28-1314.md` |
| 13:13 | [1] 맥 항상 켜짐 | `com.rra.awake`(caffeinate -dimsu) 등록·기동 PID 67659, `pmset -g assertions` PreventSystemSleep·PreventUserIdleSystemSleep·PreventUserIdleDisplaySleep = 1. 끄기 `deploy/README.md` §2 | launchctl list |
| 13:16 | 18:07 예약 | 그림 골든셋 예약(2bf156ec)을 지우고 [5]-C(local_check on) 측정 예약(6b6547d2)으로 바꿈 — 세션 전용 | CronCreate |
| 14:0x | [2] 병합 | PR #70: 말로 고치기 = Argon 명세 변경 → 검사(생성과 같음) → 새 밑그림 → Nano Banana. 현재 그림은 보내지 않음. 글자 변형 편집 1회당 2~3자 → 6회 합계 1자("점검→정검" 1회), 1회 31~41초(중앙값 32.8), 요청 반영 6/6. 그림 명세 생성도 Argon→로컬 순서. ADR 번호: A=0030, C=0031, B=0032 로 정리 | `docs/eval-2026-10-28-figure-edit.md` |
| 14:0x | [3] 웹 선반영 | PR #69(D): 섹션 "로컬 작성" 배지·실시간 검색 배지·자료원별 상태. 문장 origin `llm` 라벨을 "로컬 작성" → "AI 작성"(Argon 작성 문장과 구분) | PR #69 |
| 14:4x | [3] 병합 | PR #71: 섹션 Argon 작성(4 동시)·실패 섹션만 로컬(사유 error·rate_limit·budget·invalid)·`review.first_pass: off`(self_review)·`compose.local_check` off(측정 전)·Gemini 일일 600·`config/runs.yaml max_concurrent: 3`(로컬 단계만 전역 슬롯). 보안 G "생성 동시성 1" 은 Argon 작성 한정으로 완화(소유자 지시). 가짜 모드는 1차 검토를 켠 채(기존 e2e 호환) | ADR 0032 |
| 14:4x | 그림 로컬 대체 | B 가 그림 단계를 전역 슬롯 밖으로 뺐으나 그림 명세의 로컬 대체 호출이 슬롯 없이 돌 수 있음 → A2 `fix/figure-local-slot` 로 로컬 호출만 슬롯 안에 | 레인 B 보고 |
| 14:4x | e2e 수정 | #71 CI 에서 "옛 run" e2e 실패(가짜 백엔드가 이제 writer 를 돌려줌) → 시험이 응답에서 새 필드를 빼고 확인하도록 고침(통합 담당) | PR #71 커밋 |
| 15:xx | [4] 병합 | PR #72: 실시간 검색(키워드 Argon 4초, ScienceON 30건 7.3초, OpenAlex 30건 1.2초, NTIS ip_blocked, 캐시 0.00초). 가짜 모드 기본 꺼짐(기존 e2e 고정). 실시간 문서 보존·만료 규칙은 미정(후속) | ADR 0031 |
| 15:xx | 그림 로컬 슬롯 | PR #73: 그림 로컬 대체 호출만 전역 슬롯 안. 로컬 작성 run 은 이미 슬롯을 잡고 있어 다시 잡지 않음(교착 방지) | PR #73 |
| 15:xx | 공유 파일 | openapi 재생성(48 경로), status.md·timeline·metrics·CLAUDE.md 에 #69~#73 반영 | docs/integrate-2026-10-28-pm |
| 14:1x | [5] 도구 병합 | PR #75: `rra eval --final-review --finalize --concurrent N --local-check on/off`, [5] 비교표. 통합 담당 실수: 병합 조건이 맞지 않았는데 원격 브랜치를 지우는 명령이 함께 실행돼 #75 가 닫힘 → 같은 커밋을 다시 올리고 PR 재개·CI 통과 뒤 병합(손실 없음). 이후 브랜치 삭제는 MERGED 확인 뒤에만 | PR #75 |
| 14:2x | 측정 예산 분리 | 운영 api(ab17faa)는 Gemini 일일 300·그림 150 카운터(`data/cache/llm_budget.json`·`figure_budget.json`)를 보는데 측정 3종은 400회 이상 → 측정은 설정 사본(`RRA_CONFIG_DIR`, 카운터만 `*_eval.json`)으로 돌려 동료의 검토·그림 호출을 막지 않게 함. 실제 Gemini 키·분당 제한은 같음 | scratchpad evalcfg |
| 14:2x | [5]-B 시작 | `rra eval --label argon_b --local-check off --finalize`(골든셋 10, 실시간 검색·그림 켬, 무거운 작업 잠금) — 실시간 결과는 운영 DB 에 public 으로 저장된다(정책대로) | data/eval/argon_b.json |
| 14:28 | [5]-B 1차(실시간 검색 빠짐) | 골든셋 10: 유효 10/10·빈 초안 0·② 3.0s·생성 99.4s·최종 점수 4.12·수치 알림 42·유사과제 9/10·그림 30/30 Nano Banana(건너뜀 2)·HWPX 10/10·Gemini 작성 109·검토 10·그림 30·로컬 대체 0. 단 `build_eval` 이 실시간 검색을 연결하지 않아 실시간 인용 0/114 → `argon_b_nolive` 로 보관, PR #76 으로 고친 뒤 재측정 | data/eval/argon_b_nolive.json |
| 14:4x | [5]-B 재측정·동시 3건 | #76 병합 뒤 B 재측정(10건) → 이어서 골든셋 01~03 동시 3건 | data/eval/argon_b.json, argon_b_c3.json |
| 14:55 | [5]-B 결과 | 유효 10/10·빈 초안 0·② 15.6s(실시간 대기 포함)·생성 107s·최종 점수 4.30·수치 알림 38·실시간 인용 20%·유사과제 9/10·그림 94%·Gemini 1건 약 15회·HWPX 10/10. NTIS 실시간 100% IP 차단 | `docs/eval-2026-10-28-argon-live.md` |
| 14:56 | 동시 3건 사고 | 동시 3건 측정이 1분 만에 SIGABRT(`MTLCommandBuffer` 단언) — 임베딩·reranker 가 모델별 잠금이라 두 스레드가 동시에 Metal 사용. 운영(max_concurrent 3)이면 api 가 죽는다 → PR #77 프로세스 공용 GPU 잠금 | PR #77 |
| 15:03 | 동시 3건 재측정 | 3/3 유효·HWPX 3/3·묶음 266s(같은 3건 순차 401s, 34% 단축)·1건 240s(순차 평균 134s) — Gemini 공용 제한기 동시 4 를 나눠 씀. 시범 3명 규모에서는 그대로 둠(호출 제한기 상향은 Gemini 분당 한도 확인 뒤) | data/eval/argon_b_c3.json |
| 15:1x | [5]-3 배포 판단 | 기준(빈 초안 0, 유효 9/10+, 유사과제 9/10+, 생성 완료 단축 195→107s, HWPX 정상)을 B 가 모두 충족 → 배포. local_check 는 기본 끔 유지 — 18:07 C 측정에서 걸러 내는 것이 의미 있으면 그때 켬 | 이 표 |
| 15:1x | [5]-4 시범 안내 | pilot-guide §2·§3·§5.5·§6.5 를 Argon 작성·실시간 검색 배지·동시 3건·그림 말로 고치기로 고침 | docs/pilot-guide.md |
| 15:11 | [5]-3 배포 | `tools/deploy.sh --wait`(대기 run 0) → `4406e89`(#69~#78). 외부 주소 직원 로그인·공용 계정 거부 경로·하단 버전 확인, 실제 흐름 1건 성공(생성 111s·그림 3장 Nano Banana·최종 5/5/5/4·HWPX 정상) → 유지 | `docs/history/deploys/2026-10-28-1511.md` |
| 15:16 | ② 시간 | 배포 직후 첫 ② 69.7s — 모델 적재 + 실시간 검색 대기(최대 15s) + 자동 추천·차별화(Gemini). 이어진 ② 는 측정에서 15.6s(B 평균). 시범 중 동료가 느끼면 `live_search.wait_seconds` 를 줄이거나 자동 추천(`llm.yaml recommend.auto`)을 끄는 것을 검토 | 위 기록 |
| 15:3x | 외부 접속 장애 | 원인 조사(1차): Funnel on·공개 DNS 2개. 앱 쪽 결함 — Funnel 경유는 peer 가 전부 127.0.0.1 이라 로그인 IP 잠금(10분 20회)을 모든 외부 접속자가 한 키로 나눠 씀 → 누군가 미등록 사번으로 여러 번 시도하면 전원이 잠김. 거부·4xx 로그는 INFO 라 uvicorn warning 설정에서 버려져 상태 코드별 집계 불가였음. 수정: `X-Forwarded-For` 맨 오른쪽(127.0.0.1 peer 일 때만, `api.yaml trust_forwarded_from_loopback`), 접속자 IP 모르면 IP 잠금 없음(계정 잠금·전체 지연 유지), `rra.api.*` INFO 로그 + 4xx/5xx 접근 로그, `rra auth staff check`, deploy.sh "Funnel on" 확인(읽기만), pilot-guide §1 주소 정정(Tailscale 앱 설치 불필요)·§1.5. 접속 차단 수정이라 즉시 배포 | `fix/funnel-access` PR |
| 15:4x | 외부 접속 — 공개 경로 | **정정**: 앞서 "외부망 healthz 정상"으로 본 WebFetch 는 이 맥에서 실행돼 tailnet 경로였다(배포 후 로그 ip=100.74.2.113 = 이 맥의 Tailscale 주소). 외부 점검 사이트(check-host.net) 노드 8곳(스위스·독일·포르투갈·터키·오스트리아·미국·이란·네덜란드)에서 `https://rra.taile5afcf.ts.net/healthz` → 공개 진입 IP 103.84.155.153·.217 둘 다 **TLS 단계 "Broken pipe"(0.3~0.8초)**, 앱 로그에 도달 0건. Funnel 설정·funnel 권한·인증서 도메인·Running·방화벽 꺼짐·shields-up 꺼짐은 정상, 그러나 funnel-ingress-node 23개와 handshake·바이트 0 → **Funnel 중계가 이 맥으로 넘기지 않는 것이 주원인**(앱 잠금은 그다음 문제). Funnel 다시 등록(off→on)은 자동 실행 권한이 막혀 사람 작업으로 넘김 | pilot-guide §1.5 |

# 시범 오류·개선 17건 (2026-10-28 16:1x~) — 판단 기록

| 시각 | 항목 | 판단 | 근거 |
|---|---|---|---|
| 16:1x | 레인 배정 | A feat/precheck-flow(5·6·7·8), B feat/edit-ai(1·9·13·14·15), C feat/figures-v2(3·4·10·11), D feat/format-ui(12·2·16·17). 웹: 레인마다 새 컴포넌트 파일, 공용 틀(RunLayout·Stepper·App 라우팅)은 D, 새 응답 타입은 `web/src/api/types-<레인>.ts`. 그림 캡션 12pt·가운데는 HWPX 서식을 맡은 D 가 한다(C 와 hwpx.py 충돌 방지) | 레인 지시 |
| 16:1x | 실호출 예산 | 레인 실호출은 운영 일일 카운터와 분리(`llm_budget_lane<X>.json`·`figure_budget_laneC.json`, RRA_CONFIG_DIR 복사본). 상한: A Gemini 80, B 100, C Gemini 80·그림 30, D 0. mlx·실제 생성은 레인에서 금지(시범 중) | 레인 지시 |
| 16:1x | 16번 run 20261028070108-e98b2c54 작성 시간 | **실제 섹션 작성은 20초**(첫 섹션 +19s → 마지막 +39s, 12섹션 모두 Argon, 로컬 대체 0, 재시도 0, Gemini 14회). 화면 "사용 기록"의 sections 73초는 섹션별 시간의 **합**(4개 동시 작성), 전체 196초는 생성(74초: 검색 11·섹션 20·그림 35)에 최종 검토·마무리까지 사람이 머문 시간을 더한 값. 같은 시각 다른 run 없음(다음 run 은 07:04 시작). → 느린 것이 아니라 표시 문제: D 가 섹션 작성을 실제 경과 시간으로, 전체를 "전체 경과(사람 작업 포함)"로 표시 | `runs/staff-…/20261028070108-e98b2c54/manifest.json`·`usage.json`, `domain/rules/usage.step_durations` |
| 18:0x | C 병합 #81 | 양식에 "연구배경 및 필요성" 칸이 없어 As-Is/To-Be 는 2-나 연구목적 뒤(비면 2-가-(2) 기술적 중요도 뒤). 델파이·체계적 문헌고찰은 넷째 군 "연구 절차"(등급 없음). 정성 기법의 상·중·하도 판단이라 기법 그림 전부 "제안 내용 기반 예비 평가" 표시. 4장 초과 시 사실 그림 우선(As-Is/To-Be → 수치 → 일정 → 기법). 남은 문제: 큰 글씨에서 일부 글자 뭉개짐(2곳) — 자동 검사 없음, "확인 전" 배지·제출 전 점검으로 잡음. ADR 0033 은 C 가 씀 → D 의 ADR 은 0034·0035 로 바꿔 합친다 | PR #81, ADR 0033 |
| 18:3x | D 병합 #82 | HWPX 서식은 템플릿을 다시 만들지 않고 렌더 결과를 단계별 서식으로 고친다(ADR 0034). 내어쓰기 폭은 어림값 — 한/글에서 1건 열어 확인 필요(사람). 입력 변경 다시 쓰기는 근거를 다시 검색하지 않음(보안 A 대조 집합 유지, ADR 0035). CI 에서 그림 일정 알림 코드(#81) 설명 빠짐 → 보충 | PR #82 |
| 18:4x | A 병합 #83 | 판정 = reranker ≥ 0.5 + 아이디어 핵심 키워드 ≥ 1, 상위 10건 Argon 같음 판정(제한 40초, 실패 시 로컬 → 규칙). **정답 차단 9/9 → 4/9**: 골든셋 정답 대부분을 AI 가 "일부 겹침"으로 보고 근접으로 남김(차단 62행 → 9행). 상위 5 적중은 10/10 유지, 거짓 차단 1/3 → 0/3. 시범 피드백(무관 차단)을 우선해 채택 — 실제 중복 과제를 근접으로 낮추는 위험은 [유사함] 선택·근접 표시로 제안자가 본다. 차단 자동 활용·차별화 제안은 [유사함] 선택 뒤에만 | PR #83, `docs/eval-2026-10-28-precheck-v2.md`, ADR 0036 |
| 18:1x | [5]-C 측정 | 따로 재지 않는다: 그사이 main 에 #81~#83 이 들어와 C(로컬 검사 켬)를 지금 재면 배포본(B)과 코드가 달라 비교가 섞인다. 17건 최종 골든셋 측정에서 로컬 검사 끔/켬을 같은 코드로 함께 재고, 그 결과로 local_check 기본값을 정한다(mlx 측정 1회로 줄임) | 예약 1a660897 취소 |
