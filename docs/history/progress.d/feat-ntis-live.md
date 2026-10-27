# 레인 N 진행 기록 — feat/ntis-live (2026-10-27)

- 13:20 시작. worktree `.env` 복사(600). `rra sources check --source ntis` → 왕복 "ok" 0.5 s 인데 total=None·record_tag 후보 없음.
- 13:25 녹화 도구로 본문 확인: HTTP 200, `text/plain;charset=UTF-8`, 본문 `<error>접근 허용 IP가 아닙니다.</error>` (70~91 바이트).
  키는 받아들여졌고(키 오류 문구 아님) **호출 IP 가 활용신청 등록 IP 와 다름**. 기존 client 는 `ERROR_CODE` 류 요소만 보고 이를
  "ok" 로 올리는 결함 → `<error>` 루트·`resMsg/verifyFlag` 형식을 NtisError 로 바꾸기로.
- 13:35 공개 매뉴얼 확보(data.go.kr 참고문서 PDF): 과제검색(2021-02-08)·연구보고서 검색(2021-12-28). 레코드 요소 **HIT**,
  TOTALHITS, 과제 필드 ProjectNumber·ProjectTitle/Korean·Goal|Abstract|Effect/Full·ResearchAgency/Name·ProjectPeriod/TotalStart…
  연구보고서 `rresearchpdf/` (query·searchField·displayCount·returnType). 성과검색 `public_result`(collection rpaper·rpatent,
  addQuery DBT=PAP|PAT)·연관콘텐츠 `ConnectionContent`(pjtId, JSON) 는 공개 구현(kisti-mcp) 기준 — 매뉴얼 미확보.
- 13:40 서비스 4개 실호출 1회씩(과제·성과(rpaper)·연구보고서·연관콘텐츠): 모두 HTTP 200 + `<error>접근 허용 IP가 아닙니다.</error>`
  0.13 / 0.43 / 0.50 / 0.52 s. 같은 실패 ×3 이상 → 접근 변경: 매뉴얼 형식의 **합성 fixture** 로 코드·테스트를 마치고 끝에 재시도.

## [자동 진행] 판단
- 실호출 실패 원인: 활용신청에 등록된 서버 IP ≠ 현재 공인 IP (HTTP 200, 본문 `<error>접근 허용 IP가 아닙니다.</error>`, 오류 코드 없음).
  키 값은 어디에도 기록하지 않음. 조치: 사람이 NTIS 서버 IP 를 현재 공인 IP 로 변경(status 조각 "내가 할 일").
- source 이름은 `ntis` 유지, 자료 종류는 `raw.kind=national_rnd`·티어 `national_rnd` 로 구분 (status 조각·ADR 0020 에 이유).
- 13:30 설계·코드: `<error>`/`resMsg` 판별(`NtisClient`), 과제 FIELDS 매뉴얼 확정·이름 미저장·강조 태그 제거(`_xml.flatten` span 잎),
  연구보고서 소스(`reports.py`, `ntis_reports`), 성과·연관(`insights.py`, 포트 `ports/ntis.py`, 유스케이스 `ntis_insights.py`, 규칙 `domain/rules/ntis_insights.py`),
  파일 캐시(`persistence/file_cache.py`), 티어 `national_rnd`(gap/overlap/labels), 보고서 교차 중복(dedup), REST `POST /v1/precheck/ntis-outcomes`·views,
  composition(`build_ntis_report_source`·`build_ntis_insights`·sources check `ntis_reports`), `sources.yaml ntis` 재작성(질의 13·insights).
- 13:38 합성 fixture 5종 + README·meta, 녹화 도구 `strip_ntis_names`·`ntis_reports`. 테스트: adapters 28·domain 12·application 4·api 2 추가, skip 2건 해제.
- 13:42 전체 검사: pytest 1,522 passed·16 skipped(-n auto), lint-imports 8 kept, ruff clean(E501 은 한글 폭 2 기준으로 재줄바꿈). 드라이런
  `RRA_DB_PATH=<임시> ingest --source ntis --limit 5` → `[ntis] 실패: NtisError` 저장 0 (IP 차단). docs 조각(status·timeline·metrics·ADR 0020·external-apis) 작성.
- 13:43 작업 끝 재시도 `sources check --source ntis,ntis_reports` → 둘 다 `NtisError: 접근 허용 IP 아님` (0.5 s, 변화 없음). Accept 헤더에
  application/json 이 없으면 오류 한글이 `?` 로 깨져 온다 → XML_TYPES 에 추가(확인 호출 2회).
