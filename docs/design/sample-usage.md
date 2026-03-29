# ADOM-Clone Sample Usage Guide

This document shows practical usage patterns for the current Phase 8 build.

## 1. Launching the Game

From the repository root:

```bash
PYTHONPATH=src python3 -c "from adom_clone.client.pygame_client import run_game; run_game()"
```

## 2. Core Controls

- Move: `WASD` or arrow keys
- Wait: `.` or `Space`
- Pick up: `G`
- Use inventory slot: `1-9`
- Ranged attack mode: `F` then direction
- Arcane Bolt mode: `Z` then direction
- Venom Lance mode: `B` then direction
- Mend: `H`
- Ward: `U`
- Interact (NPC): `E`
- Rest: `V`
- Disarm trap: `X`
- Character sheet: `C`
- Talents: `T`
- Quest journal: `J`
- Save diagnostics: `O`
- Save/Load: `F5` / `F9`

## 3. Quick Start Walkthrough

## 3.1 Create Character

1. Choose race/class on creation screen.
2. Set or randomize seed.
3. Press `Enter` to start.

## 3.2 Early Loop

1. Pick up nearby resources (`G`).
2. Equip/use items with `1-9`.
3. Enter dungeon from overworld entrance.

## 3.3 Combat Samples

- **Melee**: move into an adjacent enemy.
- **Ranged**: press `F`, choose direction.
- **Caster**: press `Z`/`B` and choose direction.
- **Defense**: cast `U` before engaging dangerous casters/brutes.

## 4. Status and Survival Examples

- If slowed/fear/confused by traps or enemies, use positioning and `Wait` to stabilize.
- Use healer interaction in town (`E` near healer) to clear ailments and reduce corruption.
- Rest (`V`) only when no adjacent enemies are present.

## 5. Faction and Quest Flow Example

1. Enter town and talk to quest giver (`E`).
2. Complete quest objectives before deadline.
3. Turn in quest for XP/rewards and reputation gains.
4. Higher reputation unlocks advanced contracts (`arcane_anomaly`, `clan_beast_hunt`).

## 6. Corruption and Secrets Example

- Corruption rises in dungeon depth over turns.
- Mutation stages can shift as corruption rises/falls.
- Explore thoroughly to reveal secret rooms; perception/talent choices improve detection.

## 7. Save/Load and Diagnostics Example

1. Press `F5` to save.
2. Press `F9` to load.
3. Open diagnostics panel (`O`) to inspect categorized events:
   - `[integrity]`
   - `[migration]`
   - `[recovery]`

## 8. Programmatic Usage Example

Minimal script for simulation/testing:

```python
from adom_clone.core.game.actions import MoveAction, WaitAction
from adom_clone.core.game.session import GameSession

session = GameSession(seed=1337, class_id="wizard")
session.queue_action(WaitAction())
session.advance_turn()
session.queue_action(MoveAction(1, 0))
session.advance_turn()

print(session.player_hp_text)
print(session.player_mana_text)
print(session.faction_text)
print(session.quest_text)
```

Run with:

```bash
PYTHONPATH=src python3 your_script.py
```

## 9. Validation Commands

```bash
python3 -m ruff check src tests
python3 -m mypy src tests
python3 -m pytest tests/test_*.py -q
```
