"""발주 연구용역 공고 — 나라장터 입찰공고정보서비스 (P2-6, 레인 E 2026-10-27).

ebid.korail.com(공사 전자조달)은 목록이 POST·JS 적재이고 상세가 로그인 전용·약관을 확인할 수 없어
쓰지
않는다
(docs/korail-web-crawl.md §5). 대신 공공데이터포털 `조달청_나라장터 입찰공고정보서비스` 의 용역 조회
(`getBidPblancListInfoServcPPSSrch`, apis.data.go.kr)를 `RRA_DATA_GO_KR_KEY` 로 부른다. 키가 없으면
MissingCredential.
doc_type procurement, 유사과제 판정 티어 "발주 용역"(domain/rules/overlap), 알림 상태 "용역으로 진행
중/예정".
담당자 이름·전화·이메일 필드(ntceInsttOfcl*·exctvNm 등)는 읽지 않는다.
"""

from rra.adapters.sources.procurement.source import G2bProcurementSource, normalize_g2b_item

__all__ = ["G2bProcurementSource", "normalize_g2b_item"]
