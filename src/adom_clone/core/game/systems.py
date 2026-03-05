"""Gameplay system modules used by GameSession."""

import json
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING, cast

from adom_clone.core.ecs.components import (
    BlocksMovement,
    Consumable,
    Equipment,
    EquipmentSlot,
    Equippable,
    Fighter,
    Food,
    Hunger,
    Inventory,
    Item,
    Monster,
    OnMap,
    Player,
    Position,
)
from adom_clone.core.ecs.store import ECSStore
from adom_clone.core.game.actions import (
    DropLastItemAction,
    GameAction,
    MoveAction,
    PickupAction,
    UseItemAction,
    WaitAction,
)
from adom_clone.core.world.map_model import MapKind

if TYPE_CHECKING:
    from adom_clone.core.game.session import GameSession


class TurnSystem:
    """Processes player action queue and advances turn state."""

    def advance_turn(self, session: "GameSession") -> None:
        if session.game_over or not session._action_queue:
            return

        action = session._action_queue.popleft()
        acted = self._apply_action(session, action)
        if not acted:
            return

        session.turn_count += 1
        session.tick_hunger()
        if not session.game_over:
            session.ai_system.run_monster_turns(session)

    def _apply_action(self, session: "GameSession", action: GameAction) -> bool:
        if isinstance(action, MoveAction):
            return session.apply_move(action.dx, action.dy)
        if isinstance(action, PickupAction):
            return session.inventory_system.pickup_item(session)
        if isinstance(action, UseItemAction):
            return session.inventory_system.use_item(session, action.slot_index)
        if isinstance(action, DropLastItemAction):
            return session.inventory_system.drop_last_item(session)
        if isinstance(action, WaitAction):
            session.add_message("You wait.")
            return True
        return False


class CombatSystem:
    """Resolves attacks and combat stat calculations."""

    def attack(self, session: "GameSession", attacker: int, defender: int) -> None:
        attacker_fighter = session.ecs.get_component(attacker, Fighter)
        defender_fighter = session.ecs.get_component(defender, Fighter)
        if attacker_fighter is None or defender_fighter is None:
            return

        damage = max(
            1,
            self.effective_power(session, attacker)
            - self.effective_defense(session, defender),
        )
        defender_fighter.hp -= damage

        if attacker == session.player_entity:
            monster = session.ecs.get_component(defender, Monster)
            target_name = monster.name if monster is not None else "target"
            session.add_message(f"You hit {target_name} for {damage} damage.")
        elif defender == session.player_entity:
            monster = session.ecs.get_component(attacker, Monster)
            source_name = monster.name if monster is not None else "enemy"
            session.add_message(f"{source_name} hits you for {damage} damage.")

        if defender_fighter.hp <= 0:
            session._handle_death(defender)

    def effective_power(self, session: "GameSession", entity_id: int) -> int:
        fighter = session.ecs.get_component(entity_id, Fighter)
        if fighter is None:
            return 0
        return fighter.power + self._power_bonus(session, entity_id)

    def effective_defense(self, session: "GameSession", entity_id: int) -> int:
        fighter = session.ecs.get_component(entity_id, Fighter)
        if fighter is None:
            return 0
        return fighter.defense + self._defense_bonus(session, entity_id)

    def _power_bonus(self, session: "GameSession", entity_id: int) -> int:
        equipment = session.ecs.get_component(entity_id, Equipment)
        if equipment is None or equipment.weapon_item_id is None:
            return 0
        equippable = session.ecs.get_component(equipment.weapon_item_id, Equippable)
        return 0 if equippable is None else equippable.power_bonus

    def _defense_bonus(self, session: "GameSession", entity_id: int) -> int:
        equipment = session.ecs.get_component(entity_id, Equipment)
        if equipment is None or equipment.armor_item_id is None:
            return 0
        equippable = session.ecs.get_component(equipment.armor_item_id, Equippable)
        return 0 if equippable is None else equippable.defense_bonus


