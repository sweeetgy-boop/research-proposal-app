"""VisionReaderPort 구현 — OpenAI 호환 chat/completions 에 이미지(data URL) 를 함께 보낸다.

OpenAICompatLLM 과 같은 엔드포인트 검증(보안 C·H)·키 마스킹·재시도·JSON 모드·공유 제한기를 그대로
쓴다.
이미지는 base64 data URL 로만 보낸다(원격 URL 을 LLM 에 넘기지 않는다). 바이트·MIME 상한은
생성자에서.
"""

from __future__ import annotations

import base64

from rra.adapters.llm import _payload
from rra.adapters.llm.errors import LLMError
from rra.adapters.llm.openai_compat import OpenAICompatLLM

ALLOWED_MIME = frozenset({"image/png", "image/jpeg", "image/webp"})
DEFAULT_MAX_IMAGE_BYTES = 8 * 1024 * 1024


class OpenAICompatVisionReader(OpenAICompatLLM):
    def __init__(self, *args, max_image_bytes: int = DEFAULT_MAX_IMAGE_BYTES, **kw):
        super().__init__(*args, **kw)
        self.max_image_bytes = max_image_bytes

    async def read_image(
        self,
        prompt: str,
        image: bytes,
        *,
        mime: str,
        system: str | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
    ) -> str:
        if mime not in ALLOWED_MIME:
            raise LLMError(f"지원하지 않는 이미지 형식입니다: {mime}")
        if not image:
            raise LLMError("빈 이미지는 보내지 않습니다.")
        if len(image) > self.max_image_bytes:
            raise LLMError(
                f"이미지 {len(image)} 바이트 > 상한 {self.max_image_bytes}. 전송하지 않았습니다."
            )
        if len(prompt) > self.prompt_max_chars:
            raise LLMError(
                f"프롬프트 길이 {len(prompt)} > 상한 {self.prompt_max_chars}. 전송하지 않았습니다."
            )
        data_url = f"data:{mime};base64,{base64.b64encode(image).decode('ascii')}"

        def make(system_text: str | None):
            return _payload.build_image_messages(
                prompt, data_url, system_text, system_role=self.system_role
            )

        return await self._complete_with(
            make, system=system, max_tokens=max_tokens, json_mode=json_mode
        )
