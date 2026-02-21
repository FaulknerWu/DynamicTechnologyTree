import importlib

import pytest

_settings = importlib.import_module("settings")
ValidationError = importlib.import_module("pydantic").ValidationError
DEFAULT_LANGUAGE = _settings.DEFAULT_LANGUAGE
Settings = _settings.Settings
settings_json_schema = _settings.settings_json_schema


def test_settings_schema_defaults_and_json_schema_metadata() -> None:
    default_settings = Settings()

    assert default_settings.schema_version == 1
    assert default_settings.localization.language == DEFAULT_LANGUAGE
    assert default_settings.display.max_children_per_node == 12
    assert default_settings.display.max_tree_depth == 4
    assert default_settings.display.max_display_nodes == 128
    assert default_settings.display.max_prereq_display == 2
    assert default_settings.ingestion.diagnostic_example_limit == 10
    assert default_settings.output.eligibility_sample_size == 5
    assert default_settings.output.eligibility_unknown_warning_threshold == 1

    schema = settings_json_schema()
    root_props = schema["properties"]
    assert {
        "schema_version",
        "paths",
        "localization",
        "display",
        "ingestion",
        "output",
    }.issubset(root_props.keys())

    display_props = schema["$defs"]["DisplaySettings"]["properties"]
    assert display_props["max_children_per_node"]["minimum"] == 0
    assert display_props["max_children_per_node"]["maximum"] == 999
    assert display_props["max_tree_depth"]["minimum"] == 0
    assert display_props["max_tree_depth"]["maximum"] == 99
    assert display_props["max_display_nodes"]["minimum"] == 0
    assert display_props["max_display_nodes"]["maximum"] == 9999
    assert display_props["max_prereq_display"]["minimum"] == 0
    assert display_props["max_prereq_display"]["maximum"] == 99

    output_props = schema["$defs"]["OutputSettings"]["properties"]
    ingestion_props = schema["$defs"]["IngestionSettings"]["properties"]
    assert ingestion_props["diagnostic_example_limit"]["minimum"] == 0
    assert ingestion_props["diagnostic_example_limit"]["maximum"] == 999
    assert ingestion_props["diagnostic_example_limit"]["tab"] == "ui_tab_output"
    assert ingestion_props["diagnostic_example_limit"]["group"] == "ingestion"

    assert output_props["eligibility_sample_size"]["minimum"] == 0
    assert output_props["eligibility_sample_size"]["maximum"] == 999
    assert output_props["eligibility_unknown_warning_threshold"]["minimum"] == 0
    assert output_props["eligibility_unknown_warning_threshold"]["maximum"] == 9999
    assert output_props["eligibility_sample_size"]["tab"] == "ui_tab_output"
    assert output_props["eligibility_sample_size"]["group"] == "eligibility"

    language_schema = schema["$defs"]["LocalizationSettings"]["properties"]["language"]
    assert "english" in language_schema["enum"]
    assert "simp_chinese" in language_schema["enum"]

    assert root_props["paths"]["tab"] == "ui_tab_paths"
    assert root_props["localization"]["tab"] == "ui_tab_localization"
    assert root_props["display"]["tab"] == "ui_tab_display"
    assert language_schema["label_key"] == "ui_label_language"


def test_settings_schema_unknown_fields_rejected_with_precise_paths() -> None:
    with pytest.raises(ValidationError) as exc_info:
        Settings.model_validate(
            {
                "unknown_root": "bad",
                "paths": {"unknown_paths": "bad"},
                "localization": {"unknown_localization": "bad"},
                "display": {"unknown_display": 1},
            }
        )

    errors = exc_info.value.errors()
    locations = {tuple(error["loc"]) for error in errors}

    assert ("unknown_root",) in locations
    assert ("paths", "unknown_paths") in locations
    assert ("localization", "unknown_localization") in locations
    assert ("display", "unknown_display") in locations
    assert all(error["type"] == "extra_forbidden" for error in errors)
