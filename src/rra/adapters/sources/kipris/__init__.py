"""KIPRIS Plus 특허·실용신안 자유검색 (source kipris_kr, doc_type patent)."""

from rra.adapters.sources.kipris.client import KiprisError, KiprisPatentSource
from rra.adapters.sources.kipris.normalize import normalize_patent

__all__ = ["KiprisError", "KiprisPatentSource", "normalize_patent"]
