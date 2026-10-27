"""실제 API 응답을 fixture 로 녹화한다 (ScienceON·NTIS). .env 의 실제 키를 쓴다.

    python -m tests.tools.record_fixture scienceon --query "철도 궤도" --target ARTI --rows 10
    python -m tests.tools.record_fixture ntis --query 궤도 --rows 10

보안 D:
- 응답 본문에서 키·client_id·MAC·accounts·발급된 토큰 값(원문·URL 인코딩)을 전부 REDACTED 로 바꾼다.
  바꾼 뒤에도 남아 있으면 저장하지 않고 실패한다.
- 요청 URL 은 저장하지 않는다 (질의·target·건수만 meta 로).
- 토큰 응답은 값을 버리고 키 이름·타입(형태)만 token_shape.json 으로 남긴다.
- ScienceON 레코드의 사람 이름 항목(Author·Author2·Contributors)은 값을 NAME-REMOVED 로 바꾸고,
  출원인(Applicants)은 기관으로 보이는 이름만 남긴다(개인 출원인은 지움). fixture 에 개인 이름을
  커밋하지 않는다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, quote_plus, urlsplit

import httpx

from rra.composition import (
    build_kipris_source,
    build_ntis_report_source,
    build_ntis_source,
    build_scienceon_source,
    load_settings,
)

ROOT = Path(__file__).parents[1] / "fixtures"
MASK = b"REDACTED"
NAME_MASK = "NAME-REMOVED"
PERSON_ITEMS = ("Author", "Author2", "Contributors")
_ITEM = re.compile(r'(<item metaCode="(?P<code>[A-Za-z0-9]+)"[^>]*>)(?P<body>.*?)(</item>)', re.S)


class RecordingTransport(httpx.AsyncBaseTransport):
    def __init__(self, inner: httpx.AsyncBaseTransport | None = None):
        self.inner = inner or httpx.AsyncHTTPTransport()
        self.exchanges: list[dict[str, Any]] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        resp = await self.inner.handle_async_request(request)
        body = await resp.aread()
        query = {k: v[0] for k, v in parse_qs(urlsplit(str(request.url)).query).items()}
        self.exchanges.append(
            {
                "path": request.url.path,
                "query": query,
                "status": resp.status_code,
                "content_type": resp.headers.get("content-type", ""),
                "body": body,
            }
        )
        return httpx.Response(resp.status_code, headers=resp.headers, content=body, request=request)

    async def aclose(self) -> None:
        await self.inner.aclose()


def secret_values(settings, exchanges) -> set[str]:
    values = set()
    for field in (
        "scienceon_client_id",
        "scienceon_key",
        "scienceon_mac",
        "ntis_key",
        "kipris_key",
    ):
        secret = getattr(settings, field)
        if secret is not None and secret.get_secret_value().strip():
            values.add(secret.get_secret_value().strip())
    for ex in exchanges:
        for name in (
            "accounts",
            "token",
            "refreshToken",
            "apprvKey",
            "client_id",
            "accessKey",
            "ServiceKey",
        ):
            if ex["query"].get(name):
                values.add(ex["query"][name])
        if ex["path"].endswith("tokenrequest.do"):
            try:
                data = json.loads(ex["body"])
            except ValueError:
                continue
            for key in ("access_token", "accessToken", "refresh_token", "refreshToken"):
                if isinstance(data.get(key), str) and data[key]:
                    values.add(data[key])
    mac = next(
        (v for v in values if re.fullmatch(r"[0-9A-Fa-f]{2}([:-]?[0-9A-Fa-f]{2}){5}", v)), None
    )
    if mac:  # MAC 은 표기가 여러 가지 — 흔한 변형도 가린다
        hexes = re.sub(r"[^0-9A-Fa-f]", "", mac)
        pairs = [hexes[i : i + 2] for i in range(0, 12, 2)]
        for sep in ("-", ":", ""):
            values |= {sep.join(pairs).upper(), sep.join(pairs).lower()}
    return {v for v in values if len(v) >= 4}


def redact(body: bytes, secrets: set[str]) -> bytes:
    out = body
    for value in sorted(secrets, key=len, reverse=True):
        for form in {value, quote(value, safe=""), quote_plus(value)}:
            out = out.replace(form.encode("utf-8"), MASK)
    leftover = [v for v in secrets if v.encode("utf-8") in out]
    if leftover:
        raise SystemExit("비밀 값이 응답에 남아 있어 저장하지 않았습니다.")
    return out


def strip_person_names(body: bytes) -> bytes:
    """ScienceON XML 에서 사람 이름 항목을 가린다. 기관명(Affiliation·Publisher·기관 출원인)은
    그대로.
    """
    from rra.adapters.sources._orgs import is_organization

    def repl(m: re.Match[str]) -> str:
        code, inner = m.group("code"), m.group("body")
        value = re.sub(r"^\s*<!\[CDATA\[|\]\]>\s*$", "", inner.strip()).strip()
        if code in PERSON_ITEMS:
            new = NAME_MASK if value else ""
        elif code == "Applicants":  # 개인 출원인은 지운다 (자리표시자는 기관 판정을 통과해 버린다)
            names = [n.strip() for n in re.split(r"\s*[;|]\s*", value) if n.strip()]
            new = ";".join(n for n in names if n != NAME_MASK and is_organization(n))
        else:
            return m.group(0)
        return f"{m.group(1)}<![CDATA[{new}]]>{m.group(4)}"

    return _ITEM.sub(repl, body.decode("utf-8")).encode("utf-8")


_NTIS_NAME = re.compile(
    r"<(?P<tag>Manager|ManagerName|Author|Inventor|Researchers)>(?P<body>.*?)</(?P=tag)>", re.S
)


def strip_ntis_names(body: bytes) -> bytes:
    """NTIS XML 의 사람 이름 요소(연구책임자 Manager/Name·ManagerName, 참여연구원 Researchers/Name,
    저자 Author)를
    NAME-REMOVED 로. 기관명 요소(ResearchAgency·PublicationAgency 등)는 그대로."""

    def repl(m: re.Match[str]) -> str:
        tag, inner = m.group("tag"), m.group("body")
        if tag == "Researchers":
            inner = re.sub(r"<Name>[^<]*</Name>", "<Name>NAME-REMOVED</Name>", inner)
            return f"<{tag}>{inner}</{tag}>"
        if tag == "Manager":
            inner = re.sub(r"<Name>[^<]*</Name>", "<Name>NAME-REMOVED</Name>", inner)
            if "<Name>" not in inner and inner.strip():
                inner = "NAME-REMOVED"
            return f"<{tag}>{inner}</{tag}>"
        return f"<{tag}>{'NAME-REMOVED' if inner.strip() else ''}</{tag}>"

    return _NTIS_NAME.sub(repl, body.decode("utf-8", "replace")).encode("utf-8")


def token_shape(body: bytes) -> dict[str, str]:
    try:
        data = json.loads(body)
    except ValueError:
        return {"_": "not-json"}
    return {k: type(v).__name__ for k, v in data.items()} if isinstance(data, dict) else {}


async def record(
    source: str,
    query: str,
    target: str | None,
    rows: int,
    *,
    settings=None,
    inner: httpx.AsyncBaseTransport | None = None,
    resolver=None,
    out_root: Path = ROOT,
) -> list[Path]:
    settings = settings or load_settings()
    transport = RecordingTransport(inner)
    if source == "scienceon":
        src = build_scienceon_source(settings, transport=transport, resolver=resolver)
        src.targets = [target] if target else src.targets[:1]
        src.row_count = rows
        await src.search(query, rows)
    elif source == "kipris":
        src = build_kipris_source(settings, transport=transport, resolver=resolver)
        root = await src._fetch_root(query, 1, count=rows)  # noqa: SLF001 - 녹화 전용
        from rra.adapters.sources._xml import find_records, local

        print("record_tag 후보:", sorted({local(r.tag) for r in find_records(root)}))
    elif source == "ntis_reports":
        src = build_ntis_report_source(settings, transport=transport, resolver=resolver)
        root = await src._fetch_root(query, 1, count=rows)  # noqa: SLF001 - 녹화 전용
        from rra.adapters.sources._xml import find_records, local

        print("record_tag 후보:", sorted({local(r.tag) for r in find_records(root)}))
    else:
        src = build_ntis_source(settings, transport=transport, resolver=resolver)
        root = await src._fetch_root(query, 1, count=rows)  # noqa: SLF001 - 녹화 전용
        from rra.adapters.sources._xml import find_records, local

        print("record_tag 후보:", sorted({local(r.tag) for r in find_records(root)}))
    await src.aclose()

    secrets = secret_values(settings, transport.exchanges)
    out_dir = out_root / ("ntis" if source == "ntis_reports" else source)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d")
    saved: list[Path] = []
    for i, ex in enumerate(transport.exchanges):
        if ex["path"].endswith("tokenrequest.do"):
            path = out_dir / "token_shape.json"
            path.write_text(json.dumps(token_shape(ex["body"]), indent=2) + "\n", encoding="utf-8")
        else:
            kind = "report" if source == "ntis_reports" else (target or "project")
            name = f"{'ntis' if source == 'ntis_reports' else source}_{kind}_{stamp}_{i}"
            path = out_dir / f"{name}.xml"
            body = redact(ex["body"], secrets)
            if source == "scienceon":
                body = strip_person_names(body)
            elif source == "ntis":
                body = strip_ntis_names(body)
            path.write_bytes(body)
            meta = {
                "source": source,
                "query": query,
                "target": target,
                "rows": rows,
                "status": ex["status"],
                "content_type": ex["content_type"],
                "recorded_at": stamp,
            }
            (out_dir / f"{name}.meta.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            saved.append(path)
        print("저장:", path.name)
    return saved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser("record_fixture")
    parser.add_argument("source", choices=["scienceon", "ntis", "ntis_reports", "kipris"])
    parser.add_argument("--query", required=True)
    parser.add_argument("--target", help="ScienceON: ARTI | REPORT | PATENT")
    parser.add_argument("--rows", type=int, default=10)
    args = parser.parse_args(argv)
    asyncio.run(record(args.source, args.query, args.target, max(1, min(args.rows, 50))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
