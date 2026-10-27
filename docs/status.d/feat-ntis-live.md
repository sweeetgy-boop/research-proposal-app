## NTIS 실연결 (레인 N, feat/ntis-live, 2026-10-27)

### 1단계 실호출 (4개 서비스 — 모두 IP 차단, 키는 수락)
| 서비스 | 경로 | HTTP | 본문 | 소요 |
|---|---|---|---|---|
| 과제검색 | `public_project` | 200 `text/plain;charset=UTF-8` | `<error>접근 허용 IP가 아닙니다.</error>` | 0.13 s |
| 성과검색(rpaper) | `public_result` | 200 | 〃 | 0.43 s |
| 연구보고서 검색 | `rresearchpdf/` | 200 | 〃 | 0.50 s |
| 연관콘텐츠 추천 | `ConnectionContent` | 200 | 〃 | 0.52 s |

- 오류 코드 없음(루트 `<error>` 한 줄). 키 오류 문구("유효한 인증키가 아닙니다")가 아니므로 **활용신청에 등록된 서버 IP ≠ 현재 공인 IP** 가 원인.
- 결함 수정: 종전 client 는 `ERROR_CODE` 류 요소만 봐서 이 본문을 `rra sources check` 에 "ok(total=None)" 로 올렸다 → `<error>`·`resMsg/resCd` 본문을
  `NtisError` 로 바꾼다(`ntis/client.py error_message`, 본문 80자·키 없음). 이제 `sources check` 는 `왕복: NtisError / NTIS 오류: 접근 허용 IP가 아닙니다.`.
- 같은 실패 ×4 → 접근 변경: 공개 매뉴얼로 형식 확정 + **합성 fixture** 로 코드·테스트 완료. 작업 끝 재시도(아래 "재시도 명령").

