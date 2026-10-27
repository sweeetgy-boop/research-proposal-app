# 레인 D2 — feat/data-dir (2026-10-27, 데이터 위치 고정) 전달 사항

## 전달한 것
- **규칙** 모든 실행 데이터(적재 DB·크롤 스냅샷·받은 파일·캐시·vision_cache·inbox·eval·bench·backups)는 레인 worktree 가 아니라
  원 저장소 `data/` 절대 경로(`RRA_DATA_DIR`)에 쓴다. 계기: 합쳐진 브랜치의 worktree 를 지우면서 그 안의 미커밋 스냅샷이 사라짐.
- **설정** `Settings.data_dir`(`RRA_DATA_DIR`, 기본 None). `config_loader.resolve_data_dir`: RRA_DATA_DIR > `git rev-parse
  --git-common-dir` 의 부모/data(연결 worktree 에서도 본 체크아웃) > cwd/data. git 은 `shutil.which` 절대 경로·고정 인자·5초 timeout·
  shell 없음. 처음 정해질 때 `데이터 폴더: <경로>` 한 줄 로그(경로만).
- **경로 변환** `data_path(settings, rel, only_prefixed=False)`: 절대 경로 그대로, 상대 경로는 `data/` 접두어를 떼고 데이터 폴더 아래
  (`only_prefixed=True` 면 `data/…` 만 옮기고 `runs` 같은 상대 경로는 그대로). `data_location(settings, key, cfg=…)`·`data_locations`:
  `_DATA_LOCATIONS` 표(db·alio 3·own 2·ntis_cache·korail_web·rnd_notice·bai·molit·mofe·datago·vision_store·vision_snapshots·eval·bench).
- **조립** `composition.build_*` 가 전부 표를 거쳐 어댑터에 절대 경로를 준다(`build_repository` db, alio catalog/inbox/summary, own
  inbox 2, ntis FileCache, korail_web root(백업 파일 목록 포함), rnd_notice·bai root, molit·mofe·datago store, vision store/snapshots,
  `build_run_manager` runs_dir 는 `data/` 아래일 때만). CLI: `rra llm-bench`·`rra eval` 기본 출력·runs 폴더, `rra db backup --out
  data/backups`(launchd plist 그대로 — `data/` 접두어만 데이터 폴더로). `.env.example` 에 `RRA_DATA_DIR=` 안내.
- **어댑터** `MolitPolicySource`·`MofeEvaluationSource`·`DataGoKrFileSource` 의 `store_dir`, `RndNoticeCrawler` 의 `root` 는 필수
  인자(cwd 기준 `data/…` 기본값 제거). `NoticeConfig.snapshot_dir` 필드 제거(조립이 yaml 에서 직접 읽는다).
- **테스트** `tests/test_data_dir.py` 15건: (a) 환경변수·상대 RRA_DATA_DIR·본 체크아웃/하위 폴더·임시 git 저장소 + `git worktree add`
  → 원 저장소 data·git 없음/저장소 밖/실패 폴백·data_path 규칙·로그 1회·db/runs, (b) "worktree 경로에 데이터 쓰기 금지": 연결
  worktree 에서 RRA_DATA_DIR 없이 실제 `config/*.yaml` 로 `data_locations` 전부 + `build_*` 9종의 root/inbox 가 worktree 밖·원 저장소
  data/ 아래, 덮어쓰기 존중, (c) 정적: `src/rra` 에서 settings·config_loader·composition 밖의 `"data/…"` 리터럴·`Path("data")` 금지
  (docstring·argparse help 제외), 어댑터 생성자 기본값 없음, `.gitignore`/`.env.example`. 기존 `test_own_sources_are_wired_from_sources_yaml`
  은 상대 yaml 경로가 데이터 폴더 아래 절대 경로가 되는 새 규칙으로 기대값만 바꿈. `pytest -q -n auto` 1,670 통과·16 skip,
  `lint-imports` 8 kept, `ruff check`·`ruff format --check` 통과.
- **문서** CONTRIBUTING "데이터 위치"(규칙·worktree 삭제 전 `git status --ignored` 확인·서브에이전트 확인 절차·덮어쓰기), architecture §10 행.

## 자동 결정
- 상대 yaml 경로는 `data/` 접두어가 없어도(예: `inbox/own`) 데이터 폴더 아래로 옮긴다(의도: worktree cwd 에 데이터를 두지 않는다).
  `runs/`·사용자가 `--out`/`--runs-dir` 로 준 경로는 `data/` 로 시작할 때만 옮긴다(`only_prefixed`).
- `docs/ocr-sample`(vision sample) 은 문서라 그대로. bare 저장소·서브모듈(`--git-common-dir` 가 `.git` 이름이 아님)은 루트를
  단정하지 않고 cwd/data 폴백.

## 남은 것
- 운영 plist 는 절대 경로를 이미 쓰므로 변경 없음. 다른 레인이 이미 worktree `data/` 에 모은 자료는 원 저장소 `data/` 로 옮긴 뒤 지운다.
