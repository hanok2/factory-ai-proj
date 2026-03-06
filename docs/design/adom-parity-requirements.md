# ADOM-Parity Requirements & TODO Roadmap

## 1. Objective

Track project status against ADOM-style feature expectations, and define the next phase needed to close the largest parity gaps.

## 2. Status Legend

- `[x]` implemented in current codebase
- `[ ]` not implemented yet

## 3. Current Baseline Summary (Implemented)

- [x] Multi-depth dungeon traversal with up/down transitions
- [x] System split (`TurnSystem`, `CombatSystem`, `InventorySystem`, `AISystem`, `PersistenceSystem`)
- [x] Equipment slots (weapon/armor) with effective stat bonuses
- [x] Hunger + food consumption loop
- [x] External content definitions (character options, spawn templates)
- [x] Deterministic seed selection
- [x] Save metadata includes seed/race/class/depth context
- [x] Character creation screen (race/class/seed + starting loadout)
- [x] XP/level progression scaffold with class growth rules
- [x] Ranged projectile attacks + target selection mode
- [x] Status effects baseline (poison/bleed/stun)
- [x] Resting and natural regeneration with interruption checks
- [x] Trap trigger/disarm interactions
- [x] Save migration support (`version 2 -> 3`)
- [x] Character sheet modal UI

## 4. Requirements Backlog (Updated)

## 4.1 World Structure & Progression

### P0
- [x] Replace single dungeon with multi-level dungeon stacks
- [ ] Add persistent overworld travel nodes (town, dungeon entrances, wilderness routes)
- [x] Add staircase-based vertical progression (up/down, level identity tracking)

### P1
- [ ] Add multiple themed dungeons with unique generation parameters
- [ ] Add danger-level and loot-tier scaling by region/depth
- [ ] Add world clock and travel time costs

## 4.2 Character Creation, Classes, Races, Alignment

### P0
- [x] Character creation flow at game start
- [x] Add race/class/background templates with stat deltas and starting kits
- [ ] Add alignment axis and initial alignment choice

### P1
- [x] Level progression, XP curve, and class-dependent advancement (baseline scaffold)
- [ ] Attribute training/decay rules
- [ ] Talents/perks selected at milestones

## 4.3 Advanced Combat & Tactics

### P0
- [x] Introduce equipment slots (weapon, armor baseline)
- [ ] Extend slots (shield, rings, amulet, missiles)
- [x] Add ranged attacks and ammunition baseline
- [ ] Add damage types/resistances framework

### P1
- [x] Add status effects baseline (poison, stun, bleeding)
- [ ] Add monster special abilities/spellcasting
- [ ] Add tactical AI roles (ranged kiter, brute, support caster, coward)

## 4.4 Inventory, Items, Identification, Economy

### P0
- [ ] Add stackable items and weight/encumbrance
- [x] Add initial item categories (food/potions/weapons/armor)
- [ ] Add unidentified item states and identify mechanics

### P1
- [ ] Add item generation affixes/ego variants
- [ ] Add shops with buy/sell and price modifiers
- [ ] Add durability and repair hooks

## 4.5 Survival Systems (ADOM Signature Feel)

### P0
- [x] Add hunger/satiation states with gameplay consequences (baseline)
- [x] Add healing over time and resting with interruption checks (baseline)
- [ ] Add disease/poison baseline hazards

### P1
- [ ] Add corruption system with timed pressure zones
- [ ] Add temperature/environment hazards where relevant
- [ ] Add long-run resource attrition loops (ammo, piety, scarcity pressure)

## 4.6 Factions, NPCs, Quests, Story Arcs

### P0
- [ ] Add neutral/friendly/hostile NPC dispositions
- [ ] Add quest framework (fetch, kill target, explore)
- [ ] Add town hub with trainers/healers/shops

### P1
- [ ] Add faction reputation and response rules
- [ ] Add branching quest outcomes and failure states
- [ ] Add unique named NPC interactions

## 4.7 Religion, Morality, and Consequence Systems

### P1
- [ ] Add deity/piety system with prayers, boons, and punishments
- [ ] Add alignment drift from player actions
- [ ] Add lawful/chaotic world interactions

