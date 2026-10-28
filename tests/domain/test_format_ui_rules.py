"""레인 D 순수 규칙 — 한국어 설명 표(모든 알림 코드), 제목·파일 이름, 입력 변경 → 섹션,
근거 확인 필요, 섹션 작성 벽시계."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

import pytest

from rra.domain.models import RunState, Section, Sentence, StepRecord
from rra.domain.models.review import EvidenceDecision
from rra.domain.rules import problem_labels, request_change, run_title, usage
from rra.domain.rules.evidence import bulk_approvals, evidence_attention

ROOT = Path(__file__).parents[2]
SRC = ROOT / "src" / "rra"
WEB_LABELS = ROOT / "web" / "src" / "lib" / "labels.ts"


# ── 항목 16: 모든 알림 코드에 한국어 설명 ───────────────────────────
def _emitted_codes() -> set[str]:
    """LintProblem(code=…)·StyleFinding(…, CODE, …) 로 백엔드가 내는 코드 전부 (소스 정적 분석)."""
    consts: dict[str, str] = {}
    calls: list[ast.Call] = []
    for path in (SRC / "domain").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                consts[node.targets[0].id] = node.value.value
            if isinstance(node, ast.Call):
                calls.append(node)
    for path in (SRC / "application").rglob("*.py"):
        calls += [
            n
            for n in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
            if isinstance(n, ast.Call)
        ]
    codes: set[str] = set()

    def value(node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return consts.get(node.id)
        return None

    for call in calls:
        name = getattr(call.func, "id", getattr(call.func, "attr", ""))
        if name == "LintProblem":
            for kw in call.keywords:
                if kw.arg == "code" and (v := value(kw.value)):
                    codes.add(v)
        if name == "StyleFinding" and len(call.args) >= 2 and (v := value(call.args[1])):
            codes.add(v)
    # 건너뛴 섹션 코드(lint._SKIP_MESSAGE 의 키)·Q6 규칙 검사 코드
    from rra.domain.rules import lint, style

    codes |= set(lint._SKIP_MESSAGE) | set(lint.STYLE_CODES)
    codes |= {
        getattr(style, n) for n in dir(style) if n.isupper() and isinstance(getattr(style, n), str)
    }
    return {c for c in codes if re.fullmatch(r"[a-z][a-z_]+", c)}


def test_every_problem_code_the_backend_emits_has_a_korean_label():
    codes = _emitted_codes()
    assert {"missing", "input_missing", "evidence_mismatch", "long_sentence"} <= codes
    missing = sorted(codes - set(problem_labels.PROBLEM_LABELS))
    assert missing == [], f"한국어 설명이 없는 알림 코드: {missing}"
    for label in problem_labels.PROBLEM_LABELS.values():
        assert re.search(r"[가-힣]", label) and not re.search(r"[a-z]{3,}", label)


def test_web_label_map_is_the_same_table():
    text = WEB_LABELS.read_text(encoding="utf-8")

    def table(name: str) -> dict[str, str]:
        m = re.search(rf"export const {name}: Record<string, string> = (\{{.*?\}});", text, re.S)
        assert m, name
        body = re.sub(r"//[^\n]*", "", m.group(1))
        body = re.sub(r"^(\s*)([a-z_]+):", r'\1"\2":', body, flags=re.M)
        body = re.sub(r",\s*}", "}", body)
        return json.loads(body)

    assert table("PROBLEM_LABELS") == problem_labels.PROBLEM_LABELS
    assert table("SEVERITY_LABELS") == problem_labels.SEVERITY_LABELS
    assert table("REVIEW_SKIP_LABELS") == problem_labels.REVIEW_SKIP_LABELS
    assert table("STEP_LABELS") == problem_labels.STEP_LABELS


def test_label_helpers_never_return_codes():
    assert problem_labels.problem_label("brand_new_code") == problem_labels.UNKNOWN_PROBLEM
    assert problem_labels.severity_label("warning") == "주의"
    assert problem_labels.review_skip_label("self_review") == "1차 검토 생략(같은 모델 작성)"
    assert problem_labels.review_skip_label(None) is None
    assert problem_labels.status_label("final_reviewed") == "최종 검토 완료"


# ── 항목 2: 제목·파일 이름 ─────────────────────────────────────────
def test_draft_title_prefers_title_section_then_title_hint():
    secs = [Section(key="title", sentences=[Sentence(text="  궤도 열화 예측  ")])]
    assert run_title.draft_title(secs) == "궤도 열화 예측"
    hint = type("R", (), {"title_hint": "가제 하나"})()
    assert run_title.draft_title([Section(key="title", sentences=[])], hint) == "가제 하나"
    assert run_title.draft_title([], None) == ""
    assert run_title.draft_title([{"key": "title", "sentences": [{"text": "사전형"}]}]) == "사전형"


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("궤도 틀림 예측 모델 개발", "궤도 틀림 예측 모델 개발_v3.hwpx"),
        ('AI/IoT 기반 "스마트" 역사: 관리*방안?', "AI IoT 기반 스마트 역사 관리 방안_v3.hwpx"),
        ("  ..앞뒤 점·공백..  ", "앞뒤 점·공백_v3.hwpx"),
        ("탭\t과\n줄바꿈", "탭 과 줄바꿈_v3.hwpx"),
        ("", "연구과제제안서_v3.hwpx"),
        ("CON", "연구과제제안서_v3.hwpx"),
        ('<>:"/\\|?*', "연구과제제안서_v3.hwpx"),
    ],
)
def test_hwpx_filename_strips_invalid_characters(title, expected):
    assert run_title.hwpx_filename(title, 3) == expected


def test_hwpx_filename_shortens_long_titles():
    name = run_title.hwpx_filename("가" * 200, 12)
    stem = name.removesuffix("_v12.hwpx")
    assert len(stem) == run_title.MAX_TITLE_CHARS and stem.endswith("…")
    assert run_title.ascii_filename("20261028-ab/../x", 2) == "proposal-20261028-abx-v2.hwpx"


# ── 항목 17: 바뀐 칸 → 섹션 ─────────────────────────────────────────
KEYS = [
    "title",
    "task_type",
    "policy_importance",
    "tech_importance",
    "strategy_alignment",
    "objective",
    "method",
    "expected_management",
    "expected_technology",
    "expected_standing",
    "utilization",
    "overlap_review",
]


def test_changed_fields_ignore_whitespace_and_compare_priority_only_when_given():
    old = {"goal": "예측", "policy_basis": "", "budget": None}
    assert request_change.changed_fields(old, {"goal": " 예측 ", "policy_basis": ""}) == []
    assert request_change.changed_fields(old, {"goal": "예측", "policy_basis": "계획"}) == [
        "policy_basis"
    ]
    assert request_change.changed_fields(old, old, old_priority=["a"], new_priority=None) == []
    assert request_change.changed_fields(old, old, old_priority=["a"], new_priority=["b"]) == [
        "priority_evidence"
    ]


@pytest.mark.parametrize(
    ("fields", "sections"),
    [
        (["policy_basis"], ["policy_importance", "strategy_alignment"]),
        (
            ["beneficiaries"],
            ["expected_management", "expected_technology", "expected_standing", "utilization"],
        ),
        (["differentiation"], ["objective", "method", "overlap_review"]),
        (["title_hint"], ["title"]),
        (["constraints", "remarks"], ["method", "utilization", "overlap_review"]),
        (["department", "budget"], []),
        (["goal"], KEYS),
        (["priority_evidence"], ["tech_importance", "method"]),
    ],
)
def test_affected_sections_follow_the_prompt_inputs(fields, sections):
    got = request_change.affected_sections(
        fields, KEYS, evidence_sections=["method", "tech_importance"]
    )
    assert got == sections
    assert request_change.regen_targets("all", got, KEYS) == KEYS
    assert request_change.preserves_proposer("sections") and not request_change.preserves_proposer(
        "all"
    )


# ── 항목 16: 근거 확인 필요 ───────────────────────────────────────
def _sections():
    return [
        Section(
            key="method",
            sentences=[
                Sentence(text="a", evidence=["openalex:W1#0"]),  # 불일치
                Sentence(text="b", evidence=["openalex:W2#0"]),  # 부분
                Sentence(text="c", evidence=["korail_web:img#0"]),  # 이미지 판독
                Sentence(text="d", evidence=["openalex:W3#0", "openalex:W4#0"]),  # 지지
                Sentence(text="e", evidence=[]),
                Sentence(text="f", evidence=["x#0"], origin="app"),
            ],
        )
    ]


def test_attention_counts_only_mismatch_partial_and_image_sentences():
    support = {"s:method:0": "불일치", "s:method:1": "부분", "s:method:3": "지지"}
    basis = {"korail_web:img#0": "image_vision", "openalex:W1#0": "abstract"}
    att = evidence_attention(_sections(), [], support, basis)
    assert att["sentences"] == ["s:method:0", "s:method:1", "s:method:2"]
    assert (att["mismatch"], att["partial"], att["image"], att["bulk"]) == (1, 1, 1, 2)
    decided = [
        EvidenceDecision(sentence_id="s:method:0", evidence_id="openalex:W1#0", action="exclude")
    ]
    assert evidence_attention(_sections(), decided, support, basis)["sentences"] == [
        "s:method:1",
        "s:method:2",
    ]
    bulk = bulk_approvals(_sections(), [], att["sentences"])
    assert [(d.sentence_id, d.evidence_id, d.action) for d in bulk] == [
        ("s:method:3", "openalex:W3#0", "approve"),
        ("s:method:3", "openalex:W4#0", "approve"),
    ]


# ── 항목 16: 섹션 작성은 벽시계 ───────────────────────────────────
def test_parallel_sections_report_wall_clock_and_sum_separately():
    def step(name, a, b):
        return StepRecord(
            name=name,
            status="done",
            started_at=f"2026-10-28T07:01:{a:02d}+00:00",
            finished_at=f"2026-10-28T07:01:{b:02d}+00:00",
        )

    state = RunState(
        run_id="20261028070108-e98b2c54",
        user="local",
        steps=[
            step("retrieve", 0, 19),
            step("section:a", 19, 39),
            step("section:b", 19, 37),
            step("section:c", 20, 38),
            step("section:d", 21, 36),
        ],
        created_at="2026-10-28T07:01:00+00:00",
        updated_at="2026-10-28T07:01:40+00:00",
    )
    out = usage.step_durations(state)
    assert out["sections"] == 20.0  # +19초 ~ +39초
    assert out["sections_sum"] == 20 + 18 + 18 + 15
    assert problem_labels.step_label("sections") == "섹션 작성"
