"""RunLogPort 구현 — runs/<user>/<run_id>/manifest.json (보안 I).

- 기록하는 것: run id·상태·모델명·양식 id·시각, 쿼리 해시, 사용 doc_id(retrieved), 섹션(step)별
  상태·개수·프롬프트 해시·예외 클래스명, lint 문제의 섹션·코드·심각도, 확정한 선택형 키,
  [5] 초안 버전·검토 요약(차수별 provider/model, 외부 전송 doc_id public/internal, 보낸 문장 수).
- 기록하지 않는 것: 제안 입력 원문, 초안 문장, lint 메시지, 제안자·부서장 정보, 오류 메시지 본문,
  검토 의견·수정안 원문.
  내용은 RunManager.manifest() 가 만들고, 이 어댑터는 키 허용목록(check_manifest)으로 한 번 더
  막는다.
- 파일 권한 600 (디렉터리 700) — _fs.write_json 이 원자적으로 쓴다.
- 포트 시그니처(record(run_id, manifest))에 user 가 없으므로 run_id 로 디렉터리를 찾는다.
  run_id 는 전역 유일(시각 + 무작위 32비트)이고 형식 검증을 통과한 것만 받는다.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from rra.adapters.runs._fs import write_json
from rra.domain.models.run import is_valid_run_id

MANIFEST_KEYS = frozenset(
    {
        "run_id",
        "status",
        "model",
        "template",
        "created_at",
        "updated_at",
        "query_hash",
        "retrieved",
        "steps",
        "problems",
        "confirmed",
        "draft_version",
        "review",
        "finalized_at",
        "differentiation",
        "recommendations",
        "versions",
        "usage",
        "failed_sections",  # 빈 초안 금지(ADR 0027): 실패 섹션 키·사유만
        "fallback_sections",  # 대체 작성(ADR 0027): 섹션 키·사유·provider/model·전송 doc_id·호출 수
        "figures",  # [G] 그림: id·종류·섹션·renderer·model·호출 수·포함·확인·배치 (명세·본문 없음)
        "writer",  # [3] ADR 0032: 이 run 의 섹션 작성자 gemini | local
        "writers",  # 섹션별 작성자·로컬 대체 사유·전송 doc_id·원격 호출 수
        "local_sections",  # 로컬 대체 작성 섹션 키
        "local_check",  # 로컬 근거 대조 개수·건너뛴 섹션
        "gemini_calls",  # 초안 한 건의 Gemini 호출 수 (작성·검토·그림·합계)
        "live_search",  # [4] 실시간 검색: 상태·자료원별 상태/건수/초·키워드 개수 (키워드·본문 없음)
    }
)
WRITER_KEYS = frozenset(
    {
        "key",
        "provider",
        "model",
        "local_fallback",
        "reason",
        "public_doc_ids",
        "internal_doc_ids",
        "calls",
    }
)
LOCAL_CHECK_KEYS = frozenset(
    {"enabled", "mismatches", "skipped_sections", "sentences", "checked_sections"}
)
GEMINI_CALL_KEYS = frozenset({"compose", "review", "figures", "total"})
LIVE_SEARCH_KEYS = frozenset({"status", "keywords", "sources", "documents"})
LIVE_SOURCE_KEYS = frozenset({"source", "status", "count", "new", "seconds", "cached"})
FIGURE_KEYS = frozenset(
    {
        "id",
        "kind",
        "section",
        "renderer",
        "model",
        "calls",
        "included",
        "confirmed",
        "error",
        "placement",
        "number",
    }
)
FAILED_SECTION_KEYS = frozenset({"key", "reason"})
FALLBACK_KEYS = frozenset(
    {"key", "reason", "provider", "model", "public_doc_ids", "internal_doc_ids", "calls"}
)
VERSION_KEYS = frozenset(
    {
        "version",
        "origin",
        "changed_sections",
        "sentences",
        "alerts",
        "open_annotations",
        "decisions",
    }
)
# U8: 개수·성공 여부·점수만. 한 줄 소감은 usage.json 에만 있고 manifest 에는 오지 않는다
USAGE_KEYS = frozenset({"rewrites", "decisions", "hwpx_success", "satisfaction_score"})
DIFFERENTIATION_KEYS = frozenset(
    {
        "provider",
        "model",
        "fallback_local",
        "public_doc_ids",
        "internal_doc_ids",
        "excluded_doc_ids",
        "calls",
        "items",
        "discarded",
        "skipped_reason",
        "chosen",
    }
)
RECOMMENDATION_KEYS = frozenset(
    {
        "provider",
        "model",
        "fallback_local",
        "public_doc_ids",
        "internal_doc_ids",
        "excluded_doc_ids",
        "calls",
        "recommendations",
        "discarded",
        "skipped_reason",
        "chosen",
        "regenerated",  # 2026-10-28 레인 A: 2건 미만이라 제외 사유를 주고 한 번 다시 받음
    }
)
REVIEW_KEYS = frozenset(
    {
        "rounds",
        "skipped",
        "model",
        "error",
        "transfers",
        "final_reviews",
        "final_reviewed_version",
        "stale_edits",
        "draft_review_skipped",
    }
)
TRANSFER_KEYS = frozenset(
    {
        "round",
        "status",
        "provider",
        "model",
        "public_doc_ids",
        "internal_doc_ids",
        "sentences_sent",
        "sentences_excluded",
        "comments",
        "scores",
        "kind",
        "applied",
        "applied_version",
        "additions",  # Q5 추가 문장 제안 수
        "candidates",  # Q7 {섹션: A|B}
        "checklist_coverage",  # Q5 필수 요소 충족률
        "support",
    }
)
STEP_KEYS = frozenset(
    {
        "name",
        "status",
        "started_at",
        "finished_at",
        "error",
        "sentences",
        "dropped",
        "evidence",
        "prompt_hash",
        "parse",
        "raw_chars",
        "retries",
        "fallback",
    }
)
PROBLEM_KEYS = frozenset({"section", "code", "severity"})
MAX_TEXT_CHARS = 200  # 어떤 문자열 값도 이보다 길면 원문이 섞인 것으로 본다


def check_manifest(manifest: Mapping[str, Any]) -> None:
    """허용된 키·형태만 받는다. 원문이 들어올 수 있는 자리(message·text·request)는 없다."""
    unknown = set(manifest) - MANIFEST_KEYS
    if unknown:
        raise ValueError(f"manifest 에 허용되지 않은 키: {sorted(unknown)}")
    for step in manifest.get("steps") or []:
        extra = set(step) - STEP_KEYS
        if extra:
            raise ValueError(f"manifest step 에 허용되지 않은 키: {sorted(extra)}")
    for problem in manifest.get("problems") or []:
        extra = set(problem) - PROBLEM_KEYS
        if extra:
            raise ValueError(f"manifest problem 에 허용되지 않은 키: {sorted(extra)}")
    review = manifest.get("review") or {}
    extra = set(review) - REVIEW_KEYS
    if extra:
        raise ValueError(f"manifest review 에 허용되지 않은 키: {sorted(extra)}")
    for transfer in review.get("transfers") or []:
        extra = set(transfer) - TRANSFER_KEYS
        if extra:
            raise ValueError(f"manifest review.transfers 에 허용되지 않은 키: {sorted(extra)}")
    extra = set(manifest.get("differentiation") or {}) - DIFFERENTIATION_KEYS
    if extra:
        raise ValueError(f"manifest differentiation 에 허용되지 않은 키: {sorted(extra)}")
    extra = set(manifest.get("recommendations") or {}) - RECOMMENDATION_KEYS
    if extra:
        raise ValueError(f"manifest recommendations 에 허용되지 않은 키: {sorted(extra)}")
    for version in manifest.get("versions") or []:
        extra = set(version) - VERSION_KEYS
        if extra:
            raise ValueError(f"manifest versions 에 허용되지 않은 키: {sorted(extra)}")
    extra = set(manifest.get("usage") or {}) - USAGE_KEYS
    if extra:
        raise ValueError(f"manifest usage 에 허용되지 않은 키: {sorted(extra)}")
    for failed in manifest.get("failed_sections") or []:
        extra = set(failed) - FAILED_SECTION_KEYS
        if extra:
            raise ValueError(f"manifest failed_sections 에 허용되지 않은 키: {sorted(extra)}")
    for fb in manifest.get("fallback_sections") or []:
        extra = set(fb) - FALLBACK_KEYS
        if extra:
            raise ValueError(f"manifest fallback_sections 에 허용되지 않은 키: {sorted(extra)}")
    for writer in manifest.get("writers") or []:
        extra = set(writer) - WRITER_KEYS
        if extra:
            raise ValueError(f"manifest writers 에 허용되지 않은 키: {sorted(extra)}")
    extra = set(manifest.get("local_check") or {}) - LOCAL_CHECK_KEYS
    if extra:
        raise ValueError(f"manifest local_check 에 허용되지 않은 키: {sorted(extra)}")
    extra = set(manifest.get("gemini_calls") or {}) - GEMINI_CALL_KEYS
    if extra:
        raise ValueError(f"manifest gemini_calls 에 허용되지 않은 키: {sorted(extra)}")
    for fig in manifest.get("figures") or []:
        extra = set(fig) - FIGURE_KEYS
        if extra:
            raise ValueError(f"manifest figures 에 허용되지 않은 키: {sorted(extra)}")
    live = manifest.get("live_search") or {}
    extra = set(live) - LIVE_SEARCH_KEYS
    if extra:
        raise ValueError(f"manifest live_search 에 허용되지 않은 키: {sorted(extra)}")
    if set(live.get("keywords") or {}) - {"ko", "en"} or any(
        not isinstance(v, int) for v in (live.get("keywords") or {}).values()
    ):
        raise ValueError("manifest live_search.keywords 는 개수만 남긴다.")
    for row in live.get("sources") or []:
        extra = set(row) - LIVE_SOURCE_KEYS
        if extra:
            raise ValueError(f"manifest live_search.sources 에 허용되지 않은 키: {sorted(extra)}")
    for value in _strings(manifest):
        if len(value) > MAX_TEXT_CHARS:
            raise ValueError("manifest 에 긴 문자열이 있습니다 — 원문이 섞였을 수 있습니다.")


def _strings(value: Any):
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list | tuple | set | frozenset):
        for v in value:
            yield from _strings(v)


class FileRunLog:
    def __init__(self, root: Path):
        self.root = Path(root)

    def __repr__(self) -> str:
        return "FileRunLog()"

    def record(self, run_id: str, manifest: dict[str, Any]) -> None:
        if not is_valid_run_id(run_id):
            raise ValueError("run_id 형식이 올바르지 않습니다.")
        check_manifest(manifest)
        dirs = [p for p in self.root.glob(f"*/{run_id}") if (p / "state.json").is_file()]
        if len(dirs) != 1:
            raise FileNotFoundError("run 디렉터리를 찾을 수 없습니다.")
        write_json(dirs[0] / "manifest.json", manifest)  # 600, 원자적
