"""동의어 검토표 어댑터 (레인 E, ADR 0059) — 후보 YAML 읽기, 검토표 Markdown 쓰기, `overlap.yaml` 의
`synonyms.candidates` 구역만 바꾸기.

overlap.yaml 은 주석이 많은 설정 파일이라 yaml.dump 로 다시 쓰지 않는다. 표식 두 줄
(`# >>> synonyms.candidates` … `# <<< synonyms.candidates`) 사이만 글자로 바꾼다 — 표식이 없으면
`synonyms:` 절 끝(파일 끝)에 표식과 함께 덧붙인다. `enabled` 줄은 건드리지 않는다."""

from __future__ import annotations

import os
import re
from collections.abc import Sequence
from pathlib import Path

import yaml

from rra.domain.rules.synonyms import SynonymReview, TermStatRow

RAIL_FILE = "rail_terms.candidates.yaml"
GENERIC_FILE = "generic_terms.candidates.yaml"
BEGIN = (
    "  # >>> synonyms.candidates — rra terms review 가 만든 고신뢰 묶음. 검토 전 — 운영 반영 안 함."
)
END = "  # <<< synonyms.candidates"
_BLOCK = re.compile(r"^  # >>> synonyms\.candidates.*?^  # <<< synonyms\.candidates\n", re.S | re.M)
_SYNONYMS_SECTION = re.compile(r"^synonyms:\n(?:[ \t]+.*\n|\n)*", re.M)


class YamlTermCandidatesReader:
    def __init__(self, config_dir: Path):
        self.config_dir = Path(config_dir)

    def read(self) -> list[TermStatRow]:
        out: list[TermStatRow] = []
        for name, kind in ((RAIL_FILE, "rail"), (GENERIC_FILE, "generic")):
            path = self.config_dir / name
            if not path.is_file():
                continue
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            for row in data.get("candidates") or []:
                if not isinstance(row, dict) or not isinstance(row.get("term"), str):
                    continue
                out.append(
                    TermStatRow(
                        term=row["term"],
                        doc_freq=int(row.get("doc_freq") or 0),
                        sources={str(k): int(v) for k, v in (row.get("sources") or {}).items()},
                        examples=tuple(str(e) for e in (row.get("examples") or [])),
                        kind=kind,
                    )
                )
        return out


class TermsReviewFiles:
    def __init__(self, review_path: Path, overlap_yaml: Path):
        self.review_path = Path(review_path)
        self.overlap_yaml = Path(overlap_yaml)

    def write_review(self, markdown: str) -> str:
        self.review_path.parent.mkdir(parents=True, exist_ok=True)
        _atomic(self.review_path, markdown)
        return str(self.review_path)

    def write_candidates(self, reviews: Sequence[SynonymReview]) -> str:
        text = self.overlap_yaml.read_text(encoding="utf-8")
        block = render_block(reviews)
        if _BLOCK.search(text):
            new = _BLOCK.sub(lambda _m: block, text, count=1)
        else:
            m = _SYNONYMS_SECTION.search(text)
            if m is None:
                raise ValueError("overlap.yaml 에 synonyms 절이 없습니다")
            section = m.group(0).rstrip("\n") + "\n"
            new = text[: m.start()] + section + block + text[m.end() :]
        _atomic(self.overlap_yaml, new)
        return str(self.overlap_yaml)


def render_block(reviews: Sequence[SynonymReview]) -> str:
    """`synonyms:` 절 안에 들여 쓴 candidates 목록(표식 포함). 읽어도 되는 YAML 이다."""
    lines = [BEGIN, "  candidates:"]
    if not reviews:
        lines[-1] = "  candidates: []"
    for r in reviews:
        members = ", ".join(_q(v) for v in r.variants)
        lines.append(
            f"    - {{canonical: {_q(r.canonical)}, terms: [{members}], "
            f"doc_freq: {r.doc_freq}, cooccur: {r.cooccur}}}"
        )
    lines.append(END)
    return "\n".join(lines) + "\n"


def _q(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _atomic(path: Path, body: str) -> None:
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, path)
