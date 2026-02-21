from __future__ import annotations

from collections.abc import Iterable

TypedErrorDetails = tuple[tuple[str, str], ...]


class TypedCoreError(RuntimeError):
    def __init__(
        self, *, code: str, details: TypedErrorDetails | Iterable[tuple[str, str]] = ()
    ) -> None:
        if not isinstance(code, str) or not code.strip():
            raise ValueError("code must be a non-empty string")

        self.code = code
        self.details = self._normalize_details(details)
        super().__init__(code)

    @staticmethod
    def _normalize_details(
        details: TypedErrorDetails | Iterable[tuple[str, str]],
    ) -> TypedErrorDetails:
        normalized: list[tuple[str, str]] = []
        for entry in details:
            if len(entry) != 2:
                raise ValueError("details entries must be (key, value) tuples")
            key, value = entry
            if not isinstance(key, str) or not isinstance(value, str):
                raise TypeError("details entries must be (str, str)")
            if not key.strip():
                raise ValueError("details keys must not be blank")
            normalized.append((key, value))
        return tuple(normalized)

    def details_dict(self) -> dict[str, str]:
        return {key: value for key, value in self.details}


__all__ = ["TypedCoreError", "TypedErrorDetails"]
