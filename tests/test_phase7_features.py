import json
from pathlib import Path

from adom_clone.core.ecs.components import (
    BlocksMovement,
    DamageType,
    Fighter,
    Monster,
    Npc,
    NpcRole,
    OnMap,
    Position,
    StatusEffects,
)
from adom_clone.core.game.actions import (
    CastVenomLanceAction,
    CastWardAction,
    InteractAction,
    MoveAction,
    SelectTalentAction,
    WaitAction,
)
from adom_clone.core.game.session import GameSession
from adom_clone.core.world.generators import generate_dungeon_levels
from adom_clone.core.world.map_model import MapKind


def test_talent_tree_restrictions_and_prerequisites() -> None:
    session = GameSession(seed=1337, class_id="fighter")
    session.player_talents.points = 2

    options = dict(session.available_talent_options())
    assert "hardened" in options
    assert "chain_bolt" not in options

    session.queue_action(SelectTalentAction("steel_bulwark"))
    session.advance_turn()
    assert "steel_bulwark" not in session.player_talents.selected

    session.queue_action(SelectTalentAction("hardened"))
    session.advance_turn()
    session.queue_action(SelectTalentAction("steel_bulwark"))
    session.advance_turn()
    assert "steel_bulwark" in session.player_talents.selected


def test_venom_lance_applies_poison_and_uses_mana() -> None:
    session = GameSession(seed=1337, class_id="thief")
    start_mana = session.player_mana.current

    target_id = session.ecs.create_entity()
    session.ecs.add_component(target_id, Monster(name="venom target"))
    session.ecs.add_component(target_id, Fighter(max_hp=20, hp=20, power=0, defense=0))
    session.ecs.add_component(target_id, StatusEffects())
    session.ecs.add_component(
        target_id,
        Position(session.player_position.x + 2, session.player_position.y),
    )
    session.ecs.add_component(target_id, OnMap(kind=MapKind.OVERWORLD, depth=None))
    session.ecs.add_component(target_id, BlocksMovement())

    session.queue_action(CastVenomLanceAction(1, 0))
    session.advance_turn()

    target_stats = session.ecs.get_component(target_id, Fighter)
    target_status = session.ecs.get_component(target_id, StatusEffects)
    assert target_stats is not None
    assert target_status is not None
    assert target_stats.hp < 20
    assert target_status.poison > 0
    assert session.player_mana.current < start_mana


def test_ward_temporarily_reduces_incoming_damage() -> None:
    session = GameSession(seed=1337, class_id="wizard")
    session.queue_action(CastWardAction())
    session.advance_turn()

    hp_before = session.player_fighter.hp
    actual, _mitigated = session.apply_damage(
        session.player_entity,
        10,
        DamageType.ARCANE,
        source="test",
    )
    assert actual < 10
    assert session.player_fighter.hp == hp_before - actual


def test_quest_timeout_reduces_reputation() -> None:
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

    session.turn_count = session.quest_state.deadline_turn + 1
    session.tick_quest_timers()
    assert session.quest_state.failed
    assert session.faction_reputation["townfolk"] < 0


def test_corruption_mutation_triggers_in_dungeon() -> None:
    session = GameSession(seed=1337)
    entrance = session.overworld.entrance_pos
    assert entrance is not None

    ex, ey = entrance
    session.player_position.x, session.player_position.y = (ex - 1, ey)
    session.queue_action(MoveAction(1, 0))
    session.advance_turn()
    assert session.current_map.kind == MapKind.DUNGEON

    session.player_corruption.value = 99
    session.queue_action(WaitAction())
    session.advance_turn()

    assert session.player_corruption.mutation == "chaos_skin"
    assert session.player_resistances.arcane_pct >= 15


def test_biome_archetype_and_vault_metadata() -> None:
    levels = generate_dungeon_levels(level_count=3, seed=1337)

    assert levels[0].biome == "crypt"
    assert levels[1].biome == "fungal_caves"
    assert levels[2].biome == "molten_ruins"

    for tile_map in levels:
        assert tile_map.room_archetype in {"chamber", "crossroads", "split_halls"}
        assert tile_map.vault_pos is not None


def test_checksum_mismatch_recovers_from_backup(tmp_path: Path) -> None:
    session = GameSession(seed=1337, class_id="wizard")
    save_path = tmp_path / "savegame.json"

    session.save_to_file(str(save_path))
    session.save_to_file(str(save_path))

    payload = json.loads(save_path.read_text(encoding="utf-8"))
    payload["turn_count"] = int(payload.get("turn_count", 0)) + 5
    save_path.write_text(json.dumps(payload), encoding="utf-8")

    loaded = GameSession.load_from_file(str(save_path))
    assert any("Primary save invalid" in diag for diag in loaded.save_diagnostics)
    assert any("Recovered from backup" in diag for diag in loaded.save_diagnostics)


def _town_npc(session: GameSession, role: NpcRole) -> int:
    for entity_id, npc in session.ecs.entities_with(Npc):
        on_map = session.ecs.get_component(entity_id, OnMap)
        if on_map is None:
            continue
        if on_map.kind == MapKind.TOWN and npc.role == role:
            return entity_id
    msg = f"Town NPC not found for role {role}"
    raise AssertionError(msg)
