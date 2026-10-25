import json
from pathlib import Path

from schema_scout.domain.models import DataModel
from schema_scout.renderers.base import Renderer


class ArtifactWriter:
    """Writes model.json plus one file per renderer into an output directory."""

    MODEL_FILENAME = "model.json"

    def __init__(self, out_dir: Path, renderers: list[Renderer]):
        self._out_dir = out_dir
        self._renderers = renderers

    def write(self, model: DataModel) -> list[str]:
        self._out_dir.mkdir(parents=True, exist_ok=True)
        (self._out_dir / self.MODEL_FILENAME).write_text(json.dumps(model.to_dict(), indent=2))
        names = [self.MODEL_FILENAME]
        for renderer in self._renderers:
            (self._out_dir / renderer.filename).write_text(renderer.render(model))
            names.append(renderer.filename)
        return names
