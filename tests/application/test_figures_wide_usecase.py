"""[23] 그림 단계 본문 폭 맞춤 — 가로 비율, 높이 상한 → 넓은 비율로 다시 그림, 글자 하한 → 칸
글자를 다시 써서(잘라 줄이지 않는다, 2026-10-29 ADR 0044) 다시 그림, OCR 로 잰 Nano Banana 글자가
작으면 한 번 더(max_image_redraws 1), 4:1 은 21:9 로 생성 뒤 맞춤, 제안자 글자는 다시 쓰지 않음."""

from xml.sax.saxutils import escape

from rra.application.usecases.figures import FigureConfig, MakeFigures
from rra.domain.models.figure import Figure, parse_spec
from rra.domain.models.vision import OcrLine, OcrResult
from rra.domain.rules import figure_fit as fit
from rra.domain.rules import figure_phrases as phrases
from rra.domain.rules.figures import texts_of
from tests.fakes import FakeImageGenerator, FakePromptLibrary
from tests.figure_v2_helpers import AS_IS, CATALOG, RoutingLLM, rewrite_rows

# 긴 칸 글자(상한 20자 안, 다시 쓰기 상한 15자 밖) — 시범에서 9pt 밑으로 그려진 길이
LONG_AS_IS = {
    **AS_IS,
    "as_is": [
        {"tag": "현황", "text": "궤도 틀림이 구간마다 반복 발생함"},
        {"tag": "원인", "text": "다짐 효과가 오래 가지 않음"},
        {"tag": "한계", "text": "진행 속도를 반영하지 못함"},
    ],
}


class SizedRenderer:
    """글자 길이에 따라 글자 크기를 정하는 가짜 밑그림 — 가장 긴 글자가 limit 를 넘으면 small
    단위."""

    def __init__(
        self, *, limit: int = 16, small: float = 28.0, big: float = 37.0, cramped: tuple = ()
    ):
        self.limit, self.small, self.big = limit, small, big
        self.cramped = set(cramped)  # 이 비율에서는 글자가 늘 작다 (칸 높이가 모자람)
        self.calls: list[tuple[str, int]] = []

    def svg(self, spec, *, caption="", aspect=None):
        longest = max(len(t) for t in texts_of(spec))
        self.calls.append((aspect, longest))
        size = self.small if longest > self.limit or aspect in self.cramped else self.big
        body = "".join(f'<text font-size="{size:.1f}">{escape(t)}</text>' for t in texts_of(spec))
        return f'<svg xmlns="http://www.w3.org/2000/svg" data-overflow="0">{body}</svg>'

    def png(self, svg):
        return b"PNG" + str(len(svg)).encode()


class FakeOcr:
    """밑그림(PNG…)에서는 "현황" 줄 높이 base, 생성 그림(NB:…)에서는 heights 를 차례로."""

    engine = "fake"

    def __init__(self, heights: list[float], *, base: float = 0.05):
        self.heights = list(heights)
        self.base = base
        self.calls = 0  # 생성 그림 OCR 횟수

    async def recognize(self, image, *, mime=None):
        if bytes(image).startswith(b"PNG"):
            h = self.base
        else:
            h = self.heights[min(self.calls, len(self.heights) - 1)]
            self.calls += 1
        return OcrResult(lines=[OcrLine(text="현황", confidence=0.9, box=[0.1, 0.1, 0.3, h])])


def make(renderer, *, images=None, ocr=None, reframe=None, llm=None, **cfg):
    return MakeFigures(
        llm or RoutingLLM(),
        FakePromptLibrary(),
        renderer,
        images=images,
        ocr=ocr,
        reframe=reframe,
        pad_reference=(lambda data, aspect: b"PAD" + aspect.encode() + data) if reframe else None,
        config=FigureConfig(**cfg),
        catalog=CATALOG,
    )


def as_is_figure(data=None) -> Figure:
    spec = parse_spec("as_is_to_be", data or AS_IS)
    return Figure(id="f:objective:1", kind="as_is_to_be", section="objective", spec=spec)


async def test_baseline_fit_is_recorded_at_body_width():
    uc = make(SizedRenderer(limit=100))
    build = uc.baseline(as_is_figure())
    f = build.figure.fit
    assert f is not None and f.ratio in ("16:9", "21:9") and f.width_mm == 153.8
    assert f.fits and f.text_ok and f.min_text_pt == round(fit.font_pt(37, 153.8), 1)
    assert f.text_method == "svg" and f.redraws == 0 and f.shortened == 0


