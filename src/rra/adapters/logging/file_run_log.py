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
    }
)
VERSION_KEYS = frozenset(
    {"version", "origin", "changed_sections", "sentences", "alerts", "open_annotations"}
)
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
