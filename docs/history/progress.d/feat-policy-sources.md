# 레인 E 진행 기록 — feat/policy-sources (2026-10-27)

[P2] 보류 항목 처리: P2-2 안전 통계, P2-3 운영·수송 통계, P2-4 감사원·국정감사, P2-5 경영평가, P2-6 발주 연구용역, P2-10 판 추적 확인.
info.korail.com 은 다른 프로세스가 수집 중이라 건드리지 않는다.

## 경과
- 2026-10-27 17:05 시작. CLAUDE.md·architecture §4.16·§7·korail-web-crawl.md §4·molit/korail_web 어댑터·editions 규칙 확인.
- 2026-10-27 17:20 robots 탐색: ebid.korail.com(robots 307→오류 페이지), www.bai.go.kr(Allow /, Disallow /api/, sitemap),
  www.g2b.go.kr(Googlebot 일부만), railsafety.or.kr(20s 시간 초과 — 레인 A 와 동일), stat.molit·kosis·data.go.kr(Googlebot 일부만),
  www.alio.go.kr(Allow /), mofe.go.kr(/sch/schMain.do·/id/qustnr.do 만 Disallow), www.kric.go.kr(allow /).
- 2026-10-27 17:30 ebid.korail.com: 프레임셋 → main.do. 메뉴는 전부 `torForm` POST(`__EventTarget`·`code`·`gubun`), GET 목록은
  "총 0 건", POST 1회(code=A03, gubun=5 용역)도 목록 행 없음(목록은 JS 가 다른 경로로 채움). 상세 `fn_bid_content` 는
  "로그인 후 이용 가능". 이용약관은 POST 목록 안이라 확인 불가 → 자동 판단: 불명확 → 나라장터 공개 API 로 전환.
- 2026-10-27 17:40 apis.data.go.kr `/1230000/ad/BidPublicInfoService/getBidPblancListInfoServcPPSSrch` 는 키 없이 401
  SERVICE_KEY_IS_NULL(경로 유효, 키 필요). 옛 `BidPublicInfoService04/...01` 은 폐기(NO_OPENAPI_SERVICE_ERROR).
- 2026-10-27 17:50 감사원: 목록은 Vue SPA. 헤드리스 Chromium 으로 열면 렌더됨(전체 3,173건, 공공누리 4유형 표기). 검색어 "철도"
  55건(한국철도공사 정기감사 2025-02-20, 철도시설 안전관리 실태 점검 2026-03-09, 국가철도공단 정기감사 2021-11-16 …).
  상세 `/bai/result/branch/detail?srno=N` 에 전문 PDF·보도자료 hwp 가 있고 파일 클릭 → blob 다운로드(PDF 2.6MB 정상).
  페이지는 자체적으로 `/api/…` 를 부르지만 우리는 `/api/` URL 을 직접 요청하지 않는다(화면 조작만).
- 2026-10-27 18:00 공공데이터포털 파일데이터: "철도사고" 10건(국토교통부_철도사고 발생 현황 15122753, 한국교통안전공단_철도사고
  통계현황 3047220, 국토교통부_철도사고 통계 15123043 …), "한국철도공사 수송실적" 10건(연도별 수송실적 3050961, 철도 여객수송실적
  15088862, 화물 수송실적 3073553 …). 상세 페이지에 "로그인 없이 다운로드", 이용허락범위 제한 없음. 내려받기 2단계:
  `selectFileDataDownload.do?publicDataPk&publicDataDetailPk&fileDetailSn` (JSON, atchFileId) → `cmm/cmm/fileDownload.do?atchFileId&fileDetailSn`
  (CSV cp949, 16KB 정상). **키 없는 경로 확보** → P2-2·P2-3 는 이 경로로.
- 2026-10-27 18:10 기획재정부 보도자료 게시판(egov): `nesdta.do?searchBbsId1=…&searchCondition=1&searchKeyword1=경영실적 평가결과`
  → 2016~2025년도 "공공기관 경영실적 평가 결과 발표" 10건, 상세 `detailNesDtaView.do?searchNttId=` 에 hwpx·pdf 개별
  `FileDown.do?atchFileId&fileSn`(zip 전체받기는 쓰지 않음). 상세에 담당자 이름·전화·이메일 → strip_pii.

## [자동 진행] 판단
- (P2-6) ebid.korail.com 은 목록 POST·JS 적재·상세 로그인·약관 미확인 → "불명확" 으로 보고 나라장터 공개 API(`g2b`, 키
  `RRA_DATA_GO_KR_KEY`)로 전환. 어댑터·fixture·설정은 만들고 키 없으면 MissingCredential 로 건너뜀. 과업 개요는 API 에 없음
  (공고서 첨부는 g2b 파일 호스트 — 실응답 뒤 허용 도메인 결정) → 보류 기록.
