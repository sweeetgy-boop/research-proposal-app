from rra.domain.models import Document
from rra.domain.rules.dedup import dedup, should_replace


def test_doi_case_insensitive_dedup(docs):
    out = dedup(docs)
    assert len(out) == 2
    assert {d.doc_id for d in out} == {"alio:1", "openalex:W1"}


def _report(basis, body, doc_id="alio:c1"):
    return Document(
        doc_id=doc_id,
        source="alio",
        doc_type="internal_report",
        title="궤도 상태 진단",
        body=body,
        text_basis=basis,
    )


def test_full_text_beats_longer_summary():
    full = _report("full_text", "짧은 원문", doc_id="alio:sha-1")
    summary = _report("summary", "훨씬 긴 공개 요약 " * 20)
    assert dedup([summary, full]) == [full]
    assert dedup([full, summary]) == [full]


def test_same_basis_keeps_longer_body():
    a, b = _report("summary", "짧다"), _report("summary", "더 길다 더 길다")
    assert dedup([a, b]) == [b]


def test_should_replace_blocks_downgrade_only():
    full, summary = _report("full_text", "원문"), _report("summary", "요약")
    assert should_replace(None, summary)
    assert should_replace(summary, full)
    assert should_replace(summary, summary)
    assert not should_replace(full, summary)
