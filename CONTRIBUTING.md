# 기여 방법

## 흐름
1. `main` 에서 기능 단위의 짧은 브랜치를 만든다. 이름 규칙: `feat/<무엇>`, `fix/<무엇>`, `chore/<무엇>`, `docs/<무엇>`.
2. 로컬 검사 통과 → 커밋 → push → PR. PR 템플릿(`.github/pull_request_template.md`)을 채운다.
   ```bash
   pytest -q && lint-imports && ruff check src tests      # backend
   cd web && npm run lint && npm run typecheck && npm test  # web (있을 때)
   ```
3. CI(`.github/workflows/ci.yml`: `backend`, `web`)가 통과하면 합친다(squash 금지, merge commit). 합친 뒤 브랜치는 지운다.
4. 다음 작업이 앞 PR 에 의존하면 앞 PR 이 합쳐진 뒤 `main` 에서 새 브랜치를 만든다.
5. **경과 기록(`docs/history/`)** — 합치기 전에 반드시:
   - `docs/history/timeline.md` 에 항목 하나(날짜, 무엇을, 왜, PR 번호, 핵심 수치).
   - 수치(테스트 수·자료원 건수·생성 시간·점수 등)가 바뀌었으면 `docs/history/metrics.csv` 에 행 추가
     (`tools/history_charts.py` 로 그래프 재생성).
   - 주요 결정(모델·구조·임계치·흐름)은 `docs/history/decisions/NNNN-<slug>.md` 에 ADR(배경·선택지·결정·이유·결과).
   - 화면이 바뀌었으면 `docs/history/screens/<YYYY-MM-DD>-<화면>.png` 캡처.

## 동료 PC 준비 (백엔드 없이 프론트엔드만 개발할 때)
```bash
git clone <저장소> && cd research-proposal-app
uv venv --python 3.12 && uv pip install -e ".[dev]"     # 임베딩·모델 없이 돈다
cp .env.example .env && chmod 600 .env                   # RRA_API_TOKEN 만 채운다 (openssl rand -hex 32)
RRA_FAKE_LLM=1 .venv/bin/rra api                         # 가짜 LLM·메모리 저장소. 127.0.0.1:8000
cd web && npm install && npm run dev                      # 프론트엔드 (있을 때)
```
가짜 모드에서는 precheck·생성·검토·마무리가 모두 가짜 응답으로 즉시 돌아온다. 실제 모델·DB 는 Mac mini 에만 있다.
REST 스키마는 `docs/openapi.json` (`rra api schema` 로 생성), 세션 쿠키·CSRF 는 `deploy/README.md` §4.

## API 변경
- 요청·응답 필드가 바뀌어야 하면 **먼저 Issue** 로 올린다(어느 화면이 무엇을 필요로 하는지).
- 백엔드 PR 이 `docs/openapi.json` 을 바꾸면 PR 본문 "프론트엔드 영향" 에 **명시**한다. 프론트엔드는 그 PR 이 합쳐진 뒤 맞춘다.
- 청크·제안서 본문·검토 의견은 수집 자료·LLM 출력(비신뢰 텍스트)이다. 화면에 그대로 HTML 로 넣지 않는다.

## 비밀·데이터
- `.env`, 접속 토큰, API 키(Gemini·ScienceON·NTIS·KIPRIS), 기기 MAC 은 **공유 금지** — 채팅·이슈·PR·커밋에 넣지 않는다.
- `data/`(DB·inbox)·`runs/`·실물 양식 `config/templates/proposal_korail.hwpx` 는 커밋하지 않는다(.gitignore).
- PR 본문·이슈에 사내 과제명·제안자 이름을 적지 않는다(건수·구조만).

## 데이터 위치 (2026-10-27)
- **모든 실행 데이터는 `RRA_DATA_DIR` 한 곳에**: 적재 DB(`data/rra.sqlite`)·크롤 스냅샷(`korail_web`·`rnd_notice`·`bai`)·받은 파일
  (`molit`·`mofe`·`datago`)·캐시(`cache/ntis`, `ocr/`, `vision_cache/`, `vision_log.jsonl`)·inbox(`inbox/own`·`own_docs`·`alio`·
  `catalog`)·측정(`eval`·`bench`)·백업(`backups`). 기본값은 **원 저장소의 `data/` 절대 경로** — `git rev-parse --git-common-dir`
  의 부모(`config_loader.resolve_data_dir`). 연결 worktree 에서 돌려도 같은 곳을 쓴다. git 이 없으면 `cwd/data`.