- (P2-4) 감사원은 Playwright 로 공개 화면만 조작(검색·상세·파일 클릭), `/api/` 직접 호출 없음, 2초 간격·동시 1. 국정감사
  지적은 감사원 사이트에 없고 국회 의안정보/열린국회정보는 범위 밖 → "국정감사 = 공개 보고서 파일만" 규칙에 따라 감사원 전문
  PDF 만 수집하고 국정감사는 보류 기록.
- (P2-2·3) 키가 필요한 KOSIS·통계누리 API 대신 공공데이터포털 파일데이터(키 없음)를 1차 경로로. 광역수송 통계 xlsx 는 레인 A
  스냅샷(biz_stat_docs 18건)에 이미 있어 그 메뉴의 doc_type 만 statistics 로 바꾼다.
- (P2-5) 알리오 대신 기획재정부 보도자료(공개 PDF·HWPX)를 수집(연도별 결과 발표). 공사별 개선 권고 본문은 평가보고서(알리오
  경영평가 항목)라 범위 밖 → 기록.

## 경과 (이어서)
- 2026-10-27 18:40 도메인: DocType `statistics`·`audit`·`procurement`, SourceType `g2b`·`bai`·`mofe`·`datago`, Tier `procurement`
  (임계치 0.80 = own, 라벨 "발주 용역", `STATUS_LABELS` procuring → "용역으로 진행 중/예정"), `NON_OVERLAP_SOURCES` 에 bai·mofe·datago,
  `OVERLAP_EXCLUDED_DOC_TYPES` 에 audit·statistics. P2-10: `mark_editions` 모호(최신 판 등록일 미상)면 둘 다 현행 + `ambiguous`·
  `superseded_by` 기록(이전엔 구판 표시만 되고 valid_until 없음) — 테스트 2건 추가. korail_web 통계자료 게시판(biz_stat_docs) doc_type statistics.
- 2026-10-27 19:10 어댑터 4개: `procurement/`(g2b, 키 없으면 MissingCredential), `audit/`(bai Playwright 크롤러 + 스냅샷 소스, mofe),
  `datago/`(키 없는 2단계 파일 내려받기). config g2b·bai·mofe·datago.yaml, composition `build_*`, `_SOURCE_BUILDERS` 4개,
  `rra crawl bai`, `rra sources check` 에 g2b, REST/Streamlit 알림 `status_label`.
- 2026-10-27 19:35 감사원 1차 수집 끝: "철도" 55건, 전문 PDF 20건 45.8MB, 보류 0 (`data/bai/snapshots/2026-10-27/`). 옛 항목(1998~2010)은
  hwp 공개문만 있어 `attachment_types` 에 hwp·hwpx 를 더하고 2차 수집(같은 날 스냅샷에 덮어씀) 시작. 테스트 1,519 통과·17 skip, 계약 8, ruff 통과.
- 2026-10-27 19:40 스크래치 DB(`RRA_DB_PATH`) 로 `ingest --source datago,mofe --limit 3` 시운전 시작(임베딩 포함).

## [자동 진행] 판단 (이어서)
- 감사원 상세의 "부서명" 은 dt/th 로 잡히지 않아 `bai_department` 가 비어 있다(제목·종류·분야·등록일·파일은 정상). 적재에 영향 없어 그대로 두고 기록.
- 감사원 목록 행의 srno 는 페이지가 받은 목록 JSON 에서만 읽고(`srno_values`), `/api/` 는 만들어 부르지 않는다. 파일은 화면의 파일 링크 클릭(blob).
- ebid.korail.com 은 1회 POST 로 확인만 하고 중단(목록 행 없음·상세 로그인) — 우회 없음.
- 국정감사 지적사항: 감사원 사이트 밖(국회) → 보류 기록. 경영평가의 공사별 개선 권고 본문(평가보고서)은 알리오 항목이라 범위 밖 → 보도자료(총괄 결과)만.

- 2026-10-27 20:05 감사원 2차 수집 끝(hwp 공개문 포함): 54항목·파일 40개(pdf 20 + hwp 20)·82.5MB, 보류 1건(srno 1849 — 10초 간격 재시도 뒤에도
  실패, `snapshot.json held`). 스크래치 DB 시운전: datago 3건·mofe 3건 → 6문서·34청크 정상(제공기관 "의" 오파싱·mofe 등록일 오류 발견 → 수정).
  datago `_field` 는 메타 표 시작 이후만 보고, mofe 는 목록 등록일 우선. 세션 상한 해제 뒤 git status 확인 — 어댑터·테스트·문서 모두 작업트리에 있음.
- 2026-10-27 20:10 스크래치 DB 시운전 bai `--limit 3`: 3문서·160청크 정상(전문 PDF 샌드박스 파싱·임베딩). 커밋.
