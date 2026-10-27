## 자료원 IP 확인 (레인 I, feat/source-ip, 2026-10-27)

### 현황 행 (status.md §4 에 옮길 것)
| 레인 | 범위 | 상태 | 비고 |
|---|---|---|---|
| [I] 자료원 IP 확인 | `sources.yaml` 자료원별 `ip_restricted`·`registered_ips`, `rra sources check` 공인 IP 대조(api.ipify.org), IP 거부 응답 → 그 자료원만 건너뜀(ingest `--skip-unavailable`·사전 점검 NTIS 성과), 로그·웹 자료원 상태·`rra sources status` 에 같은 안내, `ntis_insights` 연결 확인 | 코드 완료, PR | 실호출 1회: ScienceON ok, NTIS 4개 서비스 모두 IP 거부(현재 IP 59.0.251.250 는 등록 목록에 있음) |

### 납품 목록
- domain `rules/source_ip.py` — `IpPolicy`(제한 여부·등록 IP), `is_ip_error`(NTIS 실문구 "접근 허용 IP가 아닙니다"), `ip_registered`,
  `unregistered_notice`("현재 IP <값> 가 <자료원> 등록 IP 에 없습니다. 활용신청에 추가하세요"), `SourceIpBlocked` 예외(어댑터가 하위 종류로 올린다).
- ports `PublicIpPort`(현재 공인 IP)·`SourceAvailabilityPort`(자료원별 차단 안내 기록). 어댑터 `adapters/sources/public_ip.py`(GuardedClient,
  IP 문자열만 수락)·`adapters/persistence/source_availability.py`(`<data>/cache/source_availability.json`, config_loader `_DATA_LOCATIONS` 등록).
- `ntis/client.py` — IP 거부 본문은 `NtisIpBlocked(NtisError, SourceIpBlocked)`. `ntis/insights.py` 에 `probe()`(성과 2회 + 연관 1회) → `rra sources check --source ntis_insights`.
- `usecases/diagnostics.CheckSources` — IP 제한 자료원이 왕복 가능할 때만 공인 IP 1회 조회(실패는 `ip_lookup_error` 진단만), 행에 `ip_restricted`·`registered_ips`·
  `current_ip`·`ip_registered`·`ip_notice`. 정상 왕복이면 안내 해제, 거부면 기록.
- `usecases/ingest_sources` — `SourceIpBlocked` 면 그 소스만 건너뛰고 `IngestReport.unavailable[소스]=안내`, 로그 `ingest.ip_blocked`, 가용 상태 기록.
  CLI `rra ingest --skip-unavailable` 은 IP 거부 소스를 실패로 치지 않는다(야간 적재 유지). 플래그 없으면 종전처럼 실패(종료 코드 1).
- `usecases/ntis_insights` — 첫 IP 거부 뒤 남은 호출 생략, `NtisInsights.unavailable`(REST `POST /v1/precheck/ntis-outcomes` 응답 `unavailable`), 가용 상태 기록.
- REST `GET /v1/sources/status` 행에 `notice`(차단 안내, 평소 null). 웹 `/sources` 화면: 경고 상자 + 행 배지 "호출 거부". `rra sources status` 도 `[안내]` 줄.
- 설정: `sources.yaml public_ip`(lookup_url·timeout·availability_file), `ntis.ip_restricted: true`·`registered_ips: [59.0.166.199, 59.0.251.250]`,
  `scienceon`·`openalex`·`kipris`·`g2b.yaml` `ip_restricted: false`. `security.yaml allowed_domains` 에 `api.ipify.org`(주석).

### 실호출 결과 (2026-10-27, 공인 IP 59.0.251.250 — `curl -s https://api.ipify.org`)
| 자료원 | 결과 | 비고 |
|---|---|---|
| ScienceON | ok (ARTI 1,858 / REPORT 370 / PATENT 911) | IP 제한 없음 |
| NTIS 과제검색 `public_project` | NtisIpBlocked — "접근 허용 IP가 아닙니다." | 현재 IP 가 등록 목록(설정)에 있는데도 거부 |
| NTIS 연구보고서 `rresearchpdf/` | NtisIpBlocked | 〃 |
| NTIS 성과검색 `public_result` (rpaper) | NtisIpBlocked | 〃 (`ntis_insights` probe 의 첫 요청에서 중단) |
| NTIS 연관콘텐츠 `ConnectionContent` | (성과검색 거부로 호출 안 함) | 같은 키·같은 IP 규칙 — 2026-10-27 레인 N 기록에서는 4개 모두 같은 거부 |

### 판단
- 현재 공인 IP(59.0.251.250)가 `registered_ips` 에 있는데도 NTIS 가 거부한다 → 설정 목록과 NTIS 활용신청의 실제 등록 상태가 다르거나(반영 지연·서비스별 서버 IP),
  송신 IP 가 공인 IP 조회 결과와 다를 수 있다(회선·프록시). CLI 는 이 경우 "등록 목록에는 있으나 API 가 거부했습니다" 줄을 덧붙인다.
- 안내 문구는 지시대로 "현재 IP <값> 가 <자료원> 등록 IP 에 없습니다. 활용신청에 추가하세요" 하나로 통일(CLI·로그·웹·`sources status`).

### 운영 전 해결할 것
- **API 호출 기기의 공인 IP 고정** — 전산 부서 확인 또는 고정 IP 회선의 Mac mini. IP 가 바뀌면 NTIS 활용신청의 서버 IP 와 `sources.yaml ntis.registered_ips` 를 함께 바꿔야 한다.
- NTIS 활용신청(4개 서비스)의 서버 IP 에 59.0.251.250 이 실제로 반영됐는지 확인(콜센터 042-865-1115). 반영 뒤 `rra sources check --source ntis,ntis_reports,ntis_insights`.

### 내가 할 일 (사람)
- NTIS 활용신청 서버 IP 반영 확인 → 재시도 명령 실행 → ok 가 되면 `docs/status.d/feat-ntis-live.md` 재시도 절차(녹화·합성 fixture 교체)로 진행.
- 개발 MacBook·배포 Mac mini 의 공인 IP 가 다르면 둘 다 등록하고 `registered_ips` 에도 둘 다 적는다.
