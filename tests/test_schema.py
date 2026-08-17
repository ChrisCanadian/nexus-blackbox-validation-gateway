from pathlib import Path
import pytest

from nexus_blackbox_gateway.rig import validate_spec


def test_challenge_schema_accepts_bounded_spec_and_rejects_http_provider():
    schema = Path(__file__).resolve().parents[1] / "challenge.schema.json"
    valid = {
        "name": "community-test",
        "provider": {"base_url": "https://provider.example/v1", "model": "m"},
        "steps": [{"message": "hello", "assertions": [{"type": "contains", "value": "x"}]}],
    }
    validate_spec(valid, schema)

    invalid = {
        "name": "bad",
        "provider": {"base_url": "http://127.0.0.1:9999", "model": "m"},
        "steps": [{"message": "hello"}],
    }
    with pytest.raises(ValueError):
        validate_spec(invalid, schema)
