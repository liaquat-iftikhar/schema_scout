from collections.abc import Callable

from schema_scout.domain.models import DataModel


class RelationshipReviewer:
    """Asks a human to confirm relationships below the confidence threshold."""

    def __init__(
        self,
        threshold: float,
        ask: Callable[[str], str] = input,
        say: Callable[[str], None] = print,
    ):
        self._threshold = threshold
        self._ask = ask
        self._say = say

    def review(self, model: DataModel) -> DataModel:
        kept = []
        for r in model.relationships:
            if not r.needs_review(self._threshold):
                kept.append(r)
                continue
            self._say(
                f"\n? {r.child_ref} -> {r.parent_ref}  "
                f"[{r.cardinality}, confidence {r.confidence:.2f}]\n  evidence: {r.evidence}"
            )
            if self._ask("  keep this relationship? [y/N] ").strip().lower() == "y":
                kept.append(r)
        return model.with_relationships(kept)