async def test_tries_the_taller_wide_ratio_before_cutting_words():
    renderer = SizedRenderer(limit=100, cramped=("21:9",))
    short = {
        **AS_IS,
        "as_is": [{**it, "text": it["text"][:12]} for it in AS_IS["as_is"]],
        "to_be": [{**it, "text": it["text"][:12]} for it in AS_IS["to_be"]],
    }
    uc = make(renderer)
    build = uc.baseline(as_is_figure(short))
    assert [a for a, _n in renderer.calls] == ["21:9", "16:9"]  # 글자를 자르기 전에 16:9 로
    f = build.figure.fit
    assert f.ratio == "16:9" and f.text_ok and f.shortened == 0 and f.redraws == 1


async def test_height_over_page_third_redraws_with_wider_ratio():
    uc = make(SizedRenderer(limit=100), frame=fit.BodyFrame(153.8, 200.0))  # 상한 66.7mm
    four = {**AS_IS, "as_is": [*AS_IS["as_is"], AS_IS["as_is"][0]]}  # 4칸 → 16:9 로 시작
    build = uc.baseline(as_is_figure(four))
    f = build.figure.fit
    assert f.ratio == "21:9" and f.widened and f.fits and f.redraws >= 1


async def test_proposer_text_edits_are_not_shortened_only_recorded():
    uc = make(SizedRenderer(limit=16), images=FakeImageGenerator())
    fig = as_is_figure()
    build = await uc.draw(fig, shorten=False)
    assert build.figure.spec == fig.spec  # 제안자가 고친 글자는 그대로
    assert build.figure.fit.text_ok is False and build.figure.fit.shortened == 0


async def test_ocr_small_text_stops_after_max_image_redraws():
    images = FakeImageGenerator()
    uc = make(
        SizedRenderer(limit=100),
        images=images,
        ocr=FakeOcr([0.01]),
        reframe=lambda d, m, a, r: (d, m),
        max_image_redraws=1,
    )
    build = await uc.draw(as_is_figure())
    assert len(images.calls) == 2 and build.figure.fit.text_ok is False  # 다시 그리기 1회까지


def test_short_tags_pass_validation_and_render_bigger():
    from rra.adapters.figures.render import F_SMALL, F_TAG_SHORT
    from rra.domain.rules import figures as rules
    from tests.domain.test_figures_v2_rules import pool_for

    short, n = fit.shorten_tags(as_is_figure().spec)
    assert n == 2 and fit.shorten_tags(short) is None
    pool = pool_for()
    assert rules.SIDE_TAG not in rules.validate_spec(short, pool)
    assert rules.repair_spec(short, pool).to_be[1].tag == "방안"  # 다듬기가 되돌리지 않는다
    assert F_TAG_SHORT > F_SMALL and fit.font_pt(F_TAG_SHORT, 153.8) >= 10


async def test_without_ocr_the_baseline_estimate_is_kept():
    uc = make(SizedRenderer(limit=100), images=FakeImageGenerator())
    build = await uc.draw(as_is_figure())
    assert build.figure.renderer == "nano_banana" and build.figure.fit.text_method == "baseline"


async def test_4_to_1_schedule_is_generated_at_21_9_and_reframed():
    images = FakeImageGenerator()
    seen: list[str] = []

    def reframe(data, mime, aspect, min_ratio):
        seen.append(aspect)
        assert min_ratio == 21 / 9  # 일정표는 21:9 보다 좁게 채우지 않는다
        return data, mime

    spec = parse_spec(
        "schedule",
        {
            "total_months": 24,
            "stages": [
                {"name": "현황 분석", "start_month": 1, "end_month": 6},
                {"name": "현장 실증", "start_month": 7, "end_month": 24},
            ],
        },
    )
    fig = Figure(id="f:method:1", kind="schedule", section="method", spec=spec)
    uc = make(SizedRenderer(limit=100), images=images, reframe=reframe)
    build = await uc.draw(fig)
    call = images.calls[0]
    assert call["aspect"] == "21:9" and seen == ["4:1"]
    assert "가로 4:1 띠 안에만" in call["prompt"] and "좌우 여백 최소" in call["prompt"]
    assert build.figure.fit.ratio == "4:1" and build.figure.fit.height_mm == round(153.8 / 4, 1)


