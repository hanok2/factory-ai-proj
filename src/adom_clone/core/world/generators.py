"""World and dungeon generation utilities.

Phase 7 adds biome-aware dungeon generation, archetyped room carving, and simple
vault placement hooks while preserving deterministic seed behavior.
"""

import random

from adom_clone.core.world.map_model import MapKind, Tile, TileMap

GRASS = Tile(passable=True, color=(60, 140, 70), name="grass")
MOUNTAIN = Tile(passable=False, color=(80, 80, 80), name="mountain")
DUNGEON_ENTRANCE = Tile(passable=True, color=(120, 70, 30), name="dungeon_entrance")
TOWN_GATE = Tile(passable=True, color=(150, 120, 80), name="town_gate")

STAIRS_UP = Tile(passable=True, color=(170, 170, 90), name="stairs_up")
STAIRS_DOWN = Tile(passable=True, color=(90, 170, 170), name="stairs_down")
VAULT_MARKER = Tile(passable=True, color=(210, 160, 70), name="vault")

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
        biome="wilderness",
        room_archetype="open",
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
        biome="settlement",
        room_archetype="streets",
        exit_pos=exit_pos,
    )


def generate_dungeon(
    depth: int,
    max_depth: int,
    seed: int,
    width: int = 40,
    height: int = 24,
) -> TileMap:
    """Generate one dungeon level with biome and room-archetype variation.

    The algorithm remains deterministic by deriving all variation from `seed` and
    `depth`. This keeps tests stable and allows replay parity.
    """

    rng = random.Random(seed + depth * 313)
    biome_name, floor_tile, wall_tile = _select_biome(depth)
    room_archetype = _select_room_archetype(depth)

    tiles = [[wall_tile for _ in range(width)] for _ in range(height)]

    left = 2 + rng.randint(0, 2)
    top = 2 + rng.randint(0, 2)
    right = width - 3 - rng.randint(0, 2)
    bottom = height - 3 - rng.randint(0, 2)

    # Carve floor area according to the selected archetype.
    _carve_room_archetype(
        tiles=tiles,
        archetype=room_archetype,
        floor_tile=floor_tile,
        left=left,
        top=top,
        right=right,
        bottom=bottom,
    )

    exit_pos = (left + 1, top + 1)
    up_x, up_y = exit_pos
    tiles[up_y][up_x] = STAIRS_UP

    stairs_down_pos: tuple[int, int] | None = None
    if depth < max_depth:
        stairs_down_pos = (right - 2, bottom - 2)
        down_x, down_y = stairs_down_pos
        tiles[down_y][down_x] = STAIRS_DOWN

    vault_pos = _place_vault(
        rng=rng,
        tiles=tiles,
        floor_tile=floor_tile,
        left=left,
        top=top,
        right=right,
        bottom=bottom,
        blocked_positions={exit_pos, stairs_down_pos} if stairs_down_pos else {exit_pos},
    )

    trap_positions = _generate_trap_positions(
        rng=rng,
        left=left,
        top=top,
        right=right,
        bottom=bottom,
        depth=depth,
        exit_pos=exit_pos,
        stairs_down_pos=stairs_down_pos,
        vault_pos=vault_pos,
    )

    return TileMap(
        kind=MapKind.DUNGEON,
        width=width,
        height=height,
        tiles=tiles,
        depth=depth,
        biome=biome_name,
        room_archetype=room_archetype,
        exit_pos=exit_pos,
        stairs_down_pos=stairs_down_pos,
        vault_pos=vault_pos,
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


def _select_biome(depth: int) -> tuple[str, Tile, Tile]:
    """Choose a biome palette by depth band."""
    if depth % 3 == 1:
        return (
            "crypt",
            Tile(passable=True, color=(72, 72, 88), name="crypt_floor"),
            Tile(passable=False, color=(38, 38, 48), name="crypt_wall"),
        )
    if depth % 3 == 2:
        return (
            "fungal_caves",
            Tile(passable=True, color=(66, 92, 74), name="fungal_floor"),
            Tile(passable=False, color=(40, 64, 50), name="fungal_wall"),
        )
    return (
        "molten_ruins",
        Tile(passable=True, color=(110, 70, 56), name="molten_floor"),
        Tile(passable=False, color=(78, 44, 34), name="molten_wall"),
    )


def _select_room_archetype(depth: int) -> str:
    archetypes = ("chamber", "crossroads", "split_halls")
    return archetypes[(depth - 1) % len(archetypes)]


def _carve_room_archetype(
    *,
    tiles: list[list[Tile]],
    archetype: str,
    floor_tile: Tile,
    left: int,
    top: int,
    right: int,
    bottom: int,
) -> None:
    if archetype == "crossroads":
        mid_x = (left + right) // 2
        mid_y = (top + bottom) // 2
        for y in range(top, bottom):
            for x in range(mid_x - 2, mid_x + 3):
                tiles[y][x] = floor_tile
        for y in range(mid_y - 2, mid_y + 3):
            for x in range(left, right):
                tiles[y][x] = floor_tile
        return

    if archetype == "split_halls":
        gap_y = (top + bottom) // 2
        for y in range(top, gap_y - 1):
            for x in range(left, right):
                tiles[y][x] = floor_tile
        for y in range(gap_y + 1, bottom):
            for x in range(left, right):
                tiles[y][x] = floor_tile
        corridor_x = (left + right) // 2
        for y in range(top, bottom):
            tiles[y][corridor_x] = floor_tile
        return

    # Default chamber archetype: carve one large room.
    for y in range(top, bottom):
        for x in range(left, right):
            tiles[y][x] = floor_tile


def _place_vault(
    *,
    rng: random.Random,
    tiles: list[list[Tile]],
    floor_tile: Tile,
    left: int,
    top: int,
    right: int,
    bottom: int,
    blocked_positions: set[tuple[int, int] | None],
) -> tuple[int, int] | None:
    """Place a simple vault marker tile to seed high-value content locations."""
    candidates: list[tuple[int, int]] = []
    for y in range(top + 1, bottom - 1):
        for x in range(left + 1, right - 1):
            pos = (x, y)
            if pos in blocked_positions:
                continue
            if tiles[y][x].passable:
                candidates.append(pos)

    if not candidates:
        return None

    vault_pos = rng.choice(candidates)
    vx, vy = vault_pos
    tiles[vy][vx] = VAULT_MARKER if floor_tile.passable else floor_tile
    return vault_pos


def _generate_trap_positions(
    *,
    rng: random.Random,
    left: int,
    top: int,
    right: int,
    bottom: int,
    depth: int,
    exit_pos: tuple[int, int],
    stairs_down_pos: tuple[int, int] | None,
    vault_pos: tuple[int, int] | None,
) -> set[tuple[int, int]]:
    candidates: list[tuple[int, int]] = []
    for y in range(top + 1, bottom - 1):
        for x in range(left + 1, right - 1):
            pos = (x, y)
            if pos == exit_pos or pos == stairs_down_pos or pos == vault_pos:
                continue
            candidates.append(pos)

    rng.shuffle(candidates)
    trap_count = min(len(candidates), 2 + depth)
    return set(candidates[:trap_count])
