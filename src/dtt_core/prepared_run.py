from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dtt_core import sav_reader
from dtt_core.save_context import SaveContext


class AmbiguousPlayerEmpireError(ValueError):
    def __init__(
        self,
        *,
        save_context: SaveContext,
        country_candidates: tuple[int, ...],
    ) -> None:
        self.save_context = save_context
        self.country_candidates = country_candidates
        candidate_list = ", ".join(
            str(candidate) for candidate in self.country_candidates
        )
        super().__init__(
            "ambiguous player empire: country_id is required when save contains "
            f"{len(self.country_candidates)} player candidates; "
            f"candidates=[{candidate_list}]"
        )


@dataclass(frozen=True)
class PreparedRun:
    save_context: SaveContext
    country_candidates: tuple[int, ...]
    selected_country_id: int


def prepare_run(
    save_path: Path | str,
    *,
    country_id: int | None = None,
    save_reader_limits: sav_reader.SaveReaderLimits | None = None,
) -> PreparedRun:
    if save_reader_limits is None:
        save_context = sav_reader.load_save_context(save_path)
    else:
        save_context = sav_reader.load_save_context(
            save_path, limits=save_reader_limits
        )

    candidates = tuple(sorted(set(save_context.player_country_candidates)))

    if country_id is not None:
        if country_id not in candidates:
            candidate_list = ", ".join(str(candidate) for candidate in candidates)
            raise ValueError(
                "invalid player empire: country_id must be one of "
                f"candidates=[{candidate_list}] (got country_id={country_id})"
            )
        selected_country_id = country_id
    else:
        if len(candidates) == 1:
            selected_country_id = candidates[0]
        else:
            raise AmbiguousPlayerEmpireError(
                save_context=save_context,
                country_candidates=candidates,
            )

    return PreparedRun(
        save_context=save_context,
        country_candidates=candidates,
        selected_country_id=selected_country_id,
    )


__all__ = ["AmbiguousPlayerEmpireError", "PreparedRun", "prepare_run"]
