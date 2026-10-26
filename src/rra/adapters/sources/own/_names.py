"""폴더·파일 이름 해석 (순수). macOS 는 파일명을 NFD 로 저장하므로 비교 전에 NFC 로 맞춘다."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

FORMAT_RANK = {"hwpx": 3, "hwp": 2, "pdf": 1}
_DATE_PREFIX = re.compile(r"^(?:\d{2}\.\d{1,2}\.\d{1,2}|\d{6}|\d{8})[\s_.-]*")
_PERSON = re.compile(r"^[가-힣]{2,4}\s*[-_]\s*")  # "박한균-제목", "김한수_제목", "임형석 - 제목"
_ATTACH = re.compile(r"^[\[(]?\s*붙임\s*[\])]?\s*[\d.\-]*[.)]?\s*|^\d+(?:[-.]\d+)*[.)]?\s*")
_NOISE = re.compile(
    r"공시용|공시|요약문|연구요약보고서|연구과제요약보고서|연구과제요약서|연구과제\s*요약\s*보고서|"
    r"연구과제\s*요약서|연구요약서|연구보고서|요약서|요약|최종|_\d{4}$"
)
_PUNCT = re.compile(r"[()\[\]_\-,.·\s]+")
MAX_VARIANT_CHARS = 20


def nfc(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def folder_title(name: str) -> str:
    """'25.1.6 박한균-신규 철도차량의 … 연구' → '신규 철도차량의 … 연구' (날짜·이름 제거)."""
    text = nfc(name).strip()
    text = _DATE_PREFIX.sub("", text)
    text = _PERSON.sub("", text)
    text = re.sub(r"\s*\(\d+건\)\s*$|\s+\d+건\s*$", "", text)
    return " ".join(text.split())


def is_summary_file(path: Path) -> bool:
    name = nfc(path.name)
    if name.startswith(("~$", ".")) or path.suffix.lower().lstrip(".") not in FORMAT_RANK:
        return False
    return "요약" in name or "공시용" in name


def summary_score(path: Path) -> tuple[int, int, int]:
    """(공시용 여부, 형식 순위, -경로 깊이) — 클수록 우선."""
    name = nfc(path.name)
    disclosed = 1 if "공시" in name else 0
    return disclosed, FORMAT_RANK.get(path.suffix.lower().lstrip("."), 0), -len(path.parts)


def variant_of(path: Path) -> str:
    """묶음 꼬리말: '요약문(공시용, 고속).hwp' → '고속', '요약문(화물)_공시용.hwpx' → '화물'."""
    stem = _ATTACH.sub("", nfc(path.stem))
    rest = _NOISE.sub(" ", stem)
    rest = " ".join(_PUNCT.sub(" ", rest).split())
    return rest if 0 < len(rest) <= MAX_VARIANT_CHARS else ""


def _merge_variants(groups: dict[str, list[Path]]) -> dict[str, list[Path]]:
    """'제동슈키'·'제동슈키 분리지그', '에너지 트레인'·'에너지트레인' 처럼 공백을 뺀 한쪽이
    다른 쪽의 접두면 같은 과제로 본다 ('고속' 과 '준고속' 은 접두가 아니라 다른 과제)."""
    keys = sorted(groups, key=lambda v: len(v.replace(" ", "")), reverse=True)
    canon: dict[str, str] = {}
    for key in keys:
        squashed = key.replace(" ", "")
        for longer in keys:
            if (
                longer != key
                and canon.get(longer, longer) == longer
                and (squashed and longer.replace(" ", "").startswith(squashed))
            ):
                canon[key] = canon.get(longer, longer)
                break
    merged: dict[str, list[Path]] = {}
    for key, paths in groups.items():
        merged.setdefault(canon.get(key, key), []).extend(paths)
    return merged


def select_summary_files(folder: Path) -> list[tuple[str, Path]]:
    """과제 폴더 → [(꼬리말, 파일)]. 꼬리말마다 공시용 > 일반 요약, hwpx > hwp > pdf 로 하나씩."""
    groups: dict[str, list[Path]] = {}
    for p in sorted(folder.rglob("*")):
        if p.is_file() and is_summary_file(p):
            groups.setdefault(variant_of(p), []).append(p)
    if not groups:
        return []
    groups = _merge_variants(groups)
    if len(groups) > 1 and "" in groups and any(groups[v] for v in groups if v):
        # 꼬리말 있는 파일들이 과제를 나눈다. 꼬리말 없는 파일은 그중 하나와 같은 문서다 → 뺀다
        groups.pop("")
    return [(variant, max(paths, key=summary_score)) for variant, paths in sorted(groups.items())]


def strip_person(text: str) -> str:
    """'경영연구처 박한균' → '경영연구처' (부서 뒤 2~4자 한글 이름 제거)."""
    return re.sub(
        r"(\S+(?:처|실|단|부|팀|과|원|센터|본부|연구소|사업소))\s+[가-힣]{2,4}$", r"\1", text
    )
