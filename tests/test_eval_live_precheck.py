"""[5] 측정 ② 는 운영 REST 처럼 실시간 검색을 먼저 돌린 뒤 판정한다 (composition.LivePrecheck)."""

from rra.composition import LivePrecheck


async def test_live_search_runs_before_overlap_judgement():
    order: list[str] = []

    class Live:
        async def prepare(self, owner, req):
            order.append(f"live:{owner}")

    async def precheck(req):
        order.append("precheck")
        return ["alert"]

    result = await LivePrecheck(precheck, Live(), "local")(object())
    assert result == ["alert"] and order == ["live:local", "precheck"]
