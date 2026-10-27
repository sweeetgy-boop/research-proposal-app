# 공사 홈페이지 자료 탐색·수집 기록 (레인 A, 2026-10-27)

`rra crawl korail` 이 수집하는 공사 홈페이지(회사소개 사이트)의 탐색 결과와 내려받기 경과. 설정은
`config/korail_web.yaml`, 코드는 `src/rra/adapters/sources/korail_web/`, 저장은 `data/korail_web/`(커밋 금지).
예약 실행은 없다 — 사람이 `--explore` 로 확인하고 `--download [--incremental]` 로 스냅샷을 만든다.

## 1. 도메인·robots·이용조건

| 항목 | 확인 결과 (2026-10-27) |
|---|---|
| `www.korail.com` | 승차권 예매 JS 번들 SPA(`/intro` 포함). 헤드리스 Chromium 에서 본문이 뜨지 않음(봇 보호층 dynaPath·넷퍼넬 추정). robots.txt 는 `Disallow:` 빈 값(제한 없음). 번들의 공개 설정에 회사소개 사이트 주소가 있어 그쪽으로 감 — **우회하지 않고 수집 대상에서 제외**(자동 판단 2). |
| `info.korail.com` | 회사소개 사이트(공사소개·정보공개·ESG경영·고객참여·주요사업·홍보센터). 서버 렌더 HTML(NEO CMS). `/info/index.do`. **수집 대상.** `allowed_domains` 에 추가. |
| robots.txt (info) | 빈 파일(200, 0 byte) → 제한 없음. 코드는 그래도 `urllib.robotparser` 로 Disallow 를 지킨다. |
| `<meta name="robots">` | 첫 화면에 `noindex`(검색엔진 색인 금지 선언). 수집 금지 문구는 아님. 내부 연구용 적재이며 외부 공개 색인을 만들지 않으므로 진행. |
| 저작권정책 (`contents.do?key=924`) | "저작권법 제24조의2(공공저작물의 자유이용)에 따라 코레일이 저작재산권 전부를 보유한 저작물은 별도 이용허락 없이 자유이용 가능". |
| 본문 페이지 하단 | 공공누리 **제4유형(출처표시·상업적 이용금지·변경금지)** 표기 → 항목마다 `terms` 로 기록. |
| User-Agent | `RRA research-proposal-app (internal research use) +https://github.com/sweeetgy-boop/research-proposal-app` |
| 요청 간격 | 같은 호스트 2초, 동시 1 (GuardedClient rate_limit 0.5/s). 403·429·전송 오류는 2s→5s→10s 백오프, 연속 3회 실패 "보류", 끝에 10s 간격 1회 재시도. |

페이지 구조: 목록 `selectBbsNttList.do?bbsNo=&key=&pageIndex=`("총게시물 : N 건"), 상세 `selectBbsNttView.do`
(`.detail_title`·`.date`·`.detail_content`·`.attach_file` + `downloadBbsFile.do?atchmnflNo=`), 콘텐츠 `contents.do?key=`
(`#contents`, 파일 `downloadContentsFile.do?key=&fileNo=`), 사전정보공표 `selectInfoRelWebList/Detail.do`
(`downloadInfoRelFile.do`), 갤러리형 게시판(지속가능경영보고서·기업브로슈어)은 상세 없이 `pdfDownload('<번호>')`.

## 2. 탐색 결과 (`rra crawl korail --explore`, 2026-10-27)

범위: 경영공시·경영목표·경영전략·비전, ESG·환경·안전·동반성장·윤리·사회공헌, 정보공개(사전정보공표),
주요사업 현황·통계, 보도자료·기업브로슈어. 제외: 로그인·채용·고객의소리·개인정보·갤러리·기차소개·사업실명제
(담당자 실명 공개 자료)·제정개정예고(사규).

