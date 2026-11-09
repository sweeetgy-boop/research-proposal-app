"""정책 근거 인용이 문장 중간에서 잘리지 않게 (2026-11-09 레인 B, ADR 0061).

운영 사례: 1순위 인용이 "…하자보수73)하였으나 …" 처럼 PDF 추출 문장 중간에서 시작하고 각주 번호가
단어에 붙어 있었다. fixture 는 그 조각을 넣어 지어낸 문단이다(실제 PDF 원문 아님). 규칙은 순수 함수:
각주·줄 끝 하이픈 제거(normalize_pdf) → 본문 안에서 문장 경계까지 넓힘(widen_to_sentences) →
불완전하면 뒤로(Passage.complete, rank)."""

from pathlib import Path

from rra.domain.models import Chunk, Document, PolicySuggestion
from rra.domain.models.policy import PolicyChoice, PolicySource
from rra.domain.rules.keywords import KeywordRule
from rra.domain.rules.policy_cards import policy_passage, verify_sources
from rra.domain.rules.policy_phrases import (
    is_fragment,
    match_text,
    normalize_pdf,
    pick_passage,
    pick_quote,
    rank,
    widen_to_sentences,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "policy" / "footnote_passage.txt"
BODY = FIXTURE.read_text(encoding="utf-8")
# 운영 사례처럼 문장 중간에서 시작해 중간에서 끝나는 청크
CHUNK = (
    "하자보수73)하였으나 같은 부위에서 다시 결함이 생겨 근본 원인을 분석할 필요가 있음.\n"
    "○ 상태기반 유지-\n보수 체계로 바꾸어"
)
FULL = (
    "일부 역사는 준공 뒤 결함이 반복되어 시공사가 하자보수하였으나 같은 부위에서 다시 결함이 생겨 "
    "근본 원인을 분석할 필요가 있음."
)
QUERY = "역사 결함 반복 하자보수 근본 원인 분석"
RULE = KeywordRule(min_hits=1)


def test_normalize_pdf_removes_footnotes_superscripts_and_line_end_hyphens():
    assert normalize_pdf("하자보수73)하였으나") == "하자보수하였으나"
    assert normalize_pdf("필요가 있음⁷⁴.") == "필요가 있음."
    assert normalize_pdf("상태기반 유지-\n보수 체계") == "상태기반 유지보수 체계"
    # 줄 머리 번호·연도·괄호 번호는 그대로
    for keep in ("1) 첫째 항목", "(2023) 계획", "제1) 조항", "2023) 뒤"):
        assert normalize_pdf(keep) == keep
    assert match_text("하자보수73)하였으나 다시") == match_text("하자보수하였으나 다시")


def test_widen_to_sentence_boundaries_inside_body():
    widened, anchored = widen_to_sentences(BODY, CHUNK)
    assert anchored
    assert widened.startswith("○ 일부 역사는 준공 뒤")  # 앞은 직전 줄바꿈(문장 경계)까지
    assert widened.endswith("조정할 필요가 있음.")  # 뒤는 다음 문장 끝까지
    assert "73)" not in widened and "유지보수" in widened
    # 본문에 없는 청크는 그대로
    assert widen_to_sentences(BODY, "본문에 없는 글") == ("본문에 없는 글", False)
    assert widen_to_sentences(None, CHUNK) == (CHUNK, False)
    assert widen_to_sentences("", "  ") == ("  ", False)


def test_pick_passage_with_body_returns_whole_sentence_without_footnote():
    p = pick_passage(CHUNK, QUERY, RULE, body=BODY)
    assert p.quote == FULL and p.complete
    assert "하자보수" in p.hits and "73" not in p.quote
    # 옛 모양도 같은 결과
    assert pick_quote(CHUNK, QUERY, RULE, body=BODY) == (FULL, p.hits)


def test_pick_passage_without_body_demotes_fragments_but_keeps_them():
    """본문이 없으면 넓히지 못한다 — 조각(앞이 잘림·끝이 없음)은 버리지 않고 complete=False."""
    only_fragment = "하여 같은 부위에서 다시 결함이 생겨 근본 원인을 분석할 필요가"
    p = pick_passage(only_fragment, QUERY, RULE)
    assert p.quote.startswith("같은 부위에서") is False  # 글자는 고치지 않는다 — 조각 그대로
    assert p.quote == only_fragment and not p.complete
    # 온전한 문장이 함께 있으면 키워드가 적어도 온전한 문장을 고른다
    both = (
        "점검 주기가 길어 결함을 늦게 찾는 사례가 있음. "
        "하자보수하였으나 같은 부위에서 다시 결함이 생겨 근본 원인을"
    )
    p2 = pick_passage(both, QUERY, RULE)
    assert p2.quote == "점검 주기가 길어 결함을 늦게 찾는 사례가 있음." and p2.complete
    # 키워드가 하나도 안 겹치면 첫 온전한 문장
    p3 = pick_passage(both, "전혀 다른 질의", RULE)
    assert p3.quote == "점검 주기가 길어 결함을 늦게 찾는 사례가 있음."


def test_is_fragment_rules():
    assert is_fragment("은 결함이 반복되어 분석할 필요가 있음.")  # 조사로 시작
    assert is_fragment("하여 같은 부위에서 결함이 다시 생김")  # 어미로 시작
    assert is_fragment("track geometry monitoring is required.")  # 소문자 시작
    assert is_fragment("결함이 반복되어 근본 원인을")  # 문장 끝 없음
    assert is_fragment("짧은 조각.")  # 길이 하한
    assert not is_fragment(
        "이 계획은 상태기반 유지보수 체계를 확립함"
    )  # 지시어 '이' 는 조각이 아니다
    assert not is_fragment("국가철도망 구축계획에 반영할 필요가 있음.")


def test_rank_puts_incomplete_quotes_after_complete_ones():
    def s(doc_id, hits, complete):
        return PolicySuggestion(
            doc_id=doc_id, title="t", quote="q", keywords=hits, complete=complete
        )

    ranked = rank([s("a", ["x", "y", "z"], False), s("b", ["x"], True), s("c", [], True)])
    assert [r.doc_id for r in ranked] == ["b", "c", "a"]


def test_policy_passage_uses_document_body_and_verify_matches_footnoted_original():
    doc = Document(
        doc_id="molit:p1",
        source="molit",
        doc_type="policy",
        title="시설물 유지관리 계획",
        body=BODY,
    )
    found = policy_passage(doc, CHUNK, 0.5, QUERY, RULE)
    assert found is not None and found.quote == FULL and found.complete
    # 생성 때 원문 대조(보안 A) — 각주가 붙은 원문에서도 넓힌 인용을 찾는다
    choice = PolicyChoice(
        mode="card",
        sources=[
            PolicySource(
                chunk_id="molit:p1#3",
                doc_id="molit:p1",
                source="molit",
                source_label="국토교통부",
                title=doc.title,
                quote=found.quote,
            )
        ],
    )
    verified = verify_sources(choice, {"molit:p1": doc})
    assert [c.chunk_id for c in verified] == ["molit:p1#3"]
    assert isinstance(verified[0], Chunk) and "73)" not in verified[0].text
