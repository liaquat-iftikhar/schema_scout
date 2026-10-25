import re


class SqlGuard:
    """Rejects anything but a single read-only raw statement."""

    _READ_ONLY = re.compile(r"^\s*(select|with|show|describe|explain)\b", re.I)

    @classmethod
    def assert_read_only(cls, statement: str) -> None:
        if not cls._READ_ONLY.match(statement) or ";" in statement.strip().rstrip(";"):
            raise PermissionError("Only single read-only statements are allowed")