| 메뉴 | 종류 | 건수 | 쪽 | 기간 | 첨부(1쪽 기준) | 비고 |
|---|---|---|---|---|---|---|
| 공사소개 > 일반현황 > 경영가치체계 (716) | contents | 1 | | | 이미지 1 (전략경영체계도) | 텍스트 527자 — MISSION·VISION·5대 경영목표·15 전략과제가 `.skip` 텍스트로 있음 |
| 경영공시 > 일반항목 > 중장기 경영목표 (1900) | contents | 1 | | | | 텍스트 4,606자 — 5대 경영목표·15대 전략과제·주요내용·40 KPI 표 → **전략체계 초안 근거** |
| 공사소개 > 공사연혁 (717) | contents | 1 | | | 파일 1, 이미지 8 | 31,591자 |
| 경영공시 일반항목·기관운영·주요사업·대내외 평가 (1623~1626) | contents | 4 | | | | 알리오 항목 링크 목록(1,444자, 동일 본문) |
| ESG경영 추진체계 (2250)·ESG경영선언 (2255) | contents | 2 | | | 이미지 1+1 | 비전·전략목표·12 전략과제 텍스트 |
| 지속가능경영보고서 (bbs 699) | gallery | 12 | 1 | 2015~2025 | PDF 12 | 국문·영문 |
| ESG채권 (bbs 1098) | board | 1 | 1 | | pdf 1 | |
| 환경경영체계·비전 및 전략·환경성과지표·토양환경 (799·800·808·3316) | contents | 4 | | | 이미지 1+0+4+0 | 4대 추진방향·12대 추진과제 텍스트 |
| 환경경영보고서 (bbs 346) | gallery | 15 | 2 | | PDF 15 | |
| 철도안전 안전방침·관리체계·산업안전보건·비상대응 (769·771·1480·969) | contents | 4 | | | 이미지 2+0+0+2 | 안전보건 목표 KPI 표 |
| 동반성장 > 안전 자료 (bbs 982) | board | 7 | 1 | 2025-05~2025-08 | hwp 5, pdf 1, zip 1 | zip 은 받지 않음 |
| 동반성장 추진체계·계약 길잡이 (793·2973) | contents | 2 | | | 파일 30 (길잡이) | 링크 글자만 "다운로드" → 받은 뒤 Content-Disposition 으로 형식 확정 |
| 동반성장 > 규정 자료 (bbs 978) | board | 3 | 1 | 2025-05 | hwp 3 | |
| 준법·윤리경영·인권경영 (781·785) | contents | 2 | | | 파일 1, 이미지 4+3 | |
| 인권경영 자료실 (bbs 405) | board | 29 | 3 | 2021-12~2026-04 | pdf 4, jpg 2 | 사진 첨부는 메타데이터만 |
| 사회공헌 추진체계 (789) | contents | 1 | | | 이미지 1 | |
| 정보공개 > 사전정보공개목록 (746) | preinfo | 171 | 18 | ~2026-09 | hwpx·pdf (상세별) | 링크형(상세 없음) 항목은 제외 → 상세 있는 것만 |
| 자주찾는 사전정보공개목록 (2490) | contents | 1 | | | | |
| 주요사업 사업소개·운영정보·현황 (855·1612·861·1446·866·870·871·875·876·887·890·1461·894·899·1641·1303·1541) | contents | 17 | | | 이미지 0~18/쪽 | 수송통계·시설 현황 표 텍스트 |
| 광역수송 > 통계자료 (bbs 425) | board | 18 | 2 | 2015-01~2026-02 | xlsx 7, 묶음 3 | |
| 자산개발 > 신사업자료실 (bbs 1070) | board | 8 | 1 | 2025-11~2026-04 | hwp 2, pdf 1, 묶음 5 | |
| 홍보센터 > 기업브로슈어 (bbs 427) | gallery | 24 | 2 | | PDF 24 | |
| 홍보센터 > 보도자료 (bbs 199) | board | **6,380** | 638 | 2005-01-02 ~ 2026-10-23 | hwp 1건 + 묶음(hwp+jpg) 9건 /10 | **최근 5년(2021-10-27~, 약 1,350건)만**, 사진 첨부는 이름만 기록 (자동 판단 1) |

크기 추정(1쪽 표본·HEAD): 보도자료 hwp 약 0.1MB, 사진 jpg 1~3MB/장 → 전체 6,380건 × 1~2 장이면 10GB 초과.
5년치 hwp 만 ≈ 150MB. 보고서 PDF(지속가능·환경·브로슈어 51건)는 수~수십 MB/건으로 수백 MB 추정.
연구개발·"정책 자료실" 메뉴는 사이트에 없다 — 정책 자료는 사전정보공개목록·경영공시·ESG 페이지가 그 역할을 한다.

## 3. 내려받기 경과

(아래 §3 은 `--download` 가 끝날 때마다 갱신한다.)

실행: `rra crawl korail --download` (2026-10-27 13:15 시작, 백그라운드). 2026-10-27 16:40 기준(진행 중, 사전정보공개목록까지):

