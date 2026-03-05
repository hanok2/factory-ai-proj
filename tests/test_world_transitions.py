from adom_clone.core.game.actions import MoveAction
from adom_clone.core.game.session import GameSession
from adom_clone.core.world.map_model import MapKind


def test_overworld_to_dungeon_transition() -> None:
    session = GameSession()
    assert session.current_map.kind.value == MapKind.OVERWORLD.value

    entrance = session.overworld.entrance_pos
    assert entrance is not None
    ex, ey = entrance

    pos = session.player_position
    pos.x, pos.y = (ex - 1, ey)
    session.queue_action(MoveAction(1, 0))
    session.advance_turn()

    assert session.current_map.kind.value == MapKind.DUNGEON.value


def test_dungeon_to_overworld_transition() -> None:
    session = GameSession()

    entrance = session.overworld.entrance_pos
    assert entrance is not None
    ex, ey = entrance
    pos = session.player_position
    pos.x, pos.y = (ex - 1, ey)
    session.queue_action(MoveAction(1, 0))
    session.advance_turn()
    assert session.current_map.kind.value == MapKind.DUNGEON.value

    exit_pos = session.dungeon.exit_pos
    assert exit_pos is not None
    dx, dy = exit_pos
    pos.x, pos.y = (dx + 1, dy)
    session.queue_action(MoveAction(-1, 0))
    session.advance_turn()

    assert session.current_map.kind.value == MapKind.OVERWORLD.value
