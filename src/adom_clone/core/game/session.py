"""Game session orchestration for the ADOM-inspired vertical slice.

This module coordinates map state, ECS entities/components, turn processing,
combat, inventory interactions, and persistence.
"""

import json
from collections import deque
from pathlib import Path
from typing import cast

from adom_clone.core.ecs.components import (
    BlocksMovement,
    Consumable,
    Fighter,
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
from adom_clone.core.world.generators import generate_dungeon, generate_overworld
from adom_clone.core.world.map_model import MapKind, TileMap


class GameSession:
    """Owns runtime game state and applies queued player turns."""

    def __init__(self) -> None:
        self.ecs = ECSStore()
        self.overworld = generate_overworld()
        self.dungeon = generate_dungeon()
        self.current_map: TileMap = self.overworld
        self.messages: list[str] = []
        self.game_over = False
        self.turn_count = 0
        self.kill_count = 0
        self._action_queue: deque[GameAction] = deque()

        self.player_entity = self.ecs.create_entity()
        self.ecs.add_component(self.player_entity, Player())
        self.ecs.add_component(self.player_entity, Position(2, 2))
        self.ecs.add_component(self.player_entity, OnMap(MapKind.OVERWORLD))
        self.ecs.add_component(self.player_entity, BlocksMovement())
        self.ecs.add_component(self.player_entity, Fighter(max_hp=20, hp=20, power=5, defense=1))
        self.ecs.add_component(self.player_entity, Inventory(capacity=10))

        self._spawn_initial_content()
        self.add_message("You arrive in the Drakalor wilderness.")

    @property
    def player_position(self) -> Position:
        position = self.ecs.get_component(self.player_entity, Position)
        if position is None:
            msg = "Player entity is missing Position component."
            raise RuntimeError(msg)
        return position

    @property
    def player_fighter(self) -> Fighter:
        fighter = self.ecs.get_component(self.player_entity, Fighter)
        if fighter is None:
            msg = "Player entity is missing Fighter component."
            raise RuntimeError(msg)
        return fighter

    @property
    def player_inventory(self) -> Inventory:
        inventory = self.ecs.get_component(self.player_entity, Inventory)
        if inventory is None:
            msg = "Player entity is missing Inventory component."
            raise RuntimeError(msg)
        return inventory

    @property
    def player_map(self) -> OnMap:
        on_map = self.ecs.get_component(self.player_entity, OnMap)
        if on_map is None:
            msg = "Player entity is missing OnMap component."
            raise RuntimeError(msg)
        return on_map

    @property
    def player_hp_text(self) -> str:
        fighter = self.player_fighter
        return f"{fighter.hp}/{fighter.max_hp}"

    def add_message(self, text: str) -> None:
        """Append a UI message while keeping a bounded in-memory log."""
        self.messages.append(text)
        if len(self.messages) > 200:
            del self.messages[:-200]

    def queue_action(self, action: GameAction) -> None:
        self._action_queue.append(action)

    def advance_turn(self) -> None:
        """Advance one player action and then one monster phase."""
        if self.game_over or not self._action_queue:
            return

        action = self._action_queue.popleft()
        acted = self._apply_action(action)
        if acted and not self.game_over:
            self.turn_count += 1
            self._run_monster_turns()

    def _apply_action(self, action: GameAction) -> bool:
        if isinstance(action, MoveAction):
            return self._apply_move(action.dx, action.dy)
        if isinstance(action, PickupAction):
            return self._pickup_item()
        if isinstance(action, UseItemAction):
            return self._use_item(action.slot_index)
        if isinstance(action, DropLastItemAction):
            return self._drop_last_item()
        if isinstance(action, WaitAction):
            self.add_message("You wait.")
            return True
        return False

    def _apply_move(self, dx: int, dy: int) -> bool:
        position = self.player_position
        nx = position.x + dx
        ny = position.y + dy

        if not self.current_map.is_passable(nx, ny):
            return False

        blocker = self._blocking_entity_at(nx, ny, self.current_map.kind, self.player_entity)
        if blocker is not None:
            # Bumping into a hostile blocker resolves as a melee attack instead of movement.
            if self.ecs.get_component(blocker, Monster) is not None:
                self._attack(self.player_entity, blocker)
                return True
            return False

        position.x = nx
        position.y = ny
        self._handle_transition_if_needed()
        return True

    def _pickup_item(self) -> bool:
        position = self.player_position
        item_entities = self._items_at(self.current_map.kind, position.x, position.y)
        if not item_entities:
            self.add_message("There is nothing to pick up.")
            return False

        inventory = self.player_inventory
        if len(inventory.item_ids) >= inventory.capacity:
            self.add_message("Your inventory is full.")
            return False

        item_entity = item_entities[0]
        inventory.item_ids.append(item_entity)
        self.ecs.remove_component(item_entity, Position)
        self.ecs.remove_component(item_entity, OnMap)
        item = self.ecs.get_component(item_entity, Item)
        item_name = item.name if item is not None else "item"
        self.add_message(f"You pick up {item_name}.")
        return True

    def _use_item(self, slot_index: int) -> bool:
        inventory = self.player_inventory
        if slot_index < 0 or slot_index >= len(inventory.item_ids):
            self.add_message("No item in that slot.")
            return False

        item_entity = inventory.item_ids[slot_index]
        consumable = self.ecs.get_component(item_entity, Consumable)
        item = self.ecs.get_component(item_entity, Item)

        if consumable is None or item is None:
            self.add_message("You can't use that item.")
            return False

        fighter = self.player_fighter
        before_hp = fighter.hp
        fighter.hp = min(fighter.max_hp, fighter.hp + consumable.heal_amount)
        healed = fighter.hp - before_hp

        inventory.item_ids.pop(slot_index)
        self._destroy_item(item_entity)

        if healed > 0:
            self.add_message(f"You use {item.name} and recover {healed} HP.")
        else:
            self.add_message(f"You use {item.name}, but nothing happens.")
        return True

    def _drop_last_item(self) -> bool:
        inventory = self.player_inventory
        if not inventory.item_ids:
            self.add_message("You have nothing to drop.")
            return False

        item_entity = inventory.item_ids.pop()
        position = self.player_position
        self.ecs.add_component(item_entity, Position(position.x, position.y))
        self.ecs.add_component(item_entity, OnMap(self.current_map.kind))
        item = self.ecs.get_component(item_entity, Item)
        item_name = item.name if item is not None else "item"
        self.add_message(f"You drop {item_name}.")
        return True

    def _run_monster_turns(self) -> None:
        """Execute simple chase/attack AI for monsters on the active map."""
        player_position = self.player_position
        for entity_id, _monster in self.ecs.entities_with(Monster):
            if self.game_over:
                return

            position = self.ecs.get_component(entity_id, Position)
            on_map = self.ecs.get_component(entity_id, OnMap)
            fighter = self.ecs.get_component(entity_id, Fighter)
            if position is None or on_map is None or fighter is None or fighter.hp <= 0:
                continue
            if on_map.kind != self.current_map.kind:
                continue

            dist_x = player_position.x - position.x
            dist_y = player_position.y - position.y
            if abs(dist_x) + abs(dist_y) == 1:
                self._attack(entity_id, self.player_entity)
                continue

            for dx, dy in self._chase_directions(dist_x, dist_y):
                nx = position.x + dx
                ny = position.y + dy
                if not self.current_map.is_passable(nx, ny):
                    continue
                blocker = self._blocking_entity_at(nx, ny, self.current_map.kind, entity_id)
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

    def _attack(self, attacker: int, defender: int) -> None:
        attacker_fighter = self.ecs.get_component(attacker, Fighter)
        defender_fighter = self.ecs.get_component(defender, Fighter)
        if attacker_fighter is None or defender_fighter is None:
            return

        damage = max(1, attacker_fighter.power - defender_fighter.defense)
        defender_fighter.hp -= damage

        if attacker == self.player_entity:
            monster = self.ecs.get_component(defender, Monster)
            target_name = monster.name if monster is not None else "target"
            self.add_message(f"You hit {target_name} for {damage} damage.")
        elif defender == self.player_entity:
            monster = self.ecs.get_component(attacker, Monster)
            source_name = monster.name if monster is not None else "enemy"
            self.add_message(f"{source_name} hits you for {damage} damage.")

        if defender_fighter.hp <= 0:
            self._handle_death(defender)

    def _handle_death(self, entity_id: int) -> None:
        if entity_id == self.player_entity:
            self.game_over = True
            self.add_message("You die. Game over.")
            return

        monster = self.ecs.get_component(entity_id, Monster)
        name = monster.name if monster is not None else "monster"
        self.ecs.remove_component(entity_id, Monster)
        self.ecs.remove_component(entity_id, Fighter)
        self.ecs.remove_component(entity_id, BlocksMovement)
        self.ecs.remove_component(entity_id, Position)
        self.ecs.remove_component(entity_id, OnMap)
        self.kill_count += 1
        self.add_message(f"{name} dies.")

    def _blocking_entity_at(
        self,
        x: int,
        y: int,
        map_kind: MapKind,
        excluded_entity: int,
    ) -> int | None:
        for entity_id, _blocker in self.ecs.entities_with(BlocksMovement):
            if entity_id == excluded_entity:
                continue
            position = self.ecs.get_component(entity_id, Position)
            on_map = self.ecs.get_component(entity_id, OnMap)
            if position is None or on_map is None:
                continue
            if on_map.kind == map_kind and position.x == x and position.y == y:
                return entity_id
        return None

    def _items_at(self, map_kind: MapKind, x: int, y: int) -> list[int]:
        items: list[int] = []
        for entity_id, _item in self.ecs.entities_with(Item):
            position = self.ecs.get_component(entity_id, Position)
            on_map = self.ecs.get_component(entity_id, OnMap)
            if position is None or on_map is None:
                continue
            if on_map.kind == map_kind and position.x == x and position.y == y:
                items.append(entity_id)
        return items

    def _destroy_item(self, item_entity: int) -> None:
        self.ecs.remove_component(item_entity, Item)
        self.ecs.remove_component(item_entity, Consumable)
        self.ecs.remove_component(item_entity, Position)
        self.ecs.remove_component(item_entity, OnMap)

    def _spawn_initial_content(self) -> None:
        self._spawn_item(MapKind.OVERWORLD, 4, 2, "healing herb", heal_amount=4)
        self._spawn_monster(MapKind.DUNGEON, 8, 5, "giant rat", hp=8, power=3, defense=0)
        self._spawn_monster(MapKind.DUNGEON, 12, 10, "goblin", hp=12, power=4, defense=1)
        self._spawn_item(MapKind.DUNGEON, 6, 5, "small healing potion", heal_amount=6)
        self._spawn_item(MapKind.DUNGEON, 14, 8, "small healing potion", heal_amount=6)

    def _spawn_monster(
        self,
        map_kind: MapKind,
        x: int,
        y: int,
        name: str,
        hp: int,
        power: int,
        defense: int,
    ) -> None:
        entity_id = self.ecs.create_entity()
        self.ecs.add_component(entity_id, Monster(name=name))
        self.ecs.add_component(entity_id, Fighter(max_hp=hp, hp=hp, power=power, defense=defense))
        self.ecs.add_component(entity_id, Position(x, y))
        self.ecs.add_component(entity_id, OnMap(map_kind))
        self.ecs.add_component(entity_id, BlocksMovement())

    def _spawn_item(self, map_kind: MapKind, x: int, y: int, name: str, heal_amount: int) -> None:
        entity_id = self.ecs.create_entity()
        self.ecs.add_component(entity_id, Item(name=name))
        self.ecs.add_component(entity_id, Consumable(heal_amount=heal_amount))
        self.ecs.add_component(entity_id, Position(x, y))
        self.ecs.add_component(entity_id, OnMap(map_kind))

    def monster_positions(self) -> list[tuple[int, int]]:
        positions: list[tuple[int, int]] = []
        for entity_id, _monster in self.ecs.entities_with(Monster):
            position = self.ecs.get_component(entity_id, Position)
            on_map = self.ecs.get_component(entity_id, OnMap)
            if position is None or on_map is None:
                continue
            if on_map.kind == self.current_map.kind:
                positions.append((position.x, position.y))
        return positions

    def item_positions(self) -> list[tuple[int, int]]:
        positions: list[tuple[int, int]] = []
        for entity_id, _item in self.ecs.entities_with(Item):
            position = self.ecs.get_component(entity_id, Position)
            on_map = self.ecs.get_component(entity_id, OnMap)
            if position is None or on_map is None:
                continue
            if on_map.kind == self.current_map.kind:
                positions.append((position.x, position.y))
        return positions

    def inventory_names(self) -> list[str]:
        names: list[str] = []
        for item_id in self.player_inventory.item_ids:
            item = self.ecs.get_component(item_id, Item)
            if item is not None:
                names.append(item.name)
        return names

    def to_save_data(self) -> dict[str, object]:
        """Serialize the session into a JSON-friendly dictionary."""
        entities: list[dict[str, object]] = []
        for entity_id in self._serializable_entity_ids():
            entity_data: dict[str, object] = {"id": entity_id}

            if self.ecs.get_component(entity_id, Player) is not None:
                entity_data["player"] = True

            monster = self.ecs.get_component(entity_id, Monster)
            if monster is not None:
                entity_data["monster_name"] = monster.name

            position = self.ecs.get_component(entity_id, Position)
            if position is not None:
                entity_data["position"] = {"x": position.x, "y": position.y}

            on_map = self.ecs.get_component(entity_id, OnMap)
            if on_map is not None:
                entity_data["map_kind"] = on_map.kind.value

            if self.ecs.get_component(entity_id, BlocksMovement) is not None:
                entity_data["blocks_movement"] = True

            fighter = self.ecs.get_component(entity_id, Fighter)
            if fighter is not None:
                entity_data["fighter"] = {
                    "max_hp": fighter.max_hp,
                    "hp": fighter.hp,
                    "power": fighter.power,
                    "defense": fighter.defense,
                }

            inventory = self.ecs.get_component(entity_id, Inventory)
            if inventory is not None:
                entity_data["inventory"] = {
                    "capacity": inventory.capacity,
                    "item_ids": [*inventory.item_ids],
                }

            item = self.ecs.get_component(entity_id, Item)
            if item is not None:
                entity_data["item_name"] = item.name

            consumable = self.ecs.get_component(entity_id, Consumable)
            if consumable is not None:
                entity_data["consumable"] = {"heal_amount": consumable.heal_amount}

            entities.append(entity_data)

        return {
            "version": 1,
            "current_map": self.current_map.kind.value,
            "messages": [*self.messages],
            "game_over": self.game_over,
            "turn_count": self.turn_count,
            "kill_count": self.kill_count,
            "entities": entities,
        }

    def save_to_file(self, file_path: str) -> None:
        """Persist the current run to disk as compact JSON."""
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.to_save_data(), separators=(",", ":"))
        path.write_text(payload, encoding="utf-8")

    @classmethod
    def load_from_file(cls, file_path: str) -> "GameSession":
        """Load a saved run from disk."""
        path = Path(file_path)
        raw_data = json.loads(path.read_text(encoding="utf-8"))
        return cls.from_save_data(raw_data)

    @classmethod
    def from_save_data(cls, raw_data: object) -> "GameSession":
        """Rehydrate a game session from validated save data."""
        data = _expect_dict(raw_data, "save_data")

        session = cls()
        session.ecs = ECSStore()
        session._action_queue = deque()

        session.messages = _expect_str_list(data.get("messages", []), "messages")
        if not session.messages:
            session.messages = ["Loaded save."]

        session.game_over = _expect_bool(data.get("game_over", False), "game_over")
        session.turn_count = _expect_int(data.get("turn_count", 0), "turn_count")
        session.kill_count = _expect_int(data.get("kill_count", 0), "kill_count")
        current_map_kind = MapKind(_expect_str(data.get("current_map"), "current_map"))

        entities = _expect_list(data.get("entities", []), "entities")
        max_entity_id = 0
        player_entity: int | None = None

        for raw_entity in entities:
            entity_data = _expect_dict(raw_entity, "entity")
            entity_id = _expect_int(entity_data.get("id"), "entity.id")
            max_entity_id = max(max_entity_id, entity_id)

            # Rehydrate each supported component independently so save schema can evolve
            # without requiring rigid object snapshots.

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
            if map_kind_value is not None:
                session.ecs.add_component(
                    entity_id,
                    OnMap(kind=MapKind(_expect_str(map_kind_value, "entity.map_kind"))),
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
                        defense=_expect_int(
                            fighter_data.get("defense"),
                            "entity.fighter.defense",
                        ),
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

        if player_entity is None:
            msg = "Save data is missing player entity."
            raise ValueError(msg)

        session.player_entity = player_entity
        session.ecs.set_next_entity_id(max_entity_id + 1)
        session.current_map = (
            session.overworld if current_map_kind == MapKind.OVERWORLD else session.dungeon
        )

        player_map = session.ecs.get_component(session.player_entity, OnMap)
        if player_map is None:
            session.ecs.add_component(session.player_entity, OnMap(current_map_kind))
        else:
            player_map.kind = current_map_kind

        _ = session.player_position
        _ = session.player_fighter
        _ = session.player_inventory
        _ = session.player_map
        return session

    def _serializable_entity_ids(self) -> list[int]:
        """Collect all entity IDs that carry persisted gameplay components."""
        entity_ids = {self.player_entity}
        component_types: tuple[type[object], ...] = (
            Player,
            Monster,
            Position,
            OnMap,
            BlocksMovement,
            Fighter,
            Inventory,
            Item,
            Consumable,
        )
        for component_type in component_types:
            for entity_id, _ in self.ecs.entities_with(component_type):
                entity_ids.add(entity_id)
        return sorted(entity_ids)

    def _handle_transition_if_needed(self) -> None:
        position = self.player_position
        on_map = self.player_map

        if self.current_map.kind == MapKind.OVERWORLD and self.overworld.entrance_pos is not None:
            if (position.x, position.y) == self.overworld.entrance_pos:
                self.current_map = self.dungeon
                on_map.kind = MapKind.DUNGEON
                position.x, position.y = (5, 5)
                self.add_message("You descend into the dungeon.")
                return

        if self.current_map.kind == MapKind.DUNGEON and self.dungeon.exit_pos is not None:
            if (position.x, position.y) == self.dungeon.exit_pos:
                self.current_map = self.overworld
                on_map.kind = MapKind.OVERWORLD
                ox, oy = self.overworld.entrance_pos or (2, 2)
                position.x, position.y = (ox, oy + 1)
                self.add_message("You return to the overworld.")


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
