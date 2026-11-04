"""② 선택 기록 중복 한 줄의 메모리 상태 (ADR 0056 2026-11-04 후속) — entrypoints/api/choice_dedupe.

세션마다 마지막 서명. apply → apply(같은 선택)은 한 번, apply → generate 는 둘 다, 사이에 다른
선택이 오면 다시. 최근 MAX 세션만(LRU).
"""

from __future__ import annotations

from rra.domain.models import OverlapAlert
from rra.domain.rules import similar_choice as sc
from rra.entrypoints.api.choice_dedupe import ChoiceDedupe

ROWS = [
    OverlapAlert(doc_id="a", title="과제 a", tier="own", similarity=0.85, blocking=True),
    OverlapAlert(doc_id="b", title="과제 b", tier="own", similarity=0.8, blocking=False),
]


def _recs(choices, *, event):
    return sc.choice_records(ROWS, choices, idea="h" * 16, at="t", event=event)


def test_dedupe_sequence_apply_apply_generate_apply():
    d = ChoiceDedupe()
    key = sc.session_key("staff:abc", "h" * 16)
    apply_a = sc.choice_signature(_recs({"a": "similar"}, event="apply"))
    apply_b = sc.choice_signature(_recs({"a": "unrelated"}, event="apply"))
    gen_a = sc.choice_signature(_recs({"a": "similar"}, event="generate"))
    written = []
    for sig in (apply_a, apply_a, gen_a, gen_a, apply_a, apply_b, apply_a, apply_a):
        if not d.is_repeat(key, sig):
            d.remember(key, sig)
            written.append(sig)
    assert written == [apply_a, gen_a, apply_a, apply_b, apply_a]


def test_dedupe_is_per_session_and_bounded():
    d = ChoiceDedupe(max_sessions=2)
    sig = sc.choice_signature(_recs({"a": "similar"}, event="apply"))
    k1, k2, k3 = (sc.session_key(o, "h" * 16) for o in ("staff:1", "staff:2", "guest:x"))
    d.remember(k1, sig)
    assert d.is_repeat(k1, sig) and not d.is_repeat(k2, sig)
    d.remember(k2, sig)
    d.remember(k3, sig)  # 가장 오래된 k1 을 잊는다
    assert len(d) == 2 and not d.is_repeat(k1, sig) and d.is_repeat(k3, sig)
    d.remember(k3, None)  # 줄 없음 — 그대로
    assert d.is_repeat(k3, sig)