class InventorySystem:
    """Handles item pickup/use/drop and equipment slot actions."""

    def pickup_item(self, session: "GameSession") -> bool:
        position = session.player_position
        item_entities = session.items_at(
            session.current_map.kind,
            session.current_depth,
            position.x,
            position.y,
        )
        if not item_entities:
            session.add_message("There is nothing to pick up.")
            return False

        inventory = session.player_inventory
        if len(inventory.item_ids) >= inventory.capacity:
            session.add_message("Your inventory is full.")
            return False

        item_entity = item_entities[0]
        inventory.item_ids.append(item_entity)
        session.ecs.remove_component(item_entity, Position)
        session.ecs.remove_component(item_entity, OnMap)
        item = session.ecs.get_component(item_entity, Item)
        item_name = item.name if item is not None else "item"
        session.add_message(f"You pick up {item_name}.")
        return True

    def use_item(self, session: "GameSession", slot_index: int) -> bool:
        inventory = session.player_inventory
        if slot_index < 0 or slot_index >= len(inventory.item_ids):
            session.add_message("No item in that slot.")
            return False

        item_entity = inventory.item_ids[slot_index]
        item = session.ecs.get_component(item_entity, Item)
        if item is None:
            session.add_message("That item is invalid.")
            return False

        food = session.ecs.get_component(item_entity, Food)
        if food is not None:
            hunger = session.player_hunger
            hunger.current = min(hunger.max_value, hunger.current + food.nutrition)
            inventory.item_ids.pop(slot_index)
            session.destroy_item(item_entity)
            session.add_message(f"You eat {item.name}.")
            return True

        consumable = session.ecs.get_component(item_entity, Consumable)
        if consumable is not None:
            fighter = session.player_fighter
            before_hp = fighter.hp
            fighter.hp = min(fighter.max_hp, fighter.hp + consumable.heal_amount)
            healed = fighter.hp - before_hp
            inventory.item_ids.pop(slot_index)
            session.destroy_item(item_entity)
            if healed > 0:
                session.add_message(f"You use {item.name} and recover {healed} HP.")
            else:
                session.add_message(f"You use {item.name}, but nothing happens.")
            return True

        equippable = session.ecs.get_component(item_entity, Equippable)
        if equippable is not None:
            return self._toggle_equip_item(session, item_entity, item)

        session.add_message("You can't use that item.")
        return False

    def drop_last_item(self, session: "GameSession") -> bool:
        inventory = session.player_inventory
        if not inventory.item_ids:
            session.add_message("You have nothing to drop.")
            return False

        item_entity = inventory.item_ids.pop()
        item = session.ecs.get_component(item_entity, Item)
        item_name = item.name if item is not None else "item"
        self._unequip_if_equipped(session, item_entity)

        position = session.player_position
        session.ecs.add_component(item_entity, Position(position.x, position.y))
        session.ecs.add_component(
            item_entity,
            OnMap(kind=session.current_map.kind, depth=session.current_depth),
        )
        session.add_message(f"You drop {item_name}.")
        return True

    def _toggle_equip_item(self, session: "GameSession", item_entity: int, item: Item) -> bool:
        equipment = session.player_equipment
        equippable = session.ecs.get_component(item_entity, Equippable)
        if equippable is None:
            return False

        if equippable.slot == EquipmentSlot.WEAPON:
            if equipment.weapon_item_id == item_entity:
                equipment.weapon_item_id = None
                session.add_message(f"You unequip {item.name}.")
                return True
            equipment.weapon_item_id = item_entity
            session.add_message(f"You equip {item.name}.")
            return True

        if equippable.slot == EquipmentSlot.ARMOR:
            if equipment.armor_item_id == item_entity:
                equipment.armor_item_id = None
                session.add_message(f"You remove {item.name}.")
                return True
            equipment.armor_item_id = item_entity
            session.add_message(f"You equip {item.name}.")
            return True

        return False

    def _unequip_if_equipped(self, session: "GameSession", item_entity: int) -> None:
        equipment = session.player_equipment
        if equipment.weapon_item_id == item_entity:
            equipment.weapon_item_id = None
        if equipment.armor_item_id == item_entity:
            equipment.armor_item_id = None


