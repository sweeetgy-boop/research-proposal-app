"""② 같은 연작 한 줄 REST — 가짜 모드 (2026-10-29 레인 A, ADR 0043).

가짜 저장소의 연작 표본(광역철도 수송수요예측 3판 + 다른 과제 1건)이 표에서 한 줄 + 다른 과제
한 줄로 보이고, 행마다 ``series`` {label, count, display, members[연도 순]} 가 붙는다. 화면 글자에
내부 번호가 없다(doc_id 는 근거 패널용 칸에만)."""

from __future__ import annotations

import re

import httpx

from tests.entrypoints.test_precheck_flow_api import AUTH, parts  # noqa: F401 — 픽스처

INTERNAL = re.compile(r"\b(own|alio|ntis|scienceon|openalex|korail_web|g2b):[\w-]+")
SERIES_IDEA = {
    "current_state": "광역철도 수송수요예측 오차가 신설역 개통 때 커짐",
    "root_cause": "연도별 수송수요예측 모형이 신설역 효과를 반영하지 못함",
    "limitation": "광역철도 월별 변동을 다루지 않음",
    "goal": "광역철도 수송수요예측 모형 개선",
    "title_hint": "광역철도 수송수요예측 개선",
}


def _client(app):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
    )


def _shown_text(alert: dict) -> str:
    """화면에 보이는 글자 칸 (doc_id 칸 제외)."""
    s = alert["series"] or {}
    parts_ = [alert["title"], alert.get("source_label") or "", s.get("display", "")]
    for m in s.get("members", []):
        parts_ += [m["title"], m["source_label"]]
    return " ".join(parts_)


async def test_series_row_with_members_then_choice_applies_to_whole_series(parts):  # noqa: F811
    async with _client(parts["app"]) as c:
        fast = (await c.post("/v1/precheck?stage=rule", json=SERIES_IDEA, headers=AUTH)).json()
        series_rows = [a for a in fast["alerts"] if a["series"]]
        assert len(series_rows) == 1
        row = series_rows[0]
        s = row["series"]
        assert s["label"] == "광역철도 수송수요예측 (가짜)"  # 연도를 뺀 제목
        assert s["count"] == 3 and s["display"].endswith("(연작 3건)")
        assert [m["year"] for m in s["members"]] == [2023, 2024, 2025]
        both = next(m for m in s["members"] if m["year"] == 2024)
        assert set(both["source_label"].split(" · ")) == {"사내 과제", "알리오 공시"}
        assert len(both["refs"]) == 2 and all(r["doc_id"] for r in both["refs"])
        ids = {row["doc_id"], *row["merged_ids"]}
        assert {"own:fake-series-2023", "own:fake-series-2024", "alio:fake-series-2024"} <= ids
        assert "own:fake-series-other" in {a["doc_id"] for a in fast["alerts"]}  # 다른 과제는 따로
        assert not INTERNAL.search(" ".join(_shown_text(a) for a in fast["alerts"]))

        # 구성원 한 판을 [유사함] 으로 고르면 연작 행 전체가 [유사함]
        member = next(i for i in row["merged_ids"] if i != row["doc_id"])
        body = {**SERIES_IDEA, "similar_choices": [{"doc_id": member, "choice": "similar"}]}
        chosen = (await c.post("/v1/precheck/choices", json=body, headers=AUTH)).json()
        again = next(a for a in chosen["alerts"] if a["doc_id"] == row["doc_id"])
        assert again["choice"] == "similar" and chosen["similar_count"] == 1
