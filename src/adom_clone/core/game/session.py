"""Game session orchestration for the ADOM-inspired vertical slice."""

import random
from collections import deque
from dataclasses import dataclass

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
from adom_clone.core.game.actions import GameAction
from adom_clone.core.game.content import (
    ClassDefinition,
    ItemTemplate,
    MonsterTemplate,
    RaceDefinition,
    SpawnRule,
    load_character_content,
    load_spawn_content,
)
from adom_clone.core.game.systems import (
    AISystem,
    CombatSystem,
    InventorySystem,
    PersistenceSystem,
    TurnSystem,
)
from adom_clone.core.world.generators import generate_dungeon_levels, generate_overworld
from adom_clone.core.world.map_model import MapKind, TileMap


@dataclass(frozen=True)
class CharacterSelection:
    race_id: str
    class_id: str
    seed: int


class GameSession:
    """Owns runtime game state and delegates behavior to domain systems."""

    def __init__(
        self,
        seed: int = 1337,
        race_id: str = "human",
        class_id: str = "fighter",
        dungeon_level_count: int = 3,
    ) -> None:
        self.seed = seed
        self.rng = random.Random(seed)

        races, classes = load_character_content()
        self.spawn_content = load_spawn_content()
        self.race = _find_race(races, race_id)
        self.character_class = _find_class(classes, class_id)
        self.race_id = self.race.id
        self.class_id = self.character_class.id

        self.ecs = ECSStore()
        self.overworld = generate_overworld()
        self.dungeon_levels = generate_dungeon_levels(dungeon_level_count, seed)
        self.dungeon = self.dungeon_levels[0]
        self.current_map: TileMap = self.overworld
        self.current_depth: int | None = None

        self.messages: list[str] = []
        self.game_over = False
        self.turn_count = 0
        self.kill_count = 0
        self._action_queue: deque[GameAction] = deque()

        self.turn_system = TurnSystem()
        self.combat_system = CombatSystem()
        self.inventory_system = InventorySystem()
        self.ai_system = AISystem()
        self.persistence_system = PersistenceSystem()

        self.player_entity = self.ecs.create_entity()
        self._spawn_player()
        self._spawn_world_content()
        self._grant_starting_loadout()

        self.add_message(
            (
                f"You begin your journey as a {self.race.name} "
                f"{self.character_class.name} (seed {self.seed})."
            ),
        )

    @property
    def dungeon_level_count(self) -> int:
        return len(self.dungeon_levels)

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
    def player_hunger(self) -> Hunger:
        hunger = self.ecs.get_component(self.player_entity, Hunger)
        if hunger is None:
            msg = "Player entity is missing Hunger component."
            raise RuntimeError(msg)
        return hunger

    @property
    def player_equipment(self) -> Equipment:
        equipment = self.ecs.get_component(self.player_entity, Equipment)
        if equipment is None:
            msg = "Player entity is missing Equipment component."
            raise RuntimeError(msg)
        return equipment

    @property
    def player_hp_text(self) -> str:
        fighter = self.player_fighter
        return f"{fighter.hp}/{fighter.max_hp}"

    @property
    def player_hunger_text(self) -> str:
        hunger = self.player_hunger
        return f"{hunger.current}/{hunger.max_value}"

    @property
    def player_power(self) -> int:
        return self.combat_system.effective_power(self, self.player_entity)

    @property
    def player_defense(self) -> int:
        return self.combat_system.effective_defense(self, self.player_entity)

    def add_message(self, text: str) -> None:
        self.messages.append(text)
        if len(self.messages) > 250:
            del self.messages[:-250]

    def queue_action(self, action: GameAction) -> None:
        self._action_queue.append(action)

    def advance_turn(self) -> None:
        self.turn_system.advance_turn(self)

    def tick_hunger(self) -> None:
        hunger = self.player_hunger
        hunger.current -= 1

        if hunger.current in (80, 50, 25, 10):
            self.add_message("You feel hungry.")
        if hunger.current <= 0:
            fighter = self.player_fighter
            fighter.hp -= 1
            self.add_message("You are starving!")
            if fighter.hp <= 0:
                self._handle_death(self.player_entity)

    def apply_move(self, dx: int, dy: int) -> bool:
        position = self.player_position
        nx = position.x + dx
        ny = position.y + dy

        if not self.current_map.is_passable(nx, ny):
            return False

        blocker = self.blocking_entity_at(
            nx,
            ny,
            self.current_map.kind,
            self.current_depth,
            self.player_entity,
        )
        if blocker is not None:
            if self.ecs.get_component(blocker, Monster) is not None:
                self.combat_system.attack(self, self.player_entity, blocker)
                return True
            return False

        position.x = nx
        position.y = ny
        self._handle_transition_if_needed()
        return True

    def blocking_entity_at(
        self,
        x: int,
        y: int,
        map_kind: MapKind,
        depth: int | None,
        excluded_entity: int,
    ) -> int | None:
        for entity_id, _blocker in self.ecs.entities_with(BlocksMovement):
            if entity_id == excluded_entity:
                continue
            position = self.ecs.get_component(entity_id, Position)
            on_map = self.ecs.get_component(entity_id, OnMap)
            if position is None or on_map is None:
                continue
            if (
                on_map.kind == map_kind
                and on_map.depth == depth
                and position.x == x
                and position.y == y
            ):
                return entity_id
        return None

    def items_at(self, map_kind: MapKind, depth: int | None, x: int, y: int) -> list[int]:
        items: list[int] = []
        for entity_id, _item in self.ecs.entities_with(Item):
            position = self.ecs.get_component(entity_id, Position)
            on_map = self.ecs.get_component(entity_id, OnMap)
            if position is None or on_map is None:
                continue
            if (
                on_map.kind == map_kind
                and on_map.depth == depth
                and position.x == x
                and position.y == y
            ):
                items.append(entity_id)
        return items

    def destroy_item(self, item_entity: int) -> None:
        self.ecs.remove_component(item_entity, Item)
        self.ecs.remove_component(item_entity, Consumable)
        self.ecs.remove_component(item_entity, Equippable)
        self.ecs.remove_component(item_entity, Food)
        self.ecs.remove_component(item_entity, Position)
        self.ecs.remove_component(item_entity, OnMap)

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

    def serializable_entity_ids(self) -> list[int]:
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
            Equippable,
            Equipment,
            Food,
            Hunger,
        )
        for component_type in component_types:
            for entity_id, _ in self.ecs.entities_with(component_type):
                entity_ids.add(entity_id)
        return sorted(entity_ids)

    def to_save_data(self) -> dict[str, object]:
        return self.persistence_system.to_save_data(self)

    def save_to_file(self, file_path: str) -> None:
        self.persistence_system.save_to_file(self, file_path)

    @classmethod
    def load_from_file(cls, file_path: str) -> "GameSession":
        return PersistenceSystem().load_from_file(file_path)

    @classmethod
    def from_save_data(cls, raw_data: object) -> "GameSession":
        return PersistenceSystem().from_save_data(raw_data)

    def monster_positions(self) -> list[tuple[int, int]]:
        positions: list[tuple[int, int]] = []
        for entity_id, _monster in self.ecs.entities_with(Monster):
            position = self.ecs.get_component(entity_id, Position)
            on_map = self.ecs.get_component(entity_id, OnMap)
            if position is None or on_map is None:
                continue
            if on_map.kind == self.current_map.kind and on_map.depth == self.current_depth:
                positions.append((position.x, position.y))
        return positions

    def item_positions(self) -> list[tuple[int, int]]:
        positions: list[tuple[int, int]] = []
        for entity_id, _item in self.ecs.entities_with(Item):
            position = self.ecs.get_component(entity_id, Position)
            on_map = self.ecs.get_component(entity_id, OnMap)
            if position is None or on_map is None:
                continue
            if on_map.kind == self.current_map.kind and on_map.depth == self.current_depth:
                positions.append((position.x, position.y))
        return positions

    def inventory_names(self) -> list[str]:
        names: list[str] = []
        equipment = self.player_equipment
        for item_id in self.player_inventory.item_ids:
            item = self.ecs.get_component(item_id, Item)
            if item is None:
                continue
            suffix = ""
            if equipment.weapon_item_id == item_id:
                suffix = " (wielded)"
            if equipment.armor_item_id == item_id:
                suffix = " (worn)"
            names.append(f"{item.name}{suffix}")
        return names

    def map_for_depth(self, depth: int | None) -> TileMap:
        if depth is None:
            return self.overworld
        clamped = max(1, min(depth, self.dungeon_level_count))
        return self.dungeon_levels[clamped - 1]

    @staticmethod
    def available_races() -> tuple[RaceDefinition, ...]:
        races, _ = load_character_content()
        return races

    @staticmethod
    def available_classes() -> tuple[ClassDefinition, ...]:
        _, classes = load_character_content()
        return classes

    @classmethod
    def available_character_options(
        cls,
    ) -> tuple[tuple[RaceDefinition, ...], tuple[ClassDefinition, ...]]:
        return load_character_content()

    def _spawn_player(self) -> None:
        fighter = Fighter(
            max_hp=max(1, self.character_class.base_hp + self.race.hp_bonus),
            hp=max(1, self.character_class.base_hp + self.race.hp_bonus),
            power=max(1, self.character_class.base_power + self.race.power_bonus),
            defense=max(0, self.character_class.base_defense + self.race.defense_bonus),
        )

        self.ecs.add_component(self.player_entity, Player())
        self.ecs.add_component(self.player_entity, Position(2, 2))
        self.ecs.add_component(self.player_entity, OnMap(MapKind.OVERWORLD, depth=None))
        self.ecs.add_component(self.player_entity, BlocksMovement())
        self.ecs.add_component(self.player_entity, fighter)
        self.ecs.add_component(self.player_entity, Inventory(capacity=12))
        self.ecs.add_component(self.player_entity, Equipment())
        self.ecs.add_component(
            self.player_entity,
            Hunger(current=self.race.hunger_max, max_value=self.race.hunger_max),
        )

    def _spawn_world_content(self) -> None:
        self._spawn_item_rules(self.spawn_content.overworld_items, MapKind.OVERWORLD, depth=None)

        for depth in range(1, self.dungeon_level_count + 1):
            self._spawn_item_rules(self.spawn_content.dungeon_items, MapKind.DUNGEON, depth=depth)
            self._spawn_monster_rules(self.spawn_content.dungeon_monsters, depth=depth)

    def _spawn_item_rules(
        self,
        rules: tuple[SpawnRule, ...],
        map_kind: MapKind,
        depth: int | None,
    ) -> None:
        for rule in rules:
            template = self.spawn_content.item_templates.get(rule.template_id)
            if template is None:
                continue
            for _ in range(rule.count):
                pos = self._random_spawn_position(map_kind, depth)
                if pos is None:
                    continue
                self._spawn_item_on_map(template, map_kind, depth, pos[0], pos[1])

    def _spawn_monster_rules(self, rules: tuple[SpawnRule, ...], depth: int) -> None:
        for rule in rules:
            template = self.spawn_content.monster_templates.get(rule.template_id)
            if template is None:
                continue
            for _ in range(rule.count):
                pos = self._random_spawn_position(MapKind.DUNGEON, depth)
                if pos is None:
                    continue
                self._spawn_monster(template, depth, pos[0], pos[1])

    def _random_spawn_position(
        self,
        map_kind: MapKind,
        depth: int | None,
    ) -> tuple[int, int] | None:
        tile_map = self.overworld if map_kind == MapKind.OVERWORLD else self.map_for_depth(depth)
        candidates: list[tuple[int, int]] = []
        for y in range(1, tile_map.height - 1):
            for x in range(1, tile_map.width - 1):
                if not tile_map.is_passable(x, y):
                    continue
                if map_kind == MapKind.OVERWORLD and tile_map.entrance_pos == (x, y):
                    continue
                if map_kind == MapKind.DUNGEON and (
                    tile_map.exit_pos == (x, y) or tile_map.stairs_down_pos == (x, y)
                ):
                    continue

                blocked = self.blocking_entity_at(x, y, map_kind, depth, excluded_entity=-1)
                if blocked is not None:
                    continue
                if self.items_at(map_kind, depth, x, y):
                    continue
                candidates.append((x, y))

        if not candidates:
            return None
        return self.rng.choice(candidates)

    def _spawn_monster(self, template: MonsterTemplate, depth: int, x: int, y: int) -> None:
        entity_id = self.ecs.create_entity()
        self.ecs.add_component(entity_id, Monster(name=template.name))
        self.ecs.add_component(
            entity_id,
            Fighter(
                max_hp=template.hp,
                hp=template.hp,
                power=template.power,
                defense=template.defense,
            ),
        )
        self.ecs.add_component(entity_id, Position(x, y))
        self.ecs.add_component(entity_id, OnMap(MapKind.DUNGEON, depth=depth))
        self.ecs.add_component(entity_id, BlocksMovement())

    def _spawn_item_on_map(
        self,
        template: ItemTemplate,
        map_kind: MapKind,
        depth: int | None,
        x: int,
        y: int,
    ) -> int:
        entity_id = self._create_item_entity(template)
        self.ecs.add_component(entity_id, Position(x, y))
        self.ecs.add_component(entity_id, OnMap(map_kind, depth=depth))
        return entity_id

    def _create_item_entity(self, template: ItemTemplate) -> int:
        entity_id = self.ecs.create_entity()
        self.ecs.add_component(entity_id, Item(name=template.name))
        if template.heal_amount is not None:
            self.ecs.add_component(entity_id, Consumable(heal_amount=template.heal_amount))
        if template.nutrition is not None:
            self.ecs.add_component(entity_id, Food(nutrition=template.nutrition))
        if template.equip_slot is not None:
            self.ecs.add_component(
                entity_id,
                Equippable(
                    slot=template.equip_slot,
                    power_bonus=template.power_bonus,
                    defense_bonus=template.defense_bonus,
                ),
            )
        return entity_id

    def _grant_starting_loadout(self) -> None:
        inventory = self.player_inventory
        equipment = self.player_equipment

        for template_id in self.character_class.starting_items:
            template = self.spawn_content.item_templates.get(template_id)
            if template is None:
                continue

            entity_id = self._create_item_entity(template)
            inventory.item_ids.append(entity_id)

            equippable = self.ecs.get_component(entity_id, Equippable)
            if equippable is None:
                continue

            if equippable.slot == EquipmentSlot.WEAPON and equipment.weapon_item_id is None:
                equipment.weapon_item_id = entity_id
            if equippable.slot == EquipmentSlot.ARMOR and equipment.armor_item_id is None:
                equipment.armor_item_id = entity_id

    def _handle_transition_if_needed(self) -> None:
        position = self.player_position
        on_map = self.player_map

        if self.current_map.kind == MapKind.OVERWORLD and self.overworld.entrance_pos is not None:
            if (position.x, position.y) == self.overworld.entrance_pos:
                target = self.dungeon_levels[0]
                target_pos = self._adjacent_open_tile(target, target.exit_pos)
                self.current_map = target
                self.current_depth = target.depth
                on_map.kind = MapKind.DUNGEON
                on_map.depth = target.depth
                position.x, position.y = target_pos
                self.add_message("You descend into dungeon level 1.")
                return

        if self.current_map.kind == MapKind.DUNGEON:
            depth = self.current_depth or 1

            if self.current_map.stairs_down_pos is not None:
                if (
                    (position.x, position.y) == self.current_map.stairs_down_pos
                    and depth < self.dungeon_level_count
                ):
                    target = self.map_for_depth(depth + 1)
                    target_pos = self._adjacent_open_tile(target, target.exit_pos)
                    self.current_map = target
                    self.current_depth = target.depth
                    on_map.kind = MapKind.DUNGEON
                    on_map.depth = target.depth
                    position.x, position.y = target_pos
                    self.add_message(f"You descend to dungeon level {target.depth}.")
                    return

            if (
                self.current_map.exit_pos is not None
                and (position.x, position.y) == self.current_map.exit_pos
            ):
                if depth == 1:
                    self.current_map = self.overworld
                    self.current_depth = None
                    on_map.kind = MapKind.OVERWORLD
                    on_map.depth = None
                    ox, oy = self.overworld.entrance_pos or (2, 2)
                    position.x, position.y = (ox, oy + 1)
                    self.add_message("You return to the overworld.")
                    return

                target = self.map_for_depth(depth - 1)
                target_pos = self._adjacent_open_tile(target, target.stairs_down_pos)
                self.current_map = target
                self.current_depth = target.depth
                on_map.kind = MapKind.DUNGEON
                on_map.depth = target.depth
                position.x, position.y = target_pos
                self.add_message(f"You ascend to dungeon level {target.depth}.")

    def _adjacent_open_tile(
        self,
        tile_map: TileMap,
        anchor: tuple[int, int] | None,
    ) -> tuple[int, int]:
        if anchor is None:
            return (2, 2)

        ax, ay = anchor
        candidates = [
            (ax + 1, ay),
            (ax - 1, ay),
            (ax, ay + 1),
            (ax, ay - 1),
            (ax, ay),
        ]
        for x, y in candidates:
            if tile_map.is_passable(x, y):
                return (x, y)
        return anchor


def _find_race(races: tuple[RaceDefinition, ...], race_id: str) -> RaceDefinition:
    for race in races:
        if race.id == race_id:
            return race
    msg = f"Unknown race: {race_id}"
    raise ValueError(msg)


def _find_class(classes: tuple[ClassDefinition, ...], class_id: str) -> ClassDefinition:
    for class_def in classes:
        if class_def.id == class_id:
            return class_def
    msg = f"Unknown class: {class_id}"
    raise ValueError(msg)
