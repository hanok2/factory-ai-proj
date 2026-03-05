from pathlib import Path

import pytest

from adom_clone.core.ecs.components import Consumable
from adom_clone.core.game.actions import MoveAction, PickupAction, UseItemAction, WaitAction
from adom_clone.core.game.session import GameSession
from adom_clone.core.world.map_model import MapKind


def test_save_load_round_trip(tmp_path: Path) -> None:
    session = GameSession(seed=4242, race_id="elf", class_id="wizard")

    session.player_position.x, session.player_position.y = (4, 2)
    session.queue_action(PickupAction())
    session.advance_turn()
    session.queue_action(WaitAction())
    session.advance_turn()
    session.player_fighter.hp = 9

    entrance = session.overworld.entrance_pos
    assert entrance is not None
    ex, ey = entrance
    session.player_position.x, session.player_position.y = (ex - 1, ey)
    session.queue_action(MoveAction(1, 0))
    session.advance_turn()
    assert session.current_map.kind == MapKind.DUNGEON

    save_path = tmp_path / "savegame.json"
    session.save_to_file(str(save_path))
    loaded = GameSession.load_from_file(str(save_path))

    assert loaded.current_map.kind == session.current_map.kind
    assert loaded.player_position.x == session.player_position.x
    assert loaded.player_position.y == session.player_position.y
    assert loaded.player_fighter.hp == session.player_fighter.hp
    assert loaded.inventory_names() == session.inventory_names()
    assert loaded.turn_count == session.turn_count
    assert loaded.kill_count == session.kill_count
    assert loaded.seed == 4242
    assert loaded.race_id == "elf"
    assert loaded.class_id == "wizard"

    consumable_slot = _consumable_slot(loaded)
    if consumable_slot is not None:
        loaded.queue_action(UseItemAction(consumable_slot))
        loaded.advance_turn()
        assert loaded.player_fighter.hp > 9


def test_load_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        GameSession.load_from_file(str(tmp_path / "missing-save.json"))


def test_from_save_data_requires_player_entity() -> None:
    with pytest.raises(ValueError, match="player entity"):
        GameSession.from_save_data(
            {
                "current_map": "overworld",
                "seed": 1337,
                "race_id": "human",
                "class_id": "fighter",
                "messages": ["x"],
                "entities": [],
            },
        )


def _consumable_slot(session: GameSession) -> int | None:
    for idx, item_id in enumerate(session.player_inventory.item_ids):
        if session.ecs.get_component(item_id, Consumable) is not None:
            return idx
    return None
