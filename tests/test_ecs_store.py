from adom_clone.core.ecs.components import Position
from adom_clone.core.ecs.store import ECSStore


def test_add_get_remove_component() -> None:
    ecs = ECSStore()
    entity = ecs.create_entity()

    ecs.add_component(entity, Position(1, 2))
    got = ecs.get_component(entity, Position)

    assert got is not None
    assert (got.x, got.y) == (1, 2)

    ecs.remove_component(entity, Position)
    assert ecs.get_component(entity, Position) is None


def test_entities_with_component() -> None:
    ecs = ECSStore()
    e1 = ecs.create_entity()
    e2 = ecs.create_entity()

    ecs.add_component(e1, Position(3, 4))
    ecs.add_component(e2, Position(7, 8))

    items = ecs.entities_with(Position)
    assert {(entity, (pos.x, pos.y)) for entity, pos in items} == {(e1, (3, 4)), (e2, (7, 8))}
