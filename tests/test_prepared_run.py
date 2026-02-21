# pyright: reportMissingImports=false

from __future__ import annotations

from pathlib import Path

import pytest

from conftest import _write_sav
import dtt_core.prepared_run as prepared_run_module
from dtt_core.events import NullEventSink
from dtt_core.generate_localization import GenerateLocalizationUseCase, GenerationSteps
from dtt_core.prepared_run import prepare_run
from dtt_core.save_context import SaveContext, SaveEmpireFacts


def test_prepared_run_candidates(tmp_path: Path) -> None:
    save_path = _write_sav(
        tmp_path / "candidates.sav",
        meta='name = "Prepared Run Candidates"\n',
        gamestate="\n".join(
            [
                "player = {",
                "  2 = { nested = { country = 42 } }",
                "  0 = { country = 7 country = 7 }",
                "  1 = { country = 42 }",
                "}",
                "country = {",
                '  7 = { name = "Alpha" authority = auth_democratic }',
                '  42 = { name = "Beta" authority = auth_machine_intelligence }',
                "}",
            ]
        ),
    )

    prepared = prepare_run(save_path, country_id=7)
    assert prepared.country_candidates == (7, 42)
    assert prepared.selected_country_id == 7


def test_prepared_run_ambiguous_requires_choice(tmp_path: Path) -> None:
    save_path = _write_sav(
        tmp_path / "ambiguous.sav",
        meta='name = "Prepared Run Ambiguous"\n',
        gamestate="\n".join(
            [
                "player = {",
                "  1 = { country = 42 }",
                "  0 = { country = 7 }",
                "}",
                "country = {",
                '  7 = { name = "Alpha" authority = auth_democratic }',
                '  42 = { name = "Beta" authority = auth_machine_intelligence }',
                "}",
            ]
        ),
    )

    with pytest.raises(ValueError, match="ambiguous player empire") as exc:
        prepare_run(save_path)

    assert "candidates=[7, 42]" in str(exc.value)


def test_prepared_run_parses_save_once_per_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Path | str] = []

    def _fake_load_save_context(save_path: Path | str) -> SaveContext:
        calls.append(save_path)
        return SaveContext(
            save_path=str(save_path),
            player_country_candidates=(7,),
            player_country_id=7,
            empires_by_country_id={
                7: SaveEmpireFacts(country_id=7, country_name="Once Per Run")
            },
        )

    monkeypatch.setattr(
        prepared_run_module.sav_reader,
        "load_save_context",
        _fake_load_save_context,
    )

    use_case = GenerateLocalizationUseCase(
        localize=lambda key, **kwargs: key,
        event_sink=NullEventSink(),
        steps=GenerationSteps(
            require_save_path=lambda save_path: Path(save_path or "dummy.sav"),
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

    use_case.run(save_path="once.sav")
    assert len(calls) == 1
