from dataclasses import dataclass, field
from enum import Enum


class MapKind(str, Enum):
    OVERWORLD = "overworld"
    TOWN = "town"
    DUNGEON = "dungeon"


@dataclass(frozen=True, slots=True)
class Tile:
    passable: bool
    color: tuple[int, int, int]
    name: str


@dataclass(slots=True)
class TileMap:
    kind: MapKind
    width: int
    height: int
    tiles: list[list[Tile]]
    depth: int = 0
    entrance_pos: tuple[int, int] | None = None
    town_pos: tuple[int, int] | None = None
    exit_pos: tuple[int, int] | None = None
    stairs_down_pos: tuple[int, int] | None = None
    trap_positions: set[tuple[int, int]] = field(default_factory=set)
    discovered_traps: set[tuple[int, int]] = field(default_factory=set)

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def get_tile(self, x: int, y: int) -> Tile:
        return self.tiles[y][x]

    def is_passable(self, x: int, y: int) -> bool:
        return self.in_bounds(x, y) and self.get_tile(x, y).passable
