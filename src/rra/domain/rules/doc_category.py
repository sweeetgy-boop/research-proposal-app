"""자료 분류 — 정책 근거가 될 수 있는 문서만 가려낸다 (2026-10-28 레인 B, ADR 0040).

공사 홈페이지 "정보공개 > 사전정보공표 > 사전정보공개목록" 은 한 메뉴 안에 성격이 다른 자료가 섞여
있다.
- 연구용역 목록(infoRelNo 55, 경영연구처·기술연구처 발주 연구 결과) — "레인보우 비경열차 관광수요
예측",
  "고속철도·일반여객 수송수요 예측" 같은 과제. 정책 자료가 아니라 **연구용역(사내 발주)** 이다.
- 경영계획·업무보고·경영평가 결과(IRTYP2) — 공사 경영목표·전략 → 정책 자료.
- 감사·청렴(IRTYP1)·법무(IRTYP3)·행정(IRTYP4)·정보화(IRTYP5) 공시 — 채용 친인척·법인카드·소송 판례
등
  **행정 공시**. 정책 근거가 아니다.
- 사업(IRTYP6) — 열차 소개·시설 현황 등 **사업 현황·소개**. 현황 근거일 뿐 정책 근거가 아니다
  (단, 안전보건 관리 계획·재해예방체계·안전관리등급 심사 결과는 정책 자료).

표현(ADR 0040):
- 연구용역(사내 발주) = doc_type ``procurement`` + ``raw.doc_class = "research_service"``.
procurement 는 이미
  유사과제 판정에 "용역" 티어로 들어가고(overlap_exclude 아님) 정책 근거에서는 빠진다. 화면 구분
  이름은
  "연구용역(사내 발주)".
- 행정 공시·사업 현황 = doc_type 은 그대로(policy), ``raw.doc_class`` 로만 가른다 — 정책 근거
추천·작성안에서
  빠진다(``is_policy_basis``). 섹션 근거 구성(retrieval_mix) 은 바꾸지 않는다.
- 통계자료 게시판(biz_stat_docs) = doc_type ``statistics`` (설정과 다르게 policy 로 적재된 옛 행).

규칙은 적재(korail_web normalize)와 기존 행 이주(``rra db reclassify``)가 같이 쓴다. raw.doc_class
가 없는 옛
행도 ``category_of`` 가 그 자리에서 판정하므로 이주 전에도 정책 근거 범위는 맞다.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from rra.domain.models import Document

# raw 에 저장하는 키 — raw.category 는 다른 자료원이 이미 다른 뜻(국토부 메뉴·사내 과제 종류)으로
# 쓴다
CLASS_KEY = "doc_class"

# ── 분류 이름 ──────────────────────────────────────────────
POLICY = "policy"
RESEARCH_SERVICE = "research_service"
ADMIN_RECORD = "admin_record"
STATUS = "status"
STATISTICS = "statistics"
AUDIT = "audit"
NOTICE = "notice"

CATEGORY_LABELS: dict[str, str] = {
    POLICY: "정책·전략 자료",
    RESEARCH_SERVICE: "연구용역(사내 발주)",
    ADMIN_RECORD: "행정 공시·규정",
    STATUS: "사업 현황·소개",
    STATISTICS: "통계",
    AUDIT: "감사·평가 지적",
    NOTICE: "정부 R&D 공고",
}
# 정책 근거(① 정책 근거 추천·③ 정책적 중요도 작성안)가 될 수 있는 분류
POLICY_BASIS_CATEGORIES: frozenset[str] = frozenset({POLICY, AUDIT, NOTICE})
# 정책 근거 자료원·자료 종류 — 작성안(policy_cards)과 추천(policy_suggest)이 같이 쓴다
POLICY_BASIS_SOURCES: tuple[str, ...] = ("molit", "rnd_notice", "korail_web", "bai", "mofe")
POLICY_BASIS_DOC_TYPES: frozenset[str] = frozenset({"policy", "rnd_notice", "audit"})

# ── 공사 홈페이지 사전정보공표 ────────────────────────────────
PREINFO_MENUS = frozenset({"preinfo"})
# infoRelNo — 연구용역 목록
PREINFO_RESEARCH_REL: frozenset[int] = frozenset({55})
# infoRelNo — 정책 자료 (경영실적 평가·기금 운용계획·부서별 주요계획·업무보고·예비타당성·경영목표
# 목표수준,
# 빅데이터 활용 계획, 안전관리등급 심사 결과, 산업안전보건 관리 계획, 산업재해 예방체계)
PREINFO_POLICY_REL: frozenset[int] = frozenset({34, 35, 36, 37, 39, 40, 47, 53, 106, 198, 232, 233})
# infoRelCategory — IRTYP2 경영 (연구용역 55 제외 나머지는 정책), IRTYP6 사업(현황), 그 밖은 행정
# 공시
_REL = re.compile(r"preinfo:(\d+)")
_REL_URL = re.compile(r"infoRelNo=(\d+)")
_REL_CAT = re.compile(r"infoRelCategory=(IRTYP\d)")
_RESEARCH_TITLE = re.compile(
    r"연구\s*$|연구\s*[(\[]|방안\s*연구|기술\s*개발|실용화|수요\s*예측|용역|타당성\s*(?:조사|분석|검토)"
)
_RULE_TITLE = re.compile(r"규정|세칙|세부기준|지침|절차서|가이드|수칙")

# ── 공사 홈페이지 다른 메뉴 ──────────────────────────────────
# 사업 현황·소개 (현황 근거 — 정책 근거 아님)
MENU_STATUS: frozenset[str] = frozenset(
    {
        "history",
        "env_kpi",
        "env_soil",
        "biz_pax_ops",
        "biz_metro_ops",
        "biz_stat",
        "biz_freight_ops",
        "biz_asset_stat",
        "biz_overseas_stat",
        "biz_maint_track",
        "biz_maint_civil",
        "biz_maint_bldg",
        "biz_maint_elec",
        "brochure",
        "preinfo_freq",
    }
)
# 행정 공시·규정·안내 (정책 근거 아님)
MENU_ADMIN: frozenset[str] = frozenset(
    {
        "winwin_guide",
        "contract_rules",
        "human_docs",
        "esg_bond",
        "safety_docs",
        "disclosure_general",
        "disclosure_ops",
        "disclosure_biz",
        "disclosure_eval",
    }
)
# doc_type 을 바로잡을 메뉴 (설정 korail_web.yaml 과 같은 값 — 옛 적재분)
MENU_DOC_TYPE: dict[str, str] = {"biz_stat_docs": "statistics"}
# 신사업자료실: 자체 검토·자문용역 보고서는 연구용역, 규정은 행정
MENU_STUDY: frozenset[str] = frozenset({"biz_newbiz"})
_STUDY_TITLE = re.compile(r"검토|구상|용역|타당성|분석")


def _rel_no(raw: Mapping[str, Any], url: str | None) -> int | None:
    m = _REL.match(str(raw.get("native_id") or ""))
    if m:
        return int(m.group(1))
    for u in (raw.get("page_url"), url):
        m = _REL_URL.search(str(u or ""))
        if m:
            return int(m.group(1))
    return None


def _rel_category(raw: Mapping[str, Any], url: str | None) -> str | None:
    for u in (raw.get("page_url"), url):
        m = _REL_CAT.search(str(u or ""))
        if m:
            return m.group(1)
    return None


def classify_korail(
    *,
    doc_type: str,
    title: str,
    raw: Mapping[str, Any],
    url: str | None = None,
) -> tuple[str, str | None]:
    """공사 홈페이지 문서 → (doc_type, category). 순수 함수. 보도자료·이미지 판독 문서는 그대로."""
    if doc_type in ("korail_news", "web_page"):
        return doc_type, None
    menu = str(raw.get("menu") or "")
    if menu in MENU_DOC_TYPE:
        fixed = MENU_DOC_TYPE[menu]
        return fixed, STATISTICS if fixed == "statistics" else None
    if doc_type == "statistics":
        return "statistics", STATISTICS
    names = " ".join(str(t) for t in (title, raw.get("parent_title") or "") if t)
    if menu in PREINFO_MENUS:
        rel = _rel_no(raw, url)
        if rel in PREINFO_RESEARCH_REL:
            return "procurement", RESEARCH_SERVICE
        if rel in PREINFO_POLICY_REL:
            return "policy", POLICY
        cat = _rel_category(raw, url)
        if cat == "IRTYP2" or (rel is None and cat is None):
            # 경영 분류(또는 출처를 모르는 옛 행): 제목으로 연구용역을 가린다
            if _RESEARCH_TITLE.search(names):
                return "procurement", RESEARCH_SERVICE
            return "policy", POLICY if cat == "IRTYP2" else ADMIN_RECORD
        if cat == "IRTYP6":
            return "policy", STATUS
        return "policy", ADMIN_RECORD
    if menu in MENU_STUDY:
        if _RULE_TITLE.search(names):
            return "policy", ADMIN_RECORD
        if _STUDY_TITLE.search(names):
            return "procurement", RESEARCH_SERVICE
        return "policy", STATUS
    if menu in MENU_STATUS:
        return "policy", STATUS
    if menu in MENU_ADMIN:
        return "policy", ADMIN_RECORD
    if doc_type == "procurement":
        return "procurement", RESEARCH_SERVICE
    return doc_type, POLICY if doc_type == "policy" else None


def classify(doc: Document) -> tuple[str, str | None]:
    """문서 → (바른 doc_type, category). korail_web 만 다시 판정, 나머지는 doc_type 그대로."""
    if doc.source == "korail_web":
        return classify_korail(doc_type=doc.doc_type, title=doc.title, raw=doc.raw, url=doc.url)
    return doc.doc_type, _default_category(doc.doc_type)


def _default_category(doc_type: str) -> str | None:
    return {
        "policy": POLICY,
        "audit": AUDIT,
        "rnd_notice": NOTICE,
        "statistics": STATISTICS,
    }.get(doc_type)


def category_of(doc: Document) -> str | None:
    """저장된 raw.doc_class, 없으면 그 자리에서 판정(이주 전 옛 행)."""
    stored = doc.raw.get(CLASS_KEY) if isinstance(doc.raw, Mapping) else None
    if isinstance(stored, str) and stored in CATEGORY_LABELS:
        return stored
    return classify(doc)[1]


def is_policy_basis(doc: Document) -> bool:
    """정책 근거가 될 수 있는 문서 — 정책 자료원 · 정책 종류(doc_type) · 정책 분류(category) 셋 다.

    ① 정책 근거 추천(policy_suggest) 과 ③ 정책적 중요도 작성안(policy_cards) 이 같이 쓴다."""
    if doc.source not in POLICY_BASIS_SOURCES:
        return False
    doc_type, category = classify(doc) if doc.source == "korail_web" else (doc.doc_type, None)
    if doc_type not in POLICY_BASIS_DOC_TYPES:
        return False
    stored = doc.raw.get(CLASS_KEY) if isinstance(doc.raw, Mapping) else None
    category = stored if isinstance(stored, str) and stored in CATEGORY_LABELS else category
    category = category or _default_category(doc_type)
    return category in POLICY_BASIS_CATEGORIES


def category_label(doc_type: str, category: str | None) -> str | None:
    """화면 구분 이름 — 연구용역(사내 발주) 등. 모르면 None."""
    if category and category in CATEGORY_LABELS:
        return CATEGORY_LABELS[category]
    return None
