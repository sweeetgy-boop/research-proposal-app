"""KIPRIS 분류(IPC) 검색 — 항목별 검색(getAdvancedSearch, `ipcNumber`) 실응답 fixture 로 확정
(2026-11-10, tests/fixtures/kipris/advanced/). 키·네트워크 없음.

- 정규화: 소문자로 시작하는 요소 이름(applicationNumber·inventionTitle·astrtCont·ipcNumber …)을
  기존 `normalize_patent` 가 그대로 읽는다. 개인 이름은 저장하지 않는다.
- 총 건수(`count/totalCount`) = `PatentClassCount`. 일일 카운터 공유, 실패·상한이면 None.
- 실시간 검색: "ipc:" 표식 질의는 분류 검색으로, 표식이 없으면 종전 자유검색 그대로.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx

from rra.adapters.llm.daily_budget import FileDailyBudget
from rra.adapters.sources._xml import find_records, flatten, parse
from rra.adapters.sources.kipris import KiprisClassCount, normalize_ipc, normalize_patent
from rra.adapters.sources.kipris.client import CLASS_RECORD_TAG, class_total
from rra.adapters.sources.live import LiveKipris
from rra.application.usecases.problem_card_contract import PatentClassCount
from rra.domain.rules.card_queries import class_query
from tests.adapters.test_kipris import INSTITUTIONS, KEY, page, source_for

FIX = Path(__file__).parents[1] / "fixtures" / "kipris" / "advanced"
RECORDED = sorted(FIX.glob("kipris_ipc_*.xml"))
BODY = RECORDED[0].read_text(encoding="utf-8")


def test_fixture_is_recorded_without_secrets_or_person_names():
    assert RECORDED, "KIPRIS 분류 검색 실응답 fixture 가 없다"
    meta = json.loads(RECORDED[0].with_suffix(".meta.json").read_text(encoding="utf-8"))
    assert meta["operation"] == "getAdvancedSearch" and meta["ipcNumber"] == "A01M 29/00"
    for marker in ("ServiceKey=", "accessKey=", KEY):
        assert marker not in BODY


def test_recorded_records_normalize_to_patents_with_ipc_codes():
    root = parse(BODY.encode("utf-8"))
    records = [flatten(r) for r in find_records(root, CLASS_RECORD_TAG)]
    assert len(records) == 5 and class_total(root) == 118
    docs = [normalize_patent(r, INSTITUTIONS) for r in records]
    assert len({d.doc_id for d in docs}) == 5
    assert all(d.source == "kipris_kr" and d.doc_type == "patent" and d.title for d in docs)
    assert all(d.abstract and not d.authors for d in docs)
    assert all("A01M 29/00" in d.codes for d in docs)  # 분류로 검색한 결과다
    assert all(d.pub_date is not None and d.raw["applicant_kind"] == "organization" for d in docs)


def test_normalize_ipc_accepts_only_code_shapes():
    assert normalize_ipc("a01m 29/00") == "A01M 29/00"
    assert normalize_ipc("A01M29/00") == "A01M 29/00"
    assert normalize_ipc(" A01M ") == "A01M"
    for bad in ("", "비둘기", "A01", "A01M 29", "Z99Z 1/00", "A01M 29/00 OR 1=1", "ipc:A01M"):
        assert normalize_ipc(bad) is None


async def test_search_class_sends_ipc_number_to_advanced_search():
    src, reqs = source_for([BODY])
    raws = await src.search_class("A01M29/00", 3)
    assert len(raws) == 3 and raws[0]["inventionTitle"]
    url = urlsplit(str(reqs[0].url))
    q = parse_qs(url.query)
    assert url.path == "/kipo-api/kipi/patUtiModInfoSearchSevice/getAdvancedSearch"
    assert q["ipcNumber"] == ["A01M 29/00"] and q["ServiceKey"] == [KEY]
    assert q["numOfRows"] == ["3"] and q["pageNo"] == ["1"] and "word" not in q
    assert set(q) == {"ipcNumber", "patent", "utility", "numOfRows", "pageNo", "ServiceKey"}
    assert (
        await src.search_class("비둘기", 3) == [] and len(reqs) == 1
    )  # 코드가 아니면 보내지 않는다


async def test_class_count_returns_total_and_none_on_cap_or_failure(tmp_path):
    src, reqs = source_for([BODY, httpx.Response(500), BODY])
    counter = FileDailyBudget(tmp_path / "kipris_calls.json", 3)
    count = KiprisClassCount(src, counter=counter)
    assert isinstance(count, PatentClassCount)
    assert await count("A01M 29/00") == 118
    assert parse_qs(urlsplit(str(reqs[0].url)).query)["numOfRows"] == ["1"]
    assert await count("A01M 29/00") is None  # 실패 — 예외를 올리지 않는다
    assert (
        await count("코드 아님") is None and counter.remaining() == 1
    )  # 보내지 않고, 세지도 않는다
    assert await count("A01M") == 118 and counter.remaining() == 0
    assert await count("A01M") is None and len(reqs) == 3  # 일일 상한 — 요청하지 않는다
    assert KEY not in repr(count)


async def test_live_kipris_routes_class_queries_and_shares_the_limit():
    # 분류 검색 먼저(절반까지) → 키워드 검색이 나머지
    src, reqs = source_for([BODY, page(3, 3)], docs=50)
    live = LiveKipris(src, max_requests=6)
    assert live.class_search is True
    docs = await live.fetch(["조류 접근 방지", class_query("A01M 29/00")], 6)
    paths = [urlsplit(str(r.url)).path.rsplit("/", 1)[-1] for r in reqs]
    assert paths == ["getAdvancedSearch", "freeSearchInfo"]
    assert parse_qs(urlsplit(str(reqs[0].url)).query)["numOfRows"] == ["3"]
    assert len(docs) == 6 and len({d.doc_id for d in docs}) == 6
    assert sum("A01M 29/00" in d.codes for d in docs) == 3


async def test_live_kipris_without_class_queries_is_unchanged_and_counts_calls(tmp_path):
    src, reqs = source_for([page(2, 2), page(1, 1)], docs=50)
    counter = FileDailyBudget(tmp_path / "kipris_calls.json", 10)
    live = LiveKipris(src, max_requests=3, counter=counter)
    await live.fetch(["비둘기 침입 방지", "비둘기 퇴치"], 20)
    assert all("freeSearchInfo" in str(r.url) and "accessKey" in str(r.url) for r in reqs)
    assert len(reqs) == 2 and counter.remaining() == 8
    # 분류 질의도 일일 카운터를 1씩 쓴다
    src, reqs = source_for([BODY, BODY], docs=50)
    live = LiveKipris(src, max_requests=6, counter=counter)
    await live.fetch([class_query("A01M 29/00"), class_query("A01M")], 10)
    assert len(reqs) == 2 and counter.remaining() == 6
