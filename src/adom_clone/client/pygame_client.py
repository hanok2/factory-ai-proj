"""Pygame frontend for rendering, input mapping, and HUD presentation."""

import random
from collections.abc import Iterable

import pygame

from adom_clone.core.game.actions import (
    DisarmTrapAction,
    DropLastItemAction,
    GameAction,
    MoveAction,
    PickupAction,
    RangedAttackAction,
    RestAction,
    UseItemAction,
    WaitAction,
)
from adom_clone.core.game.session import CharacterSelection, GameSession

TILE_SIZE = 24
HUD_HEIGHT = 140
PLAYER_COLOR = (245, 220, 90)
MONSTER_COLOR = (180, 60, 60)
ITEM_COLOR = (90, 200, 220)
TRAP_COLOR = (205, 80, 205)
TEXT_COLOR = (230, 230, 230)
BACKGROUND = (10, 10, 12)
DEFAULT_SAVE_FILE = "savegame.json"
CREATION_SIZE = (900, 620)


def run_game() -> None:
    """Run the interactive client loop."""
    pygame.init()
    pygame.display.set_caption("ADOM Clone - Phase 3")

    creation_screen = pygame.display.set_mode(CREATION_SIZE)
    selection = _character_creation_screen(creation_screen)
    session = GameSession(
        seed=selection.seed,
        race_id=selection.race_id,
        class_id=selection.class_id,
    )
    width_px = session.current_map.width * TILE_SIZE
    height_px = session.current_map.height * TILE_SIZE + HUD_HEIGHT
    screen = pygame.display.set_mode((width_px, height_px))
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("monospace", 18)

    running = True
    targeting_mode = False
    show_sheet = False
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if targeting_mode:
                        targeting_mode = False
                        session.add_message("Targeting cancelled.")
                        continue
                    if show_sheet:
                        show_sheet = False
                        continue
                    running = False

                if event.key == pygame.K_c:
                    show_sheet = not show_sheet
                    continue

                if targeting_mode:
                    maybe_ranged = _ranged_action_for_key(event.key)
                    if maybe_ranged is not None:
                        session.queue_action(maybe_ranged)
                        targeting_mode = False
                    continue

                if event.key == pygame.K_f:
                    targeting_mode = True
                    session.add_message("Targeting mode: choose a direction.")
                    continue

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
                    selection = _character_creation_screen(screen)
                    session = GameSession(
                        seed=selection.seed,
                        race_id=selection.race_id,
                        class_id=selection.class_id,
                    )
                    session.add_message("A new adventure begins.")
                    continue

                maybe_action = _action_for_key(event.key)
                if maybe_action is not None:
                    session.queue_action(maybe_action)

        session.advance_turn()
        _draw(screen, font, session, show_sheet, targeting_mode)
        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


def _draw(
    screen: pygame.Surface,
    font: pygame.font.Font,
    session: GameSession,
    show_sheet: bool,
    targeting_mode: bool,
) -> None:
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

    for x, y in session.trap_positions():
        trap_rect = pygame.Rect(
            x * TILE_SIZE + TILE_SIZE // 4,
            y * TILE_SIZE + TILE_SIZE // 4,
            TILE_SIZE // 2,
            TILE_SIZE // 2,
        )
        pygame.draw.rect(screen, TRAP_COLOR, trap_rect, width=2)

    for x, y in session.monster_positions():
        monster_rect = pygame.Rect(x * TILE_SIZE, y * TILE_SIZE, TILE_SIZE, TILE_SIZE)
        pygame.draw.rect(screen, MONSTER_COLOR, monster_rect)

    pos = session.player_position
    player_rect = pygame.Rect(pos.x * TILE_SIZE, pos.y * TILE_SIZE, TILE_SIZE, TILE_SIZE)
    pygame.draw.rect(screen, PLAYER_COLOR, player_rect)

    hud_y = tile_map.height * TILE_SIZE
    pygame.draw.rect(screen, (20, 20, 24), pygame.Rect(0, hud_y, screen.get_width(), HUD_HEIGHT))
    map_name = (
        tile_map.kind.value
        if tile_map.kind == session.overworld.kind
        else f"dungeon:{session.current_depth or 1}/{session.dungeon_level_count}"
    )
    map_line = (
        f"Map: {map_name} | HP: {session.player_hp_text} "
        f"| Hunger: {session.player_hunger_text}"
    )
    stats_line = (
        f"Power: {session.player_power} | Defense: {session.player_defense} "
        f"| {session.player_level_text} | Turns: {session.turn_count} | Kills: {session.kill_count}"
    )
    controls_line = (
        "Move: WASD/Arrows | G:pickup | 1-9:use/equip/eat | "
        "F:target | V:rest | X:disarm | R:drop | C:sheet"
    )
    save_line = "F5: save | F9: load | ESC: quit"
    inventory_line = _inventory_line(session)
    lines = [map_line, stats_line, controls_line, save_line, inventory_line, *session.messages[-2:]]
    if targeting_mode:
        lines.append("Targeting mode active: press a movement direction to throw.")
    if session.game_over:
        lines.append("Game over. Press ESC to quit.")
    _blit_lines(screen, font, lines, hud_y + 8)

    if show_sheet:
        _draw_character_sheet(screen, font, session)


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
    if key == pygame.K_v:
        return RestAction()
    if key == pygame.K_x:
        return DisarmTrapAction()
    if key == pygame.K_r:
        return DropLastItemAction()
    if key in (pygame.K_PERIOD, pygame.K_SPACE):
        return WaitAction()
    if pygame.K_1 <= key <= pygame.K_9:
        return UseItemAction(key - pygame.K_1)
    return None


