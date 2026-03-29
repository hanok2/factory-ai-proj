"""Game session orchestration for the ADOM-inspired vertical slice."""

import random
from collections import deque
from dataclasses import dataclass, field

from adom_clone.core.ecs.components import (
    BlocksMovement,
    Consumable,
    Corruption,
    DamageType,
    Equipment,
    EquipmentSlot,
    Equippable,
    ExperienceReward,
    Fighter,
    Food,
    Hunger,
    Inventory,
    Item,
    Mana,
    ManaSchool,
    Monster,
    Npc,
    NpcRole,
    OnMap,
    Player,
    Position,
    Progression,
    RangedWeapon,
    Resistances,
    StatusEffects,
    Talents,
)
from adom_clone.core.ecs.store import ECSStore
from adom_clone.core.game.actions import (
    CastArcaneBoltAction,
    CastVenomLanceAction,
    GameAction,
    MoveAction,
    RangedAttackAction,
)
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
from adom_clone.core.world.generators import (
    generate_dungeon_levels,
    generate_overworld,
    generate_town,
)
from adom_clone.core.world.map_model import MapKind, TileMap


@dataclass(frozen=True)
class CharacterSelection:
    race_id: str
    class_id: str
    seed: int


@dataclass(slots=True)
class QuestState:
    """Tracks a multi-step quest with timeout/failure for Phase 7 world simulation."""

    quest_id: str = "town_goblin_cull"
    stage: int = 0
    accepted: bool = False
    target_kills: int = 3
    kills_progress: int = 0
    deadline_turn: int = 0
    completed: bool = False
    failed: bool = False
    turned_in: bool = False
    journal: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TalentDefinition:
    """Describes one node in the class-specific specialization talent trees."""

    id: str
    branch: str
    classes: tuple[str, ...]
    description: str
    prerequisites: tuple[str, ...] = ()


TALENT_DEFINITIONS: dict[str, TalentDefinition] = {
    "arcane_efficiency": TalentDefinition(
        id="arcane_efficiency",
        branch="Evoker",
        classes=("wizard", "thief"),
        description="Reduce spell costs by 1 mana.",
    ),
    "chain_bolt": TalentDefinition(
        id="chain_bolt",
        branch="Evoker",
        classes=("wizard",),
        description="Arcane Bolt can strike a second nearby target.",
        prerequisites=("arcane_efficiency",),
    ),
    "keen_senses": TalentDefinition(
        id="keen_senses",
        branch="Scout",
        classes=("thief", "fighter"),
        description="Improved hidden-trap detection.",
    ),
    "poison_mastery": TalentDefinition(
        id="poison_mastery",
        branch="Assassin",
        classes=("thief", "wizard"),
        description="Venom Lance damage and poison duration increase.",
        prerequisites=("keen_senses",),
    ),
    "hardened": TalentDefinition(
        id="hardened",
        branch="Guardian",
        classes=("fighter",),
        description="Gain +10% physical resistance.",
    ),
    "steel_bulwark": TalentDefinition(
        id="steel_bulwark",
        branch="Guardian",
        classes=("fighter",),
        description="Gain +1 defense and +10% poison resistance.",
        prerequisites=("hardened",),
    ),
}

FACTIONS: tuple[str, ...] = (
    "townfolk",
    "arcane_order",
    "wild_clans",
)

QUEST_UNLOCKS: dict[str, tuple[str, int]] = {
    "town_goblin_cull": ("townfolk", -10),
    "arcane_anomaly": ("arcane_order", 5),
    "clan_beast_hunt": ("wild_clans", 5),
}

QUEST_TARGETS: dict[str, int] = {
    "town_goblin_cull": 3,
    "arcane_anomaly": 4,
    "clan_beast_hunt": 5,
}

