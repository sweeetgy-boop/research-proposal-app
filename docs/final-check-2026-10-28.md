# 2026-10-28 오후 작업 — 판단 기록과 사람 할 일

지시(13:0x): [0] 상태 확인 · [1] 맥 항상 켜짐 · [2] 그림 말로 고치기 = 명세 변경 · [3] Argon 먼저 작성 · [4] 실시간 검색 · [5] 통합 측정·배포 · [6] 보고.
레인 현황은 `docs/overnight-2026-10-28.md` "오후 레인" 표.

## 내가 할 일 (사람)

- (해당 시 추가)

## 판단 기록

| 시각 | 항목 | 판단 | 근거 |
|---|---|---|---|
| 13:05 | [0] 운영 버전 | api `a7c2e5f`(그림 #63 + 배포 시험 수정 #64~#66), main `8eced26` 은 문서만 → 최신과 같음. `figures.enabled: true`, 하단 "버전 a7c2e5f · 배포 10-28 12:02" (12:08 브라우저 확인) | healthz, `docs/history/deploys/2026-10-28-1202.md` |
| 13:05 | [0] NTIS IP | 현재 공인 IP `59.0.251.250` = 등록 IP 중 하나 → 이 시각 정상. 회선 IP 가 59.0.166.199↔59.0.251.250 로 바뀌고 오늘 오전 한때 `106.101.9.45`(미등록) 로 조회된 로그가 있다 → 고정 IP 확보 권장(아래 할 일) | api.ipify.org, rra-api.err.log `ntis_insights.ip_blocked 106.101.9.45` |
| 13:10 | [0] public_origin | `https://rra.ai-edu-lab.co.kr` → `https://rra.taile5afcf.ts.net` (외부 주소 실제 경로). Secure 쿠키·Origin 검사가 이 주소 기준이 된다. 반영 = PR 뒤 deploy | config/api.yaml |
| 13:10 | 레인 배정 | A `feat/figure-edit-spec`([2] + 그림 명세 생성을 Argon 으로 — 원래 [3] 항목이지만 그림 조립 함수 충돌을 피하려고 A 가 맡음), B `feat/argon-first`([3] 백엔드), C `feat/live-search`([4] 백엔드, B 병합 뒤 흐름 파일 통합), D `feat/web-argon-live`([3]·[4] 화면). B·C 응답 형태는 통합 담당이 미리 정해 D 와 공유 | 레인 지시 |
| 13:10 | 정책 | 외부 LLM 전송: Argon 작성도 검토와 같은 규칙(직원 public+internal, 공용 계정 internal 제외), manifest 섹션별 범위 기록, 안내 문구 없음. 실시간 검색 결과 visibility=public, 도메인은 ScienceON·NTIS·OpenAlex 만(이미 allowed_domains) | 지시 [공통 규칙] |
