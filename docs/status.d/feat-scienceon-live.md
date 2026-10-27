## ScienceON 실연결 (레인 B, feat/scienceon-live, 2026-10-27)

### 1단계 실호출 (완료)
| target | 질의 | HTTP | 총건수 | 소요 |
|---|---|---|---|---|
| 토큰 발급 | — | 200 JSON | access·refresh 64자, 2h/2w | 0.1 s |
| ARTI 국내논문 | 철도 궤도 | 200 XML | 1,858 | sources check 전체 2.2 s (토큰+2건, 1 req/s) |
| REPORT 국내연구보고서 | 철도 궤도 | 200 XML | 370 | 〃 |
| PATENT 특허(한국) | 철도 궤도 | 200 XML | 911 | 녹화 1.3 s |

실패 → 원인 → 조치:
- `ValueError 인증키는 32바이트` — `.env` 의 `RRA_SCIENCEON_CLIENT_ID`(32자)와 `RRA_SCIENCEON_KEY`(64자)가 **서로 바뀌어 있음**
  (가이드: client_id 64자, 인증키 32자). 키 변형 시도 3회(hex 해독·앞/뒤 32자) 모두 XML E5001 → 접근을 바꿔 공식 가이드로 확인.
  **원본 `.env` 는 손대지 않았다 — 통합 세션이 두 값을 서로 바꿔 넣어야 한다.** (worktree 사본만 교체해 검증)
- `HTTP 406` — `GuardedClient` 가 Accept: application/json 만 보냄. `get_bytes` 가 `accept_types` 로 Accept 헤더를 만들도록 수정.
- 가이드와 다른 코드 가정 수정: 재발급 파라미터 `refresh_token`(refreshToken 아님), 토큰 오류가 XML 로도 옴(E5001 등), 응답
  `parameterData` 에 client_id·token 원문 포함(녹화 REDACTED 확인).

### 2단계 fixture·매핑 (완료)
- `tests/fixtures/scienceon/scienceon_{ARTI,REPORT,PATENT}_20261027_1.xml` 각 10건 + `token_shape.json`. 사람 이름 제거
  (Author·Author2·Contributors → NAME-REMOVED, 개인 출원인 삭제). 녹화 도구가 자동으로 한다.
- FIELDS 확정(`scienceon/normalize.py`): id CN · title Title(Title2) · abstract Abstract(Abstract2) · 날짜 Pubdate/Pubyear/ApplDate ·
  DOI(`https://doi.org/…` 에서 추출) · url ContentURL(http) · 기관 Affiliation·Publisher·CoResearchOrg·ManagingAgency·
  ResearchMngAgency·Applicants(기관만) → `raw.orgs_named` + `orgs` 태그(korail·krri·kr) · PATENT ApplNum→application_no, IPC→codes,
  PatentStatus→raw.status · REPORT Pjn→raw.project_no. **authors 는 항상 빈 목록**(사람 이름 미저장, KIPRIS 와 같은 규칙).
- 테스트: skip 이던 `test_scienceon_records_normalize` 3건 실행 + fixture 2건·단위 6건 추가(XML 토큰 오류, refresh_token, Accept,
  per_query_limit, 정규화 2). `is_organization` 은 `_orgs.py` 로 옮겨 KIPRIS·ScienceON 공용.
- `sources.yaml scienceon`: search_field BI 유지, targets 에 PATENT 추가, row_count 100, per_query_limit 80, 질의 13개(한국어).

### 3단계 적재 (준비만 — 통합 세션이 실행)
- 질의 13개·총건수는 `config/sources.yaml scienceon.queries` 주석. 요청 = 토큰 1 + 13 질의 × 3 target × 1 페이지 = **40회**
  (예산 48, 1 req/s → 약 45 s). 예상 적재(중복 제거 전) ARTI ≈ 940 · REPORT ≈ 870 · PATENT ≈ 590 ≈ **2,400건**;
  ARTI+REPORT 만이면 ≈ 1,800. 임베딩(초록 청크) 포함 전체 5분 안쪽 예상.
- 명령(`--limit` 기본 200 이라 반드시 올릴 것):
  ```bash
  cd /Users/chan/projects/research-proposal-app && .venv/bin/rra db backup && \
  .venv/bin/rra ingest --source scienceon --limit 3000
  ```
  1,000~2,000 으로 줄이려면 `per_query_limit: 50` 또는 `targets: [ARTI, REPORT]`. 뒤이어 `rra precheck` 로 scienceon 근거 확인.
- 드라이런 완료: `RRA_DB_PATH=<임시> rra ingest --source scienceon --limit 5` → fetched 5·normalized 5·stored 5·chunks 5, 16 s
  (임베딩 모델 로드 포함, 요청 2회). 실 DB 미접촉.

### 특허 판정 (ADR 0015)
ScienceON PATENT 를 **기본 특허 자료원**으로, KIPRIS 는 선택(키 확보 뒤 보강)으로 한다. 근거: 한국특허 911건("철도 궤도"),
필드 Title·Abstract·Applicants(기관)·ApplNum·ApplDate·PublDate·GrantDate·IPC·PatentStatus 모두 있고 **발명자 항목이 출력에
없어** 이름 제거 부담이 없다. 같은 키·같은 레이트리밋으로 논문·보고서와 함께 수집된다. KIPRIS 는 등록상태·청구항 등 상세가
필요할 때(키 확보 뒤)만 추가.

### 남은 일·대기
- (사람) 원본 `.env` 의 CLIENT_ID·KEY 값 교체. Mac mini `.env` 도 같은 확인.
- (통합) 3단계 적재 실행, `docs/status.md`·`external-apis` 표 반영, CLAUDE.md "키 대기" 문구 갱신.
- 후속: ScienceON 응답 `parameterData` 는 로그에 남기지 말 것(토큰 원문). 429 가 나오면 `max_requests_per_run` 하향.
