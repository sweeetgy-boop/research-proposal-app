# 0020. NTIS 연결 — source 이름 유지·국가R&D 과제 티어·IP 차단 시 합성 fixture (2026-10-27)

## 배경
NTIS 키(과제검색·성과검색·연구보고서·연관콘텐츠 4개 승인, 2027-05-27 까지)로 첫 실호출을 했더니 4개 서비스 모두 HTTP 200 에
`<error>접근 허용 IP가 아닙니다.</error>` 를 돌려줬다(키는 수락, 활용신청의 서버 IP 가 현재 공인 IP 와 다름). 기존 client 는 이 본문을
"ok" 로 올리고 있었다. 지시는 source_type `national_rnd` 추가·국가R&D 과제 티어·보고서 교차 중복·성과/연관 조회였다.

## 선택지
1. SourceType 에 `national_rnd` 를 추가하고 NTIS 문서의 source 를 그 값으로 저장.
2. source 는 `ntis` 그대로 두고 자료 종류는 `raw.kind` 와 유사과제 **티어** `national_rnd` 로 구분.
3. 실호출이 될 때까지 코드·테스트를 멈춘다 / 매뉴얼 형식의 합성 fixture 로 진행.

## 결정
- **2**: source 는 자료원(어댑터) 이름, `national_rnd` 는 자료 종류·티어. `Tier` 에 `national_rnd` 추가(임계치 0.80 = own, 라벨 "국가R&D 과제"),
  `is_national_rnd(doc)` = source ntis + doc_type rnd_project. 보고서는 doc_type `report`(raw.kind national_rnd_report)로 같은 source.
- **합성 fixture** 로 진행: data.go.kr 참고문서(과제검색 2021-02-08·연구보고서 2021-12-28 매뉴얼 PDF)의 응답명세·예시를 철도 내용으로 옮기고
  `SYNTHETIC` 표시. 성과검색·연관콘텐츠는 매뉴얼이 없어 공개 구현(kisti-mcp) 기준. IP 반영 뒤 실응답으로 교체(status 조각 재시도 명령).
- 오류 본문(`<error>`, `resMsg/resCd`)은 파싱 전에 `NtisError` 로 — `sources check` 가 거짓 ok 를 내지 않게.

## 이유
- SourceType 변경은 doc_id 접두어·SOURCE_LABELS·retrieval_mix.yaml(통합 세션 소유)·CLI `--source`·저장 문서의 source 값·웹 타입까지 번져
  병렬 레인과 충돌한다. 티어 분리로 "국가R&D 과제" 구분(알림 라벨·임계치·문장)은 그대로 얻는다.
- 매뉴얼 응답명세가 공개돼 있어 레코드 태그(HIT)·필드명은 확정할 수 있고, 실응답에서 달라질 수 있는 것(성과·연관 형식, 링크 패턴)은 표시해 두었다.

## 결과
- `rra sources check --source ntis` → `왕복: NtisError / NTIS 오류: 접근 허용 IP가 아닙니다.` (종전: ok, total=None).
- 테스트 1,522 passed·16 skipped, 계약 8 kept. 적재는 IP 반영 뒤 통합 세션(status 조각 3단계).
