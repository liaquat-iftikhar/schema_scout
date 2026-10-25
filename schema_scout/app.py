from dataclasses import dataclass
from pathlib import Path

from schema_scout.agent.erd_agent import ErdAgent
from schema_scout.config import AgentConfig, DatabaseConfig, LlmConfig
from schema_scout.database.client import DatabaseClient
from schema_scout.database.sqlalchemy_repository import SqlAlchemyRepository
from schema_scout.llm import create_llm_client
from schema_scout.output.artifact_writer import ArtifactWriter
from schema_scout.output.relationship_reviewer import RelationshipReviewer
from schema_scout.renderers import DbmlRenderer, MermaidRenderer, ReportRenderer
from schema_scout.tools.registry import ToolRegistry


@dataclass(frozen=True)
class RunOptions:
    schemas: list[str]
    out_dir: Path
    label: str | None = None  # display name; defaults to the database name or dialect
    interactive: bool = False
    threshold: float = 0.85


class SchemaScoutApp:
    """Composition root: wires database, agent, review and output together."""

    def __init__(self, database: DatabaseConfig, llm: LlmConfig, agent: AgentConfig):
        self._database = database
        self._llm_config = llm
        self._agent_config = agent

    def run(self, options: RunOptions) -> list[str]:
        llm = create_llm_client(self._llm_config)  # fail fast on bad provider config
        client = DatabaseClient(self._database)
        try:
            label = options.label or client.database_name or client.dialect_name
            repository = SqlAlchemyRepository(client, label, options.schemas)
            agent = ErdAgent(
                llm,
                ToolRegistry.for_database(repository),
                self._agent_config,
            )
            model = agent.run(repository.label, repository.schemas, repository.dialect_name)

            if options.interactive:
                model = RelationshipReviewer(options.threshold).review(model)

            writer = ArtifactWriter(
                options.out_dir,
                [
                    MermaidRenderer(),
                    DbmlRenderer(repository.known_columns),
                    ReportRenderer(repository.label),
                ],
            )
            return writer.write(model)
        finally:
            client.close()
