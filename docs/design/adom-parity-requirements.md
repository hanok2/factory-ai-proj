# ADOM-Parity Requirements & TODO Roadmap

## 1. Purpose

This document defines a requirements-oriented backlog for evolving the current roguelike toward ADOM-style depth.

## 2. Product Principles

1. **Systemic depth over visual complexity**.
2. **Meaningful long-run consequences** (risk, corruption, scarcity, world reactions).
3. **Strong replayability** via procedural content, diverse starts, and emergent interactions.
4. **Hard but fair** difficulty curve with discoverable mechanics.

## 3. Priority Legend

- **P0**: Required foundation to support ADOM-like loop.
- **P1**: Core ADOM-feel systems.
- **P2**: High-value depth/polish.
- **P3**: Extended parity and content scale.

## 4. Requirements Backlog

## 4.1 World Structure & Progression

### P0 TODOs
- [ ] Replace single dungeon with multi-level dungeon stacks.
- [ ] Add persistent overworld travel nodes (town, dungeon entrances, wilderness routes).
- [ ] Add staircase-based vertical progression (up/down, level identity tracking).

### P1 TODOs
- [ ] Add multiple themed dungeons with unique generation parameters.
- [ ] Add danger-level and loot-tier scaling by region/depth.
- [ ] Add world clock and travel time costs.

### Acceptance Targets
- Save/load preserves full world graph and visited-state.
- Player can branch between at least 3 independent dungeon lines.

## 4.2 Character Creation, Classes, Races, Alignment

### P0 TODOs
- [ ] Character creation flow at game start.
- [ ] Add race/class/background templates with stat deltas and starting kits.
- [ ] Add alignment axis and initial alignment choice.

### P1 TODOs
- [ ] Level progression, XP curve, and class-dependent advancement.
- [ ] Attribute training/decay rules.
- [ ] Talents/perks selected at milestones.

### Acceptance Targets
- At least 6 class/race combinations produce materially different early game.

## 4.3 Advanced Combat & Tactics

### P0 TODOs
- [ ] Introduce equipment slots (weapon, armor, shield, rings, amulet, missiles).
- [ ] Add ranged attacks and ammunition.
- [ ] Add damage types/resistances framework.

### P1 TODOs
- [ ] Add status effects (poison, stun, bleeding, confusion, blindness).
- [ ] Add monster special abilities/spellcasting.
- [ ] Add tactical AI roles (ranged kiter, brute, support caster, coward).

### Acceptance Targets
- Combat log exposes source, type, and mitigation for each damage event.

## 4.4 Inventory, Items, Identification, Economy

### P0 TODOs
- [ ] Add stackable items and weight/encumbrance.
- [ ] Add item categories (food, potions, scrolls, wands, armor, weapons, tools).
- [ ] Add unidentified item states and identify mechanics.

### P1 TODOs
- [ ] Add item generation affixes/ego variants.
- [ ] Add shops with buy/sell and price modifiers.
- [ ] Add durability and repair hooks.

### Acceptance Targets
- Unknown items can be discovered via use, skill checks, or identify services.

## 4.5 Survival Systems (ADOM Signature Feel)

### P0 TODOs
- [ ] Add hunger/satiation states with gameplay consequences.
- [ ] Add healing over time and resting with interruption risks.
- [ ] Add disease/poison baseline hazards.

### P1 TODOs
- [ ] Add corruption system with timed pressure zones.
- [ ] Add temperature/environment hazards where relevant.
- [ ] Add long-run resource attrition loops (food, ammo, piety, consumables).

### Acceptance Targets
- Survival pressure influences route decisions; not merely cosmetic.

## 4.6 Factions, NPCs, Quests, Story Arcs

### P0 TODOs
- [ ] Add neutral/friendly/hostile NPC dispositions.
- [ ] Add simple quest framework (fetch, kill target, explore).
- [ ] Add town hub with trainers/healers/shops.

### P1 TODOs
- [ ] Add faction reputation and response rules.
- [ ] Add branching quest outcomes and failure states.
- [ ] Add unique named NPC interactions.

### Acceptance Targets
- Quest outcomes can lock/unlock content and influence endings.

## 4.7 Religion, Morality, and Consequence Systems

### P1 TODOs
- [ ] Add deity/piety system with prayers, boons, and punishments.
- [ ] Add alignment drift from player actions.
- [ ] Add lawful/chaotic world interactions.

### P2 TODOs
- [ ] Add sacrificial altars and devotion-based progression hooks.

