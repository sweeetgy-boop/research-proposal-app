"""xlsx·xls 첨부: 워커의 시트 구조를 본문 텍스트로 (2026-10-27)."""

from rra.adapters.sources.korail_web._sheets import sheets_to_text


def test_sheets_become_pipe_rows_with_sheet_headers():
    raw = {
        "sheets": [
            {
                "name": "수송",
                "rows": [["구분", "2023", "2024"], ["수송인원", 1234, 1300], [None, None]],
            },
            {"name": "빈시트", "rows": [[None, ""]]},
        ]
    }
    text = sheets_to_text(raw)
    assert text == "[수송]\n구분 | 2023 | 2024\n수송인원 | 1234 | 1300"


def test_non_sheet_results_are_left_alone_and_limits_apply():
    assert sheets_to_text({"text": "본문"}) is None
    assert sheets_to_text("x") is None
    rows = [["r", i] for i in range(10)]
    text = sheets_to_text({"sheets": [{"name": "s", "rows": rows}]}, max_rows=3)
    assert text.count("\n") == 3
    assert sheets_to_text({"sheets": [{"name": "s", "rows": rows}]}, max_chars=10).startswith("[s]")
