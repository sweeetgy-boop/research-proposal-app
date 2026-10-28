"""[23] 그림 단계 본문 폭 맞춤 — 가로 비율, 높이 상한 → 넓은 비율로 다시 그림, 글자 하한 → 글자
줄여 다시
그림, OCR 로 잰 Nano Banana 글자가 작으면 한 번 더, 4:1 은 21:9 로 생성 뒤 맞춤, 제안자 글자는
줄이지 않음."""

from xml.sax.saxutils import escape

from rra.application.usecases.figures import FigureConfig, MakeFigures
from rra.domain.models.figure import Figure, parse_spec
from rra.domain.models.vision import OcrLine, OcrResult
from rra.domain.rules import figure_fit as fit
from rra.domain.rules.figures import texts_of
from tests.fakes import FakeImageGenerator, FakePromptLibrary
from tests.figure_v2_helpers import AS_IS, CATALOG, RoutingLLM


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


def make(renderer, *, images=None, ocr=None, reframe=None, **cfg):
    return MakeFigures(
        RoutingLLM(),
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


async def test_small_text_shortens_labels_and_redraws_until_readable():
    renderer = SizedRenderer(limit=16)
    uc = make(renderer)
    build = uc.baseline(as_is_figure())
    f = build.figure.fit
    assert f.text_ok and f.shortened >= 1 and f.redraws >= 1
    assert max(len(t) for t in texts_of(build.figure.spec)) <= 16
    longest = [n for _a, n in renderer.calls]
    assert longest[0] > 16 and longest[-1] <= 16  # 처음엔 작았고 줄인 뒤 다시 그렸다
    for t in texts_of(build.figure.spec):  # 줄인 글자도 원래 글자의 앞부분
        assert any(o.startswith(t) for o in texts_of(as_is_figure().spec))


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
    build = uc.baseline(as_is_figure())
    f = build.figure.fit
    assert f.ratio == "21:9" and f.widened and f.fits and f.redraws >= 1


async def test_proposer_text_edits_are_not_shortened_only_recorded():
    uc = make(SizedRenderer(limit=16), images=FakeImageGenerator())
    fig = as_is_figure()
    build = await uc.draw(fig, shorten=False)
    assert build.figure.spec == fig.spec  # 제안자가 고친 글자는 그대로
    assert build.figure.fit.text_ok is False and build.figure.fit.shortened == 0


async def test_ocr_small_text_on_nano_banana_image_redraws_once_bigger_without_cutting_words():
    images = FakeImageGenerator()
    ocr = FakeOcr([0.02, 0.06])  # 첫 그림 "현황" 이 밑그림의 0.4배(≈4pt) → 다시 그린 그림은 1.2배
    uc = make(SizedRenderer(limit=100), images=images, ocr=ocr, reframe=lambda d, m, a, r: (d, m))
    four = {**AS_IS, "as_is": [*AS_IS["as_is"], AS_IS["as_is"][0]]}
    fig = as_is_figure(four)
    build = await uc.draw(fig)
    f = build.figure
    assert len(images.calls) == 2 and f.calls == 2 and ocr.calls == 2
    assert "글자를 더 크게" in images.calls[1]["prompt"] and "약 4.0pt" in images.calls[1]["prompt"]
    assert f.fit.text_method == "ocr" and f.fit.text_ok and f.fit.redraws == 1
    assert f.spec == fig.spec and f.fit.shortened == 0  # 글자(내용)는 그대로


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
    assert len(images.calls) == 2 and build.figure.fit.text_ok is False


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
    build = await uc.draw(as_is_figure(short))
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
