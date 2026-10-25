from collections.abc import Callable

from schema_scout.config import ConfigError, LlmConfig
from schema_scout.llm.base import LlmClient


def _anthropic(config: LlmConfig) -> LlmClient:
    from schema_scout.llm.anthropic_client import AnthropicClient

    return AnthropicClient(config)


def _openai(config: LlmConfig) -> LlmClient:
    from schema_scout.llm.openai_client import OpenAiClient

    return OpenAiClient(config)


# provider name -> (builder, pip extra that provides its SDK)
_PROVIDERS: dict[str, tuple[Callable[[LlmConfig], LlmClient], str]] = {
    "anthropic": (_anthropic, "anthropic"),
    "openai": (_openai, "openai"),
}


def available_providers() -> list[str]:
    return sorted(_PROVIDERS)


def create_llm_client(config: LlmConfig) -> LlmClient:
    """Build the client for `config.provider`. To add a provider, subclass LlmClient and register it here."""
    try:
        builder, extra = _PROVIDERS[config.provider.lower()]
    except KeyError:
        raise ConfigError(
            f"Unknown llm.provider {config.provider!r}; available: {', '.join(available_providers())}"
        ) from None
    try:
        return builder(config)
    except ImportError as e:
        raise ConfigError(
            f'Provider {config.provider!r} needs its SDK: pip install -e ".[{extra}]" ({e})'
        ) from e
