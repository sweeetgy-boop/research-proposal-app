"""템플릿 모드 테스트용 최소 HWPX 양식 생성 — slots.yaml 의 모든 자리표시자를 표 칸에 넣는다.

    .venv/bin/python tests/tools/make_hwpx_template.py [출력 경로]

실물 양식(config/templates/proposal_korail.hwpx)은 담당자가 한컴오피스에서 자리표시자를 입력해
만든다.
이 스크립트는 그 구조를 흉내 낸 작은 파일을 fixture 로 남길 뿐이다.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "tests" / "fixtures" / "hwpx" / "proposal_template_min.hwpx"


def main(out: Path = DEFAULT_OUT) -> Path:
    from hwpx.document import HwpxDocument

    from rra.adapters.rendering import SlotMap

    data = yaml.safe_load(
        (ROOT / "config" / "templates" / "proposal_korail.slots.yaml").read_text(encoding="utf-8")
    )
    slots = SlotMap.from_config(data)
    doc = HwpxDocument.new()
    doc.add_heading("연구과제 제안서 (테스트 템플릿)", level=1)
    rows = [("연구과제명", slots.text["title"]), ("예산과목", slots.input["budget.account"])]
    rows += [(f"본문:{k}", ph) for k, ph in slots.text.items() if k != "title"]
    rows += [(f"입력:{k}", ph) for k, ph in slots.input.items() if k != "budget.account"]
    rows += [(f"체크:{k}:{i}", ph) for k, opts in slots.choice.items() for i, ph in opts.items()]
    rows += [(f"하단:{k}", ph) for k, ph in slots.render_only.items()]
    table = doc.add_table(len(rows), 2)
    for r, (label, ph) in enumerate(rows):
        table.set_cell_text(r, 0, label)
        table.set_cell_text(r, 1, ph)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(doc.to_bytes())
    return out


if __name__ == "__main__":
    path = main(Path(sys.argv[1])) if len(sys.argv) > 1 else main()
    print(path, path.stat().st_size, "bytes")
