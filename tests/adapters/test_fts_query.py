"""보안 E: FTS5 MATCH 입력 인용 검증."""

import random
import sqlite3
import string

import pytest

from rra.adapters.persistence import _sql


@pytest.fixture
def fts():
    conn = sqlite3.connect(":memory:")
    conn.execute(
        'CREATE VIRTUAL TABLE t USING fts5(text, tokenize="unicode61 remove_diacritics 2")'
    )
    conn.execute("INSERT INTO t(text) VALUES ('궤도의 틀림을 자동으로 감지한다')")
    conn.execute("INSERT INTO t(text) VALUES ('track geometry monitoring')")
    return conn


def match(conn, expr):
    return conn.execute("SELECT rowid FROM t WHERE t MATCH ?", (expr,)).fetchall()


def test_tokens_are_quoted_and_prefixed():
    assert _sql.quote_fts_query("궤도 틀림") == '"궤도"* OR "틀림"*'


def test_operators_become_plain_search_terms():
    expr = _sql.quote_fts_query("a OR b NEAR NOT c")
    assert expr == '"a"* OR "or"* OR "b"* OR "near"* OR "not"* OR "c"*'


@pytest.mark.parametrize(
    "raw", ['"', "*", "^", "()", ":", "-", "+", '""""', "   ", "***", "!@#$%^&*()", ""]
)
def test_operator_only_input_yields_no_query(raw):
    assert _sql.quote_fts_query(raw) == ""


def test_quote_escaping_is_defensive():
    assert _sql.quote_fts_query('a"b') == '"a"* OR "b"*'


def test_token_and_length_caps():
    expr = _sql.quote_fts_query(" ".join(f"t{i}" for i in range(100)))
    assert expr.count(" OR ") == _sql.MAX_FTS_TOKENS - 1
    assert _sql.clamp_query("가" * 5000) == "가" * _sql.MAX_QUERY_CHARS


def test_duplicate_tokens_collapse():
    assert _sql.quote_fts_query("궤도 궤도 궤도") == '"궤도"*'


def test_prefix_match_finds_korean_particle_forms(fts):
    assert match(fts, _sql.quote_fts_query("궤도")) == [(1,)]
    assert match(fts, _sql.quote_fts_query("track")) == [(2,)]


def test_sql_injection_attempt_is_inert(fts):
    """세미콜론·주석·따옴표는 전부 평범한 검색 토큰이 된다."""
    expr = _sql.quote_fts_query("'; DROP TABLE t; --")
    assert expr == '"drop"* OR "table"* OR "t"*'
    match(fts, expr)  # 문법 오류 없이 실행되고
    assert fts.execute("SELECT count(*) FROM t").fetchone()[0] == 2  # 테이블은 그대로


def test_fuzz_never_raises_operational_error(fts):
    random.seed(20260908)
    alphabet = string.printable + "궤도틀림자동"
    for _ in range(200):
        # 보안용 난수가 아니라 퍼징 입력이라 표준 random 으로 충분하다.
        raw = "".join(
            random.choice(alphabet)
            for _ in range(random.randint(0, 40))  # noqa: S311
        )
        expr = _sql.quote_fts_query(raw)
        if expr:
            match(fts, expr)


def test_clamp_k_bounds():
    assert _sql.clamp_k(0) == 1
    assert _sql.clamp_k(10**6) == _sql.MAX_K
    with pytest.raises(TypeError):
        _sql.clamp_k("20")


def test_placeholders_rejects_non_integer():
    assert _sql.placeholders(3) == "?,?,?"
    for bad in ("3", 0, -1, True, 10**6):
        with pytest.raises(ValueError):
            _sql.placeholders(bad)


def test_clamp_queries_drops_blanks_and_caps_count():
    out = _sql.clamp_queries(["  a  ", "", "   "] + [f"q{i}" for i in range(20)])
    assert out[0] == "a"
    assert len(out) <= _sql.MAX_QUERIES
