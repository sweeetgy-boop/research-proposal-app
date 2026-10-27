"""데이터 위치 고정 — 모든 실행 데이터는 레인 worktree 가 아니라 원 저장소의 data/ 절대 경로
(RRA_DATA_DIR)에 둔다.

(a) resolve_data_dir·data_path 단위 (환경변수 > git common dir 의 부모/data > cwd/data)
(b) worktree 보호: 연결 worktree 에서 RRA_DATA_DIR 없이 조립하면 모든 데이터 경로가 worktree 밖,
    원 저장소 data/ 아래
(c) 정적: src/rra 는 settings·config_loader·composition 밖에서 "data/…" 경로 리터럴을 만들지 않는다
"""

from __future__ import annotations

import ast
import logging
import shutil
import subprocess
from pathlib import Path

import pytest

from rra import config_loader as cl
from rra.config_loader import data_locations, data_path, resolve_data_dir
from rra.settings import Settings

ROOT = Path(__file__).parents[1]
ROOT_CONFIG = ROOT / "config"
SRC = ROOT / "src" / "rra"
GIT = shutil.which("git")

# "data/…" 리터럴을 둘 수 있는 유일한 곳 — 기본값 선언(settings)·데이터 위치 표(config_loader)·
# 조립(composition)
ALLOWED_LITERAL_FILES = {"settings.py", "config_loader.py", "composition.py"}