- **worktree 는 데이터를 갖지 않는다.** 합쳐진 브랜치의 worktree 를 지울 때 그 안의 미커밋 스냅샷이 함께 사라진 일(2026-10-27)이 계기다.
  지우기 전에 `git -C <worktree> status --ignored --short | grep '^!! data/'` 로 데이터가 남아 있는지 본다. 남아 있으면 원 저장소
  `data/` 로 옮긴 뒤 지운다.
- **코드 규칙**: 상대 데이터 경로(`settings.db_path` 기본값, `config/*.yaml` 의 `snapshot_dir`·`store_dir`·`cache_dir`·`*_inbox`)는
  `config_loader.data_path`/`data_location` 이 데이터 폴더 기준 절대 경로로 바꾸고 조립(`composition.build_*`)이 어댑터에 절대 경로를
  준다. 어댑터·유스케이스·진입점에 `"data/…"` 리터럴이나 cwd 기준 기본값을 두지 않는다(`tests/test_data_dir.py` 가 막는다 —
  새 데이터 경로는 `config_loader._DATA_LOCATIONS` 표에 더한다). `runs/` 는 그대로(`data/` 아래로 지정했을 때만 옮긴다).
- **덮어쓰기**: `.env` 또는 환경변수 `RRA_DATA_DIR=/절대/경로` (상대면 cwd 기준). 기동 로그에 `데이터 폴더: <경로>` 한 줄이 남는다.
  `RRA_DB_PATH` 가 상대 경로면 `RRA_DATA_DIR` 기준이다.
- **자료를 모으는 서브에이전트·레인**은 시작할 때 `PYTHONPATH=src .venv/bin/python -c "from rra.composition import
  load_settings, resolve_data_dir; print(resolve_data_dir(load_settings()))"` 로 원 저장소 `data/` 가 찍히는지 확인하고, 다른 곳에
  모아야 하면 `RRA_DATA_DIR` 를 명시한다.

## 코드 규칙 (백엔드)
- 헥사고날 계층(`CLAUDE.md`, `docs/architecture.md` §1). `lint-imports` 계약 8건이 강제한다.
- 새 기능은 domain → ports → usecase(fake 로 테스트) → adapter. 테스트는 LLM·임베딩·네트워크 없이 돌아야 한다(`tests/fakes.py`).
- 키 값·원문은 로그·manifest·테스트 fixture 에 남기지 않는다(보안 D·I).

## 병렬 작업 — 조각 파일과 공유 파일 (2026-10-27)

여러 브랜치가 동시에 진행될 때 공유 파일의 충돌을 막는 규칙.

- **공유 파일은 통합 담당(메인 세션)만 고친다**: `docs/openapi.json`, `docs/status.md`, `docs/history/timeline.md`·`metrics.csv`,
  `README.md`, `docs/presentation*/`, `CONTRIBUTING.md`, `config/retrieval_mix.yaml`.
- **작업 브랜치는 조각 파일만 쓴다**: `docs/history/timeline.d/<날짜>-<브랜치>.md`(연표 행), `docs/history/metrics.d/<브랜치>.csv`
  (metrics.csv 와 같은 머리글), `docs/status.d/<브랜치>.md`(현황 행·납품 목록), `docs/history/decisions/`(새 ADR 파일만),
  `docs/history/screens/`(새 캡처만), `docs/history/progress.d/<브랜치>.md`(30분마다 진행 메모). API 변경은 PR 본문
  "프론트엔드 영향" 에 경로 목록으로 적는다.
- **합칠 때** 통합 담당이 조각을 공유 파일에 모으고 `rra api schema` 로 `docs/openapi.json` 을 다시 만든다. 모은 조각 파일은
  지우지 않고 남긴다(이력).
- `config/*.yaml` 과 `composition.py` 는 최소한으로 고치고, 새 항목은 가능하면 새 파일·새 함수로 추가한다.
- **무거운 작업은 한 번에 하나**(mlx 서버 사용·임베딩·재색인·대량 파싱·OCR·적재·측정): `tools/with_heavy_lock.py -- <명령>` 으로
  `runs/.heavy.lock` 을 잡고 돌린다. mlx 서버는 한 번에 하나만 띄운다.
- **테스트는 병렬**: `pytest -q -n auto`(pytest-xdist). 병렬에서 깨지는 테스트는 임시 디렉터리·포트·전역 상태를 분리해 고친다.
  CI 는 backend-unit / backend-api, web-check / web-e2e 로 나눠 돌고, 보호 규칙의 필수 검사 이름 `backend`·`detect`·`web` 은
  나눈 job 이 모두 통과해야 성공하는 모음 job 이다.
