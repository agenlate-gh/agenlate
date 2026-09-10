"""Provider access.

Import from here rather than reaching into submodules, so the seam stays
visible: everything above depends on LLMClient, not on any provider.
"""

from .base import LLMClient, LLMError, LLMResponse, Usage
from .fake import FakeLLM, ScriptExhausted
from .openrouter import OpenRouterClient

__all__ = [
    "FakeLLM",
    "LLMClient",
    "LLMError",
    "LLMResponse",
    "OpenRouterClient",
    "ScriptExhausted",
    "Usage",
]
