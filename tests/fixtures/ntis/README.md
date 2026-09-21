# NTIS 과제검색 fixture (실응답)

## 키 발급 (한 번)
1. NTIS(www.ntis.go.kr) 로그인 → OpenAPI(rndopen) → **국가R&D 과제검색 서비스(대국민용)** 활용신청.
2. 승인되면 apprvKey 를 `.env`(권한 600)에 `RRA_NTIS_KEY=...`.
3. 매뉴얼에서 과제검색 요청 경로를 확인해 `config/sources.yaml` `ntis.project_path` 와 맞는지 본다.
4. `rra sources check --source ntis` → 왕복 ok, 총건수와 **record_tag 후보** 확인.

## 녹화
```bash
python -m tests.tools.record_fixture ntis --query 궤도 --rows 10
python -m tests.tools.record_fixture ntis --query 철도차량 --rows 10
grep -rl "apprvKey=" tests/fixtures/ntis && echo "비밀 흔적 있음 — 커밋 금지"
```
- 도구가 출력한 record_tag 후보를 `config/sources.yaml` `ntis.record_tag` 에 적는다 (비어 있으면 수집 불가).
- `pytest tests/adapters/test_real_source_fixtures.py -v` → 필드 매핑 확인
  (`src/rra/adapters/sources/ntis/projects.py` 의 `FIELDS` 후보를 실제 태그로 좁힌다).
- 코레일 철도연구원 과제가 `own` 티어로 가려면 수행 부서 필드가 있어야 한다 — 없으면 알려 줄 것.
