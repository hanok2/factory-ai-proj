# ADOM-Clone Phase 8 Detailed Design

## 1. Purpose

Phase 8 extends the Phase 7 baseline from foundational systems into encounter ecology and long-run progression pressure. The implementation focuses on role-driven monster behavior, richer status interactions, reputation-gated quest progression, biome-aware encounter weighting, corruption stage evolution, secret-room discovery, and stronger save diagnostics.

## 2. Design Goals

1. Make encounters tactically distinct through monster roles.
2. Expand status gameplay beyond poison/bleed/stun with new player and monster control states.
3. Move faction reputation from a single-axis gate (`townfolk`) to multi-faction progression.
4. Improve procedural identity by tying spawn tables to biome/depth constraints.
5. Evolve corruption from one threshold trigger into staged mutation progression plus mitigation.
6. Add secret discovery as an exploration feedback loop.
7. Improve persistence observability with categorized diagnostics.

## 3. Core Architecture Impact

Phase 8 preserves the existing layered structure:

- `core/ecs`: components and store
- `core/game`: session logic + systems (turn, AI, combat, persistence)
- `core/world`: tile maps and generators
- `content`: JSON templates and spawn rules
- `client`: pygame rendering/input

Changes are additive and integrated through `GameSession` orchestration and `AISystem` execution.

## 4. Data Model Extensions

## 4.1 ECS Components

### `Monster`

Extended with:

- `role: MonsterRole`
- `faction: str`

`MonsterRole` enum values:

- `brute`
- `skirmisher`
- `caster`
- `support`

### `StatusEffects`

Extended with:

- `slow: int`
- `fear: int`
- `confuse: int`

Existing fields retained (`poison`, `bleed`, `stun`, `ward_turns`, `ward_strength`).

### `TileMap`

Extended with secret-room state:

- `secret_rooms: set[(x, y)]`
- `discovered_secrets: set[(x, y)]`

## 4.2 Content Schema

`MonsterTemplate` now includes:

- `role`
- `faction`

`SpawnRule` now supports weighted/filtered spawn constraints:

- `weight`
- `biomes`
- `min_depth`
- `max_depth`

These are loaded from `spawns.json` and used by weighted rule selection in `GameSession`.

## 5. Gameplay Systems

## 5.1 Role-Driven AI

`AISystem` behavior is now role-specific:

- **Brute**: direct pressure and melee engagement.
- **Skirmisher**: attempts disengage behavior under pressure, opportunistic jabs.
- **Caster**: ranged/control pressure with arcane attacks and control statuses.
- **Support**: heals adjacent wounded allies or applies slow pressure.

Cross-cutting AI effects:

- slow can skip turns,
- confuse disrupts deterministic movement intent,
- stun remains hard-disable,
- status ticks continue through `apply_status_damage`.

## 5.2 Expanded Status Pipeline

New status semantics:

- **slow**: intermittent action suppression / reduced action cadence,
- **fear**: can prevent aggressive player actions when adjacent threats exist,
- **confuse**: directional actions may be redirected.

Status application can now originate from:

- spell interactions,
- trap outcomes,
- monster role actions,
- quest/encounter side effects.

All statuses serialize through persistence and are restored across load.

## 5.3 Trap and Exploration Feedback

Trap outcome selector expanded to include new status outcomes (`slow`, `fear`, `confuse`) in addition to prior effects.

Secret-room loop:

- generation creates hidden anchors per dungeon level,
- exploration checks reveal nearby secrets,
- revealed secrets are tracked separately from hidden pool.

## 6. Faction and Quest Progression

## 6.1 Reputation Model

Faction state now tracks:

- `townfolk`
- `arcane_order`
- `wild_clans`

Reputation adjustments are tied to:

- quest outcomes (success/failure),
- NPC service interactions,
- faction-affiliated kills.

## 6.2 Quest Unlock Flow

Quest chain progresses through reputation-gated contracts:

1. `town_goblin_cull`
2. `arcane_anomaly`
3. `clan_beast_hunt`

Each quest can enforce minimum reputation requirements before acceptance.

Quest state remains staged and deadline-driven, with timeout penalties propagating into reputation.

## 7. Corruption Progression

Phase 8 introduces staged corruption mutation progression:

- baseline stage (none),
- `chaos_skin`,
- `void_sight`.

Transition behavior:

- mutation effects are applied/reverted through transition deltas,
- corruption can be reduced by mitigation sources (e.g., healer interaction),
- mutation stage is recalculated after both increase and reduction.

## 8. Procedural Encounter Diversity

Dungeon encounters now honor rule-level constraints:

- biome matching,
- depth windows,
- weighted selection.

This preserves deterministic generation while broadening biome identity and encounter variation.

## 9. Persistence and Diagnostics

## 9.1 Save Schema

Schema advanced to **v6**.

Serialized additions include:

- monster role/faction,
- extended status fields,
- secret room state,
- expanded faction map.

Migration behavior includes v5 → v6 conversion and checksum invalidation when structure changes.

## 9.2 Diagnostics Categories

Diagnostic entries are now category-tagged:

- `[integrity]`
- `[migration]`
- `[recovery]`

This supports clearer troubleshooting in diagnostics UI surfaces and logs.

## 10. Testing Strategy (Phase 8)

Phase 8 tests validate:

- role-specific AI behavior,
- status/control effects,
- biome-weighted spawn filtering,
- faction-gated quest acceptance,
- corruption stage transitions + mitigation,
- secret-room reveal flow,
- diagnostics category tagging,
- migration expectation update to save schema v6.

## 11. Backward Compatibility Notes

- Existing save loads are supported via migration path up to v6.
- Legacy checksums are intentionally invalidated during structural migration.
- Existing gameplay loops (movement/combat/inventory/world transitions) remain compatible.

## 12. Known Extension Points

1. Add more role abilities per biome/faction archetype.
2. Expand status interactions (stacking/counters/immunities).
3. Add faction-specific questline trees and rewards.
4. Enrich secret-room rewards/events.
5. Add UI overlays for role/faction/secret telemetry.
