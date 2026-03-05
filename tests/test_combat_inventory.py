from adom_clone.core.ecs.components import Fighter, Monster, OnMap
from adom_clone.core.game.actions import MoveAction, PickupAction, UseItemAction
from adom_clone.core.game.session import GameSession
from adom_clone.core.world.map_model import MapKind


def test_pickup_and_use_item_restores_hp() -> None:
    session = GameSession()
    position = session.player_position
    position.x, position.y = (4, 2)
    session.player_fighter.hp = 10

    session.queue_action(PickupAction())
    session.advance_turn()
    assert len(session.player_inventory.item_ids) == 1

    session.queue_action(UseItemAction(0))
    session.advance_turn()
    assert len(session.player_inventory.item_ids) == 0
    assert session.player_fighter.hp > 10


def test_player_moves_into_monster_to_attack() -> None:
    session = GameSession()
    session.current_map = session.dungeon
    session.player_map.kind = MapKind.DUNGEON
    session.player_position.x, session.player_position.y = (7, 5)

    goblin_entity = _monster_by_name(session, "giant rat")
    goblin_stats_before = session.ecs.get_component(goblin_entity, Fighter)
    assert goblin_stats_before is not None
    goblin_hp_before = goblin_stats_before.hp
    player_hp_before = session.player_fighter.hp

    session.queue_action(MoveAction(1, 0))
    session.advance_turn()

    assert (session.player_position.x, session.player_position.y) == (7, 5)
    goblin_stats_after = session.ecs.get_component(goblin_entity, Fighter)
    assert goblin_stats_after is not None
    assert goblin_stats_after.hp < goblin_hp_before
    assert session.player_fighter.hp < player_hp_before


def _monster_by_name(session: GameSession, name: str) -> int:
    for entity_id, monster in session.ecs.entities_with(Monster):
        on_map = session.ecs.get_component(entity_id, OnMap)
        if on_map is None:
            continue
        if monster.name == name and on_map.kind == MapKind.DUNGEON:
            return entity_id
    msg = f"Monster not found: {name}"
    raise AssertionError(msg)
