# 연구제안서 작성 앱 (research-proposal-app)

연구과제 제안서 자동 작성 — 헥사고날 구조, 보안코딩 반영. 설계는 `docs/architecture.md`.

## 설치

```bash
uv venv --python 3.12 && source .venv/bin/activate
uv pip install -e ".[dev]"        # persistence + llm + mcp + 검사 도구
pytest -q && lint-imports && ruff check src tests
```

임베딩 모델까지 쓰려면 `uv pip install -e ".[adapters]"` (torch 포함, 무겁다).

## Step 3 (현재)

- `adapters/llm/openai_compat.py` — OpenAI 호환 `/v1/chat/completions` (mlx-lm · OpenAI 공용).
  재시도·타임아웃·`json_mode` 폴백. provider가 로컬인데 base_url이 루프백이 아니면 기동 거부(보안 H).
- `adapters/llm/prompts/*.md` — 시스템·섹션 프롬프트. `PromptLibraryPort`로 주입한다.
- `composition.py` — `build_llm(stage=)` · `build_prompt_library()` · `build_precheck()`.
- `entrypoints/mcp/` — stdio MCP 서버. 읽기 도구 2개(`rra_precheck`, `rra_search`). `docs/mcp.md`.

```bash
rra precheck --current-state "..." --root-cause "..." --limitation "..." --goal "..."
rra search "궤도 틀림 자동 감지" -k 5
rra llm-check --stage compose     # mlx-lm 왕복 1회
rra mcp                           # = python -m rra.entrypoints.mcp.server
```

## 다음 단계

- Step 4: `adapters/sources/openalex.py` (허용목록 httpx 클라이언트), `ingest_sources`
- Step 5: `adapters/sources/alio/` (catalog · filedrop · sandbox 파서)
- Step 6: `RunManager` + MCP `rra_generate` · `rra_get_draft`
