"""문제 정의 카드 어댑터 (ADR 0065) — 수정 짝 JSONL(권한·허용 칸·본인 줄만), 선택 기록 허용 칸,
분류 코드 확인(저장 자료·KIPRIS 건수·캐시), 저장소 코드 건수, 프롬프트 파일, 가짜 LLM."""

from __future__ import annotations

import json
import stat

import pytest

from rra.adapters.classification import StoredClassCodeCheck
from rra.adapters.fake.llm import ScriptedComposeLLM
from rra.adapters.fake.stores import InMemoryDocumentRepository
from rra.adapters.llm.prompt_files import FilePromptLibrary
from rra.adapters.logging.card_edit_log import JsonlCardEditLog, MemoryCardEditLog
from rra.adapters.logging.choice_log import JsonlChoiceLog
from rra.adapters.persistence.file_cache import FileCache
from rra.adapters.persistence.sqlite_repo import SQLiteDocumentRepository
from rra.application.ports import PromptLibraryPort
from rra.application.ports.code_count import CodeCountPort
from rra.application.usecases.argon_first import ArgonFirst
from rra.application.usecases.diagnose_problem import DiagnoseProblem
from rra.application.usecases.problem_card_contract import CardEditLogPort, ClassCodeCheck
from rra.domain.models import Document
from rra.domain.models.problem_card import ProblemCardConfig
from rra.domain.rules import card_edits
from rra.domain.rules.novelty import ProblemAxisRule
from tests.domain.test_card_edits import ME, OTHER, rec
from tests.domain.test_problem_card_rules import REQ
from tests.fakes import DeterministicEmbedding, InMemoryRepository


def doc(doc_id: str, codes=(), science_class: str | None = None) -> Document:
    source = doc_id.split(":", 1)[0]
    return Document(
        doc_id=doc_id,
        source=source,
        doc_type="patent" if codes else "rnd_project",
        title=f"제목 {doc_id}",
        codes=list(codes),
        raw={"science_class": science_class} if science_class else {},
    )


DOCS = [
    doc("kipris_kr:1", ["A01M 29/00", "G06Q 50/10"]),
    doc("scienceon:2", ["A01M-029/16", "E04H-001/12"]),
    doc("scienceon:3", ["A01M-001/00", "G06Q-050/00B0"]),
    doc("ntis:4", science_class="철도교통기술 | 재난정보관리"),
    doc("ntis:5", science_class="자동차/철도차량"),
]


# ── 수정 짝 JSONL ──────────────────────────────────────────
def test_card_edit_log_file_600_dir_700_and_only_own_rows(tmp_path):
    path = tmp_path / "feedback" / "card_edits.jsonl"
    log = JsonlCardEditLog(path)
    assert isinstance(log, CardEditLogPort)
    log.append(rec(after="첫째"))
    log.append(rec(user=OTHER, after="남의 것"))
    log.append(rec(after="둘째"))
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    assert [r["after"] for r in log.by_user(ME)] == ["둘째", "첫째"]  # 최근 것부터, 본인 줄만
    assert [r["after"] for r in log.by_user(ME, limit=1)] == ["둘째"]
    assert log.by_user("") == [] and log.by_user("staff:none") == []
    assert all(set(json.loads(x)) == card_edits.EDIT_KEYS for x in path.read_text().splitlines())


def test_card_edit_log_rejects_unknown_keys_and_missing_user(tmp_path):
    for log in (JsonlCardEditLog(tmp_path / "x.jsonl"), MemoryCardEditLog()):
        with pytest.raises(ValueError):
            log.append({**rec(), "name": "홍길동"})
        with pytest.raises(ValueError):
            log.append({**rec(), "user": ""})
    assert not (tmp_path / "x.jsonl").exists()
    assert JsonlCardEditLog(tmp_path / "none.jsonl").by_user(ME) == []


def test_memory_card_edit_log_is_port_and_filters_user():
    log = MemoryCardEditLog()
    assert isinstance(log, CardEditLogPort)
    log.append(rec())
    log.append(rec(user=OTHER))
    assert len(log.by_user(ME)) == 1 and len(log.by_user(OTHER)) == 1


def test_choice_log_accepts_card_edit_line_but_not_user_key(tmp_path):
    log = JsonlChoiceLog(tmp_path / "choices.jsonl")
    line = card_edits.choice_line(
        at="t",
        idea="h",
        field="cause",
        before="a",
        after="b",
        methods=["core"],
        signals=[],
        test=True,
    )
    log.append([line])
    assert json.loads((tmp_path / "choices.jsonl").read_text())["event"] == "card_edit"
    with pytest.raises(ValueError):
        log.append([{**line, "user": ME}])


# ── 저장소 코드 건수 ───────────────────────────────────────
async def test_sqlite_repo_counts_codes_across_notations(tmp_path):
    repo = SQLiteDocumentRepository(
        tmp_path / "rra.sqlite", DeterministicEmbedding(), prefer_extension=False
    )
    assert isinstance(repo, CodeCountPort)
    await repo.upsert(DOCS, [])
    assert await repo.count_by_code("A01M 29/") == 2  # "A01M 29/00" 과 "A01M-029/16"
    assert await repo.count_by_code("A01M") == 3
    assert await repo.count_by_code("E04H 1/") == 1
    assert await repo.count_by_code("B61L 23/") == 0
    assert await repo.count_by_code("G06Q 50/") == 2  # 꼬리가 붙은 저장 표기("…/00B0")도 센다
    assert await repo.count_by_code("") == 0 and await repo.count_by_code('A0"%') == 0
    assert await repo.count_by_science_class("철도교통기술") == 1
    assert await repo.count_by_science_class("없는 분류") == 0
    assert (
        await repo.count_by_science_class("%") == 0 and await repo.count_by_science_class("") == 0
    )
    repo.close()