def settings_for(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


@pytest.fixture(autouse=True)
def _fresh_git_cache():
    """cwd 를 바꾸는 테스트가 있으므로 git 루트 캐시를 비운다(프로세스 공유)."""
    cl._git_repo_root.cache_clear()
    yield
    cl._git_repo_root.cache_clear()


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(  # noqa: S603
        [GIT, "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        timeout=30,
    )


@pytest.fixture
def repo_and_worktree(tmp_path: Path) -> tuple[Path, Path]:
    """원 저장소(커밋 1개) + 연결 worktree. 둘 다 resolve 한 절대 경로."""
    if GIT is None:
        pytest.skip("git 없음")
    repo = (tmp_path / "origin-repo").resolve()
    repo.mkdir()
    _git("init", "-q", cwd=repo)
    (repo / "README").write_text("x", encoding="utf-8")
    _git("add", "README", cwd=repo)
    _git("commit", "-q", "-m", "init", cwd=repo)
    wt = (tmp_path / "lanes" / "feat-x").resolve()
    _git("worktree", "add", "-q", "-b", "feat/x", str(wt), cwd=repo)
    return repo, wt


# ── (a) 단위 ────────────────────────────────────────────────
def test_env_override_wins_and_is_absolute(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "elsewhere" / "data"
    assert resolve_data_dir(settings_for(data_dir=target)) == target.resolve()
    # 상대 RRA_DATA_DIR 는 cwd 기준 절대 경로로
    assert (
        resolve_data_dir(settings_for(data_dir=Path("rel-data")))
        == (tmp_path / "rel-data").resolve()
    )


def test_env_variable_feeds_settings(monkeypatch, tmp_path):
    monkeypatch.setenv("RRA_DATA_DIR", str(tmp_path / "from-env"))
    assert Settings(_env_file=None).data_dir == tmp_path / "from-env"
    monkeypatch.delenv("RRA_DATA_DIR")
    assert Settings(_env_file=None).data_dir is None


def test_main_checkout_resolves_to_its_own_data(repo_and_worktree, monkeypatch):
    repo, _wt = repo_and_worktree
    monkeypatch.chdir(repo)
    assert resolve_data_dir(settings_for()) == repo / "data"
    # 하위 폴더에서 실행해도 저장소 루트/data
    sub = repo / "src" / "pkg"
    sub.mkdir(parents=True)
    cl._git_repo_root.cache_clear()
    monkeypatch.chdir(sub)
    assert resolve_data_dir(settings_for()) == repo / "data"


def test_linked_worktree_resolves_to_original_repo_data(repo_and_worktree, monkeypatch):
    repo, wt = repo_and_worktree
    monkeypatch.chdir(wt)
    resolved = resolve_data_dir(settings_for())
    assert resolved == repo / "data"
    assert not resolved.is_relative_to(wt)


def test_falls_back_to_cwd_data_without_git(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cl.shutil, "which", lambda _name: None)
    assert resolve_data_dir(settings_for()) == tmp_path.resolve() / "data"


def test_falls_back_to_cwd_data_outside_any_repo(tmp_path, monkeypatch):
    if GIT is None:
        pytest.skip("git 없음")
    outside = tmp_path / "plain"
    outside.mkdir()
    monkeypatch.chdir(outside)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.resolve()))
    assert resolve_data_dir(settings_for()) == outside.resolve() / "data"


def test_git_failure_is_tolerated(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def boom(*_a, **_k):
        raise subprocess.TimeoutExpired("git", 5)

    monkeypatch.setattr(cl.subprocess, "run", boom)
    assert resolve_data_dir(settings_for()) == tmp_path.resolve() / "data"


def test_data_path_rebases_relative_paths_only(tmp_path):
    s = settings_for(data_dir=tmp_path / "D")
    root = (tmp_path / "D").resolve()
    assert data_path(s, "data/korail_web") == root / "korail_web"  # data/ 접두어는 뗀다
    assert data_path(s, Path("data/cache/ntis")) == root / "cache" / "ntis"
    assert (
        data_path(s, "inbox/own") == root / "inbox" / "own"
    )  # 맨이름 상대 경로도 데이터 폴더 아래
    assert data_path(s, tmp_path / "abs") == tmp_path / "abs"  # 절대 경로는 그대로
    # only_prefixed: runs/ 같은 비데이터 상대 경로는 건드리지 않는다
    assert data_path(s, "runs", only_prefixed=True) == Path("runs")
    assert data_path(s, "data/eval/runs/x", only_prefixed=True) == root / "eval" / "runs" / "x"
    assert data_path(None, tmp_path / "abs") == tmp_path / "abs"  # settings 없이도 절대 경로는 통과


def test_resolve_logs_the_path_once(tmp_path, caplog):
    target = (tmp_path / "logged").resolve()
    cl._announced.discard(target)
    with caplog.at_level(logging.INFO, logger="rra.config_loader"):
        resolve_data_dir(settings_for(data_dir=target))
        resolve_data_dir(settings_for(data_dir=target))
    lines = [r.getMessage() for r in caplog.records if "데이터 폴더" in r.getMessage()]
    assert lines == [f"데이터 폴더: {target}"]


def test_db_and_runs_follow_the_rule(tmp_path):
    from rra.composition import data_locations as composed

    s = settings_for(data_dir=tmp_path / "D")
    assert composed(s)["db"] == (tmp_path / "D").resolve() / "rra.sqlite"
    assert data_path(s, s.runs_dir, only_prefixed=True) == Path("runs")


# ── (b) worktree 보호 ────────────────────────────────────────
WORKTREE_BUILDERS = {
    "build_korail_web_source": "root",
    "build_rnd_notice_source": "root",
    "build_bai_source": "root",
    "build_alio_source": "inbox",
    "build_alio_summary_source": "inbox",
    "build_alio_catalog": "catalog_dir",
    "build_own_projects_source": "inbox",
    "build_own_docs_source": "inbox",
    "build_vision_store": "root",
}  # vision_snapshots 는 스냅샷 폴더가 있어야 만들어진다 — data_locations 키로만 검사


def test_worktree_never_holds_data(repo_and_worktree, monkeypatch):
    """worktree 경로에 데이터 쓰기 금지 — 연결 worktree 에서 RRA_DATA_DIR 없이 조립하면
    composition 이 쓰는 모든 데이터 경로가 worktree 밖, 원 저장소 data/ 아래다."""
    import rra.composition as comp

    repo, wt = repo_and_worktree
    monkeypatch.delenv("RRA_DATA_DIR", raising=False)
    monkeypatch.chdir(wt)
    settings = settings_for(config_dir=ROOT_CONFIG)  # 실제 config/*.yaml (data/… 상대 경로들)

    located = data_locations(settings)
    assert set(located) == set(cl.DATA_LOCATION_KEYS) and len(located) >= 15
    for key, path in located.items():
        assert path.is_absolute(), key
        assert path.is_relative_to(repo / "data"), (key, path)
        assert not path.is_relative_to(wt), (key, path)

    for builder, attr in WORKTREE_BUILDERS.items():
        obj = getattr(comp, builder)(settings)
        path = Path(getattr(obj, attr))
        assert path.is_absolute() and path.is_relative_to(repo / "data"), (builder, path)
        assert not path.is_relative_to(wt), (builder, path)

    # 백업 대상 `data/backups` 도 같은 규칙 (rra db backup --out data/backups)
    assert data_path(settings, "data/backups", only_prefixed=True) == repo / "data" / "backups"


def test_worktree_rule_honours_explicit_override(repo_and_worktree, monkeypatch):
    repo, wt = repo_and_worktree
    override = repo.parent / "shared-data"
    monkeypatch.setenv("RRA_DATA_DIR", str(override))
    monkeypatch.chdir(wt)
    settings = Settings(_env_file=None, config_dir=ROOT_CONFIG)
    for key, path in data_locations(settings).items():
        assert path.is_relative_to(override.resolve()), (key, path)


# ── (c) 정적 ────────────────────────────────────────────────
def _data_literals(path: Path) -> list[tuple[int, str]]:
    """docstring·argparse help 를 뺀, "data/" 로 시작하는 문자열 리터럴과 Path("data")."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    skip: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                skip.add(id(body[0].value))
        if isinstance(node, ast.keyword) and node.arg == "help":
            skip.add(id(node.value))
            for sub in ast.walk(node.value):
                skip.add(id(sub))
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in skip:
            if node.value.startswith("data/"):
                found.append((node.lineno, node.value))
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "Path"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "data"
        ):
            found.append((node.lineno, "Path('data')"))
    return found


def test_no_data_literals_outside_settings_loader_composition():
    """새 코드는 data_path/data_location 을 거친다 — 어댑터·유스케이스·진입점에 "data/…" 를 쓰지
    않는다."""
    offenders = {}
    for py in sorted(SRC.rglob("*.py")):
        if py.name in ALLOWED_LITERAL_FILES and py.parent == SRC:
            continue
        hits = _data_literals(py)
        if hits:
            offenders[str(py.relative_to(ROOT))] = hits
    assert not offenders, f"data_path 를 거치지 않은 데이터 경로 리터럴: {offenders}"


def test_adapters_take_explicit_store_paths():
    """어댑터 생성자는 cwd 기준 data/ 기본값을 갖지 않는다(조립이 절대 경로를 준다)."""
    import inspect

    from rra.adapters.sources.audit.mofe import MofeEvaluationSource
    from rra.adapters.sources.datago.source import DataGoKrFileSource
    from rra.adapters.sources.molit.source import MolitPolicySource
    from rra.adapters.sources.rnd_notice.crawler import RndNoticeCrawler

    for cls, name in [
        (MofeEvaluationSource, "store_dir"),
        (DataGoKrFileSource, "store_dir"),
        (MolitPolicySource, "store_dir"),
        (RndNoticeCrawler, "root"),
    ]:
        param = inspect.signature(cls.__init__).parameters[name]
        assert param.default is inspect.Parameter.empty, (cls.__name__, name)


def test_env_and_gitignore_keep_data_out_of_commits():
    """data/ 는 루트 .gitignore 에 있고(커밋 금지), .env.example 이 RRA_DATA_DIR 를 안내한다."""
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "/data/" in ignore
    assert "RRA_DATA_DIR" in (ROOT / ".env.example").read_text(encoding="utf-8")
