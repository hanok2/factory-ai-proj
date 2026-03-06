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
    ExperienceReward,
    Fighter,
    Food,
    Hunger,
    Inventory,
    Item,
    Monster,
    OnMap,
    Player,
    Position,
    Progression,
    RangedWeapon,
    StatusEffects,
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
        self.regen_counter = 0
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
    def player_progression(self) -> Progression:
        progression = self.ecs.get_component(self.player_entity, Progression)
        if progression is None:
            msg = "Player entity is missing Progression component."
            raise RuntimeError(msg)
        return progression

    @property
    def player_status(self) -> StatusEffects:
        status = self.ecs.get_component(self.player_entity, StatusEffects)
        if status is None:
            msg = "Player entity is missing StatusEffects component."
            raise RuntimeError(msg)
        return status

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

    @property
    def player_level_text(self) -> str:
        progression = self.player_progression
        return f"Lv {progression.level} | XP {progression.xp}/{progression.xp_to_next}"

    def add_message(self, text: str) -> None:
        self.messages.append(text)
        if len(self.messages) > 250:
            del self.messages[:-250]

    def queue_action(self, action: GameAction) -> None:
        self._action_queue.append(action)

    def advance_turn(self) -> None:
        self.turn_system.advance_turn(self)

    def consume_player_stun_turn(self) -> bool:
        status = self.player_status
        if status.stun <= 0:
            return False
        status.stun -= 1
        self.add_message("You are stunned and cannot act.")
        return True

    def consume_monster_stun_turn(self, entity_id: int) -> bool:
        status = self.ecs.get_component(entity_id, StatusEffects)
        if status is None or status.stun <= 0:
            return False
        status.stun -= 1
        return True

    def apply_status_damage(self, entity_id: int) -> None:
        fighter = self.ecs.get_component(entity_id, Fighter)
        status = self.ecs.get_component(entity_id, StatusEffects)
        if fighter is None or status is None or fighter.hp <= 0:
            return

        damage = 0
        if status.poison > 0:
            status.poison -= 1
            damage += 1
        if status.bleed > 0:
            status.bleed -= 1
            damage += 1
        if damage <= 0:
            return

        fighter.hp -= damage
        if entity_id == self.player_entity:
            self.add_message(f"You suffer {damage} damage from ongoing effects.")
        else:
            monster = self.ecs.get_component(entity_id, Monster)
            if monster is not None:
                self.add_message(f"{monster.name} suffers {damage} damage from effects.")

        if fighter.hp <= 0:
            self._handle_death(entity_id)

    def apply_natural_regen(self) -> None:
        fighter = self.player_fighter
        if fighter.hp >= fighter.max_hp:
            self.regen_counter = 0
            return
        if self.has_adjacent_monster():
            self.regen_counter = 0
            return

        self.regen_counter += 1
        if self.regen_counter < 8:
            return

        self.regen_counter = 0
        fighter.hp = min(fighter.max_hp, fighter.hp + 1)
        self.add_message("You recover 1 HP.")

    def rest_player(self) -> bool:
        if self.has_adjacent_monster():
            self.add_message("You cannot rest while enemies are nearby.")
            return False

        fighter = self.player_fighter
        before_hp = fighter.hp
        fighter.hp = min(fighter.max_hp, fighter.hp + 2)
        healed = fighter.hp - before_hp
        if healed <= 0:
            self.add_message("You rest, but you are already fully healed.")
            return True

        self.add_message(f"You rest and recover {healed} HP.")
        return True

    def has_adjacent_monster(self) -> bool:
        px, py = self.player_position.x, self.player_position.y
        for entity_id, _ in self.ecs.entities_with(Monster):
            position = self.ecs.get_component(entity_id, Position)
            on_map = self.ecs.get_component(entity_id, OnMap)
            fighter = self.ecs.get_component(entity_id, Fighter)
            if position is None or on_map is None or fighter is None:
                continue
            if fighter.hp <= 0:
                continue
            if on_map.kind != self.current_map.kind or on_map.depth != self.current_depth:
                continue
            if abs(px - position.x) + abs(py - position.y) == 1:
                return True
        return False

    def disarm_nearby_trap(self) -> bool:
        trap = self._nearest_trap_to_player()
        if trap is None:
            self.add_message("There is no trap to disarm nearby.")
            return False

        self.current_map.trap_positions.discard(trap)
        self.add_message("You disarm a trap.")
        return True

    def first_ranged_projectile(self) -> tuple[int, int, Item, RangedWeapon] | None:
        for idx, item_id in enumerate(self.player_inventory.item_ids):
            item = self.ecs.get_component(item_id, Item)
            ranged = self.ecs.get_component(item_id, RangedWeapon)
            if item is None or ranged is None:
                continue
            return idx, item_id, item, ranged
        return None

    def consume_inventory_item(self, slot_index: int, item_entity: int) -> None:
        inventory = self.player_inventory
        if 0 <= slot_index < len(inventory.item_ids):
            inventory.item_ids.pop(slot_index)
        self.destroy_item(item_entity)

    def apply_status(
        self,
        entity_id: int,
        *,
        poison: int = 0,
        bleed: int = 0,
        stun: int = 0,
    ) -> None:
        status = self.ecs.get_component(entity_id, StatusEffects)
        if status is None:
            status = StatusEffects()
            self.ecs.add_component(entity_id, status)

        if poison > 0:
            status.poison = max(status.poison, poison)
        if bleed > 0:
            status.bleed = max(status.bleed, bleed)
        if stun > 0:
            status.stun = max(status.stun, stun)

    def grant_player_xp(self, xp: int) -> None:
        if xp <= 0:
            return

        progression = self.player_progression
        progression.xp += xp
        self.add_message(f"You gain {xp} XP.")

        while progression.xp >= progression.xp_to_next:
            progression.xp -= progression.xp_to_next
            progression.level += 1
            progression.xp_to_next = self.character_class.xp_base + progression.level * 6

            fighter = self.player_fighter
            hp_gain = max(1, self.character_class.hp_per_level)
            fighter.max_hp += hp_gain
            fighter.hp += hp_gain
            if progression.level % max(1, self.character_class.power_every) == 0:
                fighter.power += 1
            if progression.level % max(1, self.character_class.defense_every) == 0:
                fighter.defense += 1

            self.add_message(f"You advance to level {progression.level}!")

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
        self._trigger_player_trap_if_present()
        if self.game_over:
            return True
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
        self.ecs.remove_component(item_entity, RangedWeapon)
        self.ecs.remove_component(item_entity, Food)
        self.ecs.remove_component(item_entity, Position)
        self.ecs.remove_component(item_entity, OnMap)

    def _handle_death(self, entity_id: int) -> None:
        if entity_id == self.player_entity:
            self.game_over = True
            self.add_message("You die. Game over.")
            return

        monster = self.ecs.get_component(entity_id, Monster)
        reward = self.ecs.get_component(entity_id, ExperienceReward)
        name = monster.name if monster is not None else "monster"
        self.ecs.remove_component(entity_id, Monster)
        self.ecs.remove_component(entity_id, Fighter)
        self.ecs.remove_component(entity_id, BlocksMovement)
        self.ecs.remove_component(entity_id, Position)
        self.ecs.remove_component(entity_id, OnMap)
        self.ecs.remove_component(entity_id, StatusEffects)
        self.ecs.remove_component(entity_id, ExperienceReward)
        self.kill_count += 1
        self.add_message(f"{name} dies.")
        if reward is not None:
            self.grant_player_xp(reward.xp)

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
            RangedWeapon,
            Equipment,
            Food,
            Hunger,
            StatusEffects,
            Progression,
            ExperienceReward,
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

    def trap_positions(self) -> list[tuple[int, int]]:
        return sorted(self.current_map.trap_positions)

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
        self.ecs.add_component(
            self.player_entity,
            Progression(level=1, xp=0, xp_to_next=self.character_class.xp_base),
        )
        self.ecs.add_component(self.player_entity, StatusEffects())

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
                if (x, y) in tile_map.trap_positions:
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
        self.ecs.add_component(entity_id, ExperienceReward(xp=template.xp_reward))
        self.ecs.add_component(entity_id, StatusEffects())
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
        if template.ranged_damage is not None and template.ranged_range is not None:
            self.ecs.add_component(
                entity_id,
                RangedWeapon(damage=template.ranged_damage, range=template.ranged_range),
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

    def _trigger_player_trap_if_present(self) -> None:
        pos = (self.player_position.x, self.player_position.y)
        if pos not in self.current_map.trap_positions:
            return

        self.current_map.trap_positions.discard(pos)
        depth = 0 if self.current_depth is None else self.current_depth
        trap_damage = 2 + depth
        self.player_fighter.hp -= trap_damage

        selector = (pos[0] * 31 + pos[1] * 17 + depth) % 3
        if selector == 0:
            self.apply_status(self.player_entity, poison=3)
            effect_text = "poison"
        elif selector == 1:
            self.apply_status(self.player_entity, bleed=3)
            effect_text = "bleeding"
        else:
            self.apply_status(self.player_entity, stun=1)
            effect_text = "stun"

        self.add_message(f"You trigger a trap for {trap_damage} damage and suffer {effect_text}.")
        if self.player_fighter.hp <= 0:
            self._handle_death(self.player_entity)

    def _nearest_trap_to_player(self) -> tuple[int, int] | None:
        px, py = self.player_position.x, self.player_position.y
        candidates = [
            pos
            for pos in self.current_map.trap_positions
            if abs(pos[0] - px) <= 1 and abs(pos[1] - py) <= 1
        ]
        if not candidates:
            return None

        candidates.sort(key=lambda pos: (abs(pos[0] - px) + abs(pos[1] - py), pos[1], pos[0]))
        return candidates[0]

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
            if tile_map.is_passable(x, y) and (x, y) not in tile_map.trap_positions:
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
