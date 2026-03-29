import json
from pathlib import Path

from adom_clone.core.ecs.components import (
    BlocksMovement,
    Fighter,
    Monster,
    MonsterRole,
    Npc,
    NpcRole,
    OnMap,
    Position,
    StatusEffects,
)
from adom_clone.core.game.actions import InteractAction, MoveAction, WaitAction
from adom_clone.core.game.session import GameSession
from adom_clone.core.world.map_model import MapKind


def test_caster_role_ai_applies_control_effects_to_player() -> None:
    session = GameSession(seed=1337)

    caster_id = session.ecs.create_entity()
    session.ecs.add_component(
        caster_id,
        Monster(name="test caster", role=MonsterRole.CASTER, faction="arcane_order"),
    )
    session.ecs.add_component(caster_id, Fighter(max_hp=10, hp=10, power=2, defense=0))
    session.ecs.add_component(
        caster_id,
        Position(session.player_position.x + 3, session.player_position.y),
    )
    session.ecs.add_component(caster_id, OnMap(kind=MapKind.OVERWORLD, depth=None))
    session.ecs.add_component(caster_id, BlocksMovement())
    session.ecs.add_component(caster_id, StatusEffects())

    session.queue_action(WaitAction())
    session.advance_turn()

    assert session.player_status.confuse > 0 or session.player_status.fear > 0


def test_skirmisher_role_ai_attempts_disengage_when_adjacent() -> None:
    session = GameSession(seed=1337)
    sx = session.player_position.x + 1
    sy = session.player_position.y

    skirmisher_id = session.ecs.create_entity()
    session.ecs.add_component(
        skirmisher_id,
        Monster(name="test skirmisher", role=MonsterRole.SKIRMISHER),
    )
    session.ecs.add_component(skirmisher_id, Fighter(max_hp=9, hp=3, power=2, defense=0))
    session.ecs.add_component(skirmisher_id, Position(sx, sy))
    session.ecs.add_component(skirmisher_id, OnMap(kind=MapKind.OVERWORLD, depth=None))
    session.ecs.add_component(skirmisher_id, BlocksMovement())
    session.ecs.add_component(skirmisher_id, StatusEffects())

    session.queue_action(WaitAction())
    session.advance_turn()

    moved = session.ecs.get_component(skirmisher_id, Position)
    assert moved is not None
    assert abs(moved.x - session.player_position.x) + abs(moved.y - session.player_position.y) >= 2


def test_biome_spawn_profiles_filter_monsters_by_biome() -> None:
    session = GameSession(seed=1337, dungeon_level_count=3)

    depth_one_names = _monster_names_in_depth(session, 1)
    depth_two_names = _monster_names_in_depth(session, 2)

    # Fungal-only and molten-only entries should not leak into crypt depth.
    assert "clan shaman" not in depth_one_names
    assert "ember warlock" not in depth_one_names
    # Molten-only caster should not spawn in fungal biome depth.
    assert "ember warlock" not in depth_two_names


def test_reputation_gates_quest_unlocks() -> None:
    session = GameSession(seed=1337)
    _enter_town(session)

    quest_giver = _town_npc(session, NpcRole.QUEST_GIVER)
    quest_pos = session.ecs.get_component(quest_giver, Position)
    assert quest_pos is not None
    session.player_position.x, session.player_position.y = (quest_pos.x + 1, quest_pos.y)

    session.quest_state.quest_id = "arcane_anomaly"
    session.quest_state.accepted = False
    session.quest_state.completed = False
    session.quest_state.failed = False
    session.quest_state.turned_in = False
    session.quest_state.target_kills = 4
    session.faction_reputation["arcane_order"] = 2

    session.queue_action(InteractAction())
    session.advance_turn()
    assert not session.quest_state.accepted

    session.faction_reputation["arcane_order"] = 6
    session.queue_action(InteractAction())
    session.advance_turn()
    assert session.quest_state.accepted


def test_corruption_stage_progression_and_healer_reduction() -> None:
    session = GameSession(seed=1337)
    _enter_dungeon(session)

    session.player_corruption.value = 179
    session.queue_action(WaitAction())
    session.advance_turn()
    assert session.player_corruption.mutation == "void_sight"

    healer = _town_npc(session, NpcRole.HEALER)
    healer_component = session.ecs.get_component(healer, Npc)
    assert healer_component is not None
    session._interact_healer(healer_component)

    assert session.player_corruption.value < 180
    assert session.player_corruption.mutation in {"chaos_skin", None}


def test_secret_room_reveals_on_exploration() -> None:
    session = GameSession(seed=1337)
    _enter_dungeon(session)

    assert session.current_map.secret_rooms
    secret = next(iter(session.current_map.secret_rooms))
    session.player_position.x, session.player_position.y = (secret[0], max(1, secret[1] - 1))
    session.detect_nearby_secrets()

    assert secret in session.current_map.discovered_secrets


def test_diagnostics_are_category_tagged(tmp_path: Path) -> None:
    session = GameSession(seed=1337)
    save_path = tmp_path / "savegame.json"

    session.save_to_file(str(save_path))
    assert any(diag.startswith("[integrity]") for diag in session.save_diagnostics)

    session.save_to_file(str(save_path))
    payload = json.loads(save_path.read_text(encoding="utf-8"))
    payload["turn_count"] = int(payload.get("turn_count", 0)) + 7
    save_path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = GameSession.load_from_file(str(save_path))
    assert any(diag.startswith("[recovery]") for diag in loaded.save_diagnostics)


def _monster_names_in_depth(session: GameSession, depth: int) -> set[str]:
    names: set[str] = set()
    for entity_id, monster in session.ecs.entities_with(Monster):
        on_map = session.ecs.get_component(entity_id, OnMap)
        if on_map is None:
            continue
        if on_map.kind == MapKind.DUNGEON and on_map.depth == depth:
            names.add(monster.name)
    return names


def _enter_town(session: GameSession) -> None:
    town_pos = session.overworld.town_pos
    assert town_pos is not None
    tx, ty = town_pos
    session.player_position.x, session.player_position.y = (tx - 1, ty)
    session.queue_action(MoveAction(1, 0))
    session.advance_turn()
    assert session.current_map.kind == MapKind.TOWN


def _enter_dungeon(session: GameSession) -> None:
    entrance = session.overworld.entrance_pos
    assert entrance is not None
    ex, ey = entrance
    session.player_position.x, session.player_position.y = (ex - 1, ey)
    session.queue_action(MoveAction(1, 0))
    session.advance_turn()
    assert session.current_map.kind == MapKind.DUNGEON


def _town_npc(session: GameSession, role: NpcRole) -> int:
    for entity_id, npc in session.ecs.entities_with(Npc):
        on_map = session.ecs.get_component(entity_id, OnMap)
        if on_map is None:
            continue
        if on_map.kind == MapKind.TOWN and npc.role == role:
            return entity_id
    msg = f"Town NPC not found for role {role}"
    raise AssertionError(msg)