| 항목 | 값 |
|---|---|
| 항목(페이지·게시글) | 229건 — 콘텐츠 29, 지속가능경영보고서 7/12, 환경경영보고서 9/15, 안전 자료 7, 규정 자료 3, 인권경영 자료실 29, 사전정보공개 151 |
| 파일 | 207개 (pdf 33, hwp 25, hwpx 80, pptx 35, xlsx 34), 본문 이미지 67 |
| 디스크 | 654MB (`data/korail_web/snapshots/2026-10-27/`, 내용 주소 저장이라 같은 파일은 한 번) |
| 건너뜀 | zip 등 형식 7, 사진 첨부(정책상 메타데이터만) 5 |
| 텍스트 레이어 없는 PDF | 4건 (manifest `text_layer: false` — 적재 시 `no_text_layer` 경고) |
| 보류(50MB 상한 초과 추정) | 지속가능경영보고서 5건, 환경경영보고서 6건, 사전정보공개 첨부 2건 — 끝에 10초 간격 1회 재시도 뒤 `snapshot.json held` 에 남는다 |
| 남은 것 | 주요사업 콘텐츠 17, 통계자료 18, 신사업자료실 8, 기업브로슈어 24, 보도자료(2021-10-27~) 약 1,350건 — 2초 간격이라 약 2~3시간 |

이어 가기(중단됐거나 끝난 뒤 보충): `rra crawl korail --download --incremental` — 같은 날 스냅샷을 이어 받고(받은 게시글은
다시 받지 않음), 보류 항목만 다시 시도한다. 50MB 를 넘는 보고서는 `config/korail_web.yaml max_file_mb` 를 올린 뒤 같은 명령.

## 4. 수집처 확장 탐색 ([P2], 2026-10-27)

| 수집처 | 확인 결과 | 상태 |
|---|---|---|
| P2-1 국토교통부 정책자료 (`www.molit.go.kr/USR/policyData/m_34681/`) | robots: `/USR/BORD0201/*`·`/search/` 만 Disallow (정책자료 허용). WAF 가 첫 요청에 쿠키(307 자기 리다이렉트)를 주며 GuardedClient 가 hop 안에서 처리. "철도" 48건, 국가철도망 구축계획 3건(제4차 2023-03-30 등록), 철도산업발전 2건, 철도안전종합 1건. 상세에 담당자 이름·전화 있음 → 저장 전 제거. 첨부 `DownloadMltm2.jsp?FilePath=&FileName=` (pdf·hwp). | **구현** `adapters/sources/molit/`, `rra ingest --source molit`, 판 추적(제N차 → 현행/구판, 구판 `valid_until` = 다음 판 등록일). 실사이트 probe 통과 |
| P2-2 철도 안전 통계 | `railsafety.or.kr`(교통안전공단 철도안전정보종합관리시스템) 연결 시간 초과(20s). `stat.molit.go.kr`·`kosis.kr` robots 는 Googlebot 일부 경로만 제한. 공사 자체 수송·시설 통계는 §2 주요사업 페이지·통계자료 게시판(xlsx)으로 이미 수집. | 탐색만. 다음: KOSIS 철도사고 통계 API(data.go.kr 키) 또는 stat.molit 통계누리 파일 — `statistics` doc_type 은 미정의 |
| P2-4 감사원 감사결과 (`www.bai.go.kr/bai/result/branch/list`) | robots Allow(단 `/api/` Disallow), sitemap 있음. 목록 페이지는 3.7KB 뼈대만(JS 렌더) → Playwright 또는 내부 `/api/`(robots 금지) 필요. | 보류(자동 판단 2: robots 가 막은 API 는 쓰지 않음). 대안: 감사원 공개 보고서 PDF 직접 URL 수집 |
| P2-6 연구용역 공고 (`ebid.korail.com`) | 프레임셋 + POST 폼(`torForm`, `__EventTarget`, TouchEn 키보드보안) 로 목록 조회, GET 은 "총 0 건". robots 는 오류 페이지로 307. | 보류. 대안: 공공데이터포털 나라장터 입찰공고정보 API(`apis.data.go.kr`, 키 필요, 이미 allowed_domains) 로 `procurement` 수집 — overlap.yaml 새 키·"용역으로 진행 중/예정" 상태는 미구현 |
| P2-10 판 추적 | `domain/rules/editions.py` — 제목의 "제N차" 로 계획 가족을 묶고 최신만 현행. 차수가 없거나 등록일을 모르면 둘 다 현행(모호하면 유지). | 구현(molit 에 적용) |
| P2-3·5·7·8·9 | 미착수 | — |

## 5. P2-7 국토교통 분야 정부 R&D 공고·RFP (레인 G, 2026-10-27)

탐색은 GET/POST 각 1~4회(2초 간격), 상세·첨부는 표본 1건씩. `rnd_notice` 자료원(doc_type `rnd_notice`, visibility public,
`valid_until` = 접수 마감일 → 저장소의 만료 규칙(`sqlite_repo._VALID`)으로 마감 지난 공고는 검색·precheck 에서 빠진다).

