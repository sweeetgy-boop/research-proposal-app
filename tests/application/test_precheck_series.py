"""② 같은 연작 한 줄 (2026-10-29 레인 A, ADR 0043) — 연작을 묶은 뒤에도 표가 서로 다른 과제 k 줄,
reranker 입력은 종전 건수 이하, AI 같음 판정은 연작 행을 한 번(라벨·판 제목과 함께). FakeLLM 만."""

from __future__ import annotations

from rra.application.usecases.judge_sameness import SameJudge
from rra.application.usecases.precheck_overlap import PrecheckOverlap
from rra.domain.models import Document, ProposalRequest
from rra.domain.rules.keywords import KeywordRule
from rra.domain.rules.overlap import RerankRule
from rra.domain.rules.overlap_candidates import OverlapCandidateRule, SourceMember
from rra.domain.rules.series import SeriesRule
from tests.application.test_precheck_flow_usecases import verdicts
from tests.fakes import FakeLLM, InMemoryRepository

IDEA = ProposalRequest(
    title_hint="신설역 개통을 반영한 광역철도 월별 수송수요 예측 모형 개선",
    current_state="광역철도 수송수요는 해마다 시계열 모형으로 다음 해 수요를 예측한다.",
    root_cause="신설역 개통이 잦아 과거 시계열만으로는 개통 초기 수요 변화를 반영하기 어렵다.",
    limitation="신설역 수요는 별도 가정으로 보정해 예측 오차가 크다.",
    goal="신설역 개통 효과와 월별 계절성을 반영하는 광역철도 수송수요 예측 모형을 만든다.",
)


def _doc(doc_id: str, title: str, *, visibility: str = "public") -> Document:
    source = doc_id.split(":", 1)[0]
    return Document(
        doc_id=doc_id,
        source=source,
        doc_type={"own": "rnd_project", "alio": "internal_report"}.get(source, "procurement"),
        title=title,
        body=f"{title}. 광역철도 수송수요를 예측함.",
        visibility=visibility,
    )


SERIES = [
    _doc(f"{src}:gy{y}", f"{y}년도 광역철도 수송수요 예측 연구")
    for y in range(2016, 2028)
    for src in ("own", "alio", "korail_web")
]
GOSOK = [_doc(f"own:gs{y}", f"{y}년도 고속철도 수송수요 예측 연구") for y in range(2023, 2028)]
OTHERS = [
    _doc("own:nambu", "경기남부권 신설노선 개통에 따른 광역철도 수송수요 변화 예측"),
    _doc("own:ai", "AI 기반 철도 단기 수송수요 예측 자동화 연구"),
    _doc("alio:mid", "광역철도 중장기(2026~2055) 수송수요 예측 연구"),
    _doc("own:station", "역세권 개발에 따른 승차 인원 변화 분석"),
]
ALL = [*SERIES, *GOSOK, *OTHERS]


class Scorer:
    """reranker 대역 — 연작이 가장 높고, 그다음 다른 과제. 받은 건수를 기록한다."""

    model_name = "fake/scorer"

    def __init__(self):
        self.sizes: list[int] = []

    async def score_documents(self, query, docs):
        self.sizes.append(len(docs))
        out = []
        for d, _ in docs:
            if "gy" in d.doc_id:
                out.append(0.9 + int(d.doc_id[-4:]) / 100000)
            elif "gs" in d.doc_id:
                out.append(0.8)
            else:
                out.append({"own:nambu": 0.75, "alio:mid": 0.7, "own:ai": 0.65}.get(d.doc_id, 0.2))
        return out


def _repo() -> InMemoryRepository:
    repo = InMemoryRepository()
    repo.seed(ALL, [])
    # e5 순위: 연작이 상위를 메운다 (시범 08 과 같은 모양)
    repo.similar = [(d, 0.9 - i * 0.001) for i, d in enumerate(ALL)]
    return repo