async def test_prompt_asks_for_horizontal_layout_per_technique_arrangement():
    swot = parse_spec(
        "technique",
        {
            "technique": "swot",
            "title": "SWOT 분석",
            "groups": [
                {"name": n, "items": [{"text": "항목", "rating": "상"}]}
                for n in ("강점", "약점", "기회", "위협")
            ],
        },
    )
    from rra.domain.rules.figures import image_prompt

    p = image_prompt(swot, arrange="row")
    assert "가로 한 줄에 나란히" in p and "세로로 쌓지 않는다" in p
    cb = swot.model_copy(update={"groups": swot.groups[:2]})
    assert "왼쪽·오른쪽 두 단" in image_prompt(cb, arrange="split")
    assert "오른쪽 화살표로 잇는다" in image_prompt(swot, arrange="flow")
    six = swot.model_copy(update={"groups": swot.groups + swot.groups[:2]})
    assert "가로 두 줄" in image_prompt(six, arrange="row")  # 5개 이상은 두 줄


async def test_small_text_without_anything_to_shorten_asks_for_bigger_text_once():
    images = FakeImageGenerator()
    short = {
        **AS_IS,
        "as_is": [{**it, "text": it["text"][:8]} for it in AS_IS["as_is"]],
        "to_be": [{**it, "text": it["text"][:8]} for it in AS_IS["to_be"]],
        "solution": AS_IS["solution"][:8],
    }
    uc = make(
        SizedRenderer(limit=100),
        images=images,
        ocr=FakeOcr([0.02, 0.05]),
        reframe=lambda d, m, a, r: (d, m),
    )
    fig = as_is_figure(short)
    fig = fig.model_copy(update={"spec": fit.shorten_tags(fig.spec)[0]})  # 이름표도 이미 두 글자
    build = await uc.draw(fig)
    assert len(images.calls) == 2
    assert (
        "글자를 더 크게" in images.calls[1]["prompt"]
        and "글자를 더 크게" not in images.calls[0]["prompt"]
    )
    f = build.figure.fit
    assert f.text_ok and f.redraws == 1 and f.shortened == 0 and f.text_method == "ocr"


async def test_pixel_size_of_generated_image_updates_height_and_ratio():
    uc = make(
        SizedRenderer(limit=100),
        images=FakeImageGenerator(),
        reframe=lambda d, m, a, r: (d, m),
    )
    uc.image_size = lambda data: (2000, 1000)  # 흰 여백을 자른 뒤 2:1
    build = await uc.draw(as_is_figure())
    f = build.figure.fit
    assert f.ratio == "2.00:1" and f.height_mm == round(153.8 / 2, 1) and f.fits


# ── 2026-10-29 ADR 0044: 잘라 줄이지 않고 다시 쓴다 ─────────────────────────────
def _is_whole_words_of(new: str, old: str) -> bool:
    """new 의 낱말이 모두 old 의 온전한 낱말(끝 낱말만 조사·어미를 덜 수 있다)인가."""
    old_words = old.split()
    toks = new.split()
    return all(
        t in old_words or (i == len(toks) - 1 and any(w.startswith(t) for w in old_words))
        for i, t in enumerate(toks)
    )


async def test_small_baseline_text_is_rewritten_by_argon_not_cut():
    """밑그림 글자가 작으면 칸 글자를 잘라 줄이지 않고 Argon 에게 상한 −25% 안의 완결 구절로 다시
    쓰게 한 뒤 밑그림부터 다시 그린다. 이름표(해결 방안·기대효과)는 두 글자로."""
    llm = RoutingLLM()
    renderer = SizedRenderer(limit=15)
    uc = make(renderer, llm=llm)
    fig = as_is_figure(LONG_AS_IS)
    build = await uc.draw(fig)
    f = build.figure
    calls = llm.prompts_for("[그림 글자 다시 쓰기: as_is_to_be]")
    assert len(calls) == 1
    rows = rewrite_rows(calls[0])
    assert {r["상한"] for r in rows} == {15, 10}  # 20·14자 × 0.75
    assert "뜻이 완결된 짧은 구절" in calls[0] and "잘라" in calls[0]
    assert f.fit.text_ok and f.fit.shortened >= 1 and f.fit.redraws >= 1
    before = {it["text"] for it in LONG_AS_IS["as_is"]}
    for it in f.spec.as_is:
        assert len(it.text) <= 15 and phrases.is_complete(it.text)
        if it.text not in before:  # 다시 쓴 칸 — 원래 글자의 온전한 낱말로만
            orig = next(o for o in before if _is_whole_words_of(it.text, o))
            assert orig
    assert [it.tag for it in f.spec.to_be] == ["목표", "방안", "효과"]
    assert renderer.calls[-1][1] <= 15  # 다시 그린 밑그림은 다시 쓴 글자로


