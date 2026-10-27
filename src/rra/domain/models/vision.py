"""이미지 판독(P3) 값 객체. 전부 비신뢰 데이터 — 웹 페이지 이미지·OCR·LLM 출력에서 온다.

ImageItem   크롤 스냅샷 manifest 의 이미지 한 건 (docs/vision-manifest.md).
OcrResult   macOS Vision 줄 단위 인식 결과 (대조용).
VisionReading  Argon(LLM) 판독 JSON 을 검증해 담은 것. 숫자는 OCR 대조 뒤에만 근거가 된다.
ImageReadResult  이미지 하나의 최종 결과 — argon / ocr_only / failed / skipped.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

IMAGE_TYPES = ("체계도·조직도·흐름도", "표", "그래프", "글자 이미지", "기타")
ImageType = Literal["체계도·조직도·흐름도", "표", "그래프", "글자 이미지", "기타"]
ReadStatus = Literal["argon", "ocr_only", "failed", "skipped"]
# 처리 순서 그룹 — 경영목표·전략·비전 > ESG·정책 > 통계 > 보도자료 > 기타 (config/vision.yaml order)
OrderGroup = Literal["strategy", "esg_policy", "statistics", "press", "other"]
ORDER_GROUPS: tuple[OrderGroup, ...] = ("strategy", "esg_policy", "statistics", "press", "other")

MAX_TEXT_CHARS = 20_000
MAX_TITLE_CHARS = 300
MAX_SUMMARY_CHARS = 2_000


class ImageItem(BaseModel):
    """스냅샷 manifest 의 이미지 한 건. path 는 스냅샷 폴더 기준 상대 경로."""

    sha256: str
    path: str
    url: str | None = None  # 원본 이미지 URL
    page_url: str | None = None  # 이미지가 실린 페이지
    page_title: str | None = None
    page_doc_id: str | None = None  # 적재된 페이지 문서 id (있으면 raw.image.page_doc_id)
    alt: str | None = None
    caption: str | None = None
    width: int | None = None
    height: int | None = None
    bytes: int | None = None
    mime: str | None = None
    order_group: OrderGroup | None = None  # manifest 가 주면 우선, 없으면 page_url·title 로 판정
    source: str = "korail_web"
    repeat_pages: int = 1  # 같은 sha256 이 실린 페이지 수 (manifest 전체에서 센다)
    trust: Literal["untrusted"] = "untrusted"


class OcrLine(BaseModel):
    text: str
    confidence: float = Field(ge=0.0, le=1.0)
    box: list[float] | None = None  # [x, y, w, h] 0~1 정규화 (Vision 좌표)


class OcrResult(BaseModel):
    lines: list[OcrLine] = Field(default_factory=list)
    engine: str = "macos_vision"
    languages: list[str] = Field(default_factory=lambda: ["ko-KR", "en-US"])
    elapsed_sec: float | None = None

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)


class VisionReading(BaseModel):
    """LLM 판독 JSON (검증 후). structure 는 image_type 별 자유 구조 — 수치는 OCR 대조 전엔
    참고용."""

    image_type: ImageType = "기타"
    title: str = Field(default="", max_length=MAX_TITLE_CHARS)
    text: str = Field(default="", max_length=MAX_TEXT_CHARS)
    structure: dict[str, Any] = Field(default_factory=dict)
    summary: str = Field(default="", max_length=MAX_SUMMARY_CHARS)
    uncertain: bool = False
    trust: Literal["untrusted"] = "untrusted"


class ImageReadResult(BaseModel):
    sha256: str
    status: ReadStatus
    item: ImageItem
    ocr: OcrResult | None = None
    ocr_error: str | None = None  # OcrUnavailable 등 클래스명만
    reading: VisionReading | None = None
    vision_error: str | None = None  # 클래스명·짧은 코드만 (본문·키 금지)
    confirmed_numbers: list[str] = Field(default_factory=list)  # OCR 에도 있는 수치 표기
    unconfirmed_numbers: list[str] = Field(default_factory=list)  # "판독 확인 필요"
    cached: bool = False  # vision_cache 적중 (호출 없음)
    elapsed_sec: float | None = None

    @property
    def needs_check(self) -> bool:
        return bool(self.unconfirmed_numbers) or bool(self.reading and self.reading.uncertain)