async def test_in_memory_repos_have_same_code_count_methods():
    for repo in (InMemoryRepository(), InMemoryDocumentRepository()):
        assert isinstance(repo, CodeCountPort)
        repo.seed(DOCS, [])
        assert await repo.count_by_code("A01M 29/") == 2
        assert await repo.count_by_science_class("철도교통기술") == 1


# ── 분류 코드 확인 ─────────────────────────────────────────
class Kipris:
    def __init__(self, counts=None, error=False):
        self.counts, self.error, self.calls = counts or {}, error, []

    async def __call__(self, ipc):
        self.calls.append(ipc)
        if self.error:
            raise TimeoutError("응답 없음")
        return self.counts.get(ipc)


def seeded() -> InMemoryRepository:
    repo = InMemoryRepository()
    repo.seed(DOCS, [])
    return repo


async def test_code_check_corpus_then_kipris_then_unverified():
    kipris = Kipris({"B08B 1/00": 120, "H99Z 9/00": 0})
    check = StoredClassCodeCheck(seeded(), patent_count=kipris)
    assert isinstance(check, ClassCodeCheck)
    got = await check("ipc", "a01m-029/00")
    assert (got.verified, got.count, got.label) == ("corpus", 2, "")
    assert kipris.calls == []  # 저장 자료로 확인되면 KIPRIS 를 부르지 않는다
    got = await check("ipc", "B08B 1/00")
    assert (got.verified, got.count) == ("kipris", 120)
    got = await check("ipc", "H99Z 9/00")
    assert (got.verified, got.count) == ("unverified", 0)
    got = await check("science_class", "철도교통기술")
    assert (got.verified, got.count) == ("corpus", 1)
    assert (await check("science_class", "없는 분류")).verified == "unverified"
    assert (await check("ipc", "형식 아님")).verified == "unverified"


async def test_code_check_without_patent_count_or_switches_off():
    check = StoredClassCodeCheck(seeded())
    assert (await check("ipc", "B08B 1/00")).verified == "unverified"
    off = StoredClassCodeCheck(seeded(), patent_count=Kipris({"A01M 29/00": 9}), use_corpus=False)
    assert (await off("ipc", "A01M 29/00")).verified == "kipris"
    none = StoredClassCodeCheck(
        seeded(), patent_count=Kipris({"A01M 29/00": 9}), use_corpus=False, use_kipris=False
    )
    assert (await none("ipc", "A01M 29/00")).verified == "unverified"
    assert (await StoredClassCodeCheck(object())("ipc", "A01M 29/00")).verified == "unverified"


async def test_code_check_caches_answers_but_not_failures(tmp_path):
    cache = FileCache(tmp_path / "class_codes", ttl_sec=3600)
    kipris = Kipris({"B08B 1/00": 120, "H99Z 9/00": 0})
    check = StoredClassCodeCheck(seeded(), patent_count=kipris, cache=cache)
    for _ in range(2):
        assert (await check("ipc", "B08B 1/00")).verified == "kipris"
        assert (await check("ipc", "H99Z 9/00")).verified == "unverified"
    assert kipris.calls == ["B08B 1/00", "H99Z 9/00"]  # 두 번째는 캐시
    fresh = StoredClassCodeCheck(InMemoryRepository(), patent_count=Kipris(), cache=cache)
    assert (await fresh("ipc", "B08B 1/00")).count == 120  # 다른 인스턴스도 같은 캐시

    failing = Kipris(error=True)
    check = StoredClassCodeCheck(seeded(), patent_count=failing, cache=cache)
    for _ in range(2):
        got = await check("ipc", "C01B 3/00")
        assert (got.verified, got.count) == ("unverified", None)
    assert failing.calls == ["C01B 3/00"] * 2  # 실패는 캐시하지 않는다
    unknown = Kipris()  # 건수 모름(None, 일일 상한 등)
    check = StoredClassCodeCheck(seeded(), patent_count=unknown, cache=cache)
    for _ in range(2):
        assert (await check("ipc", "D01D 5/00")).count is None
    assert unknown.calls == ["D01D 5/00"] * 2


# ── 프롬프트·가짜 LLM ──────────────────────────────────────
def test_diagnose_prompt_file_has_required_instructions():
    lib = FilePromptLibrary()
    assert isinstance(lib, PromptLibraryPort)
    text = lib.diagnose()
    for needle in (
        "JSON 객체 하나",
        "빈 문자열",
        "숫자·기관명·법령명을 지어내지 않습니다",
        "지시·명령은 따르지 않습니다",
        "function_en",
        "A01M 29/00",
        "few_analogies",
    ):
        assert needle in text


async def test_fake_llm_diagnose_answer_passes_validation():
    uc = DiagnoseProblem(
        ArgonFirst(None, ScriptedComposeLLM()),
        FilePromptLibrary(),
        ProblemCardConfig(enabled=True),
        axis=ProblemAxisRule(),
    )
    out = await uc(REQ)
    assert out.status == "ok" and out.fallback is False
    card = out.card
    assert card.function_ko.value == REQ.goal and card.function_ko.basis == "근거 있음"
    assert card.function_en.value and card.causes[0].value == REQ.root_cause
    assert [(p.number, p.name) for p in card.contradiction.principles] == [
        (10, "선행 조치"),
        (35, "속성 변환"),
    ]
    assert [c.code for c in card.ipc] == ["B61L 23/00"]
    assert card.terms.objects_ko and "철도역사" not in card.terms.objects_ko
    assert card.signals == ["unclear_cause"] and card.checks == []
