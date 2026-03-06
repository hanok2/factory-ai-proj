# ADOM-Clone Current Design (Phase 5 Foundation)

## 1. Scope of the Current Build

The current build is a **Phase 5 foundation milestone** that extends the ADOM-oriented scaffold into basic tactical and progression play.

Implemented baseline features:

- ECS component model with dedicated gameplay systems,
- overworld + multi-depth dungeon traversal,
- character creation (race/class/seed),
- turn-based combat, equipment, inventory interactions,
- ranged projectile attacks with directional targeting,
- hunger and food consumption loop,
- status effects (poison/bleed/stun),
- trap trigger/disarm interactions,
- resting and natural regeneration,
- XP and level progression with class growth rules,
- deterministic seeded initialization,
- save/load with schema migration (`v2 -> v3`) and expanded metadata.

## 2. Runtime Architecture

## 2.1 Layering

- **Core domain (`src/adom_clone/core`)**
  - ECS store and components,
  - world map models/generators,
  - gameplay systems (`TurnSystem`, `CombatSystem`, `InventorySystem`, `AISystem`, `PersistenceSystem`),
  - session orchestration (`GameSession`) and content loading.
- **Content (`src/adom_clone/content`)**
  - JSON configuration for character options and spawn/template definitions.
- **Client (`src/adom_clone/client`)**
  - pygame loop, input mapping, character creation screen, rendering and HUD.

## 2.2 ECS + Systems

- **Entity**: integer ID (`ECSStore.create_entity`).
- **Components**: data-only structs (position, fighter, hunger, equipment, item traits, etc.).
- **Systems**:
  - `TurnSystem`: action dispatch + turn progression,
  - `CombatSystem`: damage/effective stats/death processing,
  - `InventorySystem`: pickup/use/equip/drop/eat,
  - `AISystem`: simple chase-and-attack behavior,
  - `PersistenceSystem`: session serialization/deserialization.

`GameSession` now coordinates systems and map/content lifecycle rather than containing all rule logic inline.

## 3. World and Progression Model

- **Overworld** contains a dungeon entrance.
- **Dungeons** are generated as `dungeon_levels[1..N]` with up/down transitions:
  - descend from overworld to level 1,
  - descend via `stairs_down_pos` to deeper levels,
  - ascend via `exit_pos` toward shallower levels,
  - ascend from level 1 back to overworld.

Depth context is tracked in both map state and `OnMap.depth` entity component.

## 4. Character and Build Initialization

- Character options are loaded from `character_options.json`.
- Player chooses:
  - race,
  - class,
  - deterministic seed.
- Class and race combine to derive starting HP/power/defense and hunger cap.
- Starting loadout is data-driven and can include equippable gear, food, and consumables.

## 5. Combat, Equipment, Inventory, Hunger

## 5.1 Combat

- Movement into hostile blockers resolves as melee attack.
- Effective combat values include equipment bonuses:
  - weapon -> power bonus,
  - armor -> defense bonus.
- Ranged attacks are supported through projectile items and directional targeting mode.
- Status hooks support poison/bleed damage-over-time and stun turn loss.

## 5.2 Equipment

- Slots currently implemented:
  - weapon,
  - armor.
- `UseItemAction` toggles equip/unequip for equippable items.

## 5.3 Inventory

- Supports pickup, slot-based use (`1..9`), and drop-last.
- Use behavior branches by item traits:
  - healing consumable,
  - food,
  - equippable.

## 5.4 Hunger

- Hunger decreases per acted turn.
- Threshold messages provide player feedback.
- Starvation deals HP damage and can cause death.

## 5.5 Resting and Regeneration

- `RestAction` restores HP when no adjacent monster is threatening the player.
- Natural regeneration restores HP periodically while out of immediate danger.

## 5.6 Traps

- Dungeons now generate active trap positions.
- Traps can be disarmed and can trigger damage + status effects.

## 6. Persistence and Determinism

- Save schema now includes:
  - `version`,
  - `seed`, `race_id`, `class_id`,
  - dungeon depth context,
  - trap state snapshots,
  - regen counter,
  - run metrics (`turn_count`, `kill_count`),
  - full component reconstruction payload.
- Rehydration validates key shapes/types, rebuilds ECS state, and migrates v2 saves to v3.

## 7. Client/UI State

Current client supports:

- character creation UI (race/class/seed),
- map + entity rendering,
- HUD with HP/hunger/power/defense/turns/kills,
- inventory display with equipped markers,
- targeting mode for ranged attacks,
- character sheet modal with build metadata,
- save/load/new-run hotkeys.

## 8. Test Coverage Snapshot

Current automated tests verify:

- ECS component lifecycle,
- overworld <-> dungeon transitions and depth movement,
- combat interactions,
- progression and XP leveling,
- ranged attack behavior,
- rest and trap interactions,
- v2 -> v3 save migration,
- inventory/heal/food/equipment behavior,
- save/load round-trip and metadata persistence.

Validation pipeline: `pytest`, `ruff`, `mypy`.

## 9. Current Constraints / Gaps

Despite this Phase 5 progress, ADOM parity is still far from complete. Major gaps:

- no deep skill/talent trees or attribute training,
- no spellcasting system and limited status variety,
- no corruption/piety/alignment systems,
- no quest/faction/NPC economy loops,
- no robust biome diversity, vaults, or secret mechanics,
- no long-run world simulation (time/region consequences).

## 10. Next Phase Direction (Phase 6)

To move toward ADOM parity, the next implementation phase should prioritize:

1. **Deep progression** (talents/skills and milestone choices beyond basic leveling).
2. **Expanded tactical combat** (spellcasting, resistances, and richer status ecosystem).
3. **World simulation systems** (town services, quests, faction/NPC state).
4. **Procedural expansion** (biomes, vaults, secret content, richer encounter tables).
5. **Persistence hardening** (backup/corruption handling and richer run manifest data).

This sequencing preserves current architecture while unlocking higher-value ADOM mechanics incrementally.
