# 2026-10-28 오후 작업 — 판단 기록과 사람 할 일

지시(13:0x): [0] 상태 확인 · [1] 맥 항상 켜짐 · [2] 그림 말로 고치기 = 명세 변경 · [3] Argon 먼저 작성 · [4] 실시간 검색 · [5] 통합 측정·배포 · [6] 보고.
레인 현황은 `docs/overnight-2026-10-28.md` "오후 레인" 표.

## 내가 할 일 (사람)

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