def _precheck(repo, *, series=True, scorer=None, judge=None, k=5):
    return PrecheckOverlap(
        repo,
        k=k,
        keywords=KeywordRule(),
        reranker=scorer if scorer is not None else Scorer(),
        rerank=RerankRule(threshold=0.5),
        candidates=OverlapCandidateRule(
            project=(
                SourceMember(source="own"),
                SourceMember(source="alio"),
                SourceMember(source="korail_web"),
            ),
            per_source=3,
            pool_size=12,
        ),
        series=SeriesRule() if series else None,
        same_judge=judge,
    )


async def test_without_series_the_table_is_all_one_series():
    """종전(연작 묶기 없음): 같은 제목만 합쳐져 표가 연작 판으로 찬다 — 다른 과제가 못 든다."""
    result = await _precheck(_repo(), series=False).run(IDEA, ai=False)
    titles = [a.title for a in result.alerts]
    assert all("광역철도 수송수요 예측 연구" in t for t in titles)
    assert "own:nambu" not in {a.doc_id for a in result.alerts}


async def test_series_row_frees_the_table_for_other_projects():
    scorer = Scorer()
    result = await _precheck(_repo(), scorer=scorer).run(IDEA, ai=False)
    rows = result.alerts
    assert len(rows) == 5  # 묶은 뒤에도 k 줄
    first = rows[0]
    assert first.series is not None and first.series.label == "광역철도 수송수요 예측"
    # 대표 = reranker 에 보낸 판(연작마다 e5 상위 2건) 중 점수 최고
    assert first.doc_id in {"own:gy2016", "alio:gy2016"}
    assert first.series.count >= 2 and len(first.merged_ids) >= first.series.count - 1
    years = [m.year for m in first.series.members]
    assert years == sorted(years)
    assert rows[1].series is not None and rows[1].series.label == "고속철도 수송수요 예측"
    others = {a.doc_id for a in rows[2:]}
    assert others == {"own:nambu", "alio:mid", "own:ai"}
    # reranker 입력은 종전과 같은 k × 3 건 이하 (연작마다 상위 2건만)
    assert scorer.sizes and max(scorer.sizes) <= 15


async def test_series_row_is_judged_once_with_label_and_editions():
    answer = verdicts(
        ("own:gy2016", "partial", "광역철도 수요 예측 대상은 같으나 월별·신설역 반영이 다름"),
        ("own:gs2023", "different", "고속철도로 대상이 다름"),
        ("own:nambu", "partial", "신설노선 수요 변화라는 문제가 겹침"),
        ("alio:mid", "different", "중장기 예측으로 기간이 다름"),
        ("own:ai", "different", "단기 자동화로 방법이 다름"),
    )
    llm = FakeLLM([answer])
    pre = _precheck(_repo(), judge=SameJudge(primary=llm, repo=_repo()))
    result = await pre.run(IDEA)
    assert result.judgment.status == "ai" and len(llm.calls) == 1
    prompt = llm.calls[0]
    assert prompt.count('<doc id="own:gy2016">') == 1
    assert "alio:gy2016" not in prompt  # 같은 연작의 다른 판은 따로 판정하지 않는다
    assert "[연작] 광역철도 수송수요 예측" in prompt
    assert "2017년도 광역철도 수송수요 예측 연구" in prompt
    row = next(a for a in result.alerts if a.doc_id == "own:gy2016")
    assert row.judgment == "partial" and row.series is not None


async def test_series_without_reranker_groups_before_cut():
    repo = _repo()
    pre = PrecheckOverlap(repo, k=4, series=SeriesRule())
    rows = (await pre.run(IDEA, ai=False)).alerts
    assert len(rows) == 4
    assert len({a.doc_id for a in rows}) == 4
    assert rows[0].series is not None and rows[0].series.label == "광역철도 수송수요 예측"
    # 저장소에서 넓게 받았다 (fetch_multiplier)
    assert any(kw["k"] >= 16 for name, kw in repo.calls if name == "find_similar")
