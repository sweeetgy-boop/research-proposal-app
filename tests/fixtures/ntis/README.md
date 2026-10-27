# NTIS fixture (과제검색·연구보고서·성과검색·연관콘텐츠) — 2026-10-27 실응답

모두 **실응답 녹화**다(합성 `*SYNTHETIC*` 는 2026-10-27 19:11 에 지웠다). 녹화 도구 `tests/tools/record_fixture.py`,
현재 공인 IP 59.0.166.199(활용신청 등록 IP) 에서 호출. 키·URL 은 어디에도 없다(`*.meta.json` 에 질의·건수·content-type 만).

| 파일 | 서비스·경로 | 질의 | 건수 / 총건수 | 비고 |
|---|---|---|---|---|
| `ntis_project_20261027_track.xml` | 과제검색 `public_project` | `철도 궤도` (searchFd BI, displayCnt 10) | 10 / 1,087 | 주관 한국철도기술연구원 7·한국철도공사 1·서울과기대 2 |
| `ntis_project_20261027_catenary.xml` | 과제검색 | `전차선` | 10 / 193 | 중소기업·대학 주관 과제 위주 |
| `ntis_report_20261027_track.xml` | 연구보고서 `rresearchpdf/` | `철도 궤도` (searchField BI, displayCount 10, returnType xml) | 10 / 202 | DocUrl 에 맨 `&` 그대로(원문 보존) |
| `ntis_outcome_20261027_rpaper.xml` | 성과검색 `public_result` collection=rpaper, addQuery DBT=PAP | 과제번호 `1615007833` | 10 / 13 | `HIT SITID="PAP"` |
| `ntis_outcome_20261027_rpatent.xml` | 성과검색 collection=rpatent, DBT=PAT | `1615007833` | 2 / 2 | 출원 1·등록 1, Registrant 기관 |
| `ntis_related_20261027.json` | 연관콘텐츠 `ConnectionContent` pjtId | `1615007833` | 10 | JSON 객체(문자열 감싸기 푼 꼴) |

## 응답 형식 (실측)
- 실서버는 **Accept 에 `application/json` 이 있으면 본문 전체를 JSON 문자열 하나로 감싸** 보낸다 (`"<?xml …"`, content-type
  `application/json;charset=UTF-8`). Accept 에 json 이 없으면 `text/plain;charset=UTF-8` 날 XML. 오류 본문 한글은 json Accept 가
  있어야 살아오므로 어댑터는 json 을 유지하고 문자열을 푼다(`ntis/client.py unwrap_json_string`). 녹화본은 **푼 꼴**로 저장
  (`meta.json_wrapped: true`). 이것이 2026-10-27 `rra sources check` 의 `XmlResponseError (ParseError)` 원인이었다.
- 루트 `RESULT`(xmlns:xsi·xsi:noNamespaceSchemaLocation 속성만, 네임스페이스 없음) > QUERYTRANSFORMS·COUNTLIST(COLCOUNT NAME=
  project|rresearchpdf)·NAVIGATION(NAVIGATIONENTRY ×13 — 자동 record_tag 탐지가 이것을 고른다)·TOTALHITS·STARTPOSITION·HITS·
  SEARCHTIME·RESULTSET > `HIT NO="n"`. 공개 매뉴얼(2021)과 같다. `record_tag: HIT` 확정.
- 과제검색 HIT 필드: ProjectNumber·SecretProject·ProjectTitle/Korean|English·Manager/Name·Researchers/Name|ManCount|WomanCount·
  Goal|Abstract|Effect/Full|Teaser·Keyword/Korean|English·OrderAgency/Name·ResearchAgency/Name(주관)·BudgetProject/Name·BusinessName·
  BigprojectTitle·ManageAgency/Name(전문기관)·Ministry/Name·ProjectYear·ProjectPeriod/Start|End(YYYYMMDD)|TotalStart|TotalEnd
  (`YYYY-MM-DD 00:00:00.0`)·OrganizationPNumber·ScienceClass(type=old|new, sequence 1~3)/Large|Medium|Small·MinistryScienceClass·
  TempScienceClass·PerformAgent·DevelopmentPhases·TechnologyLifecycle·Region·EconomicSocialGoal·SixTechnology·ApplyArea·
  ContinuousFlag·PolicyProjectFlag·GovernmentFunds·SbusinessFunds·TotalFunds·CorporateRegistrationNumber·SeriesProject·PrePjtId.
  강조는 **이스케이프된** `&lt;span class="search_word"&gt;`. 수행 부서 필드 없음.
