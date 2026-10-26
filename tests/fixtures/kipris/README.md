# KIPRIS 실응답 fixture

`python -m tests.tools.record_fixture kipris --query "철도 궤도" --rows 10` 로 녹화한다 (.env 의 RRA_KIPRIS_KEY 사용).
응답에서 accessKey/ServiceKey 값은 REDACTED 로 바뀌고, 남아 있으면 저장하지 않는다. `*.xml` 이 있으면
`tests/adapters/test_real_source_fixtures.py::test_kipris_records_normalize` 가 돈다 (없으면 skip).
레코드 태그 후보는 녹화 도구가 출력한다 → `config/sources.yaml kipris.record_tag`.
