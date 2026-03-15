import random

from adom_clone.core.world.map_model import MapKind, Tile, TileMap

GRASS = Tile(passable=True, color=(60, 140, 70), name="grass")
MOUNTAIN = Tile(passable=False, color=(80, 80, 80), name="mountain")
DUNGEON_ENTRANCE = Tile(passable=True, color=(120, 70, 30), name="dungeon_entrance")
TOWN_GATE = Tile(passable=True, color=(150, 120, 80), name="town_gate")
FLOOR = Tile(passable=True, color=(70, 70, 90), name="floor")
WALL = Tile(passable=False, color=(40, 40, 50), name="wall")
STAIRS_UP = Tile(passable=True, color=(170, 170, 90), name="stairs_up")
STAIRS_DOWN = Tile(passable=True, color=(90, 170, 170), name="stairs_down")
TOWN_FLOOR = Tile(passable=True, color=(95, 75, 60), name="town_floor")
TOWN_WALL = Tile(passable=False, color=(70, 55, 45), name="town_wall")


def generate_overworld(width: int = 40, height: int = 24) -> TileMap:
    tiles = [[GRASS for _ in range(width)] for _ in range(height)]

    for x in range(width):
        tiles[0][x] = MOUNTAIN
        tiles[height - 1][x] = MOUNTAIN
    for y in range(height):
        tiles[y][0] = MOUNTAIN
        tiles[y][width - 1] = MOUNTAIN

    entrance_pos = (width // 2, height // 2)
    ex, ey = entrance_pos
    tiles[ey][ex] = DUNGEON_ENTRANCE

    town_pos = (5, height // 2)
    tx, ty = town_pos
    tiles[ty][tx] = TOWN_GATE

    return TileMap(
        kind=MapKind.OVERWORLD,
        width=width,
        height=height,
        tiles=tiles,
        entrance_pos=entrance_pos,
        town_pos=town_pos,
    )


def generate_town(width: int = 24, height: int = 16) -> TileMap:
    tiles = [[TOWN_FLOOR for _ in range(width)] for _ in range(height)]

    for x in range(width):
        tiles[0][x] = TOWN_WALL
        tiles[height - 1][x] = TOWN_WALL
    for y in range(height):
        tiles[y][0] = TOWN_WALL
        tiles[y][width - 1] = TOWN_WALL

    exit_pos = (1, height // 2)
    ex, ey = exit_pos
    tiles[ey][ex] = TOWN_GATE

    return TileMap(
        kind=MapKind.TOWN,
        width=width,
        height=height,
        tiles=tiles,
        exit_pos=exit_pos,
    )


def generate_dungeon(
    depth: int,
    max_depth: int,
    seed: int,
    width: int = 40,
    height: int = 24,
) -> TileMap:
    rng = random.Random(seed + depth * 313)
    tiles = [[WALL for _ in range(width)] for _ in range(height)]

    left = 2 + rng.randint(0, 2)
    top = 2 + rng.randint(0, 2)
    right = width - 3 - rng.randint(0, 2)
    bottom = height - 3 - rng.randint(0, 2)

    for y in range(top, bottom):
        for x in range(left, right):
            tiles[y][x] = FLOOR

    exit_pos = (left + 1, top + 1)
    up_x, up_y = exit_pos
    tiles[up_y][up_x] = STAIRS_UP

    stairs_down_pos: tuple[int, int] | None = None
    if depth < max_depth:
        stairs_down_pos = (right - 2, bottom - 2)
        down_x, down_y = stairs_down_pos
        tiles[down_y][down_x] = STAIRS_DOWN

    trap_positions = _generate_trap_positions(
        rng=rng,
        left=left,
        top=top,
        right=right,
        bottom=bottom,
        depth=depth,
        exit_pos=exit_pos,
        stairs_down_pos=stairs_down_pos,
    )

    return TileMap(
        kind=MapKind.DUNGEON,
        width=width,
        height=height,
        tiles=tiles,
        depth=depth,
        exit_pos=exit_pos,
        stairs_down_pos=stairs_down_pos,
        trap_positions=trap_positions,
    )


def generate_dungeon_levels(
    level_count: int,
    seed: int,
    width: int = 40,
    height: int = 24,
) -> list[TileMap]:
    return [
        generate_dungeon(
            depth=depth,
            max_depth=level_count,
            seed=seed,
            width=width,
            height=height,
        )
        for depth in range(1, level_count + 1)
    ]


def _generate_trap_positions(
    rng: random.Random,
    left: int,
    top: int,
    right: int,
    bottom: int,
    depth: int,
    exit_pos: tuple[int, int],
    stairs_down_pos: tuple[int, int] | None,
) -> set[tuple[int, int]]:
    candidates: list[tuple[int, int]] = []
    for y in range(top + 1, bottom - 1):
        for x in range(left + 1, right - 1):
            pos = (x, y)
            if pos == exit_pos or pos == stairs_down_pos:
                continue
            candidates.append(pos)

    rng.shuffle(candidates)
    trap_count = min(len(candidates), 2 + depth)
    return set(candidates[:trap_count])
