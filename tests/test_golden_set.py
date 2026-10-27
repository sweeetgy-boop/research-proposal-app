"""골든셋 회귀 — tests/golden/*.yaml 이 ProposalRequest 로 읽히고, 정답 유사과제(expected_similar)
형식이 맞는지.

실제 생성·검색은 `rra eval`([Q] Q9·[4])이 한다. 여기서는 파일 형식만 고정한다: 10건(기존 3 +
2026-10-27 추가 7 — 공시용 요약문 7개 분야를 바탕으로 재구성한 아이디어), 필수 4칸, 정답 doc_id 는
"<source>:<id>" 꼴, 03 은 정답 없음.
"""

import re
from pathlib import Path

import yaml

from rra.domain.models import ProposalRequest

GOLDEN = sorted((Path(__file__).parent / "golden").glob("*.yaml"))
DOC_ID = re.compile(r"^(openalex|scienceon|kipris_kr|kipris_intl|ntis|alio|own):[^\s]+$")


def test_golden_set_has_ten_ideas_that_validate_and_carry_answers():
    assert [p.stem[:2] for p in GOLDEN] == [f"{i:02d}" for i in range(1, 11)]
    for path in GOLDEN:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        expected = data.pop("expected_similar")
        req = ProposalRequest(**data)
        assert req.current_state and req.root_cause and req.limitation and req.goal
        assert isinstance(expected, list) and all(DOC_ID.match(x) for x in expected)
        if path.stem.startswith("03"):
            assert expected == []  # 철도 무관 — 차단 알림이 없어야 적중
        else:
            assert expected, path.name
