"""KIPRIS Plus 특허·실용신안 자유검색·분류 검색 (source kipris_kr, doc_type patent)."""

from rra.adapters.sources.kipris.client import (
    KiprisClassCount,
    KiprisError,
    KiprisPatentSource,
    normalize_ipc,
)
from rra.adapters.sources.kipris.normalize import normalize_patent

__all__ = [
    "KiprisClassCount",
    "KiprisError",
    "KiprisPatentSource",
    "normalize_ipc",
    "normalize_patent",
]
