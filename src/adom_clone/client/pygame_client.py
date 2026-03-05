"""Pygame frontend for rendering, input mapping, and HUD presentation."""

from collections.abc import Iterable

import pygame

from adom_clone.core.game.actions import (
    DropLastItemAction,
    GameAction,
    MoveAction,
    PickupAction,
    UseItemAction,
    WaitAction,
)
from adom_clone.core.game.session import GameSession

TILE_SIZE = 24
HUD_HEIGHT = 140
PLAYER_COLOR = (245, 220, 90)
MONSTER_COLOR = (180, 60, 60)
ITEM_COLOR = (90, 200, 220)
TEXT_COLOR = (230, 230, 230)
BACKGROUND = (10, 10, 12)
DEFAULT_SAVE_FILE = "savegame.json"


def run_game() -> None:
    """Run the interactive client loop."""
    pygame.init()
    pygame.display.set_caption("ADOM Clone - Phase 3")

    session = GameSession()
    width_px = session.current_map.width * TILE_SIZE
    height_px = session.current_map.height * TILE_SIZE + HUD_HEIGHT
    screen = pygame.display.set_mode((width_px, height_px))
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("monospace", 18)

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

                if event.key == pygame.K_F5:
                    # Save/load hotkeys are kept in the client to avoid coupling UI concerns
                    # to the core turn-resolution code.
                    session.save_to_file(DEFAULT_SAVE_FILE)
                    session.add_message(f"Saved to {DEFAULT_SAVE_FILE}.")
                    continue

                if event.key == pygame.K_F9:
                    try:
                        session = GameSession.load_from_file(DEFAULT_SAVE_FILE)
                        session.add_message(f"Loaded {DEFAULT_SAVE_FILE}.")
                    except FileNotFoundError:
                        session.add_message(f"Save file not found: {DEFAULT_SAVE_FILE}.")
                    except ValueError:
                        session = GameSession()
                        session.add_message("Save file invalid; started a new run.")
                    continue

                if event.key == pygame.K_n:
                    session = GameSession()
                    session.add_message("A new adventure begins.")
                    continue

                maybe_action = _action_for_key(event.key)
                if maybe_action is not None:
                    session.queue_action(maybe_action)

        session.advance_turn()
        _draw(screen, font, session)
        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


def _draw(screen: pygame.Surface, font: pygame.font.Font, session: GameSession) -> None:
    """Draw map tiles, entities, and HUD."""
    screen.fill(BACKGROUND)
    tile_map = session.current_map

    for y in range(tile_map.height):
        for x in range(tile_map.width):
            tile = tile_map.get_tile(x, y)
            rect = pygame.Rect(x * TILE_SIZE, y * TILE_SIZE, TILE_SIZE, TILE_SIZE)
            pygame.draw.rect(screen, tile.color, rect)

    for x, y in session.item_positions():
        item_rect = pygame.Rect(
            x * TILE_SIZE + TILE_SIZE // 4,
            y * TILE_SIZE + TILE_SIZE // 4,
            TILE_SIZE // 2,
            TILE_SIZE // 2,
        )
        pygame.draw.rect(screen, ITEM_COLOR, item_rect)

    for x, y in session.monster_positions():
        monster_rect = pygame.Rect(x * TILE_SIZE, y * TILE_SIZE, TILE_SIZE, TILE_SIZE)
        pygame.draw.rect(screen, MONSTER_COLOR, monster_rect)

    pos = session.player_position
    player_rect = pygame.Rect(pos.x * TILE_SIZE, pos.y * TILE_SIZE, TILE_SIZE, TILE_SIZE)
    pygame.draw.rect(screen, PLAYER_COLOR, player_rect)

    hud_y = tile_map.height * TILE_SIZE
    pygame.draw.rect(screen, (20, 20, 24), pygame.Rect(0, hud_y, screen.get_width(), HUD_HEIGHT))
    map_line = (
        f"Map: {tile_map.kind.value} | HP: {session.player_hp_text} "
        f"| Turns: {session.turn_count} | Kills: {session.kill_count}"
    )
    controls_line = "Move: WASD/Arrows | G: pickup | 1-9:use | R:drop | .:wait | N:new run"
    save_line = "F5: save | F9: load | ESC: quit"
    inventory_line = _inventory_line(session)
    lines = [map_line, controls_line, save_line, inventory_line, *session.messages[-2:]]
    if session.game_over:
        lines.append("Game over. Press ESC to quit.")
    _blit_lines(screen, font, lines, hud_y + 8)


def _inventory_line(session: GameSession) -> str:
    """Build a compact inventory line for HUD display."""
    items = session.inventory_names()
    if not items:
        return "Inventory: (empty)"
    labeled = [f"{idx + 1}:{name}" for idx, name in enumerate(items[:9])]
    return f"Inventory: {' | '.join(labeled)}"


def _blit_lines(
    screen: pygame.Surface,
    font: pygame.font.Font,
    lines: Iterable[str],
    start_y: int,
) -> None:
    y = start_y
    for line in lines:
        rendered = font.render(line, True, TEXT_COLOR)
        screen.blit(rendered, (8, y))
        y += rendered.get_height() + 4


def _action_for_key(key: int) -> GameAction | None:
    """Translate key presses into domain actions."""
    if key in (pygame.K_w, pygame.K_UP):
        return MoveAction(0, -1)
    if key in (pygame.K_s, pygame.K_DOWN):
        return MoveAction(0, 1)
    if key in (pygame.K_a, pygame.K_LEFT):
        return MoveAction(-1, 0)
    if key in (pygame.K_d, pygame.K_RIGHT):
        return MoveAction(1, 0)
    if key == pygame.K_g:
        return PickupAction()
    if key == pygame.K_r:
        return DropLastItemAction()
    if key in (pygame.K_PERIOD, pygame.K_SPACE):
        return WaitAction()
    if pygame.K_1 <= key <= pygame.K_9:
        return UseItemAction(key - pygame.K_1)
    return None