| 수집처 | robots·이용조건 | 목록 구조 | 최근 2년 건수 | 첨부(RFP) | 마감일 | 상태 |
|---|---|---|---|---|---|---|
| KAIA 사업공고 > 국토교통R&D 공고 (`www.kaia.re.kr/KAIA/contents/K30101000000.do`) | `Allow: /`. 저작권정책: 공공누리 제3유형(출처표시·변경금지, 게시물별 확인) | **GET** `?page=N`(10건/쪽, 최신순), 열 = 번호·제목·사업명·공고기간·등록일. 상세 `?schM=view&id=<20자리>`, 본문은 PDF 뷰어(iframe)뿐 | 전체 1,224건(2005~), 11쪽≈2023-07 → 2년 ≈ 80~100건(8~10쪽) | `/afile/fileDownload/<id>` octet-stream + Content-Disposition 이름. 공고문 pdf 0.1~0.3MB, 안내서 pdf 1~3MB, 서식 zip 33MB(받지 않음) | 목록·상세 "공고기간" (시작 ~ 마감) | **구현** — 주 수집처 |
| IRIS 사업공고 (`www.iris.go.kr/contents/retrieveBsnsAncmBtinSituListView.do`) | `/wklounge/…`·`/sysadmn/…` 만 Disallow(사업공고 경로 허용). 저작권 안내 페이지 없음(개인정보처리방침·이용안내만) → 정부 공고문 출처 표시 | JS 템플릿 + **공개 검색 폼 POST** `/contents/retrieveBsnsAncmBtinSituList.do` → JSON(`listBsnsAncmBtinSitu`, `paginationInfo`). 필터 `ancmPrg`(ancmIng 접수중·ancmPre 예정·ancmEnd 마감), `blngGovdSe`+`blngGovdSeArr`=AR4004 국토교통부, `sorgnId(+Arr)`=10002 KAIA. 상세 GET `retrieveBsnsAncmView.do?ancmId=` 에 소관부처·전문기관·공고번호·공고일자·접수기간·**공고문 본문 인라인**·사업담당자 이름(전화) | 마감 전체 19,113건, 국토교통부 945건(전 기간), 접수중 0·예정 1(2026-10-27). 2년 안은 79건 — 그중 63건이 KAIA 와 같은 공고(합침), IRIS 에만 있는 것 16건(모두 KAIA 전문기관) | 세션 POST 다운로드(`/comm/file/retrieveCheckFileDownload.do` → `fileDownload.do`) — 받지 않고 이름만(`post_download`). 공고문 본문이 인라인이라 RFP 텍스트는 확보 | JSON `rcveStrDe`·`rcveEndDe`, 상세 "접수기간" | **구현** — 보조 수집처(국토교통부 필터), 첨부는 보류 |
| NTIS 공고 (`www.ntis.go.kr`) | **`User-agent: * / Disallow: /`** — 공개 페이지 수집 금지 | — | — | — | — | 보류(자동 판단 2). 공고 OpenAPI 유무는 키 투입 뒤 확인(과제검색 어댑터와 같은 키) |
| 공공데이터포털 R&D 공고 API (`www.data.go.kr`) | Googlebot 일부 경로만 제한 | "사업공고" API 검색: 과기정통부_사업공고(15074634), 산기평 지역균형 유관기관 사업공고(15106158·15067525), 식약처 연구관리 사업공고(15067899) 등 — **국토교통 R&D 공고 API 없음** | — | — | — | 범위 밖(타 부처·키 필요). 필요하면 과기정통부_사업공고를 키 투입 뒤 어댑터 추가 |

중복: 같은 공고가 KAIA 와 IRIS 에 함께 실린다(표본: 국토교통연구기획 제2차 공고·재공고 모두 양쪽). `domain/rules/notices.notice_key`
(제목에서 공고번호·괄호·기호·"재공고/공고/시행" 제거 + 기관 + 공고일 → 16자 해시)로 한 문서로 합치고 나머지 URL 은 `raw.notice.also_in`.
KAIA 가 먼저 돌아 PDF 공고문이 붙고 IRIS 는 같은 키면 `duplicate_of` 로만 기록된다.

수집 명령: `rra crawl rnd-notice --explore` → `rra crawl rnd-notice --download [--limit N] [--incremental]`
(스냅샷 `data/rnd_notice/snapshots/<날짜>/manifest.jsonl`, 첨부 `files/<sha[:2]>/<sha>.<ext>`, 본문 `items/<site>/<id>.txt`),
적재 `rra ingest --source rnd_notice --limit 600`. 실행 경과는 `docs/history/progress.d/feat-rnd-notice.md`.

수집 결과(2026-10-27): 공고 99건(KAIA 83 + IRIS 16, 두 사이트에 함께 실린 63건은 한 문서로 합침), 첨부 229개 808MB(KAIA pdf·hwp; IRIS 첨부 40건은 이름만), 등록일 2024-10-30~2026-08-20 (완료, 2년 범위). 보류 0, 오류 0, 50MB 초과 안내서 6건 미수집. 스냅샷 575MB(커밋 안 함).
