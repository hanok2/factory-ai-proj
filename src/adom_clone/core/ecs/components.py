from dataclasses import dataclass, field

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
