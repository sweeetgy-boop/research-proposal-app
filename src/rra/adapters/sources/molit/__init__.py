"""국토교통부 정책자료(정책정보 게시판) — 철도 계획·정책 문서 (P2-1, 레인 A 2026-10-27).

www.molit.go.kr/USR/policyData/m_34681/lst.jsp?search=<질의> 목록 → dtl.jsp?id= 상세 →
첨부(pdf·hwp·hwpx)를 받아 샌드박스에서 텍스트를 뽑는다. doc_type policy. "제N차 ○○계획" 은
판(edition)을 추적해 최신만 현행,
이전 판은 구판(valid_until = 다음 판 등록일). 담당자 이름·전화번호는 저장하지 않는다.
"""

from rra.adapters.sources.molit.source import MolitPolicySource, normalize_molit_item

__all__ = ["MolitPolicySource", "normalize_molit_item"]
