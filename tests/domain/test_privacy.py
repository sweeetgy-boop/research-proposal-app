"""개인정보 제거 — 전화·이메일·이름(직함·부서 뒤)·긴 번호. 부서명은 남긴다."""

from rra.domain.rules.privacy import strip_personal


def test_phone_email_and_extension_are_masked():
    r = strip_personal("문의: 042-615-1234, 010-1234-5678, 내선 2345, mail hong@korail.com")
    assert r.text == "문의: [전화], [전화], [전화], mail [이메일]"
    assert r.removed == {"phone": 3, "email": 1}


def test_name_after_title_or_department_is_removed_but_department_stays():
    r = strip_personal("담당자 경영연구처 박한균 (042-615-1111)\n작성자: 김철수\n기술연구처 이영희")
    assert "박한균" not in r.text and "김철수" not in r.text and "이영희" not in r.text
    assert "경영연구처" in r.text and "기술연구처" in r.text
    assert r.text.startswith("담당자 경영연구처 [이름] ([전화])")
    assert r.removed["name"] == 3


def test_id_like_long_numbers_are_masked_but_ordinary_figures_stay():
    r = strip_personal("주민번호 901010-1234567, 수송인원 1,234만명, 2024년 3.5%")
    assert r.text == "주민번호 [번호], 수송인원 1,234만명, 2024년 3.5%"


def test_plain_text_without_personal_data_is_unchanged():
    text = "비전: 국민과 함께하는 철도. 목표 2030년 30% 감축."
    r = strip_personal(text)
    assert r.text == text and r.removed == {}
    assert strip_personal("").text == ""