### P2
- [ ] Add sacrificial altars and devotion-based progression hooks

## 4.8 Procedural Generation Depth

### P0
- [x] Add depth-based dungeon generation variability (baseline)
- [ ] Add richer room/corridor/vault generation variants
- [ ] Add biome/tile-set specific generation rules
- [ ] Add spawn tables tuned by depth + biome + region

### P1
- [ ] Add special vaults and rare rooms
- [x] Add trap generation and disarm interactions (baseline)
- [ ] Add secret doors and hidden content mechanics

## 4.9 UI/UX and Information Architecture

### P0
- [x] Add character creation flow UI
- [x] Add modal character sheet screen (core stats/equipment/metadata)
- [x] Add target selection UI for ranged actions
- [ ] Add keybinding help panel and command palette

### P1
- [ ] Add combat/event log filters and scrollback
- [ ] Add compare-tooltip for items/equipment
- [ ] Add run summary screen on death/victory

## 4.10 Persistence, Replay, and Meta Features

### P0
- [x] Expand save schema with deterministic metadata (seed/race/class/depth)
- [x] Add save migration framework baseline (`v2 -> v3`)
- [ ] Add robust corruption handling (backup saves, diagnostics)
- [ ] Add run manifest metadata (score, duration, outcomes)

### P1
- [ ] Add leaderboard/high-score table
- [ ] Add optional challenge seeds/modes

## 4.11 Engineering Requirements

### P0
- [x] Split gameplay orchestration into modular systems
- [x] Introduce content data files for monsters/items/characters
- [ ] Add deterministic simulation regression tests by seed

### P1
- [ ] Add property-based tests for generation invariants
- [ ] Add scenario integration tests for progression loops
- [ ] Add profiling hooks for turn-time hotspots

## 5. Parity Gap Snapshot

Largest missing ADOM-parity dimensions:

1. **Deep progression** (skills, talents, attribute training)
2. **Advanced tactical combat** (spells, resistances, richer status interactions)
3. **Simulation pressure systems** (corruption, piety/alignment, ecosystem consequences)
4. **Narrative/world systems** (quests, factions, NPC services, towns)
5. **Content density** (biomes, vaults, secrets, encounter variety)

## 6. Next Phase of Development (Phase 6)

## 6.1 Goal

Deliver the next leap from baseline tactical parity to **systems depth parity** by expanding progression complexity, spell/status interactions, and world simulation loops.

## 6.2 Completed Phase 5 Sprint

1. [x] Add XP + leveling scaffold with per-class growth rules.
2. [x] Add status-effect framework (poison/bleed/stun core hooks).
3. [x] Add ranged combat baseline (projectile item + target selection mode).
4. [x] Add basic resting and natural regen with interruption checks.
5. [x] Add trap tiles with trigger/disarm interaction and combat log feedback.
6. [x] Add save migration layer (`version 2 -> 3`) with compatibility tests.
7. [x] Add structured character sheet modal (stats, equipment, hunger, seed metadata).

## 6.3 Immediate Next Sprint (Phase 6 TODO Cut)

1. [ ] Add talent/feat selection at level-up milestones.
2. [ ] Add spellcasting baseline (projectile spell + utility spell) and mana resource.
3. [ ] Add resistance/damage-type layer and wire it into combat log output.
4. [ ] Add simple town hub map with healer/shop NPC interactions.
5. [ ] Add quest-state scaffold (single chain) with save-persistent progress.
6. [ ] Add trap perception/hidden-trap discovery hooks.
7. [ ] Add save backup + corruption diagnostics on load failure.

## 6.4 Sprint Exit Criteria

- progression loop is functional and test-covered,
- at least one non-melee combat path exists,
- at least one non-trivial survival/tactical decision (rest vs risk, trap handling, status management) is present,
- save/load remains backward-compatible for existing saves.

## 7. Validation Checklist for Each New Feature

- [ ] Data-driven where feasible (avoid hardcoded one-off logic)
- [ ] Unit tests for rules and edge cases
- [ ] Integration test for gameplay flow impact
- [ ] Persistence compatibility verified
- [ ] Player-facing UI/log feedback included
