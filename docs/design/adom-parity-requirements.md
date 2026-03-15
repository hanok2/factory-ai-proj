# ADOM-Parity Requirements & TODO Roadmap

## 1. Objective

Track feature parity progress and define the next delivery wave toward ADOM-like systemic depth.

## 2. Status Legend

- `[x]` implemented
- `[ ]` pending

## 3. Current Baseline (Phase 7 Completed)

- [x] Multi-depth dungeon traversal and staircase transitions
- [x] Overworld + town + dungeon world routing
- [x] Character creation (race/class/seed)
- [x] Modular systems architecture (`Turn`, `Combat`, `Inventory`, `AI`, `Persistence`)
- [x] Equipment + melee + ranged combat
- [x] Spellcasting suite (`Arcane Bolt`, `Venom Lance`, `Mend`, `Ward`) with mana schools
- [x] Class-restricted branching talents with prerequisites
- [x] Damage types + resistance mitigation
- [x] Hidden trap discovery + disarm flow
- [x] Faction reputation influence on town NPC services
- [x] Multi-step quest journal with timeout/failure outcomes
- [x] Biome/archetype/vault dungeon generation baseline
- [x] Corruption meter baseline with mutation trigger
- [x] Save migration up to `v5`
- [x] Save integrity checksum validation + backup fallback diagnostics

## 4. Backlog by Domain

## 4.1 World Structure & Progression

### P0
- [x] Multi-level dungeon stack
- [x] Town hub node in overworld
- [ ] Additional overworld travel nodes and route costs

### P1
- [ ] Multiple dungeon branches with differentiated progression goals
- [ ] Region danger scaling and encounter ecology
- [ ] World clock and travel-time consequences

## 4.2 Character Progression

### P0
- [x] XP and level-up progression
- [x] Talent-point milestone hooks
- [x] Class specialization branches (initial implementation)
- [ ] Attribute training/decay loops

### P1
- [ ] Expanded skill training and class-specific passive ecosystems
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
- [x] Corruption baseline and mutation trigger
- [ ] Disease/toxin families and cure loops

### P1
- [ ] Environmental hazard layers (temperature/terrain)
- [ ] Long-run attrition balancing (ammo/food/piety economy)

## 4.5 NPC, Quest, and World Simulation

### P0
- [x] NPC role interactions (healer/shop/quest giver)
- [x] Reputation-aware town interactions
- [x] Multi-step quest state + journal + timeout/failure

### P1
- [ ] Faction-specific questlines and standing-driven unlock sets
- [ ] Named NPC progression and quest chains
- [ ] Consequence propagation to world state and endings

## 4.6 Procedural Content

### P0
- [x] Depth-aware spawn and trap generation baseline
- [x] Biome generation variants
- [x] Room archetype + vault layout hooks

### P1
- [ ] Encounter diversification by biome + depth + world state
- [ ] Secret rooms and puzzle/lock feature hooks
- [ ] Trap family diversification with richer disarm outcomes

## 4.7 Persistence and Reliability

### P0
- [x] Versioned migration (`v2 -> v5`)
- [x] Backup fallback for corrupted primary saves
- [x] Save integrity checksums + diagnostics panel integration

### P1
- [ ] Run manifest metadata (score, duration, endings)
- [ ] Leaderboard/challenge mode records

## 5. Parity Gap Snapshot

Largest remaining parity gaps:

1. **Advanced encounter ecology** (monster roles, caster AI, biome encounter tables)
2. **Long-run progression pressure** (expanded corruption, diseases, alignment/economy)
3. **World consequence depth** (multi-faction questlines, branching outcomes, region state)
4. **Procedural variety scale** (secret structures, special room mechanics, encounter families)

## 6. Next Phase (Phase 8) Plan

## 6.1 Goal

Move from structural/system parity to **encounter ecology and long-run world consequence depth**.

## 6.2 Phase 8 TODO Cut

1. [ ] Introduce monster role families (brute/skirmisher/caster/support) with role-aware AI behaviors.
2. [ ] Add advanced status set (slow/fear/confuse) with player + monster application paths.
3. [ ] Expand faction layer to at least two additional factions and standing-driven quest unlock gates.
4. [ ] Add biome-specific encounter tables and weighted spawn profiles.
5. [ ] Add corruption stage progression beyond first mutation with at least one reversible mitigation path.
6. [ ] Add secret room placement and reveal mechanics tied to exploration/perception systems.
7. [ ] Extend save diagnostics with explicit category tags for integrity/migration/recovery events.

## 6.3 Phase 8 Exit Criteria

- Distinct monster behavior patterns are visible in combat encounters.
- Faction standing meaningfully changes quest access and rewards.
- Biome identity affects both map layout and encounter makeup.
- Corruption develops beyond a single trigger and has tactical tradeoffs.
- Save diagnostics remain readable and actionable under failure scenarios.

## 7. Validation Checklist (Per New Feature)

- [ ] Data-driven definitions included
- [ ] Unit + integration tests updated
- [ ] Save compatibility verified
- [ ] UI/log feedback implemented
- [ ] Balancing knobs identified for iteration