def _ranged_action_for_key(key: int) -> RangedAttackAction | None:
    if key in (pygame.K_w, pygame.K_UP):
        return RangedAttackAction(0, -1)
    if key in (pygame.K_s, pygame.K_DOWN):
        return RangedAttackAction(0, 1)
    if key in (pygame.K_a, pygame.K_LEFT):
        return RangedAttackAction(-1, 0)
    if key in (pygame.K_d, pygame.K_RIGHT):
        return RangedAttackAction(1, 0)
    return None


def _draw_character_sheet(
    screen: pygame.Surface,
    font: pygame.font.Font,
    session: GameSession,
) -> None:
    panel = pygame.Rect(40, 40, screen.get_width() - 80, screen.get_height() - 80)
    pygame.draw.rect(screen, (8, 8, 12), panel)
    pygame.draw.rect(screen, (220, 220, 230), panel, width=2)

    equipment = session.player_equipment
    inv_names = session.inventory_names()
    weapon_name = "none"
    armor_name = "none"
    if equipment.weapon_item_id is not None:
        weapon_name = next((name for name in inv_names if "(wielded)" in name), "equipped")
    if equipment.armor_item_id is not None:
        armor_name = next((name for name in inv_names if "(worn)" in name), "equipped")

    lines = [
        "Character Sheet (C to close)",
        f"Race: {session.race.name}",
        f"Class: {session.character_class.name}",
        f"Seed: {session.seed}",
        f"{session.player_level_text}",
        f"HP: {session.player_hp_text}",
        f"Hunger: {session.player_hunger_text}",
        f"Power: {session.player_power}",
        f"Defense: {session.player_defense}",
        f"Weapon: {weapon_name}",
        f"Armor: {armor_name}",
        f"Turns: {session.turn_count} | Kills: {session.kill_count}",
    ]
    _blit_lines(screen, font, lines, panel.y + 12)


def _character_creation_screen(screen: pygame.Surface) -> "CharacterSelection":
    races, classes = GameSession.available_character_options()
    race_idx = 0
    class_idx = 0
    seed = 1337

    title_font = pygame.font.SysFont("monospace", 28)
    body_font = pygame.font.SysFont("monospace", 22)
    help_font = pygame.font.SysFont("monospace", 18)
    clock = pygame.time.Clock()

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                raise SystemExit(0)
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:
                    race_idx = (race_idx - 1) % len(races)
                elif event.key == pygame.K_DOWN:
                    race_idx = (race_idx + 1) % len(races)
                elif event.key == pygame.K_LEFT:
                    class_idx = (class_idx - 1) % len(classes)
                elif event.key == pygame.K_RIGHT:
                    class_idx = (class_idx + 1) % len(classes)
                elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    seed = max(1, seed - 1)
                elif event.key in (pygame.K_EQUALS, pygame.K_KP_PLUS):
                    seed += 1
                elif event.key == pygame.K_r:
                    seed = random.randint(1, 999_999)
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    return CharacterSelection(
                        race_id=races[race_idx].id,
                        class_id=classes[class_idx].id,
                        seed=seed,
                    )

        screen.fill((8, 8, 10))
        title = title_font.render("Character Creation", True, TEXT_COLOR)
        screen.blit(title, (24, 24))

        race = races[race_idx]
        class_def = classes[class_idx]
        lines = [
            f"Race (UP/DOWN): {race.name}",
            f"Class (LEFT/RIGHT): {class_def.name}",
            f"Seed (+/- or R=random): {seed}",
            "",
            (
                f"Class stats: HP {class_def.base_hp} | "
                f"Pow {class_def.base_power} | Def {class_def.base_defense}"
            ),
            "",
            "Press ENTER to start",
        ]

        y = 90
        for line in lines:
            rendered = body_font.render(line, True, TEXT_COLOR)
            screen.blit(rendered, (24, y))
            y += rendered.get_height() + 8

        hint = help_font.render(
            "Tip: Use item keys (1-9) to consume, heal, or equip gear.",
            True,
            (170, 170, 190),
        )
        screen.blit(hint, (24, screen.get_height() - 40))

        pygame.display.flip()
        clock.tick(60)

