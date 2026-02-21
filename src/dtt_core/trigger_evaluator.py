from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Iterable, Mapping

from dtt_core.clausewitz_parser import Assignment, Atom, Block, ClausewitzNode
from dtt_core.save_context import SaveContext, SaveEmpireFacts

_TRUE_LITERALS = frozenset({"yes", "true", "1", "on"})
_FALSE_LITERALS = frozenset({"no", "false", "0", "off"})

_SUPPORTED_POLITY_PREDICATES = frozenset(
    {
        "is_gestalt",
        "is_machine_empire",
        "is_hive_empire",
        "is_regular_empire",
        "is_individual_machine",
    }
)

SUPPORTED_MEMBERSHIP_PREDICATES = frozenset(
    {
        "has_origin",
        "has_ascension_perk",
        "has_ethic",
        "has_civic",
        "has_authority",
        "has_country_flag",
        "has_dlc",
    }
)

_SUPPORTED_MEMBERSHIP_PREDICATES = SUPPORTED_MEMBERSHIP_PREDICATES

_AUTO_POLITY_CONTEXTS: dict[str, dict[str, bool]] = {
    "regular": {
        "is_gestalt": False,
        "is_machine_empire": False,
        "is_hive_empire": False,
        "is_regular_empire": True,
        "is_individual_machine": False,
    },
    "corporate": {
        "is_gestalt": False,
        "is_machine_empire": False,
        "is_hive_empire": False,
        "is_regular_empire": True,
        "is_individual_machine": False,
    },
    "hive": {
        "is_gestalt": True,
        "is_machine_empire": False,
        "is_hive_empire": True,
        "is_regular_empire": False,
        "is_individual_machine": False,
    },
    "machine": {
        "is_gestalt": True,
        "is_machine_empire": True,
        "is_hive_empire": False,
        "is_regular_empire": False,
        "is_individual_machine": True,
    },
}


@dataclass(frozen=True)
class EmpireProfile:
    mode: str
    name: str
    predicates: Mapping[str, bool]
    memberships: Mapping[str, frozenset[str]] = field(default_factory=dict)

    @classmethod
    def auto(cls, polity: str) -> EmpireProfile:
        key = polity.strip().casefold()
        if key not in _AUTO_POLITY_CONTEXTS:
            supported = ", ".join(sorted(_AUTO_POLITY_CONTEXTS))
            raise ValueError(
                f"Unsupported auto polity context: {polity!r}. Expected one of: {supported}"
            )
        return cls(
            mode="auto",
            name=key,
            predicates=dict(_AUTO_POLITY_CONTEXTS[key]),
            memberships={},
        )

    @classmethod
    def auto_contexts(cls) -> dict[str, EmpireProfile]:
        return {name: cls.auto(name) for name in _AUTO_POLITY_CONTEXTS}

    @classmethod
    def profile(
        cls,
        predicates: Mapping[str, bool],
        *,
        name: str = "custom",
        memberships: Mapping[str, str | Iterable[str]] | None = None,
    ) -> EmpireProfile:
        normalized: dict[str, bool] = {}
        for raw_key, raw_value in predicates.items():
            key = raw_key.strip().casefold()
            if not key:
                continue
            normalized[key] = bool(raw_value)

        normalized_memberships = cls._normalize_memberships(memberships or {})
        return cls(
            mode="profile",
            name=name,
            predicates=normalized,
            memberships=normalized_memberships,
        )

    @classmethod
    def from_save_empire_facts(
        cls, facts: SaveEmpireFacts, *, name: str | None = None
    ) -> EmpireProfile:
        profile_name = name or facts.country_name or f"country_{facts.country_id}"
        return cls(
            mode="save",
            name=profile_name,
            predicates=facts.to_polity_predicates(),
            memberships=facts.to_membership_predicates(),
        )

    @classmethod
    def from_save_context(
        cls,
        context: SaveContext,
        *,
        country_id: int | None = None,
        name: str | None = None,
    ) -> EmpireProfile:
        facts = context.resolve_empire(country_id=country_id)
        if facts is None:
            requested_country_id = (
                context.player_country_id if country_id is None else country_id
            )
            raise ValueError(
                "Save context does not provide empire facts for "
                f"country_id={requested_country_id!r}"
            )
        return cls.from_save_empire_facts(facts, name=name)

    @property
    def is_auto_mode(self) -> bool:
        return self.mode == "auto"

    @property
    def is_profile_mode(self) -> bool:
        return self.mode == "profile"

    @property
    def is_save_mode(self) -> bool:
        return self.mode == "save"

    def resolve_predicate(self, predicate: str) -> bool | None:
        return self.predicates.get(predicate.casefold())

    def resolve_membership(self, predicate: str, value: str) -> bool | None:
        candidates = self.memberships.get(predicate.casefold())
        if candidates is None:
            return None

        normalized_value = value.strip().casefold()
        if not normalized_value:
            return False
        return normalized_value in candidates

    @staticmethod
    def _normalize_memberships(
        memberships: Mapping[str, str | Iterable[str]],
    ) -> dict[str, frozenset[str]]:
        normalized: dict[str, frozenset[str]] = {}
        for raw_key, raw_values in memberships.items():
            key = raw_key.strip().casefold()
            if not key:
                continue
            normalized[key] = EmpireProfile._normalize_membership_values(raw_values)
        return normalized

    @staticmethod
    def _normalize_membership_values(values: str | Iterable[str]) -> frozenset[str]:
        if isinstance(values, str):
            normalized = values.strip().casefold()
            return frozenset({normalized}) if normalized else frozenset()

        normalized_values = {
            token for token in (item.strip().casefold() for item in values) if token
        }
        return frozenset(normalized_values)


