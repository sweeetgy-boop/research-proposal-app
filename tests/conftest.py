import pytest

from rra.domain.models import Chunk, Document, ProposalRequest


@pytest.fixture
def req():
    return ProposalRequest(
        current_state="궤도 틀림 점검이 수작업",
        root_cause="센서 부재",
        limitation="주기 점검만 가능",
        goal="상시 자동 감지",
    )


@pytest.fixture
def docs():
    return [
        Document(
            doc_id="alio:1",
            source="alio",
            doc_type="internal_report",
            title="궤도 상태 자동 감지 연구",
            body="1장 서론 ... 2장 방법 ...",
            orgs=["korail"],
            department="철도연구원",
            toc=["1장 서론", "2장 방법"],
        ),
        Document(
            doc_id="openalex:W1",
            source="openalex",
            doc_type="paper",
            title="Track geometry monitoring",
            abstract="IMU-based",
            doi="10.1/x",
        ),
        Document(
            doc_id="scienceon:9",
            source="scienceon",
            doc_type="paper",
            title="Track Geometry Monitoring",
            abstract="dup",
            doi="10.1/X",
        ),
    ]


@pytest.fixture
def chunks(docs):
    return [
        Chunk(chunk_id="alio:1#0", doc_id="alio:1", ordinal=0, text="1장 서론 ..."),
        Chunk(chunk_id="openalex:W1#0", doc_id="openalex:W1", ordinal=0, text="IMU-based"),
    ]


@pytest.fixture
def own():
    """own 티어 기준 (config/sources.yaml own_unit 과 같은 모양)."""
    from rra.domain.rules.overlap import OwnUnit

    return OwnUnit(org="korail", departments=frozenset({"철도연구원", "경영연구처", "기술연구처"}))
