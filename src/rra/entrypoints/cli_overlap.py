"""레인 E CLI 서브명령 — `rra db idf`(말뭉치 IDF 표 만들기)·`rra terms review`(동의어 검토표).

cli.py 는 공용 파일이라 여기 두고, 통합 때 메인이 cli.py 에 다음 두 줄을 붙인다(PR 본문 "통합 때
메인이
반영할 조립 변경"):

    from rra.entrypoints.cli_overlap import register_db, register_terms
    register_db(db_sub)        # `db = sub.add_parser("db", …)` 의 db_sub 뒤
    register_terms(terms_sub)  # `terms = sub.add_parser("terms", …)` 의 terms_sub 뒤

출력은 건수·경로만(본문·키 없음).
"""

from __future__ import annotations

import argparse
import asyncio

EXIT_OK = 0


def cmd_db_idf(args: argparse.Namespace) -> int:
    """저장소 청크를 훑어 IDF 표를 `data/cache/idf.json` 에 쓴다 (읽기만, DB 수정 없음)."""
    from rra.composition import build_idf, load_settings

    settings = load_settings()
    usecase, path = build_idf(settings)
    report = asyncio.run(usecase())
    print(
        f"IDF 표: 문서 {report.documents:,}건 / 청크 {report.chunks:,}개 → 토큰 {report.terms:,}개 "
        f"(max_idf {report.max_idf:.2f}) → {path}"
    )
    print("스위치 overlap.yaml idf_weighting.enabled 가 true 일 때만 판정에 쓰인다 (기본 false).")
    return EXIT_OK


def cmd_terms_review(args: argparse.Namespace) -> int:
    """용어 후보 두 파일 → 동의어 검토표 + overlap.yaml synonyms.candidates 구역 (스위치는 안
    건드린다)."""
    from rra.composition import build_terms_review, load_settings

    usecase = build_terms_review(
        load_settings(), review_path=args.out, candidates_dir=args.candidates_dir
    )
    report = usecase()
    print(
        f"후보 행 {report.rows}건 → 묶음 {report.reviews}건 (고신뢰 {report.high} · "
        f"검토 필요 {report.reviews - report.high})"
    )
    print(f"  검토표: {report.review_path}")
    print(f"  후보 구역: {report.candidates_path} (synonyms.candidates — 검토 전, 운영 반영 안 함)")
    print("synonyms.enabled 는 사람이 검토표를 확인한 뒤에만 켠다.")
    return EXIT_OK


def register_db(db_sub) -> None:
    idf = db_sub.add_parser(
        "idf", help="말뭉치 IDF 표 만들기 → data/cache/idf.json (유사과제 핵심어 가중, ADR 0059)"
    )
    idf.set_defaults(handler=cmd_db_idf)


def register_terms(terms_sub) -> None:
    rv = terms_sub.add_parser(
        "review",
        help="동의어 후보 검토표(docs/review/terms-review.md) + overlap.yaml 후보 구역 (ADR 0059)",
    )
    rv.add_argument("--out", default=None, help="검토표 경로 (기본 docs/review/terms-review.md)")
    rv.add_argument(
        "--candidates-dir",
        default=None,
        help="*.candidates.yaml 이 있는 폴더 (기본 config/; worktree 에서는 원 저장소 config/)",
    )
    rv.set_defaults(handler=cmd_terms_review)


def main(argv: list[str] | None = None) -> int:
    """독립 실행(통합 전): `python -m rra.entrypoints.cli_overlap db idf | terms review`."""
    ap = argparse.ArgumentParser(prog="rra-overlap")
    sub = ap.add_subparsers(dest="cmd", required=True)
    db = sub.add_parser("db")
    register_db(db.add_subparsers(dest="db_cmd", required=True))
    terms = sub.add_parser("terms")
    register_terms(terms.add_subparsers(dest="terms_cmd", required=True))
    args = ap.parse_args(argv)
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
