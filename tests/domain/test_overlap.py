from rra.domain.rules.overlap import judge


def test_own_tier_blocks_at_lower_threshold(docs):
    alerts = judge([(docs[0], 0.82), (docs[1], 0.82)])
    own = next(a for a in alerts if a.doc_id == "alio:1")
    ext = next(a for a in alerts if a.doc_id == "openalex:W1")
    assert own.tier == "own" and own.blocking
    assert ext.tier == "external" and not ext.blocking
