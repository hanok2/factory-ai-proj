# ADOM-Parity Requirements & TODO Roadmap

## 1. Objective

Track feature parity progress and define the next delivery wave toward ADOM-like systemic depth.

## 2. Status Legend

- `[x]` implemented
- `[ ]` pending

## 3. Current Baseline (Phase 6 Completed)

- [x] Multi-depth dungeon traversal and staircase transitions
- [x] Overworld + town + dungeon world routing
- [x] Character creation (race/class/seed)
- [x] Modular systems architecture (`Turn`, `Combat`, `Inventory`, `AI`, `Persistence`)
- [x] Equipment + melee + ranged combat
- [x] Spellcasting baseline (Arcane Bolt + Mend) with mana
- [x] Damage types + resistance mitigation logs
- [x] XP leveling + talent milestones + talent selection
- [x] Hidden trap discovery + disarm flow
- [x] Town NPC services + quest scaffold
- [x] Save migration up to `v4`
- [x] Save backup fallback and corruption diagnostics

## 4. Backlog by Domain

## 4.1 World Structure & Progression

### P0
- [x] Multi-level dungeon stack
- [x] Town hub node in overworld
- [ ] Additional overworld travel nodes and route costs

### P1
- [ ] Multiple themed dungeon lines
- [ ] Region danger scaling and encounter ecology
- [ ] World clock and travel-time consequences

## 4.2 Character Progression

### P0
- [x] XP and level-up progression
- [x] Talent-point milestone hooks
- [ ] Attribute training/decay loops

### P1
- [ ] Class skill trees and milestone specialization branches
- [ ] Alignment axis and progression influence

## 4.3 Combat & Tactics

### P0
- [x] Melee + ranged + spells baseline
- [x] Typed damage/resistance pipeline
- [x] Baseline status effect support

### P1
- [ ] Extended statuses (confusion/blindness/slow/fear)
- [ ] Monster casters and role-driven tactical AI
- [ ] Equipment slot expansion (rings/amulets/missiles)

## 4.4 Survival Systems

### P0
- [x] Hunger + resting + regen loops
- [x] Trap hazards and discovery mechanics
- [ ] Disease/toxin variants and cure loops

### P1
- [ ] Corruption pressure systems
- [ ] Environmental hazard layers (temperature/terrain)
- [ ] Long-run attrition balancing (ammo/food/piety economy)

## 4.5 NPC, Quest, and World Simulation

### P0
- [x] NPC role interactions (healer/shop/quest giver)
- [x] Save-persistent single quest scaffold
- [ ] Multi-quest journal and branching outcomes

### P1
- [ ] Faction reputation and response behaviors
- [ ] Named NPC progression and quest chains
- [ ] Consequence propagation to world state and endings

## 4.6 Procedural Content

### P0
- [x] Depth-aware spawn and trap generation baseline
- [ ] Biome/tile-set generation variants
- [ ] Room archetype/vault/secret layout systems

### P1
- [ ] Encounter table diversification by biome + depth + world state
- [ ] Trap families with disarm skill checks and loot hooks

## 4.7 Persistence and Reliability

### P0
- [x] Versioned migration (`v2 -> v4`)
- [x] Backup fallback for corrupted primary saves
- [ ] Save integrity checksum + explicit diagnostics UI

### P1
- [ ] Run manifest metadata (score, duration, endings)
- [ ] Leaderboard/challenge mode records

## 5. Parity Gap Snapshot

Largest remaining parity gaps:

1. **Deep progression complexity** (skills/specs/attributes beyond milestones)
2. **Advanced combat ecology** (spells, AI roles, broader status gameplay)
3. **World consequence simulation** (factions, branching quest outcomes, reactive world)
4. **Procedural scale** (biomes, vaults, secrets, encounter diversity)
5. **Long-run ADOM systems** (corruption/piety/morality pressure)

## 6. Next Phase (Phase 7) Plan

## 6.1 Goal

Move from baseline systems depth to **emergent progression + world consequence depth**.

## 6.2 Phase 7 TODO Cut

1. [ ] Add multi-branch talent trees with class-specific specialization paths.
2. [ ] Add mana schools + second offensive spell archetype + utility spell scaling.
3. [ ] Add faction reputation layer and tie NPC services/quest availability to standing.
4. [ ] Add multi-step quest journal with failure/timeout outcomes.
5. [ ] Add biome-based dungeon variants with room archetype and vault generation.
6. [ ] Add corruption meter baseline and one corruption mutation effect.
7. [ ] Add save integrity checks and in-client corruption diagnostics panel.

## 6.3 Phase 7 Exit Criteria

- Build paths diverge materially through specialization choices.
- NPC/quest availability changes based on player world interactions.
- Dungeon runs feel biome-distinct and no longer layout-homogeneous.
- At least one long-run pressure system (corruption) is active and test-covered.

## 7. Validation Checklist (Per New Feature)

- [ ] Data-driven definitions included
- [ ] Unit + integration tests updated
- [ ] Save compatibility verified
- [ ] UI/log feedback implemented
- [ ] Balancing knobs identified for iteration
