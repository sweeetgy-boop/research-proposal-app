# ScienceON fixture (실응답)

## 키 발급 (한 번)
1. ScienceON API Gateway(scienceon.kisti.re.kr/apigateway) 가입 → 애플리케이션 등록 → client_id·인증키(32자) 발급.
2. **MAC 주소 2개 등록**: 개발 MacBook, 배포 Mac mini. (`ifconfig en0 | grep ether`)
3. `.env`(권한 600)에 기기별로:
   ```
   RRA_SCIENCEON_CLIENT_ID=...
   RRA_SCIENCEON_KEY=...          # 32자
   RRA_SCIENCEON_MAC=AA-BB-CC-DD-EE-FF   # 이 기기의 MAC
   ```
4. `rra sources check --source scienceon` → 왕복 ok, target 별 총건수 확인.

## 녹화
```bash
python -m tests.tools.record_fixture scienceon --query "철도 궤도" --target ARTI --rows 10
python -m tests.tools.record_fixture scienceon --query "철도 궤도" --target REPORT --rows 10
grep -rlE "accounts=|token=" tests/fixtures/scienceon && echo "비밀 흔적 있음 — 커밋 금지"
```
- 응답 본문의 키·client_id·MAC·토큰 값은 도구가 `REDACTED` 로 바꾸고, 남으면 저장하지 않는다.
- 토큰 응답은 형태만 `token_shape.json` 으로 남는다(값 없음).
- 녹화 후 `pytest tests/adapters/test_real_source_fixtures.py -v` → 필드 매핑 확인
  (`src/rra/adapters/sources/scienceon/normalize.py` 의 `FIELDS` 후보를 실제 metaCode 로 좁힌다).
