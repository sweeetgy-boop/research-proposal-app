# ScienceON fixture (실응답, 2026-10-27 녹화)

## 키 발급 (한 번)
1. ScienceON API Gateway(scienceon.kisti.re.kr/apigateway) 가입 → 애플리케이션 등록 → **client_id(64자)·인증키(32자)** 발급.
2. **MAC 주소 2개 등록**: 개발 MacBook, 배포 Mac mini. (`ifconfig en0 | grep ether`)
3. `.env`(권한 600)에 기기별로:
   ```
   RRA_SCIENCEON_CLIENT_ID=...   # 64자
   RRA_SCIENCEON_KEY=...         # 32자 (둘이 바뀌면 "인증키는 32자여야 합니다" — 값을 서로 바꿔 넣을 것)
   RRA_SCIENCEON_MAC=AA-BB-CC-DD-EE-FF   # 이 기기의 MAC
   ```
4. `rra sources check --source scienceon` → 왕복 ok, target 별 총건수 확인.

## 녹화
```bash
python -m tests.tools.record_fixture scienceon --query "철도 궤도" --target ARTI --rows 10
python -m tests.tools.record_fixture scienceon --query "철도 궤도" --target REPORT --rows 10
python -m tests.tools.record_fixture scienceon --query "철도 궤도" --target PATENT --rows 10
grep -rlE "accounts=|token=" tests/fixtures/scienceon && echo "비밀 흔적 있음 — 커밋 금지"
```
- 응답의 `parameterData` 에 client_id·token 이 그대로 들어 있다 — 도구가 `REDACTED` 로 바꾸고, 남으면 저장하지 않는다.
- 사람 이름 항목(`Author`·`Author2`·`Contributors`)은 `NAME-REMOVED` 로 바꾸고, 출원인(`Applicants`)은 기관으로
  보이는 이름만 남긴다(개인 출원인은 지움). 기관명(`Affiliation`·`Publisher`·수행·관리기관·기관 출원인)은 남긴다.
- 토큰 응답은 형태만 `token_shape.json` 으로 남는다(값 없음).
- `pytest -q tests/adapters/test_real_source_fixtures.py` 가 fixture 로 매핑(`scienceon/normalize.py` FIELDS)을 검사한다.

## 확정된 응답 구조
`MetaData / resultSummary(TotalCount·serviceDatatype·statusCode) / parameterData / recordList / record[@rownum] / item[@metaCode]`.
metaCode 는 `normalize.py` 머리말 참조. 오류는 `errorDetail/errorCode`(코드표: API Gateway "오류코드" 안내).
