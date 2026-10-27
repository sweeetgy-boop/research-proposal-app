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


# ── 보고서 교차 자료원 동일성 (NTIS report ↔ ScienceON internal_report, 2026-10-27) ───
def _rpt(doc_id, source, doc_type, title, project_no=None, year=None, abstract=""):
    from datetime import date

    from rra.domain.models import Document

    return Document(
        doc_id=doc_id,
        source=source,
        doc_type=doc_type,
        title=title,
        abstract=abstract or None,
        pub_date=date(year, 1, 1) if year else None,
        text_basis="abstract",
        raw={"project_no": project_no} if project_no else {},
    )


def test_same_report_needs_project_no_and_title_year_agree():
    from rra.domain.rules.dedup import report_identity, same_report

    a = _rpt("ntis:R1", "ntis", "report", "궤도 틀림 감시 최종보고서", "1415171234", 2023)
    b = _rpt(
        "scienceon:C1",
        "scienceon",
        "internal_report",
        "궤도 틀림 감시 최종 보고서",
        "1415171234",
        2023,
    )
    assert report_identity(a) == report_identity(b) and same_report(a, b)
    assert not same_report(
        a,
        _rpt(
            "scienceon:C2",
            "scienceon",
            "internal_report",
            "궤도 틀림 감시 최종보고서",
            "1415171234",
            2022,
        ),
    )
    assert same_report(
        a,
        _rpt(
            "scienceon:C3",
            "scienceon",
            "internal_report",
            "궤도 틀림 감시 최종보고서",
            "1415171234",
        ),
    )
    assert not same_report(
        a,
        _rpt(
            "scienceon:C4",
            "scienceon",
            "internal_report",
            "궤도 틀림 감시 1차년도 보고서",
            "1415171234",
            2023,
        ),
    )
    assert report_identity(_rpt("alio:1", "alio", "internal_report", "t")) is None
    assert report_identity(_rpt("ntis:P", "ntis", "rnd_project", "t", "1415171234")) is None


def test_dedup_keeps_one_of_same_report_and_separates_annual_reports():
    from rra.domain.rules.dedup import dedup

    docs = [
        _rpt(
            "scienceon:C1",
            "scienceon",
            "internal_report",
            "궤도 틀림 감시 최종보고서",
            "1415171234",
            2023,
            "짧은",
        ),
        _rpt(
            "ntis:R1",
            "ntis",
            "report",
            "궤도 틀림 감시 최종보고서",
            "1415171234",
            2023,
            "더 긴 초록 본문",
        ),
        _rpt("ntis:R2", "ntis", "report", "궤도 틀림 감시 1차년도 보고서", "1415171234", 2022),
        _rpt(
            "ntis:R3", "ntis", "report", "궤도 틀림 감시 최종보고서", "9999999999", 2023
        ),  # 다른 과제, 같은 제목
    ]
    assert sorted(d.doc_id for d in dedup(docs)) == ["ntis:R1", "ntis:R2", "ntis:R3"]
