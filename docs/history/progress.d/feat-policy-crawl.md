# 레인 A 진행 기록 — feat/policy-crawl (2026-10-27)

## 경과
- 2026-10-27 11:00 [C] 탐색 시작. www.korail.com 은 JS 번들 SPA(승차권)이며 헤드리스 Chromium 에서 본문이 뜨지 않음(봇 보호층 dynaPath·넷퍼넬 추정, 우회하지 않음) → 번들의 공개 설정에서 회사소개 사이트 `info.korail.com/info/`(서버 렌더 HTML) 확인.
- 2026-10-27 11:20 info.korail.com robots.txt 비어 있음(제한 없음). 저작권정책(key=924): 저작권법 제24조의2 공공저작물 자유이용. 본문 페이지 하단 공공누리 제4유형(출처표시·상업적 이용금지·변경금지) 표기. 게시판 구조(selectBbsNttList/selectBbsNttView/downloadBbsFile, pageIndex, 총게시물 N 건) 확인. 보도자료 6,380건(2005~), 지속가능경영보고서 12, 환경경영보고서 15, 통계자료 18, 사전정보공개목록 171 등 집계.
- 2026-10-27 11:40 중장기 경영목표(key=1900) 페이지에 5대 경영목표·15대 전략과제·40 KPI 표가 텍스트로 있음 → 전략체계 초안 근거(basis: text) 확보.

## [자동 진행] 판단
- (2) www.korail.com(SPA) 은 헤드리스에서 본문이 뜨지 않고 봇 보호층이 있어 우회하지 않는다. 같은 내용을 서버 렌더로 제공하는 info.korail.com 만 수집한다. `allowed_domains` 에는 info.korail.com 만 추가.
- (1) 보도자료 6,380건 × 첨부(hwp 0.1MB + 사진 jpg 1~3MB) ≈ 10GB 초과 추정 → 보도자료는 최근 5년(2021-10-27 이후, 약 1,350건)으로 자르고, 사진(jpg·png 첨부)은 메타데이터(파일명)만 기록하고 내려받지 않는다(본문 img 는 내려받음). 설정 `korail_web.yaml` 의 메뉴별 `since`·`attachment_images` 로 되돌릴 수 있다.
- (8) 사업실명제 대상사업(327건 PDF, 담당자 실명 공개 목적)·제정개정 예고(사규)·채용·고객의소리·개인정보·갤러리·기차소개 는 범위 밖으로 둔다(설정에서 메뉴를 추가하면 수집됨).
- 2026-10-27 13:10 [C] 크롤러 코드(`adapters/sources/korail_web/`: _html·_pii·robots·snapshot·crawler·source)·`rra crawl korail`·fixture 테스트 29건 작성. 실사이트 `--explore` 완료(50개 메뉴, 보도자료 6,380건/638쪽 2005-01~2026-10, 사전정보공개 171건, 통계자료 18, 환경경영보고서 15, 지속가능경영보고서 12, 기업브로슈어 24 …). `--download` 시작(백그라운드).
- 2026-10-27 14:40 [P] 유사과제 판정에서 policy·korail_news 제외(retrieval_scope), `rra sources status`·REST 스냅샷 표시, `rra db backup` 이 index·manifest 동반, 전략체계 초안(5 방향·15 과제, basis text)·strategy.yaml source 스위치·`rra strategy draft/promote`·초안 라벨, 정책 근거 추천(`policy_suggest`, REST `/v1/ideas/policy-suggestions`, `rra policy-suggest --pick`) 구현. 내려받기 진행 중(90건·476MB, 보고서 PDF 대부분 수십 MB).
- 2026-10-27 16:50 [P2-1] molit 어댑터(실사이트 probe 통과)·판 추적, 당일 스냅샷 이어 받기. 문서 조각(timeline.d·metrics.d·status.d·ADR 0016) 작성. 내려받기 229항목·207파일·654MB 진행 중(보도자료 남음). P2-2·4·6 은 탐색만.
- (2) 감사원 목록은 JS 렌더이고 내부 `/api/` 를 robots 가 금지 → 보류. ebid.korail.com 은 세션·POST 폼 → 보류, 나라장터 공개 API 대안 기록.