### Acceptance Targets
- Morality choices produce persistent mechanical tradeoffs.

## 4.8 Procedural Generation Depth

### P0 TODOs
- [ ] Add room/corridor generation variants beyond single open area.
- [ ] Add biome/tile-set specific generation rules.
- [ ] Add spawn tables controlled by depth and biome.

### P1 TODOs
- [ ] Add special vaults and rare rooms.
- [ ] Add trap generation and disarm interactions.
- [ ] Add secret doors and hidden content mechanics.

### Acceptance Targets
- Runs differ materially while remaining balance-testable with seeded generation.

## 4.9 UI/UX and Information Architecture

### P0 TODOs
- [ ] Add modal screens for character sheet, equipment, inventory details, and message history.
- [ ] Add target selection UI for ranged/spells.
- [ ] Add keybinding help panel and command palette.

### P1 TODOs
- [ ] Add combat/event log filters and scrollback.
- [ ] Add compare-tooltip for items/equipment.
- [ ] Add run summary screen on death/victory.

### Acceptance Targets
- Player can access all critical stats and controls without external docs.

## 4.10 Persistence, Replay, and Meta Features

### P0 TODOs
- [ ] Expand save schema with migration support by version.
- [ ] Add robust corruption handling (backup saves, validation diagnostics).
- [ ] Add run manifest metadata (seed, class, score, duration).

### P1 TODOs
- [ ] Add leaderboard/high-score table.
- [ ] Add optional challenge seeds/modes.

### Acceptance Targets
- Old save versions can be migrated or gracefully rejected with recovery guidance.

## 4.11 Engineering Requirements

### P0 TODOs
- [ ] Split `GameSession` into modular systems (turn, combat, inventory, AI, persistence).
- [ ] Introduce content data files (JSON/YAML) for monsters/items/world templates.
- [ ] Add deterministic simulation tests by seed.

### P1 TODOs
- [ ] Add property-based tests for generation invariants.
- [ ] Add scenario integration tests for key progression loops.
- [ ] Add profiling/telemetry hooks for turn-time hotspots.

### Acceptance Targets
- Core gameplay loops remain deterministic under identical seed + input sequences.

## 5. Suggested Implementation Waves

## Wave A (P0 Foundation)
- Multi-level world graph
- character creation
- equipment + ranged combat
- hunger loop
- modular system refactor

## Wave B (P1 Core ADOM Feel)
- corruption + piety/alignment
- factions/quests
- advanced procgen (vaults/traps)
- deeper AI and status systems

## Wave C (P2/P3 Scale)
- broad content expansion
- advanced replay/meta systems
- long-tail polish and balancing

## 6. Immediate Next Sprint (Concrete TODO Cut)

1. [ ] Refactor `GameSession` into `TurnSystem`, `CombatSystem`, `InventorySystem`, `AISystem`, `PersistenceSystem`.
2. [ ] Introduce equipment slots and basic equippable weapons/armor.
3. [ ] Add dungeon depth array (`dungeon_1..dungeon_n`) and staircase transitions.
4. [ ] Add hunger timer and food consumables.
5. [ ] Convert monster/item spawn definitions to external content data files.
6. [ ] Add deterministic seed selection and include seed in save metadata.
7. [ ] Add a character creation screen (race/class + starting loadout).

## 7. Gap Snapshot vs Current Build

### Implemented now
- Overworld + single dungeon, turn loop, melee combat, basic inventory, save/load, pygame HUD.

### Missing for ADOM-like depth
- character generation and long-run progression,
- layered world graph with multiple dungeons and towns,
- survival systems (hunger/corruption/piety),
- rich itemization and identification,
- quest/faction/NPC consequence loops,
- broad encounter and biome diversity.

## 8. Dependency-Aware Delivery Order

1. **Engine modularization first** (split `GameSession`) to reduce coupling risk.
2. **Data-driven content next** so new systems don’t hardcode templates.
3. **Progression + equipment** before advanced combat mechanics.
4. **Survival pressure loops** once inventory/economy depth is in place.
5. **World/quest/faction systems** after stable persistence and state graphing.

## 9. Definition of Done Checklist (Per Feature)

Every new ADOM-parity feature should satisfy all:

- [ ] represented in data files, not hardcoded constants only,
- [ ] covered by unit tests for rules and edge cases,
- [ ] integrated scenario test proves loop-level behavior,
- [ ] saved/loaded correctly through schema versioning,
- [ ] visible in UI with player-facing feedback/logging,
- [ ] documented balancing knobs for iterative tuning.
