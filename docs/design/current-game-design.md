# ADOM-Clone Current Design (Phase 6 Implementation)

## 1. Scope of the Current Build

The project now includes the full **Phase 6 sprint cut** on top of the Phase 5 baseline.

Implemented highlights:

- modular ECS-driven runtime (`Turn`, `Combat`, `Inventory`, `AI`, `Persistence`),
- overworld + town hub + multi-depth dungeon world structure,
- character creation and class/race/seed-driven starts,
- melee + ranged + spellcasting (Arcane Bolt + Mend),
- typed damage and resistance mitigation logging,
- XP leveling plus talent point milestones and talent selection,
- town NPC services (healer/shopkeeper/quest giver),
- hidden trap discovery + disarm flow,
- save migration to schema v4 with backup fallback and corruption diagnostics.

## 2. Runtime Architecture

## 2.1 Layering

- **Core domain (`src/adom_clone/core`)**
  - ECS components and store,
  - map models/generators,
  - game systems and `GameSession` orchestration.
- **Content (`src/adom_clone/content`)**
  - class/race, spawn, and template data in JSON.
- **Client (`src/adom_clone/client`)**
  - pygame input loop, render layers, HUD/modals.

## 2.2 Core Components Added in Phase 6

- `Mana`
- `Talents`
- `Resistances`
- `Npc` + `NpcRole`
- `DamageType` enum
- `QuestState` (session-level run state)

## 3. World Model

- **Overworld**
  - contains dungeon entrance and town entry tile.
- **Town**
  - contains service NPCs and quest-giver interactions.
- **Dungeon Levels**
  - maintain depth-indexed stairs and trap state.

Transition graph:

- overworld <-> town
- overworld <-> dungeon level 1
- dungeon depth N <-> N+1 via stairs

## 4. Progression + Talent Layer

- XP is granted via `ExperienceReward` on monster death.
- Level-up grants stat growth (HP/power/defense/mana scaling by class).
- Talent points are granted at class-defined milestone levels.
- Talent selection is explicit and persistent.

Current talents:

- `arcane_efficiency` (reduced spell costs)
- `keen_senses` (better hidden trap detection)
- `hardened` (+physical resistance)

## 5. Combat and Magic

## 5.1 Damage Typing

Damage now carries type (`physical`, `poison`, `arcane`) and is resolved through resistance mitigation.

Combat log messaging exposes dealt and resisted damage for player-facing clarity.

## 5.2 Spellcasting Baseline

- **Arcane Bolt**: directional projectile spell (mana cost + arcane damage).
- **Mend**: utility self-heal spell.

Mana regenerates over time; spell costs can be modified by talents.

## 6. Town NPC + Quest Scaffold

Town includes three role-based NPC interactions:

- **Quest giver**: starts and resolves a kill-target quest chain,
- **Healer**: restores HP/mana and clears statuses,
- **Shopkeeper**: provides baseline supplies.

Quest state is serialized and restored across save/load.

## 7. Hidden Trap System

- Traps are tracked separately as hidden vs discovered.
- Trap perception runs each turn with deterministic detection checks.
- Adjacent traps are reliably discoverable.
- Only discovered traps are rendered in HUD map layer.

## 8. Persistence and Recovery

Current save schema is **version 4**.

Persistence includes:

- quest state,
- town state,
- trap hidden/discovered state,
- phase 6 components (mana/talents/resistances/NPCs).

Reliability behavior:

- saves create `.bak` backups when overwriting,
- corrupted primary saves attempt backup recovery,
- diagnostics are surfaced when recovery is not possible.

## 9. Client/UI State

UI now includes:

- ranged targeting mode,
- spell targeting mode,
- talent selection modal,
- expanded character sheet (mana/talents/spells/quest),
- interact command for NPC services.

## 10. Test Coverage Snapshot

Automated coverage now validates:

- progression + talent selection,
- arcane spellcasting + mana usage,
- town interaction and quest activation,
- hidden trap discovery,
- corrupted-save fallback to backup,
- all previous combat/inventory/transition/save foundations.

## 11. Remaining Gaps After Phase 6

Major ADOM-parity gaps still open:

- deep class progression trees and skill training,
- richer spell/status ecosystems and advanced AI roles,
- multi-quest/faction/world-reaction simulation,
- broader procgen diversity (biomes, vaults, secrets),
- long-run systems (corruption/piety/alignment, economy depth).
