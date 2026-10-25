import os
from pathlib import Path

import yaml
from dynaconf import Dynaconf, Validator

ENV_PREFIX = "SCHEMA_SCOUT"
ENV_SWITCHER = f"{ENV_PREFIX}_ENV"
DEFAULT_ENV = "local"
KNOWN_ENVS = ("local", "production")

# Keys that must come from environment variables, never from a settings file.
SECRET_KEYS = frozenset({"password", "api_key", "token", "secret", "access_token"})


class SecretInFileError(ValueError):
    """A credential was found in a settings file."""


def _find_secrets(node, path: str = "") -> list[str]:
    found = []
    if isinstance(node, dict):
        for key, value in node.items():
            here = f"{path}.{key}" if path else str(key)
            if str(key).lower() in SECRET_KEYS and value not in (None, ""):
                found.append(here)
            found += _find_secrets(value, here)
    return found


def _reject_secrets_in_files(files: list[Path]) -> None:
    for file in files:
        if file.suffix.lower() not in (".yaml", ".yml"):
            continue
        offenders = _find_secrets(yaml.safe_load(file.read_text()) or {})
        if offenders:
            raise SecretInFileError(
                f"{file} contains credentials ({', '.join(offenders)}). Remove them and set "
                f"environment variables instead, e.g. {ENV_PREFIX}_DATABASE__PASSWORD."
            )


def _find_upwards(name: str) -> Path | None:
    here = Path.cwd().resolve()
    for folder in (here, *here.parents):
        if (folder / name).is_file():
            return folder / name
    return None


def build_settings(extra_files: list[Path] | None = None, env: str | None = None) -> Dynaconf:
    """Layered, environment-aware settings; later sources win.

    The environment is `env` (--env), else $SCHEMA_SCOUT_ENV, else "local". Each file holds a
    `default:` section plus one section per environment; `default` is always loaded and the
    selected section is merged over it.

    1. settings.yaml (found in the working directory or its parents): connection details
    2. any file passed via --config
    3. a .env file
    4. environment variables prefixed SCHEMA_SCOUT_, with `__` for nesting
       (e.g. SCHEMA_SCOUT_DATABASE__PASSWORD). Credentials are accepted only from here.
    """
    selected = (env or os.getenv(ENV_SWITCHER) or DEFAULT_ENV).lower()
    if selected not in KNOWN_ENVS:
        raise ValueError(f"Unknown environment {selected!r}; expected one of {KNOWN_ENVS}")

    base = _find_upwards("settings.yaml")
    files = [f.resolve() for f in ([base] if base else []) + list(extra_files or [])]
    _reject_secrets_in_files(files)
    settings = Dynaconf(
        envvar_prefix=ENV_PREFIX,
        settings_files=[str(f) for f in files],
        load_dotenv=True,
        environments=True,
        env=selected,
        merge_enabled=True,  # an env section overrides single nested keys, not whole blocks
        validators=[
            Validator("agent.max_tool_chars", "llm.max_tokens", gte=1),
            # optional: unset or null means "no limit"
            Validator(
                "agent.max_turns",
                condition=lambda v: v is None or v >= 1,
                messages={"condition": "{name} must be unset/null or >= 1, got {value}"},
            ),
        ],
    )
    settings.validators.validate()
    return settings
