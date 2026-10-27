"""측정 harness (P3 ⑦) — 이미지 종류별 나란히 보기 표본 + 요약표. 파일 쓰기는 진입점이 한다.

종류별 최대 N건(기본 30): 원본 경로·OCR 텍스트·Argon JSON. 요약표: 구조화 성공률(structure 비어 있지
않은
argon 결과 / Argon 시도), 숫자 대조 통과율(확인 / (확인+미확인)), 장당 처리 시간(평균 초), 실제 호출
수.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from rra.domain.models.vision import IMAGE_TYPES, ImageReadResult

DEFAULT_PER_TYPE = 30
OCR_ONLY_TYPE = "(OCR 만)"


@dataclass
class TypeStats:
    count: int = 0
    attempted: int = 0  # Argon 호출(캐시 포함)로 결과를 얻으려 한 수 = argon + failed
    structured: int = 0
    confirmed: int = 0
    unconfirmed: int = 0
    calls: int = 0  # 캐시가 아닌 실제 호출
    elapsed: float = 0.0
    timed: int = 0

    @property
    def structure_rate(self) -> float | None:
        return self.structured / self.attempted if self.attempted else None

    @property
    def number_rate(self) -> float | None:
        total = self.confirmed + self.unconfirmed
        return self.confirmed / total if total else None

    @property
    def sec_per_image(self) -> float | None:
        return self.elapsed / self.timed if self.timed else None


@dataclass
class SampleReport:
    entries: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    stats: dict[str, TypeStats] = field(default_factory=dict)
    per_type: int = DEFAULT_PER_TYPE

    def files(self) -> dict[str, str]:
        """{파일 이름: 내용}. 진입점이 --out 폴더에 쓴다."""
        out = {
            "summary.md": self.markdown(),
            "summary.json": json.dumps(self.table(), ensure_ascii=False, indent=2),
        }
        for kind, rows in self.entries.items():
            out[f"{_slug(kind)}.json"] = json.dumps(rows, ensure_ascii=False, indent=2)
        return out

    def table(self) -> list[dict[str, Any]]:
        rows = []
        for kind in [*IMAGE_TYPES, OCR_ONLY_TYPE]:
            st = self.stats.get(kind)
            if st is None:
                continue
            rows.append(
                {
                    "image_type": kind,
                    "count": st.count,
                    "structure_rate": _pct(st.structure_rate),
                    "number_rate": _pct(st.number_rate),
                    "sec_per_image": round(st.sec_per_image, 2)
                    if st.sec_per_image is not None
                    else None,
                    "calls": st.calls,
                }
            )
        return rows

    def markdown(self) -> str:
        lines = [
            "| 이미지 종류 | 건수 | 구조화 성공률 | 숫자 대조 통과율 | 장당 처리 시간(초) "
            "| 실제 호출 수 |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for row in self.table():
            lines.append(
                f"| {row['image_type']} | {row['count']} | {_fmt(row['structure_rate'])} | "
                f"{_fmt(row['number_rate'])} | {_fmt(row['sec_per_image'])} | {row['calls']} |"
            )
        return "\n".join(lines) + "\n"


def _pct(v: float | None) -> float | None:
    return round(v * 100, 1) if v is not None else None


def _fmt(v: Any) -> str:
    return "-" if v is None else str(v)


def _slug(kind: str) -> str:
    table = {
        "체계도·조직도·흐름도": "diagram",
        "표": "table",
        "그래프": "chart",
        "글자 이미지": "text_image",
        "기타": "other",
        OCR_ONLY_TYPE: "ocr_only",
    }
    return table.get(kind, "other")


def build_sample(
    results: Iterable[ImageReadResult], *, per_type: int = DEFAULT_PER_TYPE
) -> SampleReport:
    report = SampleReport(per_type=per_type)
    for r in results:
        kind = r.reading.image_type if r.reading is not None else OCR_ONLY_TYPE
        st = report.stats.setdefault(kind, TypeStats())
        st.count += 1
        if r.status in ("argon", "failed"):
            st.attempted += 1
            if not r.cached:
                st.calls += 1
        if r.reading is not None and r.reading.structure:
            st.structured += 1
        st.confirmed += len(r.confirmed_numbers)
        st.unconfirmed += len(r.unconfirmed_numbers)
        if r.elapsed_sec is not None:
            st.elapsed += r.elapsed_sec
            st.timed += 1
        rows = report.entries.setdefault(kind, [])
        if len(rows) < per_type:
            rows.append(
                {
                    "sha256": r.sha256,
                    "path": r.item.path,
                    "url": r.item.url,
                    "page_url": r.item.page_url,
                    "status": r.status,
                    "cached": r.cached,
                    "ocr_text": r.ocr.text if r.ocr else None,
                    "ocr_error": r.ocr_error,
                    "argon": r.reading.model_dump() if r.reading else None,
                    "vision_error": r.vision_error,
                    "confirmed_numbers": list(r.confirmed_numbers),
                    "unconfirmed_numbers": list(r.unconfirmed_numbers),
                    "elapsed_sec": r.elapsed_sec,
                }
            )
    return report
