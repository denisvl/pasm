"""Shared utility helpers."""

from typing import Iterable, List, TypeVar


T = TypeVar("T")


def unique_ordered(items: Iterable[T]) -> List[T]:
    """Return items with duplicates removed, preserving first-seen order."""
    seen = set()
    ordered: List[T] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered
