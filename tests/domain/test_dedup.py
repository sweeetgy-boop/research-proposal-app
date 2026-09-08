from rra.domain.rules.dedup import dedup


def test_doi_case_insensitive_dedup(docs):
    out = dedup(docs)
    assert len(out) == 2
    assert {d.doc_id for d in out} == {"alio:1", "openalex:W1"}
