"""공공데이터포털 파일데이터 — 철도 안전·운영·수송 통계 (doc_type statistics, P2-2·P2-3, 레인 E
2026-10-27).

키 없이 받는다(상세 페이지에 "로그인 없이 다운로드", 이용허락범위 제한 없음): 데이터셋 페이지
`/data/<pk>/fileData.do`
→
`fn_fileDataDown(pk, detailPk, '', sn, hist)` 인자·제목·제공기관·수정일·설명 →
`/tcs/dss/selectFileDataDownload.do` (JSON,
atchFileId) → `/cmm/cmm/fileDownload.do?atchFileId&fileDetailSn` (CSV·XLSX).
파일은 샌드박스에서 텍스트로,,
표는
앞
max_rows 행만
본문에 넣는다(수치 근거용). 같은 pk 는 갱신될 때마다 한 문서를 덮어쓴다(판이 아니라 기록 — editions
미적용).
대상 목록은 config/datago.yaml datasets.
"""

from rra.adapters.sources.datago.source import DataGoKrFileSource, normalize_datago_item

__all__ = ["DataGoKrFileSource", "normalize_datago_item"]
