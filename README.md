# factory-ai-proj

## Current Project State

This repository currently contains a playable ADOM-inspired roguelike foundation with:

- ECS-based entities/components and modular gameplay systems,
- overworld + multi-depth dungeon transitions,
- character creation (race/class/seed),
- combat (melee+ranged), equipment, inventory, and status effects,
- hunger, traps, resting/natural regeneration, and XP leveling,
- save/load with v2->v3 migration support,
- externalized content definitions in JSON.

## Design and Roadmap Docs

- Current architecture and behavior: `docs/design/current-game-design.md`
- ADOM parity requirements and prioritized TODO roadmap: `docs/design/adom-parity-requirements.md`

## Next Development Focus

The next phase targets deeper ADOM parity through spellcasting/resistance systems, town+quest simulation loops, and richer procedural world content.