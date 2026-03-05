from pathlib import Path

import pytest

from adom_clone.core.game.actions import MoveAction, PickupAction, UseItemAction, WaitAction
from adom_clone.core.game.session import GameSession
from adom_clone.core.world.map_model import MapKind


def test_save_load_round_trip(tmp_path: Path) -> None:
    session = GameSession()

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

    loaded.queue_action(UseItemAction(0))
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
                "messages": ["x"],
                "entities": [],
            },
        )
