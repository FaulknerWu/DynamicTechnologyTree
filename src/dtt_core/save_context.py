"""Save-derived data contracts for trigger evaluation.

Trigger evaluation targets current-save empire facts only (authority, ethics,
civics, origin, perks, flags, DLCs, and derived polity booleans), not future
state changes. Strictness policy: unresolved facts stay Unknown by omission;
evaluators should propagate Unknown, and later eligibility layers may exclude
Unknown results.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field


def _normalize_key(value: str) -> str:
    return value.strip().casefold()


def _normalize_token(value: str) -> str:
    return value.strip().casefold()


def _normalize_many(values: Iterable[str]) -> frozenset[str]:
    return frozenset(
        token for token in (_normalize_token(item) for item in values) if token
    )


@dataclass(frozen=True)
class SaveEmpireFacts:
    country_id: int
    country_name: str = ""
    is_gestalt: bool | None = None
    is_machine_empire: bool | None = None
    is_hive_empire: bool | None = None
    is_regular_empire: bool | None = None
    is_individual_machine: bool | None = None

    authority: str | None = None
    ethics: Iterable[str] | None = None
    civics: Iterable[str] | None = None
    origin: str | None = None
    ascension_perks: Iterable[str] | None = None
    country_flags: Iterable[str] | None = None
    dlcs: Iterable[str] | None = None

    extra_predicates: Mapping[str, bool | None] = field(default_factory=dict)
    extra_memberships: Mapping[str, str | Iterable[str] | None] = field(
        default_factory=dict
    )

    def to_polity_predicates(self) -> dict[str, bool]:
        predicates: dict[str, bool] = {}

        for key, value in (
            ("is_gestalt", self.is_gestalt),
            ("is_machine_empire", self.is_machine_empire),
            ("is_hive_empire", self.is_hive_empire),
            ("is_regular_empire", self.is_regular_empire),
            ("is_individual_machine", self.is_individual_machine),
        ):
            if value is not None:
                predicates[key] = value

        for raw_key, raw_value in self.extra_predicates.items():
            key = _normalize_key(raw_key)
            if key and raw_value is not None:
                predicates[key] = bool(raw_value)

        return predicates

    def to_membership_predicates(self) -> dict[str, frozenset[str]]:
        memberships: dict[str, frozenset[str]] = {}

        self._set_scalar_membership(memberships, "has_authority", self.authority)
        self._set_iterable_membership(memberships, "has_ethic", self.ethics)
        self._set_iterable_membership(memberships, "has_civic", self.civics)
        self._set_scalar_membership(memberships, "has_origin", self.origin)
        self._set_iterable_membership(
            memberships, "has_ascension_perk", self.ascension_perks
        )
        self._set_iterable_membership(
            memberships, "has_country_flag", self.country_flags
        )
        self._set_iterable_membership(memberships, "has_dlc", self.dlcs)

        for raw_key, raw_values in self.extra_memberships.items():
            key = _normalize_key(raw_key)
            if not key or raw_values is None:
                continue
            if isinstance(raw_values, str):
                self._set_scalar_membership(memberships, key, raw_values)
            else:
                self._set_iterable_membership(memberships, key, raw_values)

        return memberships

    @staticmethod
    def _set_scalar_membership(
        target: dict[str, frozenset[str]],
        predicate: str,
        raw_value: str | None,
    ) -> None:
        if raw_value is None:
            return
        normalized = _normalize_token(raw_value)
        if normalized:
            target[predicate] = frozenset({normalized})
            return
        target[predicate] = frozenset()

    @staticmethod
    def _set_iterable_membership(
        target: dict[str, frozenset[str]],
        predicate: str,
        raw_values: Iterable[str] | None,
    ) -> None:
        if raw_values is None:
            return
        if isinstance(raw_values, str):
            normalized = _normalize_token(raw_values)
            target[predicate] = frozenset({normalized}) if normalized else frozenset()
            return
        target[predicate] = _normalize_many(raw_values)


@dataclass(frozen=True)
class SaveParseReport:
    member_uncompressed_sizes: Mapping[str, int] = field(default_factory=dict)
    member_compressed_sizes: Mapping[str, int] = field(default_factory=dict)
    member_encodings: Mapping[str, str] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class SaveContext:
    save_path: str
    empires_by_country_id: Mapping[int, SaveEmpireFacts] = field(default_factory=dict)
    player_country_id: int | None = None
    player_country_candidates: tuple[int, ...] = ()
    save_name: str | None = None
    dlcs: frozenset[str] = field(default_factory=frozenset)
    report: SaveParseReport | None = None

    def sorted_country_ids(self) -> tuple[int, ...]:
        return tuple(sorted(self.empires_by_country_id))

    def resolve_empire(self, country_id: int | None = None) -> SaveEmpireFacts | None:
        resolved_country_id = (
            self.player_country_id if country_id is None else country_id
        )
        if resolved_country_id is None:
            return None
        return self.empires_by_country_id.get(resolved_country_id)