### 내가 할 일 (사람)
- **NTIS 서버 IP 를 현재 공인 IP 로 변경**: ntis.go.kr 로그인 → 데이터활용 > OpenAPI(https://www.ntis.go.kr/rndopen/api/mng/apiMain.do) >
  활용신청 내역(4개 서비스)의 서버 IP. 현재 공인 IP 는 호출 기기에서 `curl -s https://api.ipify.org` (개발 MacBook·배포 Mac mini 가 다르면 둘 다,
  변동 IP 면 반영 때마다). 변경 반영 뒤 재시도 명령 실행. 콜센터 042-865-1115.

### 재시도 명령 (통합 세션, IP 반영 뒤)
```bash
cd /Users/chan/projects/research-proposal-app
PYTHONPATH=src .venv/bin/python -m rra.entrypoints.cli sources check --source ntis,ntis_reports     # 왕복 ok·총건수·record_tag 후보(HIT)
PYTHONPATH=src .venv/bin/python -m tests.tools.record_fixture ntis --query "철도 궤도" --rows 10        # 과제검색 녹화(이름 제거)
PYTHONPATH=src .venv/bin/python -m tests.tools.record_fixture ntis_reports --query "철도 궤도" --rows 10 # 연구보고서 녹화
rm tests/fixtures/ntis/*SYNTHETIC*; grep -rl "apprvKey=" tests/fixtures/ntis; pytest -q tests/adapters/test_ntis.py tests/adapters/test_real_source_fixtures.py
```
성과검색·연관콘텐츠 형식(공개 구현 기준)은 녹화 도구가 없다 — 실응답은 `POST /v1/precheck/ntis-outcomes` 1회로 확인하고 `adapters/sources/ntis/insights.py`
FIELDS·`normalize_related` 를 맞춘다. 과제 상세 링크 `views.NTIS_PROJECT_URL`(pjtInfo.do?pjtId=) 도 그때 확인.

### 2단계 형식·fixture·매핑 (공개 매뉴얼 기준, 합성)
- 매뉴얼(data.go.kr 참고문서 PDF): 과제검색(대국민용) 2021-02-08, 연구보고서 검색 2021-12-28. 성과검색·연관콘텐츠는 매뉴얼 미확보 → 공개 구현(kisti-mcp) 기준.
- `sources.yaml ntis`: `record_tag: HIT`, `project_path /rndopen/openApi/public_project`, `report_path /rndopen/openApi/rresearchpdf/`,
  `outcome_path /rndopen/openApi/public_result`, `related_path /rndopen/openApi/ConnectionContent`, 질의 13개(한국어, openalex 분야 순), `per_query_limit 150`, `insights{}`.
- FIELDS 확정(`ntis/projects.py`): id ProjectNumber · title ProjectTitle/Korean · abstract = [연구목표] Goal/Full + [연구내용] Abstract/Full + [기대효과] Effect/Full ·
  orgs ResearchAgency/Name(주관연구기관) → korail/krri/kr · pub_date/project_period ProjectPeriod/TotalStart·TotalEnd(없으면 Start·End, 그것도 없으면 ProjectYear-01-01) ·
  codes Keyword/Korean · raw{kind=national_rnd, project_no, agencies, order_agency, ministry, budget(TotalFunds), year, phase, science_class}. **수행 부서 필드 없음** →
  department None. **Manager/Name·Researchers/Name(사람 이름)은 읽지 않는다, authors=[]**. 검색어 강조 `<span class="search_word">` 제거(`_xml.flatten` 은 span 만 가진
  요소를 잎으로, `strip_highlight` 는 이스케이프된 꼴도).
- 연구보고서(`ntis/reports.py`, doc_type `report`, raw.kind national_rnd_report): id TermSn · title ResultTitle/Korean · abstract Abstract/Korean · pub_date PublicationYear|Ym ·
  url DocUrl(https 만) · orgs ManageAgency|LeadAgency·PublicationAgency · toc Contents · raw.project_no ProjectNumber. Manager 미저장.
- fixture `tests/fixtures/ntis/*SYNTHETIC*`(과제 3·보고서 2·성과 논문 2/특허 1·연관 JSON 4) + SYNTHETIC.meta.json. 녹화 도구 `strip_ntis_names`(Manager·Researchers·Author·ManagerName)·
  `ntis_reports` 소스 추가. `test_real_source_fixtures.py` NTIS skip 2건 해제(과제·보고서 매핑, 이름 없음 검사).

### 3단계 적재 설계 (실행은 통합 세션 — 대기열)
- 명령(`--limit` 기본 200 → 올릴 것). source 이름 `ntis`(과제, doc_type rnd_project)·`ntis_reports`(보고서, doc_type report), 둘 다 `source="ntis"` 로 저장:
  ```bash
  cd /Users/chan/projects/research-proposal-app && .venv/bin/rra db backup && \
  .venv/bin/rra ingest --source ntis --limit 2000 && .venv/bin/rra ingest --source ntis_reports --limit 1500
  ```
- 요청 예산: 질의 13 × 2페이지(display 100, per_query_limit 150) = **26회/소스**(예산 60, 2 req/s → 약 15 s). 예상 건수(중복 제거 전): 과제 ≤ 1,950, 보고서 ≤ 1,950 —
  실제 총건수는 IP 반영 뒤 `sources check` 로 (매뉴얼 예시 "나노" 과제 74,080건·보고서 9,482건이라 철도 질의도 상한까지 찰 가능성 큼). 적재 뒤 `rra precheck` 로
  national_rnd 알림 확인, 골든셋으로 임계치(0.80) 점검.
- 드라이런: `RRA_DB_PATH=<임시> rra ingest --source ntis --limit 5` → `[ntis] 실패: NtisError`, 저장 0 (IP 차단, 0.4 s). 실 DB 미접촉. IP 반영 뒤 같은 명령으로 재확인.

### 판정·설계 (ADR 0020)
- **source 이름은 `ntis` 유지**, 자료 종류는 `raw.kind=national_rnd|national_rnd_report` + 티어 `national_rnd`. 이유: SourceType 을 바꾸면 doc_id 접두어·
  `SOURCE_LABELS`·retrieval_mix.yaml·CLI `--source`·저장된 문서의 source 값까지 바뀌어 다른 레인과 충돌한다. 자료원(adapter) 이름과 자료 종류를 분리.
- 유사과제 티어 `national_rnd`(`domain/rules/overlap.py is_national_rnd`: source ntis + doc_type rnd_project): own 다음·domestic_rail 앞. 임계치 **0.80(own 과 같음)**,
  라벨 "국가R&D 과제"(REST tier_label·Streamlit TIER). no_overlap_statement 에도 포함. 골든셋 확인은 적재 뒤 통합 세션.
- 보고서 중복(`domain/rules/dedup.report_identity·same_report`): doc_type report|internal_report 이고 raw.project_no 가 있으면 키 = 과제번호+제목(정규화)+연도. NTIS report ↔
  ScienceON REPORT(Pjn → raw.project_no) 가 같은 보고서면 하나(근거 수준 같으면 본문·초록 긴 쪽). 연차 보고서(제목 다름)는 따로.
- 성과·연관콘텐츠(`usecases/ntis_insights.py`, 포트 `application/ports/ntis.py`, 규칙 `domain/rules/ntis_insights.py`): 알림 중 national_rnd 상위 3건(차단→유사도)의
  과제번호로 논문·특허 성과(참고용, 양식 근거 아님)·연관 과제(알림·저장소에 없는 것만, 과제번호 형식 검증, 점수 내림차순 ≤ 10). 캐시 `data/cache/ntis/<sha256>.json`
  (7일, `adapters/persistence/file_cache.py`), 간격 제한은 GuardedClient(`ntis.rate_limit` 2/s). 한 과제 실패는 예외 클래스명만.

### 프론트엔드 영향 (웹 레인) — `POST /v1/precheck/ntis-outcomes` (본문 = precheck 와 같은 ProposalRequest, 키 없으면 503)
```json
{"notice": "<UNTRUSTED_NOTICE>",
 "projects": [{"project_no": "1415171234", "doc_id": "ntis:1415171234", "title": "…", "tier": "national_rnd", "tier_label": "국가R&D 과제",
               "similarity": 0.86, "blocking": true, "cached": false, "error": null,
               "outcomes": [{"kind": "paper|patent", "title": "…", "year": "2023", "venue": "학술지명|등록기관", "result_id": "PAP-…", "registration_no": null}]}],
 "ntis_recommended": [{"project_no": "1415199001", "title": "…", "url": "https://www.ntis.go.kr/project/pjtInfo.do?pjtId=1415199001",
                       "score": 0.91, "rank": 1, "source_project_no": "1415171234"}]}
```
② 과제 카드: NTIS 과제(alerts[].tier == "national_rnd")에 "주요 성과" (projects[].outcomes, 참고용 표시), 목록 아래 "NTIS 추천" (ntis_recommended, url 링크).
precheck 응답(`/v1/precheck`)의 `alerts[].tier` 에 새 값 `national_rnd`·`tier_label` "국가R&D 과제" 가 추가된다.

### retrieval_mix 추가 규칙 (통합 세션이 `config/retrieval_mix.yaml` 에 반영)
- `rnd_project`(raw.kind national_rnd): 유사과제 판정 후보에 포함(overlap_exclude 아님). 섹션 근거로는 **유사과제·차별성(특이사항)·선행연구 현황** 에만,
  필요성·기대효과 본문 근거로는 쓰지 않음(과제 요약은 연구목표·내용·기대효과 텍스트라 자기 과제처럼 읽힐 수 있음). 최소 보장 `min_per_source` 는 ntis 2.
- `report`(raw.kind national_rnd_report): 선행연구·기술동향·연구방법 섹션 근거 허용, 최소 보장 ntis 보고서 2 (ScienceON 보고서와 합쳐 "보고서" 범주로 세면 4).
- 성과(outcomes)·추천(ntis_recommended)은 화면 전용 — 근거 검색 집합에 넣지 않는다.

### 남은 일·대기
- (사람) 서버 IP 변경 → (통합) 재시도 명령·fixture 교체·성과/연관 형식 확정·적재·골든셋 임계치 확인·docs/status.md·external-apis 표·CLAUDE.md 갱신.
- 후속: `rra sources check` 는 `ntis_reports` 도 받는다(설정·키는 ntis 공유). 성과검색 `rresearch`(보고서 성과)는 public_result 에 없다는 공개 구현 메모 — 보고서는 rresearchpdf 로.
