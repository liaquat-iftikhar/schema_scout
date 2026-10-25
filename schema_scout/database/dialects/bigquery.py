from schema_scout.database.dialects.base import ApproxDistinctMixin, DialectAdapter


class BigQueryAdapter(ApproxDistinctMixin, DialectAdapter):
    name = "bigquery"
