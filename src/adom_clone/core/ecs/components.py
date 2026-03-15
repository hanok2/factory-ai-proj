from dataclasses import dataclass, field
from enum import Enum

from adom_clone.core.world.map_model import MapKind


@dataclass(slots=True)
class Position:
    x: int
    y: int


@dataclass(slots=True)
class Player:
    pass


@dataclass(slots=True)
class Monster:
    name: str


@dataclass(slots=True)
class OnMap:
    kind: MapKind
    depth: int | None = None


@dataclass(slots=True)
class BlocksMovement:
    pass


@dataclass(slots=True)
class Fighter:
    max_hp: int
    hp: int
    power: int
    defense: int


@dataclass(slots=True)
class Inventory:
    capacity: int
    item_ids: list[int] = field(default_factory=list)


@dataclass(slots=True)
class Item:
    name: str


@dataclass(slots=True)
class Consumable:
    heal_amount: int


class EquipmentSlot(str, Enum):
    WEAPON = "weapon"
    ARMOR = "armor"


@dataclass(slots=True)
class Equippable:
    slot: EquipmentSlot
    power_bonus: int = 0
    defense_bonus: int = 0


@dataclass(slots=True)
class Equipment:
    weapon_item_id: int | None = None
    armor_item_id: int | None = None


@dataclass(slots=True)
class Food:
    nutrition: int


@dataclass(slots=True)
class Hunger:
    current: int
    max_value: int


@dataclass(slots=True)
class Progression:
    level: int
    xp: int
    xp_to_next: int


@dataclass(slots=True)
class StatusEffects:
    poison: int = 0
    bleed: int = 0
    stun: int = 0


@dataclass(slots=True)
class RangedWeapon:
    damage: int
    range: int


@dataclass(slots=True)
class ExperienceReward:
    xp: int


class DamageType(str, Enum):
    PHYSICAL = "physical"
    POISON = "poison"
    ARCANE = "arcane"


@dataclass(slots=True)
class Resistances:
    physical_pct: int = 0
    poison_pct: int = 0
    arcane_pct: int = 0


@dataclass(slots=True)
class Mana:
    current: int
    max_value: int


@dataclass(slots=True)
class Talents:
    points: int = 0
    selected: list[str] = field(default_factory=list)


class NpcRole(str, Enum):
    HEALER = "healer"
    SHOPKEEPER = "shopkeeper"
    QUEST_GIVER = "quest_giver"


@dataclass(slots=True)
class Npc:
    name: str
    role: NpcRole
