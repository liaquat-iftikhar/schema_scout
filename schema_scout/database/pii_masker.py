import re


class PiiMasker:
    """Flags column names that look like they hold personal data."""

    _PATTERN = re.compile(
        r"(email|phone|ssn|passport|iban|card|password|token|secret|address|birth|dob|"
        r"first_?name|last_?name|full_?name|ip_?addr)",
        re.I,
    )
    PLACEHOLDER = "<masked: looks like PII>"

    def is_pii(self, column: str) -> bool:
        return bool(self._PATTERN.search(column))
