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
