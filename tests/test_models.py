import pytest

from schema_scout.domain.models import Cardinality, DataModel


def test_from_dict_parses_enums(model):
    assert model.relationships[0].cardinality is Cardinality.ONE_TO_MANY
    assert model.tables[1].grain == "one row per order"


def test_rejects_invalid_enum(submission):
    submission["tables"][0]["kind"] = "bogus"
    with pytest.raises(ValueError):
        DataModel.from_dict(submission)


def test_rejects_out_of_range_confidence(submission):
    submission["relationships"][0]["confidence"] = 1.5
    with pytest.raises(ValueError):
        DataModel.from_dict(submission)


def test_foreign_and_primary_keys(model):
    assert model.foreign_keys() == {"sales.fact_orders": {"customer_id"}}
    assert model.primary_keys()["sales.dim_customer"] == {"id"}


def test_to_dict_is_json_serializable(model):
    import json

    assert json.loads(json.dumps(model.to_dict()))["tables"][0]["kind"] == "dimension"
