from rra.domain.services.chunking import chunk_document


def test_toc_chunking(docs):
    ch = chunk_document(docs[0])
    assert [c.heading for c in ch] == ["1장 서론", "2장 방법"]
    assert ch[0].chunk_id == "alio:1#0"


def test_chunks_inherit_text_basis():
    from rra.domain.models import Document
    from rra.domain.services.chunking import chunk_document

    doc = Document(
        doc_id="alio:c1",
        source="alio",
        doc_type="internal_report",
        title="t",
        body="가" * 40,
        text_basis="summary",
    )
    assert {c.basis for c in chunk_document(doc, max_chars=10)} == {"summary"}
