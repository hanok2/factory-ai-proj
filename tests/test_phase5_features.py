from adom_clone.core.ecs.components import (
    BlocksMovement,
    ExperienceReward,
    Fighter,
    Item,
    Monster,
    OnMap,
    Position,
    RangedWeapon,
    StatusEffects,
)
from adom_clone.core.game.actions import (
    DisarmTrapAction,
    MoveAction,
    RangedAttackAction,
    RestAction,
)
from adom_clone.core.game.session import GameSession
from adom_clone.core.world.map_model import MapKind


def test_player_levels_up_after_xp_rewarded_kill() -> None:
    session = GameSession(seed=1337, class_id="fighter")
    before_level = session.player_progression.level
    before_max_hp = session.player_fighter.max_hp

    player_pos = session.player_position
    monster_id = session.ecs.create_entity()
    session.ecs.add_component(monster_id, Monster(name="training dummy"))
    session.ecs.add_component(monster_id, Fighter(max_hp=1, hp=1, power=0, defense=0))
    session.ecs.add_component(monster_id, Position(player_pos.x + 1, player_pos.y))
    session.ecs.add_component(monster_id, OnMap(kind=MapKind.OVERWORLD, depth=None))
    session.ecs.add_component(monster_id, BlocksMovement())
    session.ecs.add_component(monster_id, ExperienceReward(xp=50))
    session.ecs.add_component(monster_id, StatusEffects())

    session.queue_action(MoveAction(1, 0))
    session.advance_turn()

    assert session.player_progression.level > before_level
    assert session.player_fighter.max_hp > before_max_hp


def test_ranged_attack_hits_and_consumes_projectile() -> None:
    session = GameSession(seed=1337)
    player_pos = session.player_position

    projectile_id = session.ecs.create_entity()
    session.ecs.add_component(projectile_id, Item(name="test knife"))
    session.ecs.add_component(projectile_id, RangedWeapon(damage=5, range=5))
    session.player_inventory.item_ids.append(projectile_id)

    monster_id = session.ecs.create_entity()
    session.ecs.add_component(monster_id, Monster(name="target rat"))
    session.ecs.add_component(monster_id, Fighter(max_hp=2, hp=2, power=0, defense=0))
    session.ecs.add_component(monster_id, Position(player_pos.x + 3, player_pos.y))
    session.ecs.add_component(monster_id, OnMap(kind=MapKind.OVERWORLD, depth=None))
    session.ecs.add_component(monster_id, BlocksMovement())
    session.ecs.add_component(monster_id, ExperienceReward(xp=10))
    session.ecs.add_component(monster_id, StatusEffects())

    session.queue_action(RangedAttackAction(1, 0))
    session.advance_turn()

    assert projectile_id not in session.player_inventory.item_ids
    assert session.ecs.get_component(projectile_id, Item) is None
    assert session.ecs.get_component(monster_id, Monster) is None


def test_rest_is_interrupted_by_adjacent_monster_and_heals_when_safe() -> None:
    session = GameSession(seed=1337)
    session.player_fighter.hp -= 3
    hp_before_interrupt = session.player_fighter.hp

    player_pos = session.player_position
    monster_id = session.ecs.create_entity()
    session.ecs.add_component(monster_id, Monster(name="rat"))
    session.ecs.add_component(monster_id, Fighter(max_hp=3, hp=3, power=0, defense=0))
    session.ecs.add_component(monster_id, Position(player_pos.x + 1, player_pos.y))
    session.ecs.add_component(monster_id, OnMap(kind=MapKind.OVERWORLD, depth=None))
    session.ecs.add_component(monster_id, BlocksMovement())
    session.ecs.add_component(monster_id, ExperienceReward(xp=1))
    session.ecs.add_component(monster_id, StatusEffects())

    session.queue_action(RestAction())
    session.advance_turn()
    assert session.player_fighter.hp == hp_before_interrupt

    session.ecs.remove_component(monster_id, Monster)
    session.ecs.remove_component(monster_id, Fighter)
    session.ecs.remove_component(monster_id, Position)
    session.ecs.remove_component(monster_id, OnMap)
    session.ecs.remove_component(monster_id, BlocksMovement)
    session.ecs.remove_component(monster_id, ExperienceReward)
    session.ecs.remove_component(monster_id, StatusEffects)

    session.queue_action(RestAction())
    session.advance_turn()
    assert session.player_fighter.hp > hp_before_interrupt


def test_disarm_and_trigger_trap_interactions() -> None:
    session = GameSession(seed=1337)
    px, py = session.player_position.x, session.player_position.y

    trap_pos = (px + 1, py)
    session.current_map.trap_positions = {trap_pos}

    session.queue_action(DisarmTrapAction())
    session.advance_turn()
    assert trap_pos not in session.current_map.trap_positions

    session.current_map.trap_positions = {trap_pos}
    hp_before = session.player_fighter.hp
    session.queue_action(MoveAction(1, 0))
    session.advance_turn()

    assert trap_pos not in session.current_map.trap_positions
    assert session.player_fighter.hp < hp_before


def test_load_v2_save_migrates_to_v3() -> None:
    session = GameSession(seed=1337)
    save_data = session.to_save_data()
    save_data["version"] = 2
    save_data.pop("regen_counter", None)
    save_data.pop("trap_state", None)

    entities = save_data.get("entities")
    assert isinstance(entities, list)
    for raw_entity in entities:
        assert isinstance(raw_entity, dict)
        raw_entity.pop("progression", None)
        raw_entity.pop("status", None)
        raw_entity.pop("ranged", None)
        raw_entity.pop("xp_reward", None)

    loaded = GameSession.from_save_data(save_data)
    assert loaded.player_progression.level >= 1
    assert loaded.to_save_data()["version"] == 3
