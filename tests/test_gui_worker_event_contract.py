from __future__ import annotations

from pathlib import Path


def test_generation_worker_has_no_stdout_redirect_or_marker_parsing() -> None:
    worker_source = (
        Path(__file__).resolve().parents[1] / "src" / "gui" / "generation_worker.py"
    ).read_text(encoding="utf-8")

    forbidden_tokens = (
        "redirect_stdout",
        "redirect_stderr",
        "_progress_markers",
        "marker in message",
        "AMBIGUOUS_COUNTRY_SELECTION_REQUIRED",
        "UNSUPPORTED_SAVE_FORMAT_PREFIX",
    )
    for token in forbidden_tokens:
        assert token not in worker_source

    assert "event_sink=_QtEventSink(" in worker_source
    assert "generation_event = pyqtSignal(object)" in worker_source
