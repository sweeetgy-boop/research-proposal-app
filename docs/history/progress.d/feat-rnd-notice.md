# 레인 G 진행 기록 — feat/rnd-notice (2026-10-27, P2-7 국토교통 분야 정부 R&D 공고·RFP)

## 경과
- 2026-10-27 17:05 탐색 시작. robots: KAIA `Allow: /`, NTIS `Disallow: /`(전체 금지), IRIS 는 `/wklounge/…`·`/sysadmn/…` 만 금지
  (사업공고 `/contents/retrieveBsnsAncmBtinSitu*.do` 허용), data.go.kr 은 Googlebot 일부 경로만.
- 17:20 KAIA 사업공고: GET 목록(`?page=N`, 10건/쪽, 전체 1,224건, 11쪽≈2023-07), 열 = 제목·사업명·공고기간(접수 마감)·등록일.
  상세 본문은 PDF 뷰어(iframe)뿐 → 첨부 `/afile/fileDownload/<id>`(octet-stream + Content-Disposition 이름, 공고문 pdf 0.1MB·안내서
  1MB·서식 zip 33MB). 저작권정책: 공공누리 제3유형(출처표시·변경금지, 게시물별 확인).
- 17:30 IRIS 사업공고: 목록은 JS 템플릿 + 공개 검색 폼 POST(JSON, `pageIndex`·`ancmPrg`(접수중/예정/마감)·`blngGovdSe(+Arr)`=AR4004
  국토교통부·`sorgnId(+Arr)`=10002 KAIA). 마감 전체 19,113건, 국토교통부 945건, KAIA 전문기관 1,301건, 접수중 16건. 상세 GET 에
  소관부처·전문기관·공고번호·공고일자·접수기간·공고문 본문(인라인)·사업담당자 이름(전화) → 저장 전 제거. 첨부는 세션 POST
  다운로드(`/comm/file/fileDownload.do`) → 이름만 기록.
- 17:35 data.go.kr "사업공고" API 검색: 국토교통 R&D 공고 API 없음. 과기정통부_사업공고(15074634)·산기평 지역균형(15106158) 등은
  키 필요·분야 밖. NTIS 는 robots 전면 금지 → 공개 페이지 수집 안 함(키 API 만).
- 18:05 코드: `adapters/sources/rnd_notice/`(_html·crawler·source), `domain/rules/notices.py`(키·기간·마감), `GuardedClient.post_form`,
  `usecases/notice_match.py`, `rra crawl rnd-notice`, `rra notices match`, `POST /v1/ideas/notices`, `rra ingest --source rnd_notice`,
  sources status 행. 기존 테스트 1,495 통과.

## [자동 진행] 판단
- NTIS 공고 페이지는 robots 가 전면 금지 → 크롤하지 않는다. 공고 API 유무는 키 투입 뒤 확인(내가 할 일).
- IRIS 목록 POST 는 공개 검색 폼이고 robots 가 그 경로를 금지하지 않아 허용 규칙대로 쓴다(세션·로그인 없음). IRIS 첨부는 세션
  POST 다운로드라 받지 않고 이름만 기록 — 공고문 본문이 인라인이라 RFP 텍스트는 확보된다. 같은 공고가 KAIA 에 있으면 KAIA PDF 가 붙는다.
- KAIA zip(서식, 33MB)은 받지 않는다(pdf·hwp·hwpx 만). 2년 이전 공고는 목록 단계에서 멈춘다(최신순).
- rnd_notice 는 유사과제 판정·기술적 중요도 근거에서 제외(retrieval_scope·NON_OVERLAP_SOURCES), 정책 근거 추천 후보에는 넣는다
  (retrieval_mix.yaml policy_importance allow 에 이미 rnd_notice).
- 18:40 테스트 20건(fixture 해석·스냅샷 수집 MockTransport·마감→valid_until·PII·중복·백오프/보류·robots·usecase·REST·CLI) 통과, 전체 1,515.
  실사이트 `--explore` 통과(KAIA 1,224건/10쪽 표시, IRIS 국토교통부 접수중 0·예정 1·마감 945). `--download` 백그라운드 시작(18:35).
- 18:50 스크래치 DB 적재 dry run(`RRA_DB_PATH=<scratch> rra ingest --source rnd_notice --limit 3`): 3건·청크 293 — PDF 샌드박스 파싱·임베딩
  경로 확인. `rra notices match` 는 세 공고 모두 마감 지나 0건(valid_until 만료 규칙이 실제로 작동). `rra sources status` 에 공고 행·스냅샷 줄.
