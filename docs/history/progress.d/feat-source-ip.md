# 레인 I 진행 기록 — feat/source-ip (2026-10-27)

- 시작. CLAUDE.md·CONTRIBUTING(조각 파일·데이터 위치)·external-apis·ntis 어댑터·diagnostics·REST sources/status·web Sources 읽음. 데이터 폴더 = 원 저장소 data/ 확인.
- domain `rules/source_ip.py` → ports(PublicIpPort·SourceAvailabilityPort) → 유스케이스(diagnostics·ingest_sources·ntis_insights) → 어댑터(public_ip·source_availability·NtisIpBlocked) 순서로 구현, fake 로 테스트.
- 조립: `build_public_ip_probe`(allowed_domains 밖이면 None)·`build_source_availability`·`build_ntis_insight_source`, `sources check` 에 `ntis_insights` 추가.
- CLI·REST·웹(`/sources` 경고 상자·배지)·`rra sources status` 안내. config: `public_ip`, `ntis.registered_ips`, 다른 자료원 `ip_restricted: false`, security `api.ipify.org`.
- 검사: pytest 1708 passed/16 skipped(+신규), lint-imports 8 kept, ruff ok, web lint·vitest 58·build ok.
- 실호출 1회(`sources check --source scienceon,ntis,ntis_reports,ntis_insights`, 5 s): ScienceON ok, NTIS 3 대상 모두 `NtisIpBlocked`. 공인 IP 59.0.251.250 (등록 목록에 있음).
  → CLI 에 "등록 목록에는 있으나 API 가 거부" 줄 추가. 가용 상태 파일에 ntis·ntis_reports·ntis_insights 안내 기록됨(원 저장소 data/cache).
