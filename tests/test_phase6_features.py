from pathlib import Path

from adom_clone.core.ecs.components import (
    BlocksMovement,
    Fighter,
    Monster,
    Npc,
    NpcRole,
    OnMap,
    Position,
    Resistances,
)
from adom_clone.core.game.actions import (
    CastArcaneBoltAction,
    InteractAction,
    MoveAction,
    SelectTalentAction,
)
from adom_clone.core.game.session import GameSession
from adom_clone.core.world.map_model import MapKind


def test_talent_point_awarded_and_selectable() -> None:
    session = GameSession(seed=1337, class_id="wizard")
    session.grant_player_xp(200)

    assert session.player_talents.points > 0
    session.queue_action(SelectTalentAction("arcane_efficiency"))
    session.advance_turn()
    assert "arcane_efficiency" in session.player_talents.selected


def test_arcane_bolt_uses_mana_and_resistance() -> None:
    session = GameSession(seed=1337, class_id="wizard")
    start_mana = session.player_mana.current

    target_id = session.ecs.create_entity()
    session.ecs.add_component(target_id, Monster(name="resistant target"))
    session.ecs.add_component(target_id, Fighter(max_hp=20, hp=20, power=1, defense=0))
    session.ecs.add_component(target_id, Resistances(arcane_pct=50))
    session.ecs.add_component(
        target_id,
        Position(session.player_position.x + 2, session.player_position.y),
    )
    session.ecs.add_component(target_id, OnMap(kind=MapKind.OVERWORLD, depth=None))
    session.ecs.add_component(target_id, BlocksMovement())

    session.queue_action(CastArcaneBoltAction(1, 0))
    session.advance_turn()

    target_fighter = session.ecs.get_component(target_id, Fighter)
    assert target_fighter is not None
    assert target_fighter.hp < 20
    assert session.player_mana.current < start_mana


def test_town_npc_interaction_and_quest_flow() -> None:
    session = GameSession(seed=1337)
    town_pos = session.overworld.town_pos
    assert town_pos is not None

    tx, ty = town_pos
    session.player_position.x, session.player_position.y = (tx - 1, ty)
    session.queue_action(MoveAction(1, 0))
    session.advance_turn()
    assert session.current_map.kind == MapKind.TOWN

    quest_giver = _town_npc(session, NpcRole.QUEST_GIVER)
    quest_pos = session.ecs.get_component(quest_giver, Position)
    assert quest_pos is not None

    session.player_position.x, session.player_position.y = (quest_pos.x + 1, quest_pos.y)
    session.queue_action(InteractAction())
    session.advance_turn()
    assert session.quest_state.accepted


def test_hidden_trap_detection_reveals_adjacent_traps() -> None:
    session = GameSession(seed=1337)
    pos = session.player_position
    hidden = (pos.x + 1, pos.y)
    session.current_map.trap_positions = {hidden}
    session.current_map.discovered_traps = set()

    session.detect_nearby_traps()
    assert hidden in session.current_map.discovered_traps


def test_corrupted_primary_save_falls_back_to_backup(tmp_path: Path) -> None:
    session = GameSession(seed=1337, class_id="wizard")
    save_path = tmp_path / "savegame.json"

    session.save_to_file(str(save_path))
    # Second save creates a .bak copy of the first save.
    session.save_to_file(str(save_path))

    save_path.write_text("{not valid json", encoding="utf-8")
    loaded = GameSession.load_from_file(str(save_path))
    assert loaded.class_id == "wizard"
    assert any("backup" in msg.lower() for msg in loaded.messages)


def _town_npc(session: GameSession, role: NpcRole) -> int:
    for entity_id, npc in session.ecs.entities_with(Npc):
        on_map = session.ecs.get_component(entity_id, OnMap)
        if on_map is None:
            continue
        if on_map.kind == MapKind.TOWN and npc.role == role:
            return entity_id
    msg = f"Town NPC not found for role {role}"
    raise AssertionError(msg)
