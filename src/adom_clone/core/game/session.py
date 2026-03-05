from collections import deque

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
    def __init__(self) -> None:
        self.ecs = ECSStore()
        self.overworld = generate_overworld()
        self.dungeon = generate_dungeon()
        self.current_map: TileMap = self.overworld
        self.messages: list[str] = ["You arrive in the Drakalor wilderness."]
        self.game_over = False
        self._action_queue: deque[GameAction] = deque()

        self.player_entity = self.ecs.create_entity()
        self.ecs.add_component(self.player_entity, Player())
        self.ecs.add_component(self.player_entity, Position(2, 2))
        self.ecs.add_component(self.player_entity, OnMap(MapKind.OVERWORLD))
        self.ecs.add_component(self.player_entity, BlocksMovement())
        self.ecs.add_component(self.player_entity, Fighter(max_hp=20, hp=20, power=5, defense=1))
        self.ecs.add_component(self.player_entity, Inventory(capacity=10))

        self._spawn_initial_content()

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

    def queue_action(self, action: GameAction) -> None:
        self._action_queue.append(action)

    def advance_turn(self) -> None:
        if self.game_over or not self._action_queue:
            return

        action = self._action_queue.popleft()
        acted = self._apply_action(action)
        if acted and not self.game_over:
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
            self.messages.append("You wait.")
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
            self.messages.append("There is nothing to pick up.")
            return False

        inventory = self.player_inventory
        if len(inventory.item_ids) >= inventory.capacity:
            self.messages.append("Your inventory is full.")
            return False

        item_entity = item_entities[0]
        inventory.item_ids.append(item_entity)
        self.ecs.remove_component(item_entity, Position)
        self.ecs.remove_component(item_entity, OnMap)
        item = self.ecs.get_component(item_entity, Item)
        item_name = item.name if item is not None else "item"
        self.messages.append(f"You pick up {item_name}.")
        return True

    def _use_item(self, slot_index: int) -> bool:
        inventory = self.player_inventory
        if slot_index < 0 or slot_index >= len(inventory.item_ids):
            self.messages.append("No item in that slot.")
            return False

        item_entity = inventory.item_ids[slot_index]
        consumable = self.ecs.get_component(item_entity, Consumable)
        item = self.ecs.get_component(item_entity, Item)

        if consumable is None or item is None:
            self.messages.append("You can't use that item.")
            return False

        fighter = self.player_fighter
        before_hp = fighter.hp
        fighter.hp = min(fighter.max_hp, fighter.hp + consumable.heal_amount)
        healed = fighter.hp - before_hp

        inventory.item_ids.pop(slot_index)
        self._destroy_item(item_entity)

        if healed > 0:
            self.messages.append(f"You use {item.name} and recover {healed} HP.")
        else:
            self.messages.append(f"You use {item.name}, but nothing happens.")
        return True

    def _drop_last_item(self) -> bool:
        inventory = self.player_inventory
        if not inventory.item_ids:
            self.messages.append("You have nothing to drop.")
            return False

        item_entity = inventory.item_ids.pop()
        position = self.player_position
        self.ecs.add_component(item_entity, Position(position.x, position.y))
        self.ecs.add_component(item_entity, OnMap(self.current_map.kind))
        item = self.ecs.get_component(item_entity, Item)
        item_name = item.name if item is not None else "item"
        self.messages.append(f"You drop {item_name}.")
        return True

    def _run_monster_turns(self) -> None:
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
            self.messages.append(f"You hit {target_name} for {damage} damage.")
        elif defender == self.player_entity:
            monster = self.ecs.get_component(attacker, Monster)
            source_name = monster.name if monster is not None else "enemy"
            self.messages.append(f"{source_name} hits you for {damage} damage.")

        if defender_fighter.hp <= 0:
            self._handle_death(defender)

    def _handle_death(self, entity_id: int) -> None:
        if entity_id == self.player_entity:
            self.game_over = True
            self.messages.append("You die. Game over.")
            return

        monster = self.ecs.get_component(entity_id, Monster)
        name = monster.name if monster is not None else "monster"
        self.ecs.remove_component(entity_id, Monster)
        self.ecs.remove_component(entity_id, Fighter)
        self.ecs.remove_component(entity_id, BlocksMovement)
        self.ecs.remove_component(entity_id, Position)
        self.ecs.remove_component(entity_id, OnMap)
        self.messages.append(f"{name} dies.")

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

    def _handle_transition_if_needed(self) -> None:
        position = self.player_position
        on_map = self.player_map

        if self.current_map.kind == MapKind.OVERWORLD and self.overworld.entrance_pos is not None:
            if (position.x, position.y) == self.overworld.entrance_pos:
                self.current_map = self.dungeon
                on_map.kind = MapKind.DUNGEON
                position.x, position.y = (5, 5)
                self.messages.append("You descend into the dungeon.")
                return

        if self.current_map.kind == MapKind.DUNGEON and self.dungeon.exit_pos is not None:
            if (position.x, position.y) == self.dungeon.exit_pos:
                self.current_map = self.overworld
                on_map.kind = MapKind.OVERWORLD
                ox, oy = self.overworld.entrance_pos or (2, 2)
                position.x, position.y = (ox, oy + 1)
                self.messages.append("You return to the overworld.")
