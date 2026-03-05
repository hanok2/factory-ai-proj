from adom_clone.core.game.actions import MoveAction
from adom_clone.core.game.session import GameSession
from adom_clone.core.world.map_model import MapKind


def test_overworld_to_dungeon_transition() -> None:
    session = GameSession(seed=1337)
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
    session = GameSession(seed=1337)

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


def test_dungeon_depth_descend_and_ascend() -> None:
    session = GameSession(seed=1337)

    entrance = session.overworld.entrance_pos
    assert entrance is not None
    ex, ey = entrance
    session.player_position.x, session.player_position.y = (ex - 1, ey)
    session.queue_action(MoveAction(1, 0))
    session.advance_turn()
    assert session.current_depth == 1

    down = session.current_map.stairs_down_pos
    assert down is not None
    dx, dy = down
    session.player_position.x, session.player_position.y = (dx - 1, dy)
    session.queue_action(MoveAction(1, 0))
    session.advance_turn()
    assert session.current_depth == 2

    up = session.current_map.exit_pos
    assert up is not None
    ux, uy = up
    session.player_position.x, session.player_position.y = (ux + 1, uy)
    session.queue_action(MoveAction(-1, 0))
    session.advance_turn()
    assert session.current_depth == 1
