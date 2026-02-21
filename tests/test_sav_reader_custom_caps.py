# pyright: reportMissingImports=false

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import _write_sav
from dtt_core.events import NullEventSink
from dtt_core.generate_localization import GenerateLocalizationUseCase, GenerationSteps
from dtt_core.sav_reader import SaveReaderError
from settings import Settings


def test_sav_reader_custom_caps_run_with_settings_enforces_zip_member_cap(
    tmp_path: Path,
) -> None:
    save_path = _write_sav(
        tmp_path / "custom-caps.sav",
        meta=b"m" * 80,
        gamestate=b"g" * 80,
    )

    settings = Settings.model_validate(
        {
            "schema_version": 1,
            "paths": {},
            "localization": {},
            "display": {},
            "save_reader": {
                "max_member_uncompressed_size_bytes": 16,
                "max_total_uncompressed_size_bytes": 2048,
            },
        },
        strict=True,
    )

    use_case = GenerateLocalizationUseCase(
        localize=lambda key, **kwargs: key,
        event_sink=NullEventSink(),
        steps=GenerationSteps(
            require_save_path=lambda value: Path(str(value)),
            set_empire_profile=lambda _profile: None,
            scan_all_technology_files=lambda: None,
            build_technology_tree_relationships=lambda: None,
            scan_all_tech_descriptions=lambda: None,
            precompute_overlong_trees=lambda: None,
            report_circular_dependencies=lambda: None,
            display_generation_statistics=lambda: None,
            generate_all_yml_files=lambda: None,
        ),
    )

    with pytest.raises(SaveReaderError) as exc_info:
        use_case.run_with_settings(settings=settings, save_path=save_path)

    message = str(exc_info.value)
    assert "safe per-member limit" in message
    assert "(16 bytes)" in message
