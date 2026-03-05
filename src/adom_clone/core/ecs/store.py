"""Minimal ECS storage layer.

The store maps component types to per-entity component instances.
"""

from collections import defaultdict
from typing import TypeVar, cast

T = TypeVar("T")


class ECSStore:
    """In-memory ECS component index keyed by component type and entity ID."""

    def __init__(self) -> None:
        self._next_entity_id = 1
        self._components: dict[type[object], dict[int, object]] = defaultdict(dict)

    @property
    def next_entity_id(self) -> int:
        return self._next_entity_id

    def set_next_entity_id(self, next_entity_id: int) -> None:
        if next_entity_id < 1:
            msg = "next_entity_id must be positive."
            raise ValueError(msg)
        self._next_entity_id = next_entity_id

    def create_entity(self) -> int:
        entity_id = self._next_entity_id
        self._next_entity_id += 1
        return entity_id

    def add_component(self, entity_id: int, component: T) -> None:
        self._components[type(component)][entity_id] = component

    def get_component(self, entity_id: int, component_type: type[T]) -> T | None:
        raw = self._components[component_type].get(entity_id)
        if raw is None:
            return None
        return cast(T, raw)

    def remove_component(self, entity_id: int, component_type: type[object]) -> None:
        self._components[component_type].pop(entity_id, None)

    def entities_with(self, component_type: type[T]) -> list[tuple[int, T]]:
        entries = self._components[component_type].items()
        return [(entity_id, cast(T, component)) for entity_id, component in entries]
