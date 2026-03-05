from adom_clone.core.world.map_model import MapKind, Tile, TileMap

GRASS = Tile(passable=True, color=(60, 140, 70), name="grass")
MOUNTAIN = Tile(passable=False, color=(80, 80, 80), name="mountain")
DUNGEON_ENTRANCE = Tile(passable=True, color=(120, 70, 30), name="dungeon_entrance")
FLOOR = Tile(passable=True, color=(70, 70, 90), name="floor")
WALL = Tile(passable=False, color=(40, 40, 50), name="wall")
STAIRS_UP = Tile(passable=True, color=(170, 170, 90), name="stairs_up")


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

    return TileMap(
        kind=MapKind.OVERWORLD,
        width=width,
        height=height,
        tiles=tiles,
        entrance_pos=entrance_pos,
    )


def generate_dungeon(width: int = 40, height: int = 24) -> TileMap:
    tiles = [[WALL for _ in range(width)] for _ in range(height)]

    for y in range(2, height - 2):
        for x in range(2, width - 2):
            tiles[y][x] = FLOOR

    exit_pos = (3, 3)
    ex, ey = exit_pos
    tiles[ey][ex] = STAIRS_UP

    return TileMap(
        kind=MapKind.DUNGEON,
        width=width,
        height=height,
        tiles=tiles,
        exit_pos=exit_pos,
    )
