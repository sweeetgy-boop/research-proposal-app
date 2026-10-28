"""e2e·스키마 추출용 가짜 어댑터 (RRA_FAKE_LLM=1). 모델·DB·네트워크 없이 결정적 결과를 낸다.

운영에서는 절대 조립되지 않는다 — composition 이 settings.fake_llm 일 때만 끼우고 기동 시 경고를
크게 낸다.
tests/fakes.py 의 fake 와 같은 역할이지만 패키지 안에 있어 설치본에서도 돈다.
"""

from rra.adapters.fake.auth import ScriptedAuthStore
from rra.adapters.fake.figures import FakeImageGenerator
from rra.adapters.fake.live import FakeLiveSource, fake_live_sources
from rra.adapters.fake.llm import ScriptedComposeLLM, ScriptedReviewLLM
from rra.adapters.fake.ntis import ScriptedNtisInsights
from rra.adapters.fake.stores import InMemoryDocumentRepository, InMemoryRunStore, NoopRunLog

__all__ = [
    "FakeImageGenerator",
    "FakeLiveSource",
    "fake_live_sources",
    "ScriptedAuthStore",
    "InMemoryDocumentRepository",
    "InMemoryRunStore",
    "NoopRunLog",
    "ScriptedComposeLLM",
    "ScriptedNtisInsights",
    "ScriptedReviewLLM",
]
