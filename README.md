# 연구제안서 작성 앱 (research-proposal-app)

연구과제 제안서 자동 작성 — 헥사고날 구조, 보안코딩 반영.

## Step 1 (현재)
domain / application / ports / fakes / tests. 외부 I/O 없음.

```bash
uv venv --python 3.12 && source .venv/bin/activate
uv pip install -e ".[dev]"
pytest -q
lint-imports
ruff check src tests
```

## 다음 단계
- Step 2: `adapters/persistence/sqlite_repo.py`, `adapters/embedding/`
- Step 3: `adapters/sources/openalex.py` (허용목록 httpx 클라이언트)
- Step 4: `adapters/sources/alio/` (catalog · filedrop · sandbox 파서)
