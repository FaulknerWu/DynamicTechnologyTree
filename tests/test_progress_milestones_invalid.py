import importlib

import pytest

_settings = importlib.import_module("settings")
ValidationError = importlib.import_module("pydantic").ValidationError
Settings = _settings.Settings


def test_progress_milestones_invalid_non_monotonic_rejected_with_precise_path() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings.model_validate(
            {
                "schema_version": 1,
                "paths": {},
                "localization": {},
                "display": {},
                "progress_milestones": {
                    "load_order": 20,
                    "relations": 10,
                },
            },
            strict=True,
        )

    errors = exc_info.value.errors()
    locations = {tuple(error["loc"]) for error in errors}
    assert ("progress_milestones", "relations") in locations