class AISystem:
    """Simple deterministic chase-and-attack monster AI."""

    def run_monster_turns(self, session: "GameSession") -> None:
        player_position = session.player_position
        for entity_id, _monster in session.ecs.entities_with(Monster):
            if session.game_over:
                return

            position = session.ecs.get_component(entity_id, Position)
            on_map = session.ecs.get_component(entity_id, OnMap)
            fighter = session.ecs.get_component(entity_id, Fighter)
            if position is None or on_map is None or fighter is None or fighter.hp <= 0:
                continue
            if on_map.kind != session.current_map.kind or on_map.depth != session.current_depth:
                continue

            dist_x = player_position.x - position.x
            dist_y = player_position.y - position.y
            if abs(dist_x) + abs(dist_y) == 1:
                session.combat_system.attack(session, entity_id, session.player_entity)
                continue

            for dx, dy in self._chase_directions(dist_x, dist_y):
                nx = position.x + dx
                ny = position.y + dy
                if not session.current_map.is_passable(nx, ny):
                    continue
                blocker = session.blocking_entity_at(
                    nx,
                    ny,
                    session.current_map.kind,
                    session.current_depth,
                    entity_id,
                )
                if blocker is None:
                    position.x = nx
                    position.y = ny
                    break

    def _chase_directions(self, dist_x: int, dist_y: int) -> list[tuple[int, int]]:
        step_x = 0 if dist_x == 0 else (1 if dist_x > 0 else -1)
        step_y = 0 if dist_y == 0 else (1 if dist_y > 0 else -1)

        if abs(dist_x) >= abs(dist_y):
            return [(step_x, 0), (0, step_y)]
        return [(0, step_y), (step_x, 0)]


