"""녹화 도구 — 응답에 비밀이 섞여 와도 저장 파일에는 남지 않는다. 네트워크 없음."""

import json

import httpx
import pytest

from rra.settings import Settings
from tests.tools import record_fixture as rec

CID, KEY, MAC = "CID-REAL-9", "0123456789abcdef0123456789abcdef", "AA-BB-CC-DD-EE-FF"


def settings(tmp_path):
    return Settings(
        _env_file=None,
        scienceon_client_id=CID,
        scienceon_key=KEY,
        scienceon_mac=MAC,
        ntis_key="NTIS-REAL-KEY",
    )


def gateway(request):
    """비밀을 응답 본문에 되돌려 싣는 악의적(또는 부주의한) 서버."""
    if request.url.path == "/tokenrequest.do":
        return httpx.Response(
            200,
            json={
                "access_token": "ACCESS-XYZ",
                "refresh_token": "REFRESH-XYZ",
                "client_id": CID,
                "expires": 7200,
            },
        )
    token = request.url.params.get("token")
    body = (
        "<MetaData><resultSummary><TotalCount>1</TotalCount></resultSummary>"
        f"<echo>{CID} {token} aa:bb:cc:dd:ee:ff {request.url.params.get('client_id')}</echo>"
        '<recordList><record><item metaCode="CN">X1</item>'
        '<item metaCode="Title">궤도</item></record></recordList></MetaData>'
    )
    return httpx.Response(200, content=body.encode(), headers={"content-type": "text/xml"})


async def test_recorded_files_contain_no_secrets(tmp_path):
    paths = await rec.record(
        "scienceon",
        "궤도",
        "ARTI",
        1,
        settings=settings(tmp_path),
        inner=httpx.MockTransport(gateway),
        resolver=lambda h: False,
        out_root=tmp_path,
    )
    files = list((tmp_path / "scienceon").iterdir())
    blob = b"".join(f.read_bytes() for f in files)
    for secret in (CID, KEY, "ACCESS-XYZ", "REFRESH-XYZ", "AA-BB-CC-DD-EE-FF", "aa:bb:cc:dd:ee:ff"):
        assert secret.encode() not in blob, secret
    assert b"REDACTED" in paths[0].read_bytes() and "궤도".encode() in paths[0].read_bytes()
    shape = json.loads((tmp_path / "scienceon" / "token_shape.json").read_text())
    assert shape == {
        "access_token": "str",
        "refresh_token": "str",
        "client_id": "str",
        "expires": "int",
    }
    meta = json.loads(next(tmp_path.glob("scienceon/*.meta.json")).read_text())
    assert "url" not in meta and meta["query"] == "궤도"


def test_redact_refuses_when_something_survives():
    # 마스킹 후에도 남는 경우(예: 마스크가 비밀의 일부를 다시 만들어 냄)는 저장 거부
    with pytest.raises(SystemExit):
        rec.redact(b"xxREDACTEDxx", {"REDACTED"})


def test_url_encoded_forms_are_masked():
    out = rec.redact(b"a=ab%2Bc%2Fd%3D b=ab+c/d=", {"ab+c/d="})
    assert b"ab" not in out.replace(b"REDACTED", b"")


# ── NTIS: JSON 문자열로 감싸 온 응답을 풀어 저장, 사람 이름 제거 (2026-10-27 실응답 꼴) ──
NTIS_PROJECT = (
    '<?xml version="1.0" encoding="UTF-8"?>\n<RESULT><TOTALHITS>1</TOTALHITS><RESULTSET>'
    '<HIT NO="1"><ProjectNumber>1615007833</ProjectNumber><ProjectTitle><Korean>궤도</Korean>'
    "</ProjectTitle><Manager><Name>홍길동</Name></Manager><Researchers><Name>김철수;이영희</Name>"
    "<ManCount>2</ManCount></Researchers><ResearchAgency><Name>한국철도기술연구원</Name>"
    "</ResearchAgency></HIT></RESULTSET></RESULT>"
)
NTIS_PATENT = (
    '<RESULT><TOTALHITS>1</TOTALHITS><RESULTSET><HIT NO="1" SITID="PAT"><ResultID>PTR-1'
    "</ResultID><ResultTitle>장치</ResultTitle><Registrant>한국철도기술연구원;박영수</Registrant>"
    "<ProjectID>1615007833</ProjectID></HIT></RESULTSET></RESULT>"
)
NTIS_PAPER = (
    '<RESULT><TOTALHITS>1</TOTALHITS><RESULTSET><HIT NO="1" SITID="PAP"><ResultID>JNL-1'
    "</ResultID><ResultTitle>논문</ResultTitle><Author>최민수;정다은</Author>"
    "<ProjectID>1615007833</ProjectID></HIT></RESULTSET></RESULT>"
)
NTIS_RELATED = '{"PJT_ID": "1615007833", "exist": true, "items": [], "count": 0}'


def ntis_gateway(request):
    """실서버처럼 Accept 에 json 이 있으면 본문 전체를 JSON 문자열로 감싼다."""
    assert "application/json" in request.headers["accept"]
    path, q = request.url.path, request.url.params
    if path.endswith("ConnectionContent"):
        body = NTIS_RELATED
    elif path.endswith("public_result"):
        body = NTIS_PAPER if q.get("collection") == "rpaper" else NTIS_PATENT
    else:
        body = NTIS_PROJECT.replace("1615007833", f"{q.get('apprvKey')}-echo")  # 키를 되돌려 줌
    return httpx.Response(
        200, content=json.dumps(body).encode(), headers={"content-type": "application/json"}
    )


async def test_ntis_recordings_are_unwrapped_named_and_free_of_names_and_keys(tmp_path):
    kw = dict(
        settings=settings(tmp_path),
        inner=httpx.MockTransport(ntis_gateway),
        resolver=lambda h: False,
        out_root=tmp_path,
    )
    (project,) = await rec.record("ntis", "철도 궤도", None, 5, label="track", **kw)
    assert project.name.startswith("ntis_project_") and project.name.endswith("_track.xml")
    body = project.read_text(encoding="utf-8")
    assert body.startswith("<?xml") and "REDACTED-echo" in body  # JSON 문자열을 푼 XML, 키 가림
    assert "NTIS-REAL-KEY" not in body
    assert "<Name>NAME-REMOVED</Name>" in body and "홍길동" not in body and "김철수" not in body
    assert "<Name>한국철도기술연구원</Name>" in body  # 기관명은 남는다
    meta = json.loads(project.with_suffix(".meta.json").read_text())
    assert meta["json_wrapped"] is True and meta["content_type"] == "application/json"

    paths = await rec.record("ntis_insights", "1615007833", None, 5, **kw)
    names = sorted(p.name for p in paths)
    stamp = names[0].split("_")[2]
    assert names == [
        f"ntis_outcome_{stamp}_rpaper.xml",
        f"ntis_outcome_{stamp}_rpatent.xml",
        f"ntis_related_{stamp}.json",
    ]
    blob = "".join(p.read_text(encoding="utf-8") for p in paths)
    assert "<Author>NAME-REMOVED</Author>" in blob and "최민수" not in blob
    assert "<Registrant>한국철도기술연구원</Registrant>" in blob and "박영수" not in blob
    assert json.loads(paths[2].read_text(encoding="utf-8"))["exist"] is True  # 문자열 안의 JSON 풂
