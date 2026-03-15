# ADOM-Clone Current Design (Phase 7 Implementation)

## 1. Scope of the Current Build

The project now includes the full **Phase 7 sprint cut** on top of the Phase 6 baseline.

Implemented highlights:

- modular ECS-driven runtime (`Turn`, `Combat`, `Inventory`, `AI`, `Persistence`),
- overworld + town hub + multi-depth dungeon world structure,
- biome-aware dungeon generation (crypt / fungal caves / molten ruins),
- room archetypes (`chamber`, `crossroads`, `split_halls`) and vault placement hooks,
- melee + ranged + expanded spellcasting (`Arcane Bolt`, `Venom Lance`, `Mend`, `Ward`),
- mana-school scaling (`arcane`, `poison`, `vitality`) with class mastery profiles,
- class-restricted branching talent trees with prerequisites,
- faction reputation affecting NPC service behavior,
- multi-step quest state with journal entries and timeout/failure outcomes,
- corruption meter with mutation trigger (`chaos_skin`),
- save schema v5 with checksum validation + backup recovery diagnostics panel support.

## 2. Runtime Architecture

### 2.1 Layering

- **Core domain (`src/adom_clone/core`)**
  - ECS components and store,
  - map models/generators,
  - game systems and `GameSession` orchestration.
- **Content (`src/adom_clone/content`)**
  - class/race, spawn, and template data in JSON.
- **Client (`src/adom_clone/client`)**
  - pygame input loop, render layers, HUD/modals.

### 2.2 Core Components Added Through Phase 7

- `Mana`, `Talents`, `Resistances`
- `Corruption`
- `Npc` + `NpcRole`
- `DamageType`, `ManaSchool`
- expanded `StatusEffects` (ward duration/strength)
- `QuestState` with stage/progress/deadline/failure/journal fields

## 3. World Model

- **Overworld**: dungeon entrance + town entry tile.
- **Town**: healer/shopkeeper/quest-giver NPC hub.
- **Dungeon Levels**:
  - depth-indexed stairs and trap state,
  - biome metadata,
  - room archetype metadata,
  - optional vault anchor position.

Transition graph:

- overworld <-> town
- overworld <-> dungeon level 1
- dungeon depth N <-> N+1 via stairs

## 4. Progression and Talent Trees

- XP is granted via `ExperienceReward` on monster death.
- Level-up grants class-driven HP/power/defense/mana growth.
- Talent points unlock at class milestones.
- Talent selection now enforces:
  - class restrictions,
  - prerequisite chains,
  - branch-specific progression paths.

## 5. Combat and Magic

### 5.1 Damage and Resistances

Damage types remain `physical`, `poison`, and `arcane` with per-entity mitigation.
`Ward` contributes temporary resistance while active.

### 5.2 Spell Suite

- **Arcane Bolt**: directional arcane projectile, can chain via talent.
- **Venom Lance**: directional poison spell with DOT application.
- **Mend**: vitality-scaled self-heal.
- **Ward**: vitality-scaled defensive utility buff.

Spell costs and potency are influenced by class school mastery and talents.

## 6. Town, Reputation, and Questing

- Reputation (`townfolk`) gates and modifies NPC behavior.
- Quest flow is now staged:
  1. accept objective,
  2. complete kill requirement,
  3. return for turn-in,
  4. fail on deadline expiration.
- Quest journal entries are persisted and exposed in UI.

## 7. Corruption System

- Corruption increases while adventuring in dungeon floors.
- At threshold, mutation activates (`chaos_skin`) and applies baseline gameplay impact.
- Corruption and mutation status are visible in HUD/character sheet.

## 8. Persistence and Reliability

Current save schema is **version 5**.

Persistence includes:

- quest stage/progress/failure/journal,
- faction reputation,
- corruption component state,
- expanded status fields,
- trap hidden/discovered state,
- checksum (`sha256`) integrity metadata.

Reliability behavior:

- `.bak` backup rotation when overwriting saves,
- checksum validation on load,
- automatic fallback to backup if primary is corrupted/tampered,
- diagnostic entries surfaced for client diagnostics panel.

## 9. Client/UI State

UI now includes:

- ranged targeting mode,
- dual spell targeting modes (`Arcane Bolt`, `Venom Lance`),
- utility spell casting shortcuts (`Mend`, `Ward`),
- talent selection modal,
- quest journal panel,
- save diagnostics panel,
- expanded character sheet (corruption/reputation/quest data).

## 10. Test Coverage Snapshot

Automated coverage now validates:

- class talent restrictions and prerequisite gating,
- venom lance + ward behavior,
- quest timeout/failure and reputation impact,
- corruption mutation trigger,
- biome/archetype/vault dungeon metadata,
- checksum mismatch recovery via backup,
- all prior combat/inventory/transition/persistence foundations.

## 11. Remaining Gaps After Phase 7

Major ADOM-parity gaps still open:

- broader monster role ecology and tactical AI,
- deeper status ecosystem (blind/confuse/fear/slow variants),
- larger overworld travel/consequence simulation,
- expanded corruption/morality/economy long-run loops,
- richer dungeon feature diversity (secrets, encounter families, special rooms).
