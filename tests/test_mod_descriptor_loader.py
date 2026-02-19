# pyright: reportMissingImports=false

from __future__ import annotations

from pathlib import Path

from dtt_core.mod_descriptor_loader import ModDescriptorLoader, load_descriptor


def test_load_descriptor_captures_replace_paths_dependencies_and_metadata(
    tmp_path: Path,
) -> None:
    descriptor_path = tmp_path / "descriptor.mod"
    descriptor_path.write_text(
        "\n".join(
            [
                'name = "Example Mod"',
                'replace_path = "common/technology"',
                'replace_path = "localisation"',
                'dependencies = { "Core Framework" "UI Patch" }',
                'supported_version = "4.2.*"',
                'remote_file_id = "123456789"',
            ]
        ),
        encoding="utf-8",
    )

    descriptor = load_descriptor(descriptor_path)

    assert descriptor.path == descriptor_path
    assert descriptor.replace_paths == ("common/technology", "localisation")
    assert descriptor.dependencies == ("Core Framework", "UI Patch")
    assert descriptor.supported_version == "4.2.*"
    assert descriptor.remote_file_id == "123456789"
    assert descriptor.parse_diagnostics == ()


def test_loader_class_supports_dot_mod_files(tmp_path: Path) -> None:
    descriptor_path = tmp_path / "ugc_999999.mod"
    descriptor_path.write_text(
        "\n".join(
            [
                'replace_path = "common/technology"',
                'dependencies = { "Base" "Balance Pack" }',
            ]
        ),
        encoding="utf-8",
    )

    descriptor = ModDescriptorLoader().load_descriptor(descriptor_path)

    assert descriptor.replace_paths == ("common/technology",)
    assert descriptor.dependencies == ("Base", "Balance Pack")


def test_load_descriptor_uses_decode_helper_for_non_utf8_content(
    tmp_path: Path,
) -> None:
    descriptor_path = tmp_path / "descriptor.mod"
    text = "\n".join(
        ['replace_path = "common/technology"', 'dependencies = { "Cost €" }']
    )
    descriptor_path.write_bytes(text.encode("cp1252"))

    descriptor = load_descriptor(descriptor_path)

    assert descriptor.dependencies == ("Cost €",)
    assert descriptor.decode_diagnostics is not None
    assert descriptor.decode_diagnostics.used_fallback_encoding is True
    assert descriptor.decode_diagnostics.encoding_used == "cp1252"