- 연구보고서 HIT 필드: TermSn·PublicationYear·ResearchPublicNo·PublicationAgency·ResultTitle/Korean|English·Abstract/Korean|English·
  Keyword/Korean|English(`;` 구분)·Contents·PublicationCountry·PublicationLanguage(Korean)·DocUrl(scienceon originalView)·
  SpecializedAgency·ProjectNumber·ProjectTitle·LeadAgency·ManagerName·AgencyDetailProjectNumber. 강조는 **날** `<span>`,
  DocUrl 의 `&cn=` 은 이스케이프 없음 → `_xml.repair_bare_ampersands`.
- 성과검색 논문 HIT: Year·ResultID·ResultTitle·JournalName·IssnNumber·Author·Abstract/Full|Teaser·PubYear·PaperType·SciType·NationType·
  JCType·…·ProjectYear·BudgetProject·MinistryName·**ProjectID**(과제번호)·ProjectTitle·PerformAgency·ScienceClass1~3·
  DigitalObjectIdentifier. 특허 HIT: Year·ResultID·ResultTitle·RegistCountry·RegistNumber·Registrant·RegistType(출원|등록)·IprType·…·ProjectID.
- 연관콘텐츠 JSON: `{PJT_ID, KOR_PJT_NM, exist, items:[{PJT_ID, similarity_score, rank, creat_dt, KOR_PJT_NM}], count}` —
  `creat_dt` 에 비표준 `NaN` 이 섞여 온다(파이썬 json 은 받는다).

## 가명 처리 규칙 (녹화 도구 `strip_ntis_names`)
- 사람 이름 요소는 값을 `NAME-REMOVED` 로: 과제 `Manager/Name`(연구책임자)·`Researchers/Name`(참여연구원 전체 목록), 보고서
  `ManagerName`, 논문 `Author`, `Inventor`. 특허 `Registrant` 는 기관으로 보이는 이름만 남긴다(`_orgs.is_organization`).
- 기관명(ResearchAgency·PublicationAgency·PerformAgency·LeadAgency·SpecializedAgency)·사업자등록번호(CorporateRegistrationNumber,
  기관 값)는 그대로. 어댑터 normalize 는 어떤 사람 이름 요소도 읽지 않는다(authors=[]).
- 저장 전 `redact` 가 키(원문·URL 인코딩)를 REDACTED 로 바꾸고, 남으면 저장을 거부한다.
- `tests/adapters/test_real_source_fixtures.py::test_ntis_fixtures_hold_no_person_names` 가 매번 검사한다.

## 키·IP (한 번)
1. NTIS 로그인 → OpenAPI(rndopen) 활용신청 (과제검색·성과검색·연구보고서·연관콘텐츠 4개 승인, 유효 2027-05-27).
2. 활용신청의 서버 IP = 호출 기기의 현재 공인 IP (`curl -s https://api.ipify.org`, `sources.yaml ntis.registered_ips`). 다르면
   HTTP 200 + `<error>접근 허용 IP가 아닙니다.</error>`.
3. apprvKey 는 `.env`(권한 600) `RRA_NTIS_KEY=...`.
4. `rra sources check --source ntis,ntis_reports,ntis_insights` → 왕복 ok, 총건수·hits·record_tag_matches.

## 다시 녹화
```bash
python -m tests.tools.record_fixture ntis --query "철도 궤도" --rows 10 --label track
python -m tests.tools.record_fixture ntis --query 전차선 --rows 10 --label catenary
python -m tests.tools.record_fixture ntis_reports --query "철도 궤도" --rows 10 --label track
python -m tests.tools.record_fixture ntis_insights --query 1615007833 --rows 10   # 성과 2회 + 연관 1회
grep -rl "apprvKey=" tests/fixtures/ntis/*.xml tests/fixtures/ntis/*.json && echo "비밀 흔적 있음 — 커밋 금지"
pytest -q tests/adapters/test_real_source_fixtures.py tests/adapters/test_ntis.py
```
`--label` 은 파일 이름 꼬리(ASCII). `test_real_source_fixtures.py` 는 `ntis_project_*.xml`·`ntis_report_*.xml`·`ntis_outcome_*.xml`
을 모두 읽는다.
