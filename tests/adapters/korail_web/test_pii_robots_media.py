from pathlib import Path

from rra.adapters.sources.korail_web._media import image_dims, image_kind
from rra.adapters.sources.korail_web._pii import has_pii, strip_pii
from rra.adapters.sources.korail_web.robots import RobotsRules

FIX = Path(__file__).parents[2] / "fixtures" / "korail_web"
UA = "RRA research-proposal-app (internal research use) +https://github.com/x/y"


def test_strip_pii_phone_email_and_labelled_names():
    text = "담당자 홍길동 과장(042-615-3647, hong@korail.com) / 문의: 김철수 차장 010-1234-5678"
    out = strip_pii(text)
    assert "홍길동" not in out and "김철수" not in out
    assert "042" not in out and "@" not in out
    assert "담당자 [이름 삭제] 과장" in out and "[연락처 삭제]" in out and "[이메일 삭제]" in out
    assert not has_pii(out)


def test_strip_pii_keeps_departments_and_plain_text():
    text = "경영연구처장이 발표했다. 철도연구원 기술연구처 과장급 회의. 안전관리율 0.859"
    assert strip_pii(text) == text
    assert (
        strip_pii("담당부서 윤리경영처 연락처 042-615-3647")
        == "담당부서 윤리경영처 연락처 [연락처 삭제]"
    )


def test_robots_empty_allows_everything_and_disallow_is_honoured():
    empty = RobotsRules((FIX / "robots_empty.txt").read_text(), user_agent=UA)
    assert empty.empty and empty.allowed("https://info.korail.com/info/anything.do")
    rules = RobotsRules((FIX / "robots_disallow.txt").read_text(), user_agent=UA)
    assert not rules.allowed("https://info.korail.com/info/selectBbsNttList.do?bbsNo=1")
    assert not rules.allowed("https://info.korail.com/private/x")
    assert rules.allowed("https://info.korail.com/info/contents.do?key=716")


def test_image_dims_png_gif_jpeg():
    png = (
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\rIHDR"
        + (640).to_bytes(4, "big")
        + (480).to_bytes(4, "big")
    )
    assert image_dims(png) == (640, 480) and image_kind(png) == "png"
    gif = b"GIF89a" + (12).to_bytes(2, "little") + (34).to_bytes(2, "little")
    assert image_dims(gif) == (12, 34)
    jpeg = (
        b"\xff\xd8"
        + b"\xff\xc0"
        + (17).to_bytes(2, "big")
        + b"\x08"
        + (300).to_bytes(2, "big")
        + (200).to_bytes(2, "big")
    )
    assert image_dims(jpeg) == (200, 300) and image_kind(jpeg) == "jpg"
    assert image_dims(b"nope") is None
