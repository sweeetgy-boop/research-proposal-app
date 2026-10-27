"""용어 후보 추출 (P2-9). 저장소 청크 표본 → `term_candidates`(순수) → 후보 두 벌(철도 용어·흔한
단어).

쓰기는 하지 않는다 — 결과 payload(YAML 로 적을 dict 두 개)를 돌려주고 파일은 어댑터
(`adapters/terms`)가 적는다. 후보는 사람이 보고 `config/overlap.yaml` 에 옮긴다 (자동 반영 없음).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Any

from rra.application.ports.table_facts import CorpusAccessPort
from rra.domain.rules.keywords import KeywordRule
from rra.domain.rules.term_candidates import (
    CandidateConfig,
    CandidateReport,
    CorpusText,
    TermStat,
    term_candidates,
)

RAIL_FILE = "rail_terms.candidates.yaml"
GENERIC_FILE = "generic_terms.candidates.yaml"
NOTICE = (
    "후보 목록입니다 — config/overlap.yaml 에 자동 반영되지 않습니다. "
    "사람이 검토해 옮깁니다 (철도 용어는 유사과제 키워드 판정에서 '세는 말', "
    "흔한 단어는 generic_terms 에 추가 후보)."
)


class ExtractTermCandidates:
    def __init__(
        self,
        repo: CorpusAccessPort,
        rule: KeywordRule,
        *,
        config: CandidateConfig | None = None,
        today: Callable[[], date] = date.today,
    ):
        self.repo, self.rule, self.config, self.today = (
            repo,
            rule,
            config or CandidateConfig(),
            today,
        )

    async def __call__(self, *, sample: int = 5000, limit: int | None = None) -> CandidateReport:
        chunks = await self.repo.sample_chunks(sample)
        texts = [
            CorpusText(doc_id=c.doc_id, source=c.doc_id.split(":", 1)[0], text=c.text)
            for c in chunks
        ]
        config = self.config if limit is None else self.config.model_copy(update={"limit": limit})
        return term_candidates(texts, self.rule, config)

    def payloads(self, report: CandidateReport) -> dict[str, dict[str, Any]]:
        """파일 이름 → YAML 로 적을 dict."""
        base = {
            "notice": NOTICE,
            "generated": self.today().isoformat(),
            "sample": {
                "chunks": report.chunks,
                "documents": report.documents,
                "sources": dict(report.sources),
            },
            "config": self.config.model_dump(),
        }
        return {
            RAIL_FILE: {
                **base,
                "kind": "rail_terms",
                "candidates": [_row(s) for s in report.rail],
            },
            GENERIC_FILE: {
                **base,
                "kind": "generic_terms",
                "candidates": [_row(s) for s in report.generic],
            },
        }


def _row(stat: TermStat) -> dict[str, Any]:
    row: dict[str, Any] = {
        "term": stat.term,
        "doc_freq": stat.doc_freq,
        "chunk_freq": stat.chunk_freq,
        "doc_ratio": stat.doc_ratio,
        "sources": dict(stat.sources),
        "examples": list(stat.examples),
    }
    if stat.hint:
        row["hint"] = stat.hint
    return row
