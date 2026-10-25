from dataclasses import dataclass

from dynaconf import Dynaconf
from sqlalchemy.engine import URL


class ConfigError(RuntimeError):
    """Raised when required configuration is missing."""


@dataclass(frozen=True)
class DatabaseConfig:
    """A SQLAlchemy URL assembled from `database.*` settings plus the password from the environment."""

    url: URL

    @classmethod
    def from_settings(cls, settings: Dynaconf, catalog: str | None = None) -> "DatabaseConfig":
        drivername = settings.get("database.drivername")
        if not drivername:
            raise ConfigError(
                "No database configured. Set database.drivername (plus host, port, database, "
                "username) in settings.yaml for this environment; the password goes in "
                "SCHEMA_SCOUT_DATABASE__PASSWORD."
            )
        port = settings.get("database.port")
        query = {k: str(v) for k, v in (settings.get("database.query") or {}).items()}
        if catalog and drivername.startswith("databricks"):
            query["catalog"] = catalog
        return cls(
            URL.create(
                drivername,
                username=settings.get("database.username"),
                password=settings.get("database.password"),  # environment only (enforced)
                host=settings.get("database.host"),
                port=int(port) if port else None,
                database=settings.get("database.database"),
                query=query,
            )
        )


@dataclass(frozen=True)
class LlmConfig:
    """Which model backs the agent. `base_url` targets OpenAI-compatible or proxied endpoints."""

    provider: str = "anthropic"
    model: str = "claude-sonnet-5-5"
    max_tokens: int = 8000
    base_url: str | None = None
    api_key: str | None = None  # environment only; else the provider SDK's own variable

    @classmethod
    def from_settings(cls, settings: Dynaconf) -> "LlmConfig":
        return cls(
            provider=settings.get("llm.provider", cls.provider),
            model=settings.get("llm.model", cls.model),
            max_tokens=int(settings.get("llm.max_tokens", cls.max_tokens)),
            base_url=settings.get("llm.base_url") or None,
            api_key=settings.get("llm.api_key") or None,
        )

    def __repr__(self) -> str:  # never print the key
        return (
            f"LlmConfig(provider={self.provider!r}, model={self.model!r}, "
            f"max_tokens={self.max_tokens}, base_url={self.base_url!r}, "
            f"api_key={'***' if self.api_key else None})"
        )


@dataclass(frozen=True)
class AgentConfig:
    max_turns: int | None = None  # None: run until the model submits; set to add a guard rail
    max_tool_chars: int = 15_000

    @classmethod
    def from_settings(cls, settings: Dynaconf) -> "AgentConfig":
        max_turns = settings.get("agent.max_turns")
        return cls(
            max_turns=int(max_turns) if max_turns not in (None, "") else None,
            max_tool_chars=int(settings.get("agent.max_tool_chars", cls.max_tool_chars)),
        )
