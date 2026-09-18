# research-proposal-app

연구과제 제안서 자동 작성 앱 (한국철도공사 철도연구원 양식). 헥사고날 아키텍처, 보안코딩 적용.
설계 문서: docs/architecture.md

## 계층 규칙 (import-linter 강제)
- `src/rra/domain/`: 순수 파이썬. pydantic·표준라이브러리만. 다른 rra 패키지·I/O 라이브러리 import 금지.
- `src/rra/application/`: domain만 의존. ports는 `typing.Protocol`. usecases는 포트만 받음.
- `src/rra/adapters/`: 포트 구현체. 외부 라이브러리는 여기서만. usecases·entrypoints import 금지.
- `src/rra/entrypoints/`: cli·api·mcp. usecases 호출만, 로직 없음.
- `src/rra/composition.py`: 유일하게 전 계층을 아는 조립 지점.

## 보안 규칙 (반드시 지킬 것)
- A: 수집 문서 텍스트는 비신뢰. LLM 출력은 JSON만 파싱, evidence doc_id는 검색 집합과 대조.
- B: 외부 파일 파싱은 subprocess 격리, zip 상한, defusedxml만 사용.
- C: 아웃바운드 HTTP는 config/security.yaml 허용 도메인만. 캐시 키는 비밀 파라미터 제거 후 해시.
- D: 비밀은 settings.py의 SecretStr만. 로그·매니페스트에 원문·키 금지.
- E: SQL은 파라미터 바인딩. FTS5 MATCH 입력은 토큰별 인용.
- F: HWPX 슬롯 치환은 XML escape + 재파싱 검증.
- G: 웹·MCP는 127.0.0.1 바인딩, 인증 필수, 생성 동시성 1.
- H: LLM 서버 127.0.0.1, safetensors만.

## 작업 방식
- 새 기능은 domain → ports → usecase(fake로 테스트 통과) → adapter 순서.
- 어댑터 normalize()는 순수 함수, tests/fixtures 원본 응답으로 테스트.
- 커밋 전: `pytest -q && lint-imports && ruff check src tests`
- 임베딩·LLM 호출 없이 테스트가 돌아야 함 (tests/fakes.py 사용).

## 개발 환경
- macOS와 WSL 양쪽에서 작업. 둘 다 uv로 만든 `.venv` 사용.
- `.venv`는 OS별로 따로 만든다. macOS와 WSL이 같은 `.venv`를 공유하면 안 됨.

## 환경
- Python 3.12 (uv, .venv). 개발은 macOS·WSL, 배포는 M6 Mac mini 24GB + mlx-lm.
- LLM: OpenAI 호환 base_url (mlx-lm). 임베딩: sentence-transformers.
- DB: SQLite FTS5 + sqlite-vec. sqlite-vec 미설치 시 파이썬 코사인 브루트포스로 자동 폴백.

## 현재 단계
Step 3 완료 — adapters/llm/openai_compat.py(재시도·json_mode 폴백·보안 H), prompts/*.md +
PromptLibraryPort, composition.build_llm/build_prompt_library/build_precheck,
MCP stdio 서버(rra_precheck·rra_search, 읽기 전용), CLI precheck·search·llm-check·mcp.
다음: Step 4 — adapters/sources/openalex.py (키 불필요), ingest_sources 유스케이스, ingest→search 왕복 검증.

## MCP
- `.mcp.json`(프로젝트 루트, stdio, `.venv/bin/python -m rra.entrypoints.mcp.server`). 등록·보안은 docs/mcp.md.
- 도구 로직은 `entrypoints/mcp/tools.py`(mcp SDK import 없음), 등록만 `server.py`. SDK 없이도 테스트가 돈다.
- 도구 결과는 항상 비신뢰: `domain/rules/trust.untrusted_block()` / `UNTRUSTED_NOTICE` 를 거쳐 나간다.