CORRUPTION_MUTATIONS: tuple[tuple[int, str | None], ...] = (
    (180, "void_sight"),
    (100, "chaos_skin"),
    (0, None),
)


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
        self.town = generate_town()
        self.dungeon_levels = generate_dungeon_levels(dungeon_level_count, seed)
        self.dungeon = self.dungeon_levels[0]
        self.current_map: TileMap = self.overworld
        self.current_depth: int | None = None

        self.messages: list[str] = []
        self.game_over = False
        self.turn_count = 0
        self.kill_count = 0
        self.regen_counter = 0
        self.quest_state = QuestState()
        self.faction_reputation: dict[str, int] = {name: 0 for name in FACTIONS}
        self.save_diagnostics: list[str] = []
        self._action_queue: deque[GameAction] = deque()

        self.turn_system = TurnSystem()
        self.combat_system = CombatSystem()
        self.inventory_system = InventorySystem()
        self.ai_system = AISystem()
        self.persistence_system = PersistenceSystem()

        self.player_entity = self.ecs.create_entity()
        self._spawn_player()
        self._spawn_world_content()
        self._spawn_town_npcs()
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
    def player_mana(self) -> Mana:
        mana = self.ecs.get_component(self.player_entity, Mana)
        if mana is None:
            msg = "Player entity is missing Mana component."
            raise RuntimeError(msg)
        return mana

    @property
    def player_talents(self) -> Talents:
        talents = self.ecs.get_component(self.player_entity, Talents)
        if talents is None:
            msg = "Player entity is missing Talents component."
            raise RuntimeError(msg)
        return talents

    @property
    def player_resistances(self) -> Resistances:
        resistances = self.ecs.get_component(self.player_entity, Resistances)
        if resistances is None:
            msg = "Player entity is missing Resistances component."
            raise RuntimeError(msg)
        return resistances

    @property
    def player_corruption(self) -> Corruption:
        corruption = self.ecs.get_component(self.player_entity, Corruption)
        if corruption is None:
            msg = "Player entity is missing Corruption component."
            raise RuntimeError(msg)
        return corruption

    @property
    def player_hp_text(self) -> str:
        fighter = self.player_fighter
        return f"{fighter.hp}/{fighter.max_hp}"

    @property
    def player_hunger_text(self) -> str:
        hunger = self.player_hunger
        return f"{hunger.current}/{hunger.max_value}"

    @property
    def player_mana_text(self) -> str:
        mana = self.player_mana
        return f"{mana.current}/{mana.max_value}"

    @property
    def player_corruption_text(self) -> str:
        corruption = self.player_corruption
        mutation = "none" if corruption.mutation is None else corruption.mutation
        return f"{corruption.value}/100 ({mutation})"

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

    @property
    def player_talents_text(self) -> str:
        talents = self.player_talents
        if not talents.selected:
            return "Talents: none"
        return f"Talents: {', '.join(talents.selected)}"

    @property
    def quest_text(self) -> str:
        quest = self.quest_state
        if not quest.accepted:
            return "Quest: not accepted"
        if quest.failed:
            return "Quest: failed"
        if quest.turned_in:
            return "Quest: completed"
        if quest.completed:
            return "Quest: return to Captain Durn"
        remaining = max(0, quest.target_kills - quest.kills_progress)
        return f"Quest: {remaining} kills remaining"

    @property
    def spellbook_text(self) -> str:
        spells = self.character_class.starting_spells
        if not spells:
            return "Spells: none"
        return "Spells: " + ", ".join(spells)

    @property
    def faction_text(self) -> str:
        return (
            "Rep "
            f"T:{self.faction_reputation.get('townfolk', 0)} "
            f"A:{self.faction_reputation.get('arcane_order', 0)} "
            f"W:{self.faction_reputation.get('wild_clans', 0)}"
        )

    def quest_journal_lines(self) -> list[str]:
        if not self.quest_state.journal:
            return ["Quest journal is empty."]
        return [*self.quest_state.journal[-6:]]

    def add_message(self, text: str) -> None:
        self.messages.append(text)
        if len(self.messages) > 250:
            del self.messages[:-250]

    def add_diagnostic(self, category: str, text: str) -> None:
        """Track categorized save/runtime diagnostics for UI inspection panels."""
        self.save_diagnostics.append(f"[{category}] {text}")
        if len(self.save_diagnostics) > 100:
            del self.save_diagnostics[:-100]

    def queue_action(self, action: GameAction) -> None:
        self._action_queue.append(action)

    def advance_turn(self) -> None:
        self.turn_system.advance_turn(self)

    def cast_arcane_bolt(self, dx: int, dy: int) -> bool:
        """Cast a directional projectile spell that deals ARCANE damage.

        Phase 7 note:
        - arcane school mastery contributes to damage scaling,
        - `chain_bolt` specialization can hit one secondary nearby target.
        """
        if dx == 0 and dy == 0:
            self.add_message("Choose a direction for Arcane Bolt.")
            return False
        if not self.has_spell("arcane_bolt"):
            self.add_message("You have not learned Arcane Bolt.")
            return False

        mana_cost = self._spell_cost(4, ManaSchool.ARCANE)
        if not self._spend_mana(mana_cost):
            return False

        start = self.player_position
        max_range = 6
        for step in range(1, max_range + 1):
            tx = start.x + dx * step
            ty = start.y + dy * step
            if not self.current_map.in_bounds(tx, ty):
                break
            if not self.current_map.is_passable(tx, ty):
                break

            blocker = self.blocking_entity_at(
                tx,
                ty,
                self.current_map.kind,
                self.current_depth,
                self.player_entity,
            )
            if blocker is None:
                continue

            if self.ecs.get_component(blocker, Fighter) is None:
                break

            base_damage = (
                5
                + self.player_progression.level // 2
                + self._school_mastery(ManaSchool.ARCANE)
            )
            actual, mitigated = self.apply_damage(
                blocker,
                base_damage,
                DamageType.ARCANE,
                source="Arcane Bolt",
            )
            self._log_player_damage(
                blocker,
                "Arcane Bolt",
                DamageType.ARCANE,
                actual,
                mitigated,
            )
            if self._school_mastery(ManaSchool.ARCANE) >= 4:
                self.apply_status(blocker, confuse=1)

            # Talent branch extension: arcane chain can bounce to one adjacent hostile target.
            if "chain_bolt" in self.player_talents.selected:
                self._chain_bolt_followup(primary_target=blocker, bonus=max(1, base_damage // 2))
            return True

        self.add_message("Arcane Bolt dissipates without hitting a target.")
        return True

    def cast_venom_lance(self, dx: int, dy: int) -> bool:
        """Cast a poison-school offensive spell that applies damage-over-time."""
        if dx == 0 and dy == 0:
            self.add_message("Choose a direction for Venom Lance.")
            return False
        if not self.has_spell("venom_lance"):
            self.add_message("You have not learned Venom Lance.")
            return False

        mana_cost = self._spell_cost(5, ManaSchool.POISON)
        if not self._spend_mana(mana_cost):
            return False

        start = self.player_position
        for step in range(1, 6):
            tx = start.x + dx * step
            ty = start.y + dy * step
            if not self.current_map.in_bounds(tx, ty):
                break
            if not self.current_map.is_passable(tx, ty):
                break

            blocker = self.blocking_entity_at(
                tx,
                ty,
                self.current_map.kind,
                self.current_depth,
                self.player_entity,
            )
            if blocker is None:
                continue
            if self.ecs.get_component(blocker, Fighter) is None:
                break

            poison_mastery = self._school_mastery(ManaSchool.POISON)
            if "poison_mastery" in self.player_talents.selected:
                poison_mastery += 2

            base_damage = 4 + poison_mastery
            actual, mitigated = self.apply_damage(
                blocker,
                base_damage,
                DamageType.POISON,
                source="Venom Lance",
            )
            self.apply_status(
                blocker,
                poison=2 + max(0, poison_mastery // 2),
                slow=1 + poison_mastery // 4,
            )
            self._log_player_damage(
                blocker,
                "Venom Lance",
                DamageType.POISON,
                actual,
                mitigated,
            )
            return True

        self.add_message("Venom Lance misses and dissipates into the air.")
        return True

    def cast_ward(self) -> bool:
        """Cast a utility defensive spell whose potency scales with vitality mastery."""
        if not self.has_spell("ward"):
            self.add_message("You have not learned Ward.")
            return False

        mana_cost = self._spell_cost(4, ManaSchool.VITALITY)
        if not self._spend_mana(mana_cost):
            return False

        status = self.player_status
        mastery = self._school_mastery(ManaSchool.VITALITY)
        status.ward_turns = max(status.ward_turns, 4 + mastery // 2)
        status.ward_strength = max(status.ward_strength, 8 + mastery * 2)
        self.add_message(
            "A protective ward surrounds you "
            f"({status.ward_strength}% for {status.ward_turns} turns).",
        )
        return True

    def cast_mend(self) -> bool:
        """Cast a utility self-heal spell to satisfy the utility spell baseline."""
        if not self.has_spell("mend"):
            self.add_message("You have not learned Mend.")
            return False

        mana_cost = self._spell_cost(3, ManaSchool.VITALITY)
        if not self._spend_mana(mana_cost):
            return False

        fighter = self.player_fighter
        before = fighter.hp
        heal_amount = (
            4
            + self.player_progression.level // 3
            + self._school_mastery(ManaSchool.VITALITY) // 2
        )
        fighter.hp = min(fighter.max_hp, fighter.hp + heal_amount)
        healed = fighter.hp - before
        if healed <= 0:
            self.add_message("Mend shimmers, but you are already at full health.")
        else:
            self.add_message(f"Mend restores {healed} HP.")
        return True

    def select_talent(self, talent_id: str) -> bool:
        """Spend talent points on a permanent passive talent choice.

        Phase 7 talent trees enforce class restrictions and prerequisites.
        """
        talents = self.player_talents
        definition = TALENT_DEFINITIONS.get(talent_id)
        if definition is None:
            self.add_message("Unknown talent selection.")
            return False
        if talent_id in talents.selected:
            self.add_message("You already learned that talent.")
            return False
        if talents.points <= 0:
            self.add_message("No talent points available.")
            return False

        if self.class_id not in definition.classes:
            self.add_message("Your class cannot learn that talent.")
            return False

        missing_prereq = [
            prereq for prereq in definition.prerequisites if prereq not in talents.selected
        ]
        if missing_prereq:
            self.add_message(f"Talent requires: {', '.join(missing_prereq)}.")
            return False

        talents.selected.append(talent_id)
        talents.points -= 1

        # Apply immediate one-time effects for talents that grant base stats.
        if talent_id == "hardened":
            self.player_resistances.physical_pct = min(
                80,
                self.player_resistances.physical_pct + 10,
            )
        if talent_id == "steel_bulwark":
            self.player_fighter.defense += 1
            self.player_resistances.poison_pct = min(
                80,
                self.player_resistances.poison_pct + 10,
            )

        self.add_message(f"Talent learned: {talent_id}.")
        return True

    def interact_with_adjacent_npc(self) -> bool:
        """Interact with adjacent town NPCs for services and quest progression."""
        npc_entity = self._adjacent_npc()
        if npc_entity is None:
            self.add_message("No one nearby to interact with.")
            return False

        npc = self.ecs.get_component(npc_entity, Npc)
        if npc is None:
            self.add_message("That interaction target is invalid.")
            return False

        if npc.role == NpcRole.QUEST_GIVER:
            return self._interact_quest_giver(npc)
        if npc.role == NpcRole.HEALER:
            return self._interact_healer(npc)
        if npc.role == NpcRole.SHOPKEEPER:
            return self._interact_shopkeeper(npc)

        self.add_message("They have nothing to offer right now.")
        return False

    def has_spell(self, spell_id: str) -> bool:
        return spell_id in self.character_class.starting_spells

    def available_talent_options(self) -> list[tuple[str, str]]:
        talents = self.player_talents
        options: list[tuple[str, str]] = []
        for talent_id, definition in TALENT_DEFINITIONS.items():
            if talent_id in talents.selected:
                continue
            if self.class_id not in definition.classes:
                continue
            if any(prereq not in talents.selected for prereq in definition.prerequisites):
                continue
            description = f"[{definition.branch}] {definition.description}"
            options.append((talent_id, description))
        return options

    def apply_damage(
        self,
        entity_id: int,
        raw_damage: int,
        damage_type: DamageType,
        *,
        source: str,
    ) -> tuple[int, int]:
        """Apply typed damage with resistance mitigation and death handling.

        Returns `(actual_damage, mitigated_damage)` for combat log rendering.
        """
        fighter = self.ecs.get_component(entity_id, Fighter)
        if fighter is None or fighter.hp <= 0:
            return (0, 0)

        resistance_pct = self._resistance_for(entity_id, damage_type)
        mitigated = (max(0, raw_damage) * resistance_pct) // 100
        actual = max(1, raw_damage - mitigated)

        fighter.hp -= actual
        if fighter.hp <= 0:
            self._handle_death(entity_id)

        return (actual, mitigated)

    def _resistance_for(self, entity_id: int, damage_type: DamageType) -> int:
        resist = self.ecs.get_component(entity_id, Resistances)
        if resist is None:
            return 0

        ward_bonus = 0
        if entity_id == self.player_entity:
            status = self.player_status
            if status.ward_turns > 0:
                ward_bonus = status.ward_strength

        if damage_type == DamageType.PHYSICAL:
            return max(0, min(80, resist.physical_pct + ward_bonus))
        if damage_type == DamageType.POISON:
            return max(0, min(80, resist.poison_pct + ward_bonus))
        return max(0, min(80, resist.arcane_pct + ward_bonus))

    def _spell_cost(self, base_cost: int, school: ManaSchool) -> int:
        """Compute spell costs with school mastery and talent reductions."""
        reduction = self._school_mastery(school) // 5
        if "arcane_efficiency" in self.player_talents.selected:
            reduction += 1
        return max(1, base_cost - reduction)

    def _school_mastery(self, school: ManaSchool) -> int:
        class_bonus = self.character_class.school_mastery.get(school.value, 0)
        level_bonus = self.player_progression.level // 3
        return class_bonus + level_bonus

    def _spend_mana(self, amount: int) -> bool:
        mana = self.player_mana
        if mana.current < amount:
            self.add_message(f"Not enough mana ({mana.current}/{amount}).")
            return False
        mana.current -= amount
        return True

    def _log_player_damage(
        self,
        defender: int,
        source: str,
        damage_type: DamageType,
        actual: int,
        mitigated: int,
    ) -> None:
        monster = self.ecs.get_component(defender, Monster)
        target_name = monster.name if monster is not None else "target"
        self.add_message(
            f"{source} hits {target_name} for {actual} {damage_type.value} damage"
            f" ({mitigated} resisted).",
        )

    def _chain_bolt_followup(self, primary_target: int, bonus: int) -> None:
        """Apply a secondary strike to one adjacent enemy near the primary target."""
        primary_pos = self.ecs.get_component(primary_target, Position)
        if primary_pos is None:
            return

        for other_id, _monster in self.ecs.entities_with(Monster):
            if other_id == primary_target:
                continue
            on_map = self.ecs.get_component(other_id, OnMap)
            if on_map is None:
                continue
            if on_map.kind != self.current_map.kind:
                continue
            if on_map.kind == MapKind.DUNGEON and on_map.depth != self.current_depth:
                continue

            other_pos = self.ecs.get_component(other_id, Position)
            if other_pos is None:
                continue
            if abs(other_pos.x - primary_pos.x) + abs(other_pos.y - primary_pos.y) > 2:
                continue

            actual, mitigated = self.apply_damage(
                other_id,
                max(1, bonus),
                DamageType.ARCANE,
                source="Chain Bolt",
            )
            self._log_player_damage(
                other_id,
                "Chain Bolt",
                DamageType.ARCANE,
                actual,
                mitigated,
            )
            return

    def _regenerate_mana(self) -> None:
        mana = self.player_mana
        if mana.current < mana.max_value:
            mana.current += 1

    def detect_nearby_traps(self) -> None:
        """Reveal hidden traps near the player based on deterministic perception checks."""
        px, py = self.player_position.x, self.player_position.y
        perception_bonus = 35 if "keen_senses" in self.player_talents.selected else 0

        for trap in list(self.current_map.trap_positions):
            if trap in self.current_map.discovered_traps:
                continue
            dist = abs(trap[0] - px) + abs(trap[1] - py)
            if dist > 4:
                continue

            if dist <= 1:
                self.current_map.discovered_traps.add(trap)
                self.add_message(f"You notice a trap at {trap}.")
                continue

            roll_seed = self.turn_count + trap[0] * 11 + trap[1] * 17 + self.seed
            roll = roll_seed % 100
            if roll < 20 + perception_bonus:
                self.current_map.discovered_traps.add(trap)
                self.add_message(f"You spot a hidden trap at {trap}.")

    def detect_nearby_secrets(self) -> None:
        """Reveal secret-room anchors via exploration and perception checks."""
        if not self.current_map.secret_rooms:
            return

        px, py = self.player_position.x, self.player_position.y
        perception_bonus = 20 if "keen_senses" in self.player_talents.selected else 0

        for secret in list(self.current_map.secret_rooms):
            if secret in self.current_map.discovered_secrets:
                continue
            dist = abs(secret[0] - px) + abs(secret[1] - py)
            if dist > 5:
                continue
            if dist <= 1:
                self.current_map.discovered_secrets.add(secret)
                self.add_message(f"You uncover a hidden chamber near {secret}.")
                continue

            roll = (self.seed + self.turn_count + secret[0] * 7 + secret[1] * 13) % 100
            if roll < 14 + perception_bonus:
                self.current_map.discovered_secrets.add(secret)
                self.add_message(f"You sense a secret chamber near {secret}.")

    def consume_player_stun_turn(self) -> bool:
        status = self.player_status
        if status.stun <= 0:
            if status.slow > 0 and (self.turn_count + self.seed) % 2 == 0:
                self.add_message("You are slowed and lose momentum this turn.")
                return True
            return False
        status.stun -= 1
        self.add_message("You are stunned and cannot act.")
        return True

    def resolve_player_action(self, action: GameAction) -> GameAction:
        status = self.player_status
        if status.confuse <= 0:
            return action

        if isinstance(action, MoveAction):
            dx, dy = self._confused_direction()
            self.add_message("You stumble in confusion.")
            return MoveAction(dx, dy)
        if isinstance(action, RangedAttackAction):
            dx, dy = self._confused_direction()
            self.add_message("You fumble your aim in confusion.")
            return RangedAttackAction(dx, dy)
        if isinstance(action, CastArcaneBoltAction):
            dx, dy = self._confused_direction()
            self.add_message("Your arcane focus wavers.")
            return CastArcaneBoltAction(dx, dy)
        if isinstance(action, CastVenomLanceAction):
            dx, dy = self._confused_direction()
            self.add_message("Your venom lance veers off course.")
            return CastVenomLanceAction(dx, dy)
        return action

    def player_fear_prevents_action(self, action: GameAction) -> bool:
        status = self.player_status
        if status.fear <= 0:
            return False
        if not self.has_adjacent_monster():
            return False
        if isinstance(
            action,
            (MoveAction, RangedAttackAction, CastArcaneBoltAction, CastVenomLanceAction),
        ):
            self.add_message("Fear grips you and you hesitate.")
            return True
        return False

    def _confused_direction(self) -> tuple[int, int]:
        directions = [(-1, 0), (1, 0), (0, -1), (0, 1)]
        idx = (self.turn_count + self.seed + self.player_status.confuse) % len(directions)
        return directions[idx]

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

        if status.ward_turns > 0:
            status.ward_turns -= 1
            if status.ward_turns == 0:
                status.ward_strength = 0
                if entity_id == self.player_entity:
                    self.add_message("Your protective ward fades.")

        if status.poison > 0:
            status.poison -= 1
            self.apply_damage(entity_id, 1, DamageType.POISON, source="poison")
        if status.bleed > 0:
            status.bleed -= 1
            self.apply_damage(entity_id, 1, DamageType.PHYSICAL, source="bleeding")
        if status.slow > 0:
            status.slow -= 1
        if status.fear > 0:
            status.fear -= 1
        if status.confuse > 0:
            status.confuse -= 1

    def apply_natural_regen(self) -> None:
        fighter = self.player_fighter
        if fighter.hp >= fighter.max_hp:
            self.regen_counter = 0
        else:
            if self.has_adjacent_monster():
                self.regen_counter = 0
            else:
                self.regen_counter += 1
                if self.regen_counter >= 8:
                    self.regen_counter = 0
                    fighter.hp = min(fighter.max_hp, fighter.hp + 1)
                    self.add_message("You recover 1 HP.")

        self._regenerate_mana()
        self.detect_nearby_traps()
        self.detect_nearby_secrets()

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
        self.current_map.discovered_traps.discard(trap)
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
        slow: int = 0,
        fear: int = 0,
        confuse: int = 0,
        ward_turns: int = 0,
        ward_strength: int = 0,
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
        if slow > 0:
            status.slow = max(status.slow, slow)
        if fear > 0:
            status.fear = max(status.fear, fear)
        if confuse > 0:
            status.confuse = max(status.confuse, confuse)
        if ward_turns > 0:
            status.ward_turns = max(status.ward_turns, ward_turns)
        if ward_strength > 0:
            status.ward_strength = max(status.ward_strength, ward_strength)

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

            mana = self.player_mana
            mana_gain = max(1, self.character_class.mana_per_level)
            mana.max_value += mana_gain
            mana.current = min(mana.max_value, mana.current + mana_gain)

            if progression.level % max(1, self.character_class.power_every) == 0:
                fighter.power += 1
            if progression.level % max(1, self.character_class.defense_every) == 0:
                fighter.defense += 1

            if progression.level in self.character_class.talent_milestones:
                self.player_talents.points += 1
                self.add_message("You gained a talent point. Open talents with [T].")

            self.add_message(f"You advance to level {progression.level}!")

    def tick_hunger(self) -> None:
        hunger = self.player_hunger
        hunger.current -= 1

        if hunger.current in (80, 50, 25, 10):
            self.add_message("You feel hungry.")
        if hunger.current <= 0:
            actual, mitigated = self.apply_damage(
                self.player_entity,
                1,
                DamageType.PHYSICAL,
                source="starvation",
            )
            self.add_message(f"You are starving! ({actual} damage, {mitigated} resisted)")

    def tick_corruption(self) -> None:
        """Advance corruption in dungeon zones and evolve mutation stages."""
        if self.current_map.kind != MapKind.DUNGEON:
            return

        corruption = self.player_corruption
        depth = self.current_depth or 1
        corruption.value += 1 + depth // 2
        self._refresh_corruption_mutation()

    def reduce_corruption(self, amount: int, *, source: str) -> int:
        corruption = self.player_corruption
        before = corruption.value
        corruption.value = max(0, corruption.value - max(0, amount))
        reduced = before - corruption.value
        if reduced > 0:
            self.add_message(f"{source} reduces corruption by {reduced}.")
            self._refresh_corruption_mutation()
        return reduced

    def _refresh_corruption_mutation(self) -> None:
        corruption = self.player_corruption
        new_mutation = self._mutation_for_corruption(corruption.value)
        old_mutation = corruption.mutation
        if old_mutation == new_mutation:
            return

        self._apply_mutation_transition(old_mutation, new_mutation)
        corruption.mutation = new_mutation

        if new_mutation is None:
            self.add_message("Your corruption recedes and your form stabilizes.")
            return
        if new_mutation == "chaos_skin":
            self.add_message("Corruption mutates your skin with unstable arcane patterns.")
            return
        self.add_message("Corruption deepens; your senses distort into void sight.")

    def _mutation_for_corruption(self, value: int) -> str | None:
        for threshold, mutation in CORRUPTION_MUTATIONS:
            if value >= threshold:
                return mutation
        return None

    def _apply_mutation_transition(
        self,
        old_mutation: str | None,
        new_mutation: str | None,
    ) -> None:
        old_def, old_arc, old_poi = self._mutation_effects(old_mutation)
        new_def, new_arc, new_poi = self._mutation_effects(new_mutation)

        self.player_fighter.defense = max(0, self.player_fighter.defense + (new_def - old_def))
        self.player_resistances.arcane_pct = max(
            0,
            min(80, self.player_resistances.arcane_pct + (new_arc - old_arc)),
        )
        self.player_resistances.poison_pct = max(
            0,
            min(80, self.player_resistances.poison_pct + (new_poi - old_poi)),
        )

    def _mutation_effects(self, mutation: str | None) -> tuple[int, int, int]:
        if mutation == "chaos_skin":
            return (-1, 15, 0)
        if mutation == "void_sight":
            return (-2, 20, 5)
        return (0, 0, 0)

    def tick_quest_timers(self) -> None:
        """Fail active quests when their deadline expires."""
        quest = self.quest_state
        if not quest.accepted or quest.failed or quest.turned_in:
            return
        if quest.deadline_turn <= 0:
            return
        if self.turn_count <= quest.deadline_turn:
            return

        quest.failed = True
        quest.stage = 4
        quest.completed = False
        self.faction_reputation["townfolk"] = self.faction_reputation.get("townfolk", 0) - 5
        if quest.quest_id == "arcane_anomaly":
            self.faction_reputation["arcane_order"] = (
                self.faction_reputation.get("arcane_order", 0) - 4
            )
        if quest.quest_id == "clan_beast_hunt":
            self.faction_reputation["wild_clans"] = (
                self.faction_reputation.get("wild_clans", 0) - 4
            )
        quest.journal.append("Quest failed: you returned too late.")
        self.add_message("Quest failed: you missed the deadline.")

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

        if monster is not None:
            if monster.faction == "arcane_order":
                self.faction_reputation["arcane_order"] = (
                    self.faction_reputation.get("arcane_order", 0) - 1
                )
            elif monster.faction == "wild_clans":
                self.faction_reputation["wild_clans"] = (
                    self.faction_reputation.get("wild_clans", 0) - 1
                )

        if (
            self.quest_state.accepted
            and not self.quest_state.failed
            and not self.quest_state.completed
        ):
            self.quest_state.kills_progress += 1
            remaining = max(0, self.quest_state.target_kills - self.quest_state.kills_progress)
            if remaining == 0:
                self.quest_state.completed = True
                self.quest_state.stage = 2
                self.quest_state.journal.append("Objective complete. Return to Captain Durn.")
                self.add_message("Quest update: Return to Captain Durn for your reward.")
            else:
                self.quest_state.journal.append(f"Quest progress: {remaining} kills remaining.")

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
            Resistances,
            Mana,
            Talents,
            Npc,
            Corruption,
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

    def npc_positions(self) -> list[tuple[int, int]]:
        positions: list[tuple[int, int]] = []
        for entity_id, _npc in self.ecs.entities_with(Npc):
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
        return sorted(self.current_map.discovered_traps)

    def secret_positions(self) -> list[tuple[int, int]]:
        return sorted(self.current_map.discovered_secrets)

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
        self.ecs.add_component(
            self.player_entity,
            Mana(current=self.character_class.mana_base, max_value=self.character_class.mana_base),
        )
        self.ecs.add_component(self.player_entity, Talents())
        self.ecs.add_component(self.player_entity, Resistances())
        self.ecs.add_component(self.player_entity, Corruption())

    def _spawn_world_content(self) -> None:
        self._spawn_item_rules(self.spawn_content.overworld_items, MapKind.OVERWORLD, depth=None)

        for depth in range(1, self.dungeon_level_count + 1):
            self._spawn_item_rules(self.spawn_content.dungeon_items, MapKind.DUNGEON, depth=depth)
            self._spawn_monster_rules(self.spawn_content.dungeon_monsters, depth=depth)

            # Phase 7 vault hook: each generated vault receives one guaranteed reward.
            level_map = self.map_for_depth(depth)
            if level_map.vault_pos is None:
                continue
            template = self.spawn_content.item_templates.get("healing_potion")
            if template is None:
                continue
            vx, vy = level_map.vault_pos
            self._spawn_item_on_map(template, MapKind.DUNGEON, depth, vx, vy)

    def _spawn_town_npcs(self) -> None:
        """Populate the town hub with baseline service NPCs used in Phase 6."""
        self._spawn_npc("Sister Arin", NpcRole.HEALER, x=10, y=6)
        self._spawn_npc("Borin", NpcRole.SHOPKEEPER, x=14, y=9)
        self._spawn_npc("Captain Durn", NpcRole.QUEST_GIVER, x=8, y=10)

    def _spawn_npc(self, name: str, role: NpcRole, x: int, y: int) -> None:
        entity_id = self.ecs.create_entity()
        self.ecs.add_component(entity_id, Npc(name=name, role=role))
        self.ecs.add_component(entity_id, Position(x, y))
        self.ecs.add_component(entity_id, OnMap(MapKind.TOWN, depth=None))
        self.ecs.add_component(entity_id, BlocksMovement())

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
        biome = self.map_for_depth(depth).biome
        eligible_rules = [
            rule
            for rule in rules
            if self._is_spawn_rule_eligible(rule, depth, biome)
        ]
        if not eligible_rules:
            return

        spawn_count = sum(max(0, rule.count) for rule in eligible_rules)
        for _ in range(spawn_count):
            selected_rule = self._pick_weighted_spawn_rule(eligible_rules)
            if selected_rule is None:
                continue
            template = self.spawn_content.monster_templates.get(selected_rule.template_id)
            if template is None:
                continue

            pos = self._random_spawn_position(MapKind.DUNGEON, depth)
            if pos is None:
                continue
            self._spawn_monster(template, depth, pos[0], pos[1])

    def _is_spawn_rule_eligible(self, rule: SpawnRule, depth: int, biome: str) -> bool:
        if rule.min_depth is not None and depth < rule.min_depth:
            return False
        if rule.max_depth is not None and depth > rule.max_depth:
            return False
        if rule.biomes and biome not in rule.biomes:
            return False
        return True

    def _pick_weighted_spawn_rule(self, rules: list[SpawnRule]) -> SpawnRule | None:
        total_weight = sum(max(1, rule.weight) for rule in rules)
        if total_weight <= 0:
            return None

        roll = self.rng.randint(1, total_weight)
        running = 0
        for rule in rules:
            running += max(1, rule.weight)
            if roll <= running:
                return rule
        return rules[-1]

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
                    tile_map.exit_pos == (x, y)
                    or tile_map.stairs_down_pos == (x, y)
                    or tile_map.vault_pos == (x, y)
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
        self.ecs.add_component(
            entity_id,
            Monster(name=template.name, role=template.role, faction=template.faction),
        )
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
        self.ecs.add_component(
            entity_id,
            Resistances(
                physical_pct=template.physical_resist,
                poison_pct=template.poison_resist,
                arcane_pct=template.arcane_resist,
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

        if self.current_map.kind == MapKind.TOWN and self.town.exit_pos is not None:
            if (position.x, position.y) == self.town.exit_pos:
                self.current_map = self.overworld
                self.current_depth = None
                on_map.kind = MapKind.OVERWORLD
                on_map.depth = None
                tx, ty = self.overworld.town_pos or (5, 5)
                position.x, position.y = (tx + 1, ty)
                self.add_message("You leave town and return to the overworld.")
                return

        if self.current_map.kind == MapKind.OVERWORLD and self.overworld.entrance_pos is not None:
            if (
                self.overworld.town_pos is not None
                and (position.x, position.y) == self.overworld.town_pos
            ):
                target_pos = self._adjacent_open_tile(self.town, self.town.exit_pos)
                self.current_map = self.town
                self.current_depth = None
                on_map.kind = MapKind.TOWN
                on_map.depth = None
                position.x, position.y = target_pos
                self.add_message("You enter the town of Terinyo.")
                return

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
        self.current_map.discovered_traps.discard(pos)
        depth = 0 if self.current_depth is None else self.current_depth
        trap_damage = 2 + depth
        actual, mitigated = self.apply_damage(
            self.player_entity,
            trap_damage,
            DamageType.PHYSICAL,
            source="trap",
        )

        selector = (pos[0] * 31 + pos[1] * 17 + depth) % 6
        if selector == 0:
            self.apply_status(self.player_entity, poison=3)
            effect_text = "poison"
        elif selector == 1:
            self.apply_status(self.player_entity, bleed=3)
            effect_text = "bleeding"
        elif selector == 2:
            self.apply_status(self.player_entity, stun=1)
            effect_text = "stun"
        elif selector == 3:
            self.apply_status(self.player_entity, slow=3)
            effect_text = "slow"
        elif selector == 4:
            self.apply_status(self.player_entity, fear=2)
            effect_text = "fear"
        else:
            self.apply_status(self.player_entity, confuse=2)
            effect_text = "confusion"

        self.add_message(
            f"You trigger a trap for {actual} physical damage ({mitigated} resisted)"
            f" and suffer {effect_text}.",
        )

    def _nearest_trap_to_player(self) -> tuple[int, int] | None:
        px, py = self.player_position.x, self.player_position.y
        candidates = [
            pos
            for pos in self.current_map.discovered_traps
            if abs(pos[0] - px) <= 1 and abs(pos[1] - py) <= 1
        ]
        if not candidates:
            return None

        candidates.sort(key=lambda pos: (abs(pos[0] - px) + abs(pos[1] - py), pos[1], pos[0]))
        return candidates[0]

    def _adjacent_npc(self) -> int | None:
        px, py = self.player_position.x, self.player_position.y
        for entity_id, _npc in self.ecs.entities_with(Npc):
            pos = self.ecs.get_component(entity_id, Position)
            on_map = self.ecs.get_component(entity_id, OnMap)
            if pos is None or on_map is None:
                continue
            if on_map.kind != self.current_map.kind or on_map.depth != self.current_depth:
                continue
            if abs(pos.x - px) + abs(pos.y - py) == 1:
                return entity_id
        return None

    def _interact_quest_giver(self, npc: Npc) -> bool:
        quest = self.quest_state
        town_rep = self.faction_reputation.get("townfolk", 0)

        if town_rep < -10:
            self.add_message(
                f"{npc.name}: I won't trust you with contracts "
                "until your reputation improves.",
            )
            return True

        if quest.failed:
            self.add_message(f"{npc.name}: You failed the last assignment. Earn my trust first.")
            return True

        required_faction, required_rep = QUEST_UNLOCKS.get(
            quest.quest_id,
            ("townfolk", -10),
        )
        current_rep = self.faction_reputation.get(required_faction, 0)

        if not quest.accepted:
            if current_rep < required_rep:
                self.add_message(
                    f"{npc.name}: Improve {required_faction} reputation "
                    f"to at least {required_rep} before this contract.",
                )
                return True

            quest.accepted = True
            quest.stage = 1
            quest.kills_progress = 0
            quest.completed = False
            quest.turned_in = False
            quest.target_kills = QUEST_TARGETS.get(quest.quest_id, quest.target_kills)
            quest.deadline_turn = self.turn_count + 180
            quest.journal.append(
                f"Accepted quest from {npc.name}: eliminate {quest.target_kills} monsters "
                f"before turn {quest.deadline_turn}.",
            )
            self.add_message(
                f"{npc.name}: Clear {quest.target_kills} monsters in the dungeon and return.",
            )
            return True

        if quest.accepted and not quest.completed:
            if quest.kills_progress >= quest.target_kills:
                quest.completed = True
                quest.stage = 2
                quest.journal.append("Return to town and report completion.")
                self.add_message(f"{npc.name}: Well done. Turn in to claim your reward.")
                return True
            remaining = max(0, quest.target_kills - quest.kills_progress)
            self.add_message(f"{npc.name}: Keep going. {remaining} more kills needed.")
            return True

        if quest.completed and not quest.turned_in:
            quest.turned_in = True
            quest.stage = 3
            self.grant_player_xp(25)
            self._grant_reward_item("healing_potion")
            self.faction_reputation["townfolk"] = town_rep + 8
            self.faction_reputation["arcane_order"] = (
                self.faction_reputation.get("arcane_order", 0) + 4
            )
            self.faction_reputation["wild_clans"] = (
                self.faction_reputation.get("wild_clans", 0) + 3
            )
            quest.journal.append("Quest turned in. Captain Durn rewarded you.")
            self.add_message(f"{npc.name}: Excellent work. Take this reward.")

            if quest.quest_id == "town_goblin_cull":
                quest.quest_id = "arcane_anomaly"
                quest.accepted = False
                quest.completed = False
                quest.turned_in = False
                quest.failed = False
                quest.stage = 0
                quest.kills_progress = 0
                quest.target_kills = QUEST_TARGETS["arcane_anomaly"]
                quest.deadline_turn = 0
                quest.journal.append("New contract unlocked: Arcane Anomaly.")
            elif quest.quest_id == "arcane_anomaly":
                quest.quest_id = "clan_beast_hunt"
                quest.accepted = False
                quest.completed = False
                quest.turned_in = False
                quest.failed = False
                quest.stage = 0
                quest.kills_progress = 0
                quest.target_kills = QUEST_TARGETS["clan_beast_hunt"]
                quest.deadline_turn = 0
                quest.journal.append("New contract unlocked: Clan Beast Hunt.")
            return True

        self.add_message(f"{npc.name}: You have already proven yourself.")
        return True

    def _interact_healer(self, npc: Npc) -> bool:
        town_rep = self.faction_reputation.get("townfolk", 0)
        if town_rep < -15:
            self.add_message(f"{npc.name}: I cannot aid someone the town distrusts.")
            return True

        fighter = self.player_fighter
        if (
            fighter.hp >= fighter.max_hp
            and self.player_mana.current >= self.player_mana.max_value
            and self.player_corruption.value <= 0
            and self.player_status.poison <= 0
            and self.player_status.bleed <= 0
            and self.player_status.stun <= 0
            and self.player_status.slow <= 0
            and self.player_status.fear <= 0
            and self.player_status.confuse <= 0
        ):
            self.add_message(f"{npc.name}: You are already in peak condition.")
            return True

        fighter.hp = fighter.max_hp
        self.player_mana.current = self.player_mana.max_value
        self.player_status.poison = 0
        self.player_status.bleed = 0
        self.player_status.stun = 0
        self.player_status.slow = 0
        self.player_status.fear = 0
        self.player_status.confuse = 0
        self.player_status.ward_turns = 0
        self.player_status.ward_strength = 0
        self.reduce_corruption(35, source=npc.name)
        self.faction_reputation["wild_clans"] = (
            self.faction_reputation.get("wild_clans", 0) + 1
        )
        self.add_message(f"{npc.name} restores your health, mana, and cleanses ailments.")
        return True

    def _interact_shopkeeper(self, npc: Npc) -> bool:
        town_rep = self.faction_reputation.get("townfolk", 0)
        if town_rep < -20:
            self.add_message(f"{npc.name}: I don't sell to troublemakers.")
            return True

        inventory = self.player_inventory
        if len(inventory.item_ids) >= inventory.capacity:
            self.add_message(f"{npc.name}: Your pack is full.")
            return False

        if town_rep >= 15:
            reward_template = "healing_potion"
        else:
            reward_template = "ration" if self.turn_count % 2 == 0 else "throwing_knife"
        self._grant_reward_item(reward_template)
        self.faction_reputation["arcane_order"] = (
            self.faction_reputation.get("arcane_order", 0) + 1
        )
        self.add_message(f"{npc.name} hands you a {reward_template.replace('_', ' ')}.")
        return True

    def _grant_reward_item(self, template_id: str) -> None:
        template = self.spawn_content.item_templates.get(template_id)
        if template is None:
            return
        item_id = self._create_item_entity(template)
        self.player_inventory.item_ids.append(item_id)

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