class PersistenceSystem:
    """Serializes and rehydrates game state."""

    def to_save_data(self, session: "GameSession") -> dict[str, object]:
        entities: list[dict[str, object]] = []
        for entity_id in session.serializable_entity_ids():
            entity_data: dict[str, object] = {"id": entity_id}

            if session.ecs.get_component(entity_id, Player) is not None:
                entity_data["player"] = True

            monster = session.ecs.get_component(entity_id, Monster)
            if monster is not None:
                entity_data["monster_name"] = monster.name

            position = session.ecs.get_component(entity_id, Position)
            if position is not None:
                entity_data["position"] = {"x": position.x, "y": position.y}

            on_map = session.ecs.get_component(entity_id, OnMap)
            if on_map is not None:
                entity_data["map_kind"] = on_map.kind.value
                entity_data["map_depth"] = on_map.depth

            if session.ecs.get_component(entity_id, BlocksMovement) is not None:
                entity_data["blocks_movement"] = True

            fighter = session.ecs.get_component(entity_id, Fighter)
            if fighter is not None:
                entity_data["fighter"] = {
                    "max_hp": fighter.max_hp,
                    "hp": fighter.hp,
                    "power": fighter.power,
                    "defense": fighter.defense,
                }

            inventory = session.ecs.get_component(entity_id, Inventory)
            if inventory is not None:
                entity_data["inventory"] = {
                    "capacity": inventory.capacity,
                    "item_ids": [*inventory.item_ids],
                }

            equipment = session.ecs.get_component(entity_id, Equipment)
            if equipment is not None:
                entity_data["equipment"] = {
                    "weapon_item_id": equipment.weapon_item_id,
                    "armor_item_id": equipment.armor_item_id,
                }

            hunger = session.ecs.get_component(entity_id, Hunger)
            if hunger is not None:
                entity_data["hunger"] = {
                    "current": hunger.current,
                    "max_value": hunger.max_value,
                }

            item = session.ecs.get_component(entity_id, Item)
            if item is not None:
                entity_data["item_name"] = item.name

            consumable = session.ecs.get_component(entity_id, Consumable)
            if consumable is not None:
                entity_data["consumable"] = {"heal_amount": consumable.heal_amount}

            equippable = session.ecs.get_component(entity_id, Equippable)
            if equippable is not None:
                entity_data["equippable"] = {
                    "slot": equippable.slot.value,
                    "power_bonus": equippable.power_bonus,
                    "defense_bonus": equippable.defense_bonus,
                }

            food = session.ecs.get_component(entity_id, Food)
            if food is not None:
                entity_data["food"] = {"nutrition": food.nutrition}

            entities.append(entity_data)

        return {
            "version": 2,
            "seed": session.seed,
            "race_id": session.race_id,
            "class_id": session.class_id,
            "dungeon_level_count": session.dungeon_level_count,
            "current_map": session.current_map.kind.value,
            "current_depth": session.current_depth,
            "messages": [*session.messages],
            "game_over": session.game_over,
            "turn_count": session.turn_count,
            "kill_count": session.kill_count,
            "entities": entities,
        }

    def save_to_file(self, session: "GameSession", file_path: str) -> None:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.to_save_data(session), separators=(",", ":"))
        path.write_text(payload, encoding="utf-8")

    def load_from_file(self, file_path: str) -> "GameSession":
        path = Path(file_path)
        raw_data = json.loads(path.read_text(encoding="utf-8"))
        return self.from_save_data(raw_data)

    def from_save_data(self, raw_data: object) -> "GameSession":
        from adom_clone.core.game.session import GameSession

        data = _expect_dict(raw_data, "save_data")

        seed = _expect_int(data.get("seed", 1337), "seed")
        race_id = _expect_str(data.get("race_id", "human"), "race_id")
        class_id = _expect_str(data.get("class_id", "fighter"), "class_id")
        dungeon_level_count = _expect_int(data.get("dungeon_level_count", 3), "dungeon_level_count")

        session = GameSession(
            seed=seed,
            race_id=race_id,
            class_id=class_id,
            dungeon_level_count=dungeon_level_count,
        )
        session.ecs = ECSStore()
        session._action_queue = deque()

        session.messages = _expect_str_list(data.get("messages", []), "messages")
        if not session.messages:
            session.messages = ["Loaded save."]

        session.game_over = _expect_bool(data.get("game_over", False), "game_over")
        session.turn_count = _expect_int(data.get("turn_count", 0), "turn_count")
        session.kill_count = _expect_int(data.get("kill_count", 0), "kill_count")
        current_map_kind = MapKind(_expect_str(data.get("current_map"), "current_map"))
        current_depth_raw = data.get("current_depth")
        current_depth = (
            None
            if current_depth_raw is None
            else _expect_int(current_depth_raw, "current_depth")
        )

        entities = _expect_list(data.get("entities", []), "entities")
        max_entity_id = 0
        player_entity: int | None = None

        for raw_entity in entities:
            entity_data = _expect_dict(raw_entity, "entity")
            entity_id = _expect_int(entity_data.get("id"), "entity.id")
            max_entity_id = max(max_entity_id, entity_id)

            if _expect_bool(entity_data.get("player", False), "entity.player"):
                session.ecs.add_component(entity_id, Player())
                player_entity = entity_id

            monster_name = entity_data.get("monster_name")
            if monster_name is not None:
                session.ecs.add_component(
                    entity_id,
                    Monster(name=_expect_str(monster_name, "entity.monster_name")),
                )

            raw_position = entity_data.get("position")
            if raw_position is not None:
                position_data = _expect_dict(raw_position, "entity.position")
                session.ecs.add_component(
                    entity_id,
                    Position(
                        x=_expect_int(position_data.get("x"), "entity.position.x"),
                        y=_expect_int(position_data.get("y"), "entity.position.y"),
                    ),
                )

            map_kind_value = entity_data.get("map_kind")
            map_depth_value = entity_data.get("map_depth")
            if map_kind_value is not None:
                depth = (
                    None
                    if map_depth_value is None
                    else _expect_int(map_depth_value, "entity.map_depth")
                )
                session.ecs.add_component(
                    entity_id,
                    OnMap(
                        kind=MapKind(_expect_str(map_kind_value, "entity.map_kind")),
                        depth=depth,
                    ),
                )

            if _expect_bool(entity_data.get("blocks_movement", False), "entity.blocks_movement"):
                session.ecs.add_component(entity_id, BlocksMovement())

            raw_fighter = entity_data.get("fighter")
            if raw_fighter is not None:
                fighter_data = _expect_dict(raw_fighter, "entity.fighter")
                session.ecs.add_component(
                    entity_id,
                    Fighter(
                        max_hp=_expect_int(fighter_data.get("max_hp"), "entity.fighter.max_hp"),
                        hp=_expect_int(fighter_data.get("hp"), "entity.fighter.hp"),
                        power=_expect_int(fighter_data.get("power"), "entity.fighter.power"),
                        defense=_expect_int(fighter_data.get("defense"), "entity.fighter.defense"),
                    ),
                )

            raw_inventory = entity_data.get("inventory")
            if raw_inventory is not None:
                inventory_data = _expect_dict(raw_inventory, "entity.inventory")
                session.ecs.add_component(
                    entity_id,
                    Inventory(
                        capacity=_expect_int(
                            inventory_data.get("capacity"),
                            "entity.inventory.capacity",
                        ),
                        item_ids=_expect_int_list(
                            inventory_data.get("item_ids", []),
                            "entity.inventory.item_ids",
                        ),
                    ),
                )

            raw_equipment = entity_data.get("equipment")
            if raw_equipment is not None:
                equipment_data = _expect_dict(raw_equipment, "entity.equipment")
                weapon_item_raw = equipment_data.get("weapon_item_id")
                armor_item_raw = equipment_data.get("armor_item_id")
                session.ecs.add_component(
                    entity_id,
                    Equipment(
                        weapon_item_id=None
                        if weapon_item_raw is None
                        else _expect_int(weapon_item_raw, "entity.equipment.weapon_item_id"),
                        armor_item_id=None
                        if armor_item_raw is None
                        else _expect_int(armor_item_raw, "entity.equipment.armor_item_id"),
                    ),
                )

            raw_hunger = entity_data.get("hunger")
            if raw_hunger is not None:
                hunger_data = _expect_dict(raw_hunger, "entity.hunger")
                session.ecs.add_component(
                    entity_id,
                    Hunger(
                        current=_expect_int(hunger_data.get("current"), "entity.hunger.current"),
                        max_value=_expect_int(
                            hunger_data.get("max_value"),
                            "entity.hunger.max_value",
                        ),
                    ),
                )

            item_name = entity_data.get("item_name")
            if item_name is not None:
                session.ecs.add_component(
                    entity_id,
                    Item(name=_expect_str(item_name, "entity.item_name")),
                )

            raw_consumable = entity_data.get("consumable")
            if raw_consumable is not None:
                consumable_data = _expect_dict(raw_consumable, "entity.consumable")
                session.ecs.add_component(
                    entity_id,
                    Consumable(
                        heal_amount=_expect_int(
                            consumable_data.get("heal_amount"),
                            "entity.consumable.heal_amount",
                        ),
                    ),
                )

            raw_equippable = entity_data.get("equippable")
            if raw_equippable is not None:
                equippable_data = _expect_dict(raw_equippable, "entity.equippable")
                session.ecs.add_component(
                    entity_id,
                    Equippable(
                        slot=EquipmentSlot(
                            _expect_str(equippable_data.get("slot"), "entity.equippable.slot"),
                        ),
                        power_bonus=_expect_int(
                            equippable_data.get("power_bonus", 0),
                            "entity.equippable.power_bonus",
                        ),
                        defense_bonus=_expect_int(
                            equippable_data.get("defense_bonus", 0),
                            "entity.equippable.defense_bonus",
                        ),
                    ),
                )

            raw_food = entity_data.get("food")
            if raw_food is not None:
                food_data = _expect_dict(raw_food, "entity.food")
                session.ecs.add_component(
                    entity_id,
                    Food(
                        nutrition=_expect_int(
                            food_data.get("nutrition"),
                            "entity.food.nutrition",
                        ),
                    ),
                )

        if player_entity is None:
            msg = "Save data is missing player entity."
            raise ValueError(msg)

        session.player_entity = player_entity
        session.ecs.set_next_entity_id(max_entity_id + 1)

        if current_map_kind == MapKind.OVERWORLD:
            session.current_map = session.overworld
            session.current_depth = None
        else:
            dungeon_depth = 1 if current_depth is None else current_depth
            session.current_map = session.dungeon_levels[dungeon_depth - 1]
            session.current_depth = dungeon_depth

        player_map = session.ecs.get_component(session.player_entity, OnMap)
        if player_map is None:
            session.ecs.add_component(
                session.player_entity,
                OnMap(kind=current_map_kind, depth=current_depth),
            )
        else:
            player_map.kind = current_map_kind
            player_map.depth = current_depth

        _ = session.player_position
        _ = session.player_fighter
        _ = session.player_inventory
        _ = session.player_hunger
        _ = session.player_equipment
        return session


def _expect_dict(value: object, field_name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        msg = f"{field_name} must be an object."
        raise ValueError(msg)
    return cast(dict[str, object], value)


def _expect_list(value: object, field_name: str) -> list[object]:
    if not isinstance(value, list):
        msg = f"{field_name} must be an array."
        raise ValueError(msg)
    return value


def _expect_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        msg = f"{field_name} must be a string."
        raise ValueError(msg)
    return value


def _expect_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        msg = f"{field_name} must be an integer."
        raise ValueError(msg)
    return value


def _expect_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        msg = f"{field_name} must be a boolean."
        raise ValueError(msg)
    return value


def _expect_str_list(value: object, field_name: str) -> list[str]:
    raw_list = _expect_list(value, field_name)
    result: list[str] = []
    for idx, item in enumerate(raw_list):
        result.append(_expect_str(item, f"{field_name}[{idx}]"))
    return result


def _expect_int_list(value: object, field_name: str) -> list[int]:
    raw_list = _expect_list(value, field_name)
    result: list[int] = []
    for idx, item in enumerate(raw_list):
        result.append(_expect_int(item, f"{field_name}[{idx}]"))
    return result
