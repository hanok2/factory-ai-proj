# factory-ai-proj

## Current Project State

This repository currently contains a playable ADOM-inspired roguelike foundation with:

- ECS-based entities/components and modular gameplay systems,
- overworld + multi-depth dungeon transitions,
- character creation (race/class/seed),
- combat (melee, ranged, and school-based spellcasting), equipment, inventory, and status effects,
- hunger, hidden traps, resting/natural regeneration, and XP+talent progression,
- class-specific branching talent trees and corruption mutation pressure,
- biome-aware dungeon generation with room archetypes and vault hooks,
- faction reputation with quest timeout/failure and journal tracking,
- town hub NPC interactions with reputation-aware services,
- save/load with backup recovery, integrity checksums, and v2->v5 migration support,
- externalized content definitions in JSON.

## Design and Roadmap Docs

- Current architecture and behavior: `docs/design/current-game-design.md`
- ADOM parity requirements and prioritized TODO roadmap: `docs/design/adom-parity-requirements.md`

## Next Development Focus

The next phase targets expanded encounter ecology, additional status ecosystems, and broader world-consequence simulation.