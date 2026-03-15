# factory-ai-proj

## Current Project State

This repository currently contains a playable ADOM-inspired roguelike foundation with:

- ECS-based entities/components and modular gameplay systems,
- overworld + multi-depth dungeon transitions,
- character creation (race/class/seed),
- combat (melee, ranged, and spellcasting), equipment, inventory, and status effects,
- hunger, hidden traps, resting/natural regeneration, and XP+talent progression,
- town hub NPC interactions and save-persistent quest scaffolding,
- save/load with backup recovery and v2->v4 migration support,
- externalized content definitions in JSON.

## Design and Roadmap Docs

- Current architecture and behavior: `docs/design/current-game-design.md`
- ADOM parity requirements and prioritized TODO roadmap: `docs/design/adom-parity-requirements.md`

## Next Development Focus

The next phase targets deeper ADOM parity through advanced class progression, richer NPC/faction simulation, and deeper procedural biome/content variety.