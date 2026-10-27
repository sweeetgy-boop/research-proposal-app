"""감사·평가 지적 자료 (doc_type audit, P2-4·P2-5, 레인 E 2026-10-27).

- `bai`: 감사원 분야·종류별 감사결과(www.bai.go.kr/bai/result/branch/list). 목록·상세는 JS(Vue)
  렌더라 Playwright 헤드리스
  Chromium 으로 **공개 화면만 조작**(검색어 입력 → 상세 → 파일 클릭)해 전문 PDF 를
  스냅샷(`data/bai/snapshots/<날짜>/`)에
  받는다. robots 가 막은 `/api/` 는 직접 요청하지 않는다. 적재는 `BaiAuditSource` 가 스냅샷을
  읽는다(korail_web
  과
  같은
  구조).
  공공누리 제4유형(출처표시·상업적 이용금지·변경금지).
- `mofe`: 기획재정부 보도자료 게시판의 "공공기관 경영실적 평가 결과 발표"(연도별, 공개 PDF·HWPX).
  GuardedClient GET 만.
  상세의 담당자 이름·전화·이메일은 저장하지 않는다.
국정감사 지적사항은 감사원 사이트에 없어(국회 자료) 보류 — docs/korail-web-crawl.md §5.
"""

from rra.adapters.sources.audit.bai_source import BaiAuditSource, normalize_bai_record
from rra.adapters.sources.audit.mofe import MofeEvaluationSource, normalize_mofe_item

__all__ = ["BaiAuditSource", "MofeEvaluationSource", "normalize_bai_record", "normalize_mofe_item"]