@dataclass(frozen=True)
class TriggerEvaluationResult:
    value: bool | None
    reason_trace: tuple[str, ...] = ()
    unknown_predicates: tuple[str, ...] = ()
    error: str | None = None

    @property
    def is_unknown(self) -> bool:
        return self.value is None

    @property
    def is_error(self) -> bool:
        return self.error is not None


@dataclass
class _EvalState:
    value: bool | None
    reasons: list[str]
    unknown_predicates: list[str]


class TriggerEvaluator:
    def evaluate_potential(
        self, potential: Block | None, profile: EmpireProfile
    ) -> TriggerEvaluationResult:
        if potential is None:
            return TriggerEvaluationResult(value=True)

        state = self._eval_block_and(potential, profile, path="potential")
        unknown_predicates = tuple(dict.fromkeys(state.unknown_predicates))
        reason_trace = tuple(state.reasons)
        error: str | None = None

        if profile.is_profile_mode and state.value is None:
            unresolved = ", ".join(unknown_predicates) or "unexpected trigger structure"
            error = f"Profile mode requires fully-resolved predicates; unresolved: {unresolved}"
            reason_trace = reason_trace + (error,)

        return TriggerEvaluationResult(
            value=state.value,
            reason_trace=reason_trace,
            unknown_predicates=unknown_predicates,
            error=error,
        )

    def _eval_block_and(
        self, block: Block, profile: EmpireProfile, *, path: str
    ) -> _EvalState:
        if not block.items:
            return _EvalState(value=True, reasons=[], unknown_predicates=[])

        states = [
            self._eval_node(item, profile, path=f"{path}[{index}]")
            for index, item in enumerate(block.items, start=1)
        ]
        return self._combine_and(states, path=path)

    def _eval_node(
        self, node: ClausewitzNode, profile: EmpireProfile, *, path: str
    ) -> _EvalState:
        if isinstance(node, Assignment):
            return self._eval_assignment(node, profile, path=path)
        if isinstance(node, Block):
            return self._eval_block_and(node, profile, path=path)
        if isinstance(node, Atom):
            return self._unknown(
                f"{path}: unexpected atom '{node.token.value}' in potential block"
            )
        return self._unknown(
            f"{path}: unsupported node type in potential block: {type(node).__name__}"
        )

    def _eval_assignment(
        self, assignment: Assignment, profile: EmpireProfile, *, path: str
    ) -> _EvalState:
        key_raw = assignment.key.value
        key = key_raw.strip().casefold()

        if key in {"and", "or", "nor", "not"}:
            return self._eval_combinator(key, assignment, profile, path=path)

        if key == "always":
            return self._eval_always(assignment, path=path)

        if key in _SUPPORTED_POLITY_PREDICATES:
            return self._eval_polity_predicate(key, assignment, profile, path=path)

        if key in _SUPPORTED_MEMBERSHIP_PREDICATES:
            return self._eval_membership_predicate(key, assignment, profile, path=path)

        unknowns = [key] if key else []
        return self._unknown(
            f"{path}: unsupported predicate '{key_raw}'", unknown_predicates=unknowns
        )

    def _eval_combinator(
        self,
        combinator: str,
        assignment: Assignment,
        profile: EmpireProfile,
        *,
        path: str,
    ) -> _EvalState:
        if assignment.op.value not in {"=", "?="}:
            return self._unknown(
                f"{path}: combinator '{combinator.upper()}' uses unsupported operator "
                f"'{assignment.op.value}'"
            )

        if not isinstance(assignment.value, Block):
            return self._unknown(
                f"{path}: combinator '{combinator.upper()}' requires a block value"
            )

        child_path = f"{path}.{combinator.upper()}"
        children = [
            self._eval_node(item, profile, path=f"{child_path}[{index}]")
            for index, item in enumerate(assignment.value.items, start=1)
        ]

        if combinator == "and":
            return self._combine_and(children, path=child_path)

        if combinator == "or":
            return self._combine_or(children, path=child_path)

        if combinator == "nor":
            or_state = self._combine_or(children, path=f"{child_path}.OR")
            if or_state.value is True:
                return _EvalState(
                    value=False,
                    reasons=[
                        f"{child_path}: NOR resolved to false because at least one branch is true"
                    ],
                    unknown_predicates=or_state.unknown_predicates,
                )
            if or_state.value is False:
                return _EvalState(
                    value=True,
                    reasons=[],
                    unknown_predicates=or_state.unknown_predicates,
                )

            reasons = list(or_state.reasons)
            reasons.append(
                f"{child_path}: NOR resolved to unknown because child OR is unknown"
            )
            return _EvalState(
                value=None,
                reasons=reasons,
                unknown_predicates=or_state.unknown_predicates,
            )

        nested_state = self._combine_and(children, path=f"{child_path}.AND")
        if nested_state.value is True:
            return _EvalState(
                value=False,
                reasons=[
                    f"{child_path}: NOT resolved to false because nested expression is true"
                ],
                unknown_predicates=nested_state.unknown_predicates,
            )
        if nested_state.value is False:
            return _EvalState(
                value=True,
                reasons=[],
                unknown_predicates=nested_state.unknown_predicates,
            )

        reasons = list(nested_state.reasons)
        reasons.append(
            f"{child_path}: NOT resolved to unknown because nested expression is unknown"
        )
        return _EvalState(
            value=None,
            reasons=reasons,
            unknown_predicates=nested_state.unknown_predicates,
        )

    def _eval_always(self, assignment: Assignment, *, path: str) -> _EvalState:
        value = self._atom_to_bool(assignment.value)
        if value is None:
            return self._unknown(
                f"{path}: always expects yes/no style value, got unsupported expression"
            )

        op = assignment.op.value
        if op in {"=", "?="}:
            passed = value
        elif op == "!=":
            passed = not value
        else:
            return self._unknown(f"{path}: always uses unsupported operator '{op}'")

        if passed:
            return _EvalState(value=True, reasons=[], unknown_predicates=[])

        return _EvalState(
            value=False,
            reasons=[f"{path}: always resolved to false"],
            unknown_predicates=[],
        )

    def _eval_polity_predicate(
        self,
        predicate: str,
        assignment: Assignment,
        profile: EmpireProfile,
        *,
        path: str,
    ) -> _EvalState:
        expected = self._atom_to_bool(assignment.value)
        if expected is None:
            return self._unknown(
                f"{path}: predicate '{predicate}' expects yes/no style value",
                unknown_predicates=[predicate],
            )

        actual = profile.resolve_predicate(predicate)
        if actual is None:
            return self._unknown(
                f"{path}: predicate '{predicate}' is not present in profile '{profile.name}'",
                unknown_predicates=[predicate],
            )

        op = assignment.op.value
        if op in {"=", "?="}:
            matched = actual == expected
        elif op == "!=":
            matched = actual != expected
        else:
            return self._unknown(
                f"{path}: predicate '{predicate}' uses unsupported operator '{op}'",
                unknown_predicates=[predicate],
            )

        if matched:
            return _EvalState(value=True, reasons=[], unknown_predicates=[])

        return _EvalState(
            value=False,
            reasons=[
                f"{path}: predicate '{predicate}' expected {self._format_bool(expected)} "
                f"for profile '{profile.name}', got {self._format_bool(actual)}"
            ],
            unknown_predicates=[],
        )

    def _eval_membership_predicate(
        self,
        predicate: str,
        assignment: Assignment,
        profile: EmpireProfile,
        *,
        path: str,
    ) -> _EvalState:
        if not isinstance(assignment.value, Atom):
            received_type = type(assignment.value).__name__
            return self._unknown(
                f"{path}: predicate '{predicate}' expects an atom value, got "
                f"{received_type}",
                unknown_predicates=[predicate],
            )

        op = assignment.op.value
        if op in {"=", "?="}:
            expects_present = True
        elif op == "!=":
            expects_present = False
        else:
            return self._unknown(
                f"{path}: predicate '{predicate}' uses unsupported operator '{op}'",
                unknown_predicates=[predicate],
            )

        value_token = assignment.value.token.value
        actual = profile.resolve_membership(predicate, value_token)
        if actual is None:
            return self._unknown(
                f"{path}: predicate '{predicate}' is not present in profile '{profile.name}'",
                unknown_predicates=[predicate],
            )

        matched = actual if expects_present else not actual
        if matched:
            return _EvalState(value=True, reasons=[], unknown_predicates=[])

        expectation = "present" if expects_present else "absent"
        actual_state = "present" if actual else "absent"
        value_label = value_token.strip() or "<empty>"
        return _EvalState(
            value=False,
            reasons=[
                f"{path}: predicate '{predicate}' expected '{value_label}' to be "
                f"{expectation} for profile '{profile.name}', got {actual_state}"
            ],
            unknown_predicates=[],
        )

    def _combine_and(self, states: list[_EvalState], *, path: str) -> _EvalState:
        unknown_predicates = self._collect_unknowns(states)

        false_states = [state for state in states if state.value is False]
        if false_states:
            reasons = [f"{path}: AND resolved to false"]
            reasons.extend(self._collect_reasons(false_states))
            return _EvalState(
                value=False,
                reasons=reasons,
                unknown_predicates=unknown_predicates,
            )

        unknown_states = [state for state in states if state.value is None]
        if unknown_states:
            reasons = [f"{path}: AND resolved to unknown"]
            reasons.extend(self._collect_reasons(unknown_states))
            return _EvalState(
                value=None,
                reasons=reasons,
                unknown_predicates=unknown_predicates,
            )

        return _EvalState(value=True, reasons=[], unknown_predicates=unknown_predicates)

    def _combine_or(self, states: list[_EvalState], *, path: str) -> _EvalState:
        unknown_predicates = self._collect_unknowns(states)

        if any(state.value is True for state in states):
            return _EvalState(
                value=True, reasons=[], unknown_predicates=unknown_predicates
            )

        unknown_states = [state for state in states if state.value is None]
        if unknown_states:
            reasons = [f"{path}: OR resolved to unknown"]
            reasons.extend(self._collect_reasons(unknown_states))
            return _EvalState(
                value=None,
                reasons=reasons,
                unknown_predicates=unknown_predicates,
            )

        reasons = [f"{path}: OR resolved to false"]
        reasons.extend(self._collect_reasons(states))
        return _EvalState(
            value=False,
            reasons=reasons,
            unknown_predicates=unknown_predicates,
        )

    def _unknown(
        self, reason: str, *, unknown_predicates: list[str] | None = None
    ) -> _EvalState:
        return _EvalState(
            value=None,
            reasons=[reason],
            unknown_predicates=list(unknown_predicates or []),
        )

    def _collect_unknowns(self, states: list[_EvalState]) -> list[str]:
        unknowns: list[str] = []
        for state in states:
            unknowns.extend(state.unknown_predicates)
        return unknowns

    def _collect_reasons(self, states: list[_EvalState]) -> list[str]:
        reasons: list[str] = []
        for state in states:
            reasons.extend(state.reasons)
        return reasons

    def _atom_to_bool(self, node: ClausewitzNode) -> bool | None:
        if not isinstance(node, Atom):
            return None
        text = node.token.value.strip().casefold()
        if text in _TRUE_LITERALS:
            return True
        if text in _FALSE_LITERALS:
            return False
        return None

    def _format_bool(self, value: bool) -> str:
        return "yes" if value else "no"
