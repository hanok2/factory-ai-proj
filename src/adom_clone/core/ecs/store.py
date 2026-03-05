from collections import defaultdict
from typing import TypeVar, cast

T = TypeVar("T")


class ECSStore:
    def __init__(self) -> None:
        self._next_entity_id = 1
        self._components: dict[type[object], dict[int, object]] = defaultdict(dict)

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