async def test_ocr_small_text_rewrites_box_text_and_redraws_once():
    """그림 글자가 9pt 밑이면 Argon 이 다시 쓴 글자로 밑그림부터 다시 그리고 "글자를 더 크게" —
    다시 그리기는 기본 1회(max_image_redraws 2 → 1)."""
    answer = {
        "texts": [
            {"path": "as_is.0.text", "value": "궤도 틀림 반복 발생"},
            {"path": "to_be.0.text", "value": "보수 우선순위 산정"},
            {"path": "solution", "value": "진행 속도 추정"},
        ]
    }
    llm = RoutingLLM(rewrites={"as_is_to_be": answer})
    images = FakeImageGenerator()
    ocr = FakeOcr([0.02, 0.02, 0.06])  # 다시 그려도 작다 — 그래도 1회까지만
    uc = make(
        SizedRenderer(limit=100), images=images, ocr=ocr, reframe=lambda d, m, a, r: (d, m), llm=llm
    )
    assert uc.config.max_image_redraws == 1
    build = await uc.draw(as_is_figure(LONG_AS_IS))
    f = build.figure
    assert len(images.calls) == 2 and f.calls == 2
    assert "글자를 더 크게" in images.calls[1]["prompt"]
    assert len(llm.prompts_for("[그림 글자 다시 쓰기: as_is_to_be]")) == 1
    assert f.spec.as_is[0].text == "궤도 틀림 반복 발생"  # 모델이 다시 쓴 완결 구절 그대로
    assert f.spec.to_be[0].text == "보수 우선순위 산정"
    assert "- 궤도 틀림 반복 발생" in images.calls[1]["prompt"]  # 다시 그린 그림에 새 글자
    assert f.fit.shortened >= 1 and f.fit.text_ok is False  # 작으면 기록 (카드 안내)


async def test_rewrite_that_cuts_a_phrase_is_corrected_then_kept_whole():
    """다시 쓴 글자가 끊긴 구절이면 교정 재요청, 그래도 끊기면 그 칸의 온전한 낱말 묶음 —
    출처에 없는 낱말을 쓴 칸은 원래 글자 그대로 둔다. 낱말을 자르지 않는다."""
    bad = {
        "texts": [
            {"path": "as_is.0.text", "value": "궤도 틀림이 구간마다"},  # 끊김 (…마다)
            {"path": "as_is.1.text", "value": "다짐 효과 단기 소멸"},  # 출처 밖 낱말
        ]
    }
    llm = RoutingLLM(rewrites={"as_is_to_be": bad})
    uc = make(SizedRenderer(limit=15), llm=llm)
    build = await uc.draw(as_is_figure(LONG_AS_IS))
    calls = llm.prompts_for("[그림 글자 다시 쓰기: as_is_to_be]")
    assert len(calls) == 2 and "끝맺지 않은 구절" in calls[1]  # 교정 재요청이 이유를 알려 준다
    f = build.figure
    texts = [it.text for it in f.spec.as_is]
    assert all(phrases.is_complete(t) for t in texts)
    assert texts[0] != "궤도 틀림이 구간마다"
    assert _is_whole_words_of(texts[0], LONG_AS_IS["as_is"][0]["text"])
    assert "다짐 효과 단기 소멸" not in texts


async def test_short_texts_are_not_sent_for_rewrite():
    """이미 다시 쓰기 상한 안이면 Argon 을 부르지 않는다(글자가 커지지 않는다) — "글자를 더
    크게" 만."""
    llm = RoutingLLM()
    images = FakeImageGenerator()
    short = {
        **AS_IS,
        "as_is": [{**it, "text": "궤도 틀림"} for it in AS_IS["as_is"]],
        "to_be": [{**it, "text": "보수 우선순위"} for it in AS_IS["to_be"]],
        "solution": "진행 속도 추정",
    }
    uc = make(
        SizedRenderer(limit=100),
        images=images,
        ocr=FakeOcr([0.02, 0.05]),
        reframe=lambda d, m, a, r: (d, m),
        llm=llm,
    )
    fig = as_is_figure(short)
    fig = fig.model_copy(update={"spec": fit.shorten_tags(fig.spec)[0]})
    await uc.draw(fig)
    assert llm.prompts_for("[그림 글자 다시 쓰기") == [] and len(images.calls) == 2


async def test_proposer_request_words_are_protected_from_rewrite():
    llm = RoutingLLM()
    uc = make(SizedRenderer(limit=15), llm=llm)
    fig = as_is_figure(LONG_AS_IS)
    keep = LONG_AS_IS["as_is"][0]["text"]
    build = await uc.draw(fig, protect=(f"현황 칸을 '{keep}' 로",))
    assert build.figure.spec.as_is[0].text == keep  # 제안자가 적은 글자는 그대로
    rows = rewrite_rows(llm.prompts_for("[그림 글자 다시 쓰기")[0])
    assert "as_is.0.text" not in {r["path"] for r in rows}
