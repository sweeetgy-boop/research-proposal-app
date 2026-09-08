from rra.domain.services.chunking import chunk_document


def test_toc_chunking(docs):
    ch = chunk_document(docs[0])
    assert [c.heading for c in ch] == ["1장 서론", "2장 방법"]
    assert ch[0].chunk_id == "alio:1#0"
