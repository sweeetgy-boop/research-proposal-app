# NTIS fixture (과제검색·연구보고서·성과검색·연관콘텐츠)

`*_SYNTHETIC_*` 는 **합성** fixture 다 — 2026-10-27 실호출이 "접근 허용 IP가 아닙니다" 로 막혀, 공개 매뉴얼의 응답명세·예시로
만들었다(SYNTHETIC.meta.json). 서버 IP 등록 뒤 실응답을 녹화하면 합성 파일을 지우고 바꾼다.

## 형식 근거 (공개 매뉴얼, data.go.kr 참고문서)
- 과제검색 `public_project` (국가R&D 과제검색 서비스(대국민용) 매뉴얼 2021-02-08): 요청 `apprvKey·collection=project·SRWR·searchFd·
  startPosition·displayCnt`, 응답 `RESULT > TOTALHITS, RESULTSET > HIT(NO)`. 필드 ProjectNumber·ProjectTitle/Korean|English·
  Manager/Name(연구책임자, 읽지 않음)·Researchers/Name(읽지 않음)·Goal|Abstract|Effect/Full|Teaser·Keyword/Korean·OrderAgency/Name·
  ResearchAgency/Name(주관연구기관)·ManageAgency/Name·Ministry/Name·ProjectYear·ProjectPeriod/Start|End|TotalStart|TotalEnd·
  ScienceClass·DevelopmentPhases·GovernmentFunds·TotalFunds. 검색어 강조 `<span class="search_word">` 가 텍스트 안에 온다.
  **수행 부서 필드는 없다** → 코레일 과제도 own 이 아니라 `national_rnd` 티어.
- 연구보고서 `rresearchpdf/` (국가R&D 연구보고서 검색 매뉴얼 2021-12-28): 요청 `query·searchField·startPosition·displayCount·returnType`,
  필드 TermSn·PublicationYear|PublicationYm·ResearchPublicNo·PublicationAgency·ResultTitle/Korean·Abstract/Korean·Keyword/Korean·
  Contents·DocUrl·ProjectNumber·ProjectTitle·ManageAgency|LeadAgency·Manager(읽지 않음). 강조 태그는 이스케이프돼 온다.
- 성과검색 `public_result`·연관콘텐츠 `ConnectionContent`: 매뉴얼 미확보, 공개 구현(kisti-mcp) 기준. 실호출로 확정.

## 키·IP (한 번)
1. NTIS 로그인 → OpenAPI(rndopen) 활용신청 (과제검색·성과검색·연구보고서·연관콘텐츠 4개 승인됨, 유효 2027-05-27).
2. **활용신청의 서버 IP 를 호출 기기의 현재 공인 IP 로** (`curl -s https://api.ipify.org`). 다르면 HTTP 200 + `<error>접근 허용 IP가 아닙니다.</error>`.
3. apprvKey 는 `.env`(권한 600) `RRA_NTIS_KEY=...`.
4. `rra sources check --source ntis,ntis_reports` → 왕복 ok, 총건수, record_tag 후보(HIT).

## 녹화 (IP 등록 뒤)
```bash
python -m tests.tools.record_fixture ntis --query "철도 궤도" --rows 10
python -m tests.tools.record_fixture ntis --query 전차선 --rows 10
grep -rl "apprvKey=" tests/fixtures/ntis && echo "비밀 흔적 있음 — 커밋 금지"
rm tests/fixtures/ntis/*SYNTHETIC*            # 실응답으로 대체
pytest -q tests/adapters/test_real_source_fixtures.py tests/adapters/test_ntis.py
```
녹화 도구는 Manager·Researchers·Author 값을 NAME-REMOVED 로 바꾼다. `test_real_source_fixtures.py` 는 `ntis_project_*.xml`·
`ntis_report_*.xml` 을 읽는다 (합성·실응답 모두).
