"""run 저장소 — ④ 임시 저장(draft_working.json)·검토 파일 이름(draft/final)·옛 이름 호환."""

from __future__ import annotations

from rra.adapters.fake import InMemoryRunStore as FakeModeStore
from rra.adapters.runs import FileRunStore
from rra.domain.models import ProposalRequest, ReviewRound
from tests.fakes import InMemoryRunStore

REQ = ProposalRequest(current_state="a", root_cause="b", limitation="c", goal="d")
STEPS = ["retrieve", "section:title", "finalize"]


def _roundtrip(store):
    state = store.create("local", REQ, STEPS, "2026-10-27T00:00:00+00:00")
    rid = state.run_id
    assert store.load_working("local", rid) is None
    store.save_working("local", rid, {"sections": [{"key": "title", "texts": ["임시"]}]})
    assert store.load_working("local", rid)["sections"][0]["texts"] == ["임시"]
    store.save_working("local", rid, {"sections": []})  # 덮어쓴다 (버전 아님)
    assert store.load_working("local", rid) == {"sections": []}
    store.clear_working("local", rid)
    assert store.load_working("local", rid) is None
    store.clear_working("local", rid)  # 없어도 조용히
    return rid


def test_working_copy_round_trip_in_file_and_memory_stores(tmp_path):
    store = FileRunStore(tmp_path / "runs")
    rid = _roundtrip(store)
    assert not (tmp_path / "runs" / "local" / rid / "draft_working.json").exists()
    store.save_working("local", rid, {"x": 1})
    assert (tmp_path / "runs" / "local" / rid / "draft_working.json").is_file()
    assert store.list_versions("local", rid) == []  # 임시 저장은 버전이 아니다
    _roundtrip(InMemoryRunStore())
    _roundtrip(FakeModeStore())


def test_review_files_are_named_by_kind_and_legacy_names_still_load(tmp_path):
    store = FileRunStore(tmp_path / "runs")
    state = store.create("local", REQ, STEPS, "2026-10-27T00:00:00+00:00")
    rid = state.run_id
    store.save_review("local", rid, ReviewRound(round=1, kind="draft", draft_version=1))
    store.save_review("local", rid, ReviewRound(round=2, kind="final", draft_version=3))
    store.save_review("local", rid, ReviewRound(round=3, kind="final", draft_version=5))
    folder = tmp_path / "runs" / "local" / rid / "reviews"
    assert sorted(p.name for p in folder.iterdir()) == [
        "review_draft.json",
        "review_final_r1.json",
        "review_final_r2.json",
    ]
    assert store.list_reviews("local", rid) == [1, 2, 3]
    assert store.load_review("local", rid, 2).kind == "final"
    assert store.load_review("local", rid, 3).final_round == 2
    assert store.load_review("local", rid, 4) is None
    # 옛 이름(review_rN.json)으로 저장된 run 도 읽힌다 — kind 는 번호로 유추
    legacy = store.create("local", REQ, STEPS, "2026-10-27T00:00:00+00:00")
    old_dir = tmp_path / "runs" / "local" / legacy.run_id / "reviews"
    old_dir.mkdir()
    (old_dir / "review_r1.json").write_text(
        ReviewRound(round=1, draft_version=1).model_dump_json(exclude={"kind"}), encoding="utf-8"
    )
    (old_dir / "review_r2.json").write_text(
        ReviewRound(round=2, draft_version=2).model_dump_json(exclude={"kind"}), encoding="utf-8"
    )
    assert store.list_reviews("local", legacy.run_id) == [1, 2]
    assert store.load_review("local", legacy.run_id, 1).kind == "draft"
    assert store.load_review("local", legacy.run_id, 2).kind == "final"
