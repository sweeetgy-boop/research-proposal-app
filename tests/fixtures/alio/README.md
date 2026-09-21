# 알리오 fixture

실제 공시 파일로 추출기·정규화를 검증한다. 네트워크 없이 돈다.

## real/ — 실제 공시 보고서 (1~2건)
1. 알리오(www.alio.go.kr)에서 코레일(C0268)·국가철도공단(C0270) 연구보고서를 **수동으로** 받는다.
   (robots.txt 가 자동 접근을 막으므로 스크립트로 받지 않는다.)
2. `real/` 에 넣는다. 파일명은 ASCII 로 바꿔도 된다 (예: `korail_2024_track.pdf`).
3. `real/expected.yaml` 에 항목을 추가한다. sha256 은 `shasum -a 256 real/<파일>` 로 구한다.
4. `pytest tests/adapters/alio/test_real_fixtures.py -v`
   - 기대값을 모르면 먼저 비워둔 채 돌려 출력을 보고 채운다:
     `python -m tests.adapters.alio.dump_fixture real/<파일>`
5. 출처(공시 URL·공시일)를 아래 표에 적는다.

| 파일 | 기관 | 공시일 | 출처 URL |
|---|---|---|---|
| | | | |

공공기관 공시 자료이나, 비공개 표기가 있거나 개인정보가 담긴 파일은 넣지 않는다.
50MB 가 넘는 파일은 넣지 말고 앞부분만 잘라낸 사본을 쓴다 (git 저장소 크기).

## summary/ — 원문 비공개 보고서의 공개 요약 (1~2건)
원문이 비공개(정보공개법 제9조①7호)인 보고서는 파일 대신 알리오 상세 페이지의 요약을 쓴다.
1. 알리오 상세 페이지에서 제목부터 공개예정일까지 **드래그해 복사**하고, 가공하지 않은 채 `.txt`(UTF-8)로 저장한다.
   (표를 복사하면 라벨과 값이 탭으로 나뉜다. 그 구분자 그대로가 파서가 확인해야 할 입력이다.)
2. 연구책임자·저자 이름은 가명으로 바꾼다(홍길동 등). 그 외 내용은 바꾸지 않는다.
3. `summary/expected.yaml` 에 기대값을 적고 `pytest tests/adapters/alio/test_real_summaries.py -v`.
   라벨을 못 잡으면 `config/sources.yaml` 의 `alio.summary.labels` 를 맞춘다.
4. 출처(상세 URL·발간일)를 아래 표에 적는다.

| 파일 | 기관 | 발간일 | 출처 URL |
|---|---|---|---|
| korail_2026_asset.txt | 한국철도공사 (경영연구처) | 2026-08-31 | (미기재) |

## catalog/sample.csv — 공공데이터포털 카탈로그 일부
`기획재정부_공공기관 연구보고서 공시` CSV 에서 헤더 + ~20행(C0268/C0269/C0270 몇 행 + 타 기관 몇 행)을
**원본 인코딩 그대로** 잘라 넣는다. 헤더가 `alio/catalog.py` 의 `DEFAULT_COLUMNS` 와 다르면
`config/sources.yaml` 의 `alio.catalog.columns` 를 맞춘다.

## 악성 샘플
zip bomb·zip slip·XXE·위장 확장자 등은 저장소에 두지 않는다.
`tests/adapters/alio/conftest.py` 가 테스트마다 tmp 디렉터리에 생성한다.
