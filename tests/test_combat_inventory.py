from adom_clone.core.ecs.components import Consumable, Fighter, Food, Monster, OnMap, Position
from adom_clone.core.game.actions import MoveAction, PickupAction, UseItemAction, WaitAction
from adom_clone.core.game.session import GameSession
from adom_clone.core.world.map_model import MapKind


def test_pickup_and_use_item_restores_hp() -> None:
    session = GameSession()

    target = _first_healing_item_position(session)
    assert target is not None
    ix, iy = target
    position = session.player_position
    position.x, position.y = (ix, iy)
    session.player_fighter.hp = 10
    start_count = len(session.player_inventory.item_ids)

    session.queue_action(PickupAction())
    session.advance_turn()
    assert len(session.player_inventory.item_ids) == start_count + 1

    pickup_slot = len(session.player_inventory.item_ids) - 1
    session.queue_action(UseItemAction(pickup_slot))
    session.advance_turn()

    assert len(session.player_inventory.item_ids) == start_count
    assert session.player_fighter.hp > 10


def test_player_moves_into_monster_to_attack() -> None:
    session = GameSession()
    session.current_map = session.map_for_depth(1)
    session.current_depth = 1
    session.player_map.kind = MapKind.DUNGEON
    session.player_map.depth = 1

    goblin_entity = _monster_in_depth(session, depth=1)
    monster_pos = session.ecs.get_component(goblin_entity, Position)
    assert monster_pos is not None
    session.player_position.x, session.player_position.y = (monster_pos.x - 1, monster_pos.y)

    goblin_stats_before = session.ecs.get_component(goblin_entity, Fighter)
    assert goblin_stats_before is not None
    goblin_hp_before = goblin_stats_before.hp
    player_hp_before = session.player_fighter.hp

    session.queue_action(MoveAction(1, 0))
    session.advance_turn()

    assert (session.player_position.x, session.player_position.y) == (
        monster_pos.x - 1,
        monster_pos.y,
    )
    goblin_stats_after = session.ecs.get_component(goblin_entity, Fighter)
    assert goblin_stats_after is not None
    assert goblin_stats_after.hp < goblin_hp_before
    assert session.player_fighter.hp < player_hp_before


def test_hunger_ticks_down_and_food_restores() -> None:
    session = GameSession()
    hunger = session.player_hunger
    hunger.current = 15

    session.queue_action(WaitAction())
    session.advance_turn()
    assert session.player_hunger.current == 14

    food_slot = _find_food_slot(session)
    assert food_slot is not None
    session.queue_action(UseItemAction(food_slot))
    session.advance_turn()
    assert session.player_hunger.current > 14


def test_starting_equipment_affects_effective_stats() -> None:
    session = GameSession(race_id="human", class_id="fighter", seed=1337)
    assert session.player_power > session.player_fighter.power
    assert session.player_defense > session.player_fighter.defense


def _monster_in_depth(session: GameSession, depth: int) -> int:
    for entity_id, monster in session.ecs.entities_with(Monster):
        on_map = session.ecs.get_component(entity_id, OnMap)
        if on_map is None:
            continue
        if monster.name and on_map.kind == MapKind.DUNGEON and on_map.depth == depth:
            return entity_id
    msg = f"Monster not found in depth {depth}"
    raise AssertionError(msg)


def _find_food_slot(session: GameSession) -> int | None:
    for idx, item_id in enumerate(session.player_inventory.item_ids):
        if session.ecs.get_component(item_id, Food) is not None:
            return idx
    return None


def _first_healing_item_position(session: GameSession) -> tuple[int, int] | None:
    for x, y in session.item_positions():
        item_ids = session.items_at(session.current_map.kind, session.current_depth, x, y)
        if not item_ids:
            continue
        if session.ecs.get_component(item_ids[0], Consumable) is not None:
            return (x, y)
    return None
