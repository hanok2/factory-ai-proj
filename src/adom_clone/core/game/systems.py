"""Gameplay system modules used by GameSession."""

import hashlib
import json
import shutil
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING, cast

from adom_clone.core.ecs.components import (
    BlocksMovement,
    Consumable,
    Corruption,
    DamageType,
    Equipment,
    EquipmentSlot,
    Equippable,
    ExperienceReward,
    Fighter,
    Food,
    Hunger,
    Inventory,
    Item,
    Mana,
    Monster,
    MonsterRole,
    Npc,
    NpcRole,
    OnMap,
    Player,
    Position,
    Progression,
    RangedWeapon,
    Resistances,
    StatusEffects,
    Talents,
)
from adom_clone.core.ecs.store import ECSStore
from adom_clone.core.game.actions import (
    CastArcaneBoltAction,
    CastMendAction,
    CastVenomLanceAction,
    CastWardAction,
    DisarmTrapAction,
    DropLastItemAction,
    GameAction,
    InteractAction,
    MoveAction,
    PickupAction,
    RangedAttackAction,
    RestAction,
    SelectTalentAction,
    UseItemAction,
    WaitAction,
)
from adom_clone.core.world.map_model import MapKind

if TYPE_CHECKING:
    from adom_clone.core.game.session import GameSession


class TurnSystem:
    """Processes player action queue and advances turn state."""

    def advance_turn(self, session: "GameSession") -> None:
        if session.game_over or not session._action_queue:
            return

        action = session._action_queue.popleft()
        if session.consume_player_stun_turn() or session.player_fear_prevents_action(action):
            acted = True
        else:
            acted = self._apply_action(session, session.resolve_player_action(action))
        if not acted:
            return

        session.turn_count += 1
        session.tick_hunger()
        session.tick_corruption()
        session.tick_quest_timers()
        session.apply_status_damage(session.player_entity)
        session.apply_natural_regen()
        if not session.game_over:
            session.ai_system.run_monster_turns(session)

    def _apply_action(self, session: "GameSession", action: GameAction) -> bool:
        if isinstance(action, MoveAction):
            return session.apply_move(action.dx, action.dy)
        if isinstance(action, PickupAction):
            return session.inventory_system.pickup_item(session)
        if isinstance(action, UseItemAction):
            return session.inventory_system.use_item(session, action.slot_index)
        if isinstance(action, DropLastItemAction):
            return session.inventory_system.drop_last_item(session)
        if isinstance(action, RangedAttackAction):
            return session.combat_system.ranged_attack(session, action.dx, action.dy)
        if isinstance(action, RestAction):
            return session.rest_player()
        if isinstance(action, DisarmTrapAction):
            return session.disarm_nearby_trap()
        if isinstance(action, InteractAction):
            return session.interact_with_adjacent_npc()
        if isinstance(action, CastArcaneBoltAction):
            return session.cast_arcane_bolt(action.dx, action.dy)
        if isinstance(action, CastMendAction):
            return session.cast_mend()
        if isinstance(action, CastVenomLanceAction):
            return session.cast_venom_lance(action.dx, action.dy)
        if isinstance(action, CastWardAction):
            return session.cast_ward()
        if isinstance(action, SelectTalentAction):
            return session.select_talent(action.talent_id)
        if isinstance(action, WaitAction):
            session.add_message("You wait.")
            return True
        return False


class CombatSystem:
    """Resolves attacks and combat stat calculations."""

    def attack(self, session: "GameSession", attacker: int, defender: int) -> None:
        attacker_fighter = session.ecs.get_component(attacker, Fighter)
        defender_fighter = session.ecs.get_component(defender, Fighter)
        if attacker_fighter is None or defender_fighter is None:
            return

        base_damage = max(
            1,
            self.effective_power(session, attacker)
            - self.effective_defense(session, defender),
        )
        actual, mitigated = session.apply_damage(
            defender,
            base_damage,
            DamageType.PHYSICAL,
            source="melee",
        )

        if attacker == session.player_entity:
            monster = session.ecs.get_component(defender, Monster)
            target_name = monster.name if monster is not None else "target"
            session.add_message(
                f"You hit {target_name} for {actual} physical damage ({mitigated} resisted).",
            )
        elif defender == session.player_entity:
            monster = session.ecs.get_component(attacker, Monster)
            source_name = monster.name if monster is not None else "enemy"
            session.add_message(
                f"{source_name} hits you for {actual} physical damage ({mitigated} resisted).",
            )

    def ranged_attack(self, session: "GameSession", dx: int, dy: int) -> bool:
        if dx == 0 and dy == 0:
            session.add_message("Choose a direction to fire.")
            return False

        projectile = session.first_ranged_projectile()
        if projectile is None:
            session.add_message("You have no ranged projectile ready.")
            return False

        slot_index, item_entity, item, ranged = projectile
        start = session.player_position
        for step in range(1, ranged.range + 1):
            tx = start.x + dx * step
            ty = start.y + dy * step
            if not session.current_map.in_bounds(tx, ty):
                break
            if not session.current_map.is_passable(tx, ty):
                break

            blocker = session.blocking_entity_at(
                tx,
                ty,
                session.current_map.kind,
                session.current_depth,
                session.player_entity,
            )
            if blocker is None:
                continue

            target_fighter = session.ecs.get_component(blocker, Fighter)
            if target_fighter is None:
                break

            base_damage = max(
                1,
                self.effective_power(session, session.player_entity)
                + ranged.damage
                - self.effective_defense(session, blocker),
            )
            actual, mitigated = session.apply_damage(
                blocker,
                base_damage,
                DamageType.PHYSICAL,
                source=item.name,
            )
            target = session.ecs.get_component(blocker, Monster)
            target_name = "target" if target is None else target.name
            session.add_message(
                f"You throw {item.name} and hit {target_name} for {actual} physical damage"
                f" ({mitigated} resisted).",
            )
            session.consume_inventory_item(slot_index, item_entity)
            return True

        session.add_message(f"You throw {item.name}, but hit nothing.")
        session.consume_inventory_item(slot_index, item_entity)
        return True

    def effective_power(self, session: "GameSession", entity_id: int) -> int:
        fighter = session.ecs.get_component(entity_id, Fighter)
        if fighter is None:
            return 0
        return fighter.power + self._power_bonus(session, entity_id)

    def effective_defense(self, session: "GameSession", entity_id: int) -> int:
        fighter = session.ecs.get_component(entity_id, Fighter)
        if fighter is None:
            return 0
        return fighter.defense + self._defense_bonus(session, entity_id)

    def _power_bonus(self, session: "GameSession", entity_id: int) -> int:
        equipment = session.ecs.get_component(entity_id, Equipment)
        if equipment is None or equipment.weapon_item_id is None:
            return 0
        equippable = session.ecs.get_component(equipment.weapon_item_id, Equippable)
        return 0 if equippable is None else equippable.power_bonus

    def _defense_bonus(self, session: "GameSession", entity_id: int) -> int:
        equipment = session.ecs.get_component(entity_id, Equipment)
        if equipment is None or equipment.armor_item_id is None:
            return 0
        equippable = session.ecs.get_component(equipment.armor_item_id, Equippable)
        return 0 if equippable is None else equippable.defense_bonus


class InventorySystem:
    """Handles item pickup/use/drop and equipment slot actions."""

    def pickup_item(self, session: "GameSession") -> bool:
        position = session.player_position
        item_entities = session.items_at(
            session.current_map.kind,
            session.current_depth,
            position.x,
            position.y,
        )
        if not item_entities:
            session.add_message("There is nothing to pick up.")
            return False

        inventory = session.player_inventory
        if len(inventory.item_ids) >= inventory.capacity:
            session.add_message("Your inventory is full.")
            return False

        item_entity = item_entities[0]
        inventory.item_ids.append(item_entity)
        session.ecs.remove_component(item_entity, Position)
        session.ecs.remove_component(item_entity, OnMap)
        item = session.ecs.get_component(item_entity, Item)
        item_name = item.name if item is not None else "item"
        session.add_message(f"You pick up {item_name}.")
        return True

    def use_item(self, session: "GameSession", slot_index: int) -> bool:
        inventory = session.player_inventory
        if slot_index < 0 or slot_index >= len(inventory.item_ids):
            session.add_message("No item in that slot.")
            return False

        item_entity = inventory.item_ids[slot_index]
        item = session.ecs.get_component(item_entity, Item)
        if item is None:
            session.add_message("That item is invalid.")
            return False

        food = session.ecs.get_component(item_entity, Food)
        if food is not None:
            hunger = session.player_hunger
            hunger.current = min(hunger.max_value, hunger.current + food.nutrition)
            inventory.item_ids.pop(slot_index)
            session.destroy_item(item_entity)
            session.add_message(f"You eat {item.name}.")
            return True

        consumable = session.ecs.get_component(item_entity, Consumable)
        if consumable is not None:
            fighter = session.player_fighter
            before_hp = fighter.hp
            fighter.hp = min(fighter.max_hp, fighter.hp + consumable.heal_amount)
            healed = fighter.hp - before_hp
            inventory.item_ids.pop(slot_index)
            session.destroy_item(item_entity)
            if healed > 0:
                session.add_message(f"You use {item.name} and recover {healed} HP.")
            else:
                session.add_message(f"You use {item.name}, but nothing happens.")
            return True

        equippable = session.ecs.get_component(item_entity, Equippable)
        if equippable is not None:
            return self._toggle_equip_item(session, item_entity, item)

        if session.ecs.get_component(item_entity, RangedWeapon) is not None:
            session.add_message("Use [F] to enter targeting mode, then choose a direction.")
            return False

        session.add_message("You can't use that item.")
        return False

    def drop_last_item(self, session: "GameSession") -> bool:
        inventory = session.player_inventory
        if not inventory.item_ids:
            session.add_message("You have nothing to drop.")
            return False

        item_entity = inventory.item_ids.pop()
        item = session.ecs.get_component(item_entity, Item)
        item_name = item.name if item is not None else "item"
        self._unequip_if_equipped(session, item_entity)

        position = session.player_position
        session.ecs.add_component(item_entity, Position(position.x, position.y))
        session.ecs.add_component(
            item_entity,
            OnMap(kind=session.current_map.kind, depth=session.current_depth),
        )
        session.add_message(f"You drop {item_name}.")
        return True

    def _toggle_equip_item(self, session: "GameSession", item_entity: int, item: Item) -> bool:
        equipment = session.player_equipment
        equippable = session.ecs.get_component(item_entity, Equippable)
        if equippable is None:
            return False

        if equippable.slot == EquipmentSlot.WEAPON:
            if equipment.weapon_item_id == item_entity:
                equipment.weapon_item_id = None
                session.add_message(f"You unequip {item.name}.")
                return True
            equipment.weapon_item_id = item_entity
            session.add_message(f"You equip {item.name}.")
            return True

        if equippable.slot == EquipmentSlot.ARMOR:
            if equipment.armor_item_id == item_entity:
                equipment.armor_item_id = None
                session.add_message(f"You remove {item.name}.")
                return True
            equipment.armor_item_id = item_entity
            session.add_message(f"You equip {item.name}.")
            return True

        return False

    def _unequip_if_equipped(self, session: "GameSession", item_entity: int) -> None:
        equipment = session.player_equipment
        if equipment.weapon_item_id == item_entity:
            equipment.weapon_item_id = None
        if equipment.armor_item_id == item_entity:
            equipment.armor_item_id = None


class AISystem:
    """Role-aware deterministic monster AI."""

    def run_monster_turns(self, session: "GameSession") -> None:
        player_position = session.player_position
        for entity_id, monster in session.ecs.entities_with(Monster):
            if session.game_over:
                return

            position = session.ecs.get_component(entity_id, Position)
            on_map = session.ecs.get_component(entity_id, OnMap)
            fighter = session.ecs.get_component(entity_id, Fighter)
            status = session.ecs.get_component(entity_id, StatusEffects)
            if position is None or on_map is None or fighter is None or fighter.hp <= 0:
                continue
            if on_map.kind != session.current_map.kind or on_map.depth != session.current_depth:
                continue

            if session.consume_monster_stun_turn(entity_id):
                session.apply_status_damage(entity_id)
                continue

            if status is not None and status.slow > 0 and (session.turn_count + entity_id) % 2 == 0:
                session.apply_status_damage(entity_id)
                continue

            dist_x = player_position.x - position.x
            dist_y = player_position.y - position.y
            if status is not None and status.confuse > 0:
                if self._move_confused(session, entity_id, position):
                    session.apply_status_damage(entity_id)
                    continue

            acted = False
            if monster.role == MonsterRole.CASTER:
                acted = self._caster_turn(session, entity_id, position, dist_x, dist_y)
            elif monster.role == MonsterRole.SUPPORT:
                acted = self._support_turn(session, entity_id, position, dist_x, dist_y)
            elif monster.role == MonsterRole.SKIRMISHER:
                acted = self._skirmisher_turn(session, entity_id, position, dist_x, dist_y)
            else:
                acted = self._brute_turn(session, entity_id, position, dist_x, dist_y)

            if not acted and abs(dist_x) + abs(dist_y) == 1:
                session.combat_system.attack(session, entity_id, session.player_entity)
                if monster.role == MonsterRole.BRUTE and (session.turn_count + entity_id) % 3 == 0:
                    session.apply_status(session.player_entity, fear=1)
                session.apply_status_damage(entity_id)
                continue

            if not acted:
                self._move_toward(session, entity_id, position, dist_x, dist_y)

            session.apply_status_damage(entity_id)

    def _brute_turn(
        self,
        session: "GameSession",
        entity_id: int,
        position: Position,
        dist_x: int,
        dist_y: int,
    ) -> bool:
        if abs(dist_x) + abs(dist_y) <= 1:
            return False
        self._move_toward(session, entity_id, position, dist_x, dist_y)
        return True

    def _skirmisher_turn(
        self,
        session: "GameSession",
        entity_id: int,
        position: Position,
        dist_x: int,
        dist_y: int,
    ) -> bool:
        distance = abs(dist_x) + abs(dist_y)
        if distance == 1:
            fighter = session.ecs.get_component(entity_id, Fighter)
            if fighter is not None and fighter.hp < fighter.max_hp // 2:
                self._move_away(session, entity_id, position, dist_x, dist_y)
                return True
            return False
        if distance <= 3 and (session.turn_count + entity_id) % 2 == 0:
            actual, mitigated = session.apply_damage(
                session.player_entity,
                2,
                DamageType.PHYSICAL,
                source="skirmisher jab",
            )
            session.apply_status(session.player_entity, bleed=1)
            session.add_message(
                f"Skirmisher strikes for {actual} physical damage ({mitigated} resisted).",
            )
            return True

        self._move_toward(session, entity_id, position, dist_x, dist_y)
        return True

    def _caster_turn(
        self,
        session: "GameSession",
        entity_id: int,
        position: Position,
        dist_x: int,
        dist_y: int,
    ) -> bool:
        if self._in_spell_lane(position, session.player_position, max_range=4):
            actual, mitigated = session.apply_damage(
                session.player_entity,
                3,
                DamageType.ARCANE,
                source="monster spell",
            )
            if (session.turn_count + entity_id) % 2 == 0:
                session.apply_status(session.player_entity, confuse=2)
            else:
                session.apply_status(session.player_entity, fear=1)
            session.add_message(
                f"A hostile caster blasts you for {actual} arcane damage ({mitigated} resisted).",
            )
            return True

        self._move_toward(session, entity_id, position, dist_x, dist_y)
        return True

    def _support_turn(
        self,
        session: "GameSession",
        entity_id: int,
        position: Position,
        dist_x: int,
        dist_y: int,
    ) -> bool:
        ally = self._adjacent_wounded_ally(session, entity_id, position)
        if ally is not None:
            ally_fighter = session.ecs.get_component(ally, Fighter)
            if ally_fighter is not None:
                ally_fighter.hp = min(ally_fighter.max_hp, ally_fighter.hp + 2)
                session.add_message("A support monster bolsters its ally.")
                return True

        if abs(dist_x) + abs(dist_y) <= 3:
            session.apply_status(session.player_entity, slow=2)
            session.add_message("A support monster hex slows you.")
            return True

        self._move_toward(session, entity_id, position, dist_x, dist_y)
        return True

    def _move_confused(self, session: "GameSession", entity_id: int, position: Position) -> bool:
        directions = ((1, 0), (-1, 0), (0, 1), (0, -1))
        idx = (session.turn_count + entity_id) % len(directions)
        dx, dy = directions[idx]
        return self._move_if_open(session, entity_id, position, dx, dy)

    def _move_toward(
        self,
        session: "GameSession",
        entity_id: int,
        position: Position,
        dist_x: int,
        dist_y: int,
    ) -> bool:
        for dx, dy in self._chase_directions(dist_x, dist_y):
            if self._move_if_open(session, entity_id, position, dx, dy):
                return True
        return False

    def _move_away(
        self,
        session: "GameSession",
        entity_id: int,
        position: Position,
        dist_x: int,
        dist_y: int,
    ) -> bool:
        for dx, dy in self._chase_directions(-dist_x, -dist_y):
            if self._move_if_open(session, entity_id, position, dx, dy):
                return True
        return False

    def _move_if_open(
        self,
        session: "GameSession",
        entity_id: int,
        position: Position,
        dx: int,
        dy: int,
    ) -> bool:
        nx = position.x + dx
        ny = position.y + dy
        if not session.current_map.is_passable(nx, ny):
            return False
        blocker = session.blocking_entity_at(
            nx,
            ny,
            session.current_map.kind,
            session.current_depth,
            entity_id,
        )
        if blocker is not None:
            return False
        position.x = nx
        position.y = ny
        return True

    def _in_spell_lane(self, source: Position, target: Position, max_range: int) -> bool:
        if source.x == target.x:
            return abs(source.y - target.y) <= max_range
        if source.y == target.y:
            return abs(source.x - target.x) <= max_range
        return False

    def _adjacent_wounded_ally(
        self,
        session: "GameSession",
        entity_id: int,
        position: Position,
    ) -> int | None:
        for other_id, _monster in session.ecs.entities_with(Monster):
            if other_id == entity_id:
                continue
            other_position = session.ecs.get_component(other_id, Position)
            other_fighter = session.ecs.get_component(other_id, Fighter)
            other_map = session.ecs.get_component(other_id, OnMap)
            if other_position is None or other_fighter is None or other_map is None:
                continue
            if (
                other_map.kind != session.current_map.kind
                or other_map.depth != session.current_depth
            ):
                continue
            if other_fighter.hp >= other_fighter.max_hp:
                continue
            if abs(other_position.x - position.x) + abs(other_position.y - position.y) == 1:
                return other_id
        return None

    def _chase_directions(self, dist_x: int, dist_y: int) -> list[tuple[int, int]]:
        step_x = 0 if dist_x == 0 else (1 if dist_x > 0 else -1)
        step_y = 0 if dist_y == 0 else (1 if dist_y > 0 else -1)

        if abs(dist_x) >= abs(dist_y):
            return [(step_x, 0), (0, step_y)]
        return [(0, step_y), (step_x, 0)]


class PersistenceSystem:
    """Serializes and rehydrates game state."""

    def to_save_data(self, session: "GameSession") -> dict[str, object]:
        entities: list[dict[str, object]] = []
        for entity_id in session.serializable_entity_ids():
            entity_data: dict[str, object] = {"id": entity_id}

            if session.ecs.get_component(entity_id, Player) is not None:
                entity_data["player"] = True

            monster = session.ecs.get_component(entity_id, Monster)
            if monster is not None:
                entity_data["monster_name"] = monster.name
                entity_data["monster_role"] = monster.role.value
                entity_data["monster_faction"] = monster.faction

            position = session.ecs.get_component(entity_id, Position)
            if position is not None:
                entity_data["position"] = {"x": position.x, "y": position.y}

            on_map = session.ecs.get_component(entity_id, OnMap)
            if on_map is not None:
                entity_data["map_kind"] = on_map.kind.value
                entity_data["map_depth"] = on_map.depth

            if session.ecs.get_component(entity_id, BlocksMovement) is not None:
                entity_data["blocks_movement"] = True

            fighter = session.ecs.get_component(entity_id, Fighter)
            if fighter is not None:
                entity_data["fighter"] = {
                    "max_hp": fighter.max_hp,
                    "hp": fighter.hp,
                    "power": fighter.power,
                    "defense": fighter.defense,
                }

            progression = session.ecs.get_component(entity_id, Progression)
            if progression is not None:
                entity_data["progression"] = {
                    "level": progression.level,
                    "xp": progression.xp,
                    "xp_to_next": progression.xp_to_next,
                }

            status = session.ecs.get_component(entity_id, StatusEffects)
            if status is not None:
                entity_data["status"] = {
                    "poison": status.poison,
                    "bleed": status.bleed,
                    "stun": status.stun,
                    "slow": status.slow,
                    "fear": status.fear,
                    "confuse": status.confuse,
                    "ward_turns": status.ward_turns,
                    "ward_strength": status.ward_strength,
                }

            corruption = session.ecs.get_component(entity_id, Corruption)
            if corruption is not None:
                entity_data["corruption"] = {
                    "value": corruption.value,
                    "mutation": corruption.mutation,
                }

            mana = session.ecs.get_component(entity_id, Mana)
            if mana is not None:
                entity_data["mana"] = {
                    "current": mana.current,
                    "max_value": mana.max_value,
                }

            talents = session.ecs.get_component(entity_id, Talents)
            if talents is not None:
                entity_data["talents"] = {
                    "points": talents.points,
                    "selected": [*talents.selected],
                }

            resistances = session.ecs.get_component(entity_id, Resistances)
            if resistances is not None:
                entity_data["resistances"] = {
                    "physical_pct": resistances.physical_pct,
                    "poison_pct": resistances.poison_pct,
                    "arcane_pct": resistances.arcane_pct,
                }

            npc = session.ecs.get_component(entity_id, Npc)
            if npc is not None:
                entity_data["npc"] = {
                    "name": npc.name,
                    "role": npc.role.value,
                }

            inventory = session.ecs.get_component(entity_id, Inventory)
            if inventory is not None:
                entity_data["inventory"] = {
                    "capacity": inventory.capacity,
                    "item_ids": [*inventory.item_ids],
                }

            equipment = session.ecs.get_component(entity_id, Equipment)
            if equipment is not None:
                entity_data["equipment"] = {
                    "weapon_item_id": equipment.weapon_item_id,
                    "armor_item_id": equipment.armor_item_id,
                }

            hunger = session.ecs.get_component(entity_id, Hunger)
            if hunger is not None:
                entity_data["hunger"] = {
                    "current": hunger.current,
                    "max_value": hunger.max_value,
                }

            item = session.ecs.get_component(entity_id, Item)
            if item is not None:
                entity_data["item_name"] = item.name

            consumable = session.ecs.get_component(entity_id, Consumable)
            if consumable is not None:
                entity_data["consumable"] = {"heal_amount": consumable.heal_amount}

            equippable = session.ecs.get_component(entity_id, Equippable)
            if equippable is not None:
                entity_data["equippable"] = {
                    "slot": equippable.slot.value,
                    "power_bonus": equippable.power_bonus,
                    "defense_bonus": equippable.defense_bonus,
                }

            ranged = session.ecs.get_component(entity_id, RangedWeapon)
            if ranged is not None:
                entity_data["ranged"] = {
                    "damage": ranged.damage,
                    "range": ranged.range,
                }

            reward = session.ecs.get_component(entity_id, ExperienceReward)
            if reward is not None:
                entity_data["xp_reward"] = reward.xp

            food = session.ecs.get_component(entity_id, Food)
            if food is not None:
                entity_data["food"] = {"nutrition": food.nutrition}

            entities.append(entity_data)

        return {
            "version": 6,
            "seed": session.seed,
            "race_id": session.race_id,
            "class_id": session.class_id,
            "dungeon_level_count": session.dungeon_level_count,
            "current_map": session.current_map.kind.value,
            "current_depth": session.current_depth,
            "messages": [*session.messages],
            "game_over": session.game_over,
            "turn_count": session.turn_count,
            "kill_count": session.kill_count,
            "regen_counter": session.regen_counter,
            "faction_reputation": session.faction_reputation,
            "quest_state": _serialize_quest_state(session),
            "trap_state": _serialize_trap_state(session),
            "entities": entities,
        }

    def save_to_file(self, session: "GameSession", file_path: str) -> None:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Preserve previous save as a backup so corrupted writes are recoverable.
        if path.exists():
            backup_path = path.with_suffix(path.suffix + ".bak")
            shutil.copy2(path, backup_path)

        save_data = self.to_save_data(session)
        save_data["integrity"] = _compute_integrity(save_data)
        payload = json.dumps(save_data, separators=(",", ":"))
        path.write_text(payload, encoding="utf-8")
        integrity_prefix = _expect_str(save_data["integrity"], "integrity")[:10]
        session.add_diagnostic(
            "integrity",
            f"Saved {path.name} with integrity {integrity_prefix}...",
        )

    def load_from_file(self, file_path: str) -> "GameSession":
        path = Path(file_path)
        try:
            raw_data = json.loads(path.read_text(encoding="utf-8"))
            return self.from_save_data(raw_data)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            return self._load_backup_or_raise(path, exc)

    def _load_backup_or_raise(self, path: Path, exc: Exception) -> "GameSession":
        backup_path = path.with_suffix(path.suffix + ".bak")
        if backup_path.exists():
            try:
                raw_backup = json.loads(backup_path.read_text(encoding="utf-8"))
                loaded = self.from_save_data(raw_backup)
                loaded.add_diagnostic("recovery", f"Primary save invalid: {exc}")
                loaded.add_diagnostic("recovery", f"Recovered from backup: {backup_path.name}")
                loaded.add_message(
                    f"Primary save was invalid and backup was restored from {backup_path.name}.",
                )
                return loaded
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                pass

        msg = (
            f"Save data is corrupted: {exc}. "
            f"No valid backup found at {backup_path.name}."
        )
        raise ValueError(msg) from exc

    def from_save_data(self, raw_data: object) -> "GameSession":
        from adom_clone.core.game.session import GameSession

        raw_dict = _expect_dict(raw_data, "save_data")
        data = _migrate_save_data(raw_dict)
        _validate_integrity(data)

        seed = _expect_int(data.get("seed", 1337), "seed")
        race_id = _expect_str(data.get("race_id", "human"), "race_id")
        class_id = _expect_str(data.get("class_id", "fighter"), "class_id")
        dungeon_level_count = _expect_int(data.get("dungeon_level_count", 3), "dungeon_level_count")

        session = GameSession(
            seed=seed,
            race_id=race_id,
            class_id=class_id,
            dungeon_level_count=dungeon_level_count,
        )
        session.ecs = ECSStore()
        session._action_queue = deque()

        session.messages = _expect_str_list(data.get("messages", []), "messages")
        if not session.messages:
            session.messages = ["Loaded save."]
        if "integrity" in data:
            session.add_diagnostic("integrity", "Integrity check passed for loaded save payload.")
        else:
            session.add_diagnostic(
                "migration",
                "Loaded migrated save without source integrity metadata.",
            )

        session.game_over = _expect_bool(data.get("game_over", False), "game_over")
        session.turn_count = _expect_int(data.get("turn_count", 0), "turn_count")
        session.kill_count = _expect_int(data.get("kill_count", 0), "kill_count")
        session.regen_counter = _expect_int(data.get("regen_counter", 0), "regen_counter")
        session.faction_reputation = _expect_str_int_dict(
            data.get(
                "faction_reputation",
                {"townfolk": 0, "arcane_order": 0, "wild_clans": 0},
            ),
            "faction_reputation",
        )
        quest_state = data.get("quest_state")
        if quest_state is not None:
            _load_quest_state(session, quest_state)
        current_map_kind = MapKind(_expect_str(data.get("current_map"), "current_map"))
        current_depth_raw = data.get("current_depth")
        current_depth = (
            None
            if current_depth_raw is None
            else _expect_int(current_depth_raw, "current_depth")
        )
        trap_state = data.get("trap_state")
        if trap_state is not None:
            _load_trap_state(session, trap_state)

        entities = _expect_list(data.get("entities", []), "entities")
        max_entity_id = 0
        player_entity: int | None = None

        for raw_entity in entities:
            entity_data = _expect_dict(raw_entity, "entity")
            entity_id = _expect_int(entity_data.get("id"), "entity.id")
            max_entity_id = max(max_entity_id, entity_id)

            if _expect_bool(entity_data.get("player", False), "entity.player"):
                session.ecs.add_component(entity_id, Player())
                player_entity = entity_id

            monster_name = entity_data.get("monster_name")
            if monster_name is not None:
                role_raw = entity_data.get("monster_role")
                faction_raw = entity_data.get("monster_faction")
                session.ecs.add_component(
                    entity_id,
                    Monster(
                        name=_expect_str(monster_name, "entity.monster_name"),
                        role=MonsterRole(
                            _expect_str(
                                "brute" if role_raw is None else role_raw,
                                "entity.monster_role",
                            ),
                        ),
                        faction=_expect_str(
                            "dungeon_denizens" if faction_raw is None else faction_raw,
                            "entity.monster_faction",
                        ),
                    ),
                )

            raw_position = entity_data.get("position")
            if raw_position is not None:
                position_data = _expect_dict(raw_position, "entity.position")
                session.ecs.add_component(
                    entity_id,
                    Position(
                        x=_expect_int(position_data.get("x"), "entity.position.x"),
                        y=_expect_int(position_data.get("y"), "entity.position.y"),
                    ),
                )

            map_kind_value = entity_data.get("map_kind")
            map_depth_value = entity_data.get("map_depth")
            if map_kind_value is not None:
                depth = (
                    None
                    if map_depth_value is None
                    else _expect_int(map_depth_value, "entity.map_depth")
                )
                session.ecs.add_component(
                    entity_id,
                    OnMap(
                        kind=MapKind(_expect_str(map_kind_value, "entity.map_kind")),
                        depth=depth,
                    ),
                )

            if _expect_bool(entity_data.get("blocks_movement", False), "entity.blocks_movement"):
                session.ecs.add_component(entity_id, BlocksMovement())

            raw_fighter = entity_data.get("fighter")
            if raw_fighter is not None:
                fighter_data = _expect_dict(raw_fighter, "entity.fighter")
                session.ecs.add_component(
                    entity_id,
                    Fighter(
                        max_hp=_expect_int(fighter_data.get("max_hp"), "entity.fighter.max_hp"),
                        hp=_expect_int(fighter_data.get("hp"), "entity.fighter.hp"),
                        power=_expect_int(fighter_data.get("power"), "entity.fighter.power"),
                        defense=_expect_int(fighter_data.get("defense"), "entity.fighter.defense"),
                    ),
                )

            raw_progression = entity_data.get("progression")
            if raw_progression is not None:
                progression_data = _expect_dict(raw_progression, "entity.progression")
                session.ecs.add_component(
                    entity_id,
                    Progression(
                        level=_expect_int(
                            progression_data.get("level"),
                            "entity.progression.level",
                        ),
                        xp=_expect_int(progression_data.get("xp"), "entity.progression.xp"),
                        xp_to_next=_expect_int(
                            progression_data.get("xp_to_next"),
                            "entity.progression.xp_to_next",
                        ),
                    ),
                )

            raw_status = entity_data.get("status")
            if raw_status is not None:
                status_data = _expect_dict(raw_status, "entity.status")
                session.ecs.add_component(
                    entity_id,
                    StatusEffects(
                        poison=_expect_int(status_data.get("poison", 0), "entity.status.poison"),
                        bleed=_expect_int(status_data.get("bleed", 0), "entity.status.bleed"),
                        stun=_expect_int(status_data.get("stun", 0), "entity.status.stun"),
                        slow=_expect_int(status_data.get("slow", 0), "entity.status.slow"),
                        fear=_expect_int(status_data.get("fear", 0), "entity.status.fear"),
                        confuse=_expect_int(
                            status_data.get("confuse", 0),
                            "entity.status.confuse",
                        ),
                        ward_turns=_expect_int(
                            status_data.get("ward_turns", 0),
                            "entity.status.ward_turns",
                        ),
                        ward_strength=_expect_int(
                            status_data.get("ward_strength", 0),
                            "entity.status.ward_strength",
                        ),
                    ),
                )

            raw_corruption = entity_data.get("corruption")
            if raw_corruption is not None:
                corruption_data = _expect_dict(raw_corruption, "entity.corruption")
                mutation_raw = corruption_data.get("mutation")
                session.ecs.add_component(
                    entity_id,
                    Corruption(
                        value=_expect_int(
                            corruption_data.get("value", 0),
                            "entity.corruption.value",
                        ),
                        mutation=None
                        if mutation_raw is None
                        else _expect_str(mutation_raw, "entity.corruption.mutation"),
                    ),
                )

            raw_mana = entity_data.get("mana")
            if raw_mana is not None:
                mana_data = _expect_dict(raw_mana, "entity.mana")
                session.ecs.add_component(
                    entity_id,
                    Mana(
                        current=_expect_int(mana_data.get("current"), "entity.mana.current"),
                        max_value=_expect_int(mana_data.get("max_value"), "entity.mana.max_value"),
                    ),
                )

            raw_talents = entity_data.get("talents")
            if raw_talents is not None:
                talents_data = _expect_dict(raw_talents, "entity.talents")
                selected_raw = _expect_list(
                    talents_data.get("selected", []),
                    "entity.talents.selected",
                )
                selected = [
                    _expect_str(item, "entity.talents.selected_item")
                    for item in selected_raw
                ]
                session.ecs.add_component(
                    entity_id,
                    Talents(
                        points=_expect_int(talents_data.get("points", 0), "entity.talents.points"),
                        selected=selected,
                    ),
                )

            raw_resistances = entity_data.get("resistances")
            if raw_resistances is not None:
                resist_data = _expect_dict(raw_resistances, "entity.resistances")
                session.ecs.add_component(
                    entity_id,
                    Resistances(
                        physical_pct=_expect_int(
                            resist_data.get("physical_pct", 0),
                            "entity.resistances.physical_pct",
                        ),
                        poison_pct=_expect_int(
                            resist_data.get("poison_pct", 0),
                            "entity.resistances.poison_pct",
                        ),
                        arcane_pct=_expect_int(
                            resist_data.get("arcane_pct", 0),
                            "entity.resistances.arcane_pct",
                        ),
                    ),
                )

            raw_npc = entity_data.get("npc")
            if raw_npc is not None:
                npc_data = _expect_dict(raw_npc, "entity.npc")
                session.ecs.add_component(
                    entity_id,
                    Npc(
                        name=_expect_str(npc_data.get("name"), "entity.npc.name"),
                        role=NpcRole(_expect_str(npc_data.get("role"), "entity.npc.role")),
                    ),
                )

            raw_inventory = entity_data.get("inventory")
            if raw_inventory is not None:
                inventory_data = _expect_dict(raw_inventory, "entity.inventory")
                session.ecs.add_component(
                    entity_id,
                    Inventory(
                        capacity=_expect_int(
                            inventory_data.get("capacity"),
                            "entity.inventory.capacity",
                        ),
                        item_ids=_expect_int_list(
                            inventory_data.get("item_ids", []),
                            "entity.inventory.item_ids",
                        ),
                    ),
                )

            raw_equipment = entity_data.get("equipment")
            if raw_equipment is not None:
                equipment_data = _expect_dict(raw_equipment, "entity.equipment")
                weapon_item_raw = equipment_data.get("weapon_item_id")
                armor_item_raw = equipment_data.get("armor_item_id")
                session.ecs.add_component(
                    entity_id,
                    Equipment(
                        weapon_item_id=None
                        if weapon_item_raw is None
                        else _expect_int(weapon_item_raw, "entity.equipment.weapon_item_id"),
                        armor_item_id=None
                        if armor_item_raw is None
                        else _expect_int(armor_item_raw, "entity.equipment.armor_item_id"),
                    ),
                )

            raw_hunger = entity_data.get("hunger")
            if raw_hunger is not None:
                hunger_data = _expect_dict(raw_hunger, "entity.hunger")
                session.ecs.add_component(
                    entity_id,
                    Hunger(
                        current=_expect_int(hunger_data.get("current"), "entity.hunger.current"),
                        max_value=_expect_int(
                            hunger_data.get("max_value"),
                            "entity.hunger.max_value",
                        ),
                    ),
                )

            item_name = entity_data.get("item_name")
            if item_name is not None:
                session.ecs.add_component(
                    entity_id,
                    Item(name=_expect_str(item_name, "entity.item_name")),
                )

            raw_consumable = entity_data.get("consumable")
            if raw_consumable is not None:
                consumable_data = _expect_dict(raw_consumable, "entity.consumable")
                session.ecs.add_component(
                    entity_id,
                    Consumable(
                        heal_amount=_expect_int(
                            consumable_data.get("heal_amount"),
                            "entity.consumable.heal_amount",
                        ),
                    ),
                )

            raw_equippable = entity_data.get("equippable")
            if raw_equippable is not None:
                equippable_data = _expect_dict(raw_equippable, "entity.equippable")
                session.ecs.add_component(
                    entity_id,
                    Equippable(
                        slot=EquipmentSlot(
                            _expect_str(equippable_data.get("slot"), "entity.equippable.slot"),
                        ),
                        power_bonus=_expect_int(
                            equippable_data.get("power_bonus", 0),
                            "entity.equippable.power_bonus",
                        ),
                        defense_bonus=_expect_int(
                            equippable_data.get("defense_bonus", 0),
                            "entity.equippable.defense_bonus",
                        ),
                    ),
                )

            raw_food = entity_data.get("food")
            if raw_food is not None:
                food_data = _expect_dict(raw_food, "entity.food")
                session.ecs.add_component(
                    entity_id,
                    Food(
                        nutrition=_expect_int(
                            food_data.get("nutrition"),
                            "entity.food.nutrition",
                        ),
                    ),
                )

            raw_ranged = entity_data.get("ranged")
            if raw_ranged is not None:
                ranged_data = _expect_dict(raw_ranged, "entity.ranged")
                session.ecs.add_component(
                    entity_id,
                    RangedWeapon(
                        damage=_expect_int(ranged_data.get("damage"), "entity.ranged.damage"),
                        range=_expect_int(ranged_data.get("range"), "entity.ranged.range"),
                    ),
                )

            xp_reward_raw = entity_data.get("xp_reward")
            if xp_reward_raw is not None:
                session.ecs.add_component(
                    entity_id,
                    ExperienceReward(xp=_expect_int(xp_reward_raw, "entity.xp_reward")),
                )

        if player_entity is None:
            msg = "Save data is missing player entity."
            raise ValueError(msg)

        session.player_entity = player_entity
        session.ecs.set_next_entity_id(max_entity_id + 1)

        if current_map_kind == MapKind.OVERWORLD:
            session.current_map = session.overworld
            session.current_depth = None
        elif current_map_kind == MapKind.TOWN:
            session.current_map = session.town
            session.current_depth = None
        else:
            dungeon_depth = 1 if current_depth is None else current_depth
            session.current_map = session.dungeon_levels[dungeon_depth - 1]
            session.current_depth = dungeon_depth

        player_map = session.ecs.get_component(session.player_entity, OnMap)
        if player_map is None:
            session.ecs.add_component(
                session.player_entity,
                OnMap(kind=current_map_kind, depth=current_depth),
            )
        else:
            player_map.kind = current_map_kind
            player_map.depth = current_depth

        _ensure_status_components(session)
        _ensure_progression_component(session)
        _ensure_monster_xp_rewards(session)
        _ensure_phase8_components(session)

        _ = session.player_position
        _ = session.player_fighter
        _ = session.player_inventory
        _ = session.player_hunger
        _ = session.player_equipment
        _ = session.player_progression
        _ = session.player_mana
        _ = session.player_talents
        _ = session.player_resistances
        return session


def _serialize_trap_state(session: "GameSession") -> dict[str, object]:
    dungeon: dict[str, list[list[int]]] = {}
    dungeon_discovered: dict[str, list[list[int]]] = {}
    dungeon_secrets: dict[str, list[list[int]]] = {}
    dungeon_discovered_secrets: dict[str, list[list[int]]] = {}
    for tile_map in session.dungeon_levels:
        coords = sorted(tile_map.trap_positions)
        dungeon[str(tile_map.depth)] = [[x, y] for x, y in coords]
        discovered = sorted(tile_map.discovered_traps)
        dungeon_discovered[str(tile_map.depth)] = [[x, y] for x, y in discovered]
        secrets = sorted(tile_map.secret_rooms)
        dungeon_secrets[str(tile_map.depth)] = [[x, y] for x, y in secrets]
        discovered_secrets = sorted(tile_map.discovered_secrets)
        dungeon_discovered_secrets[str(tile_map.depth)] = [[x, y] for x, y in discovered_secrets]

    return {
        "overworld": [[x, y] for x, y in sorted(session.overworld.trap_positions)],
        "overworld_discovered": [[x, y] for x, y in sorted(session.overworld.discovered_traps)],
        "town": [[x, y] for x, y in sorted(session.town.trap_positions)],
        "town_discovered": [[x, y] for x, y in sorted(session.town.discovered_traps)],
        "overworld_secrets": [[x, y] for x, y in sorted(session.overworld.secret_rooms)],
        "overworld_discovered_secrets": [
            [x, y]
            for x, y in sorted(session.overworld.discovered_secrets)
        ],
        "town_secrets": [[x, y] for x, y in sorted(session.town.secret_rooms)],
        "town_discovered_secrets": [[x, y] for x, y in sorted(session.town.discovered_secrets)],
        "dungeon": dungeon,
        "dungeon_discovered": dungeon_discovered,
        "dungeon_secrets": dungeon_secrets,
        "dungeon_discovered_secrets": dungeon_discovered_secrets,
    }


def _load_trap_state(session: "GameSession", raw: object) -> None:
    data = _expect_dict(raw, "trap_state")
    overworld_raw = _expect_list(data.get("overworld", []), "trap_state.overworld")
    session.overworld.trap_positions = _coords_set(overworld_raw, "trap_state.overworld")
    overworld_discovered_raw = _expect_list(
        data.get("overworld_discovered", []),
        "trap_state.overworld_discovered",
    )
    session.overworld.discovered_traps = _coords_set(
        overworld_discovered_raw,
        "trap_state.overworld_discovered",
    )

    town_raw = _expect_list(data.get("town", []), "trap_state.town")
    session.town.trap_positions = _coords_set(town_raw, "trap_state.town")
    town_discovered_raw = _expect_list(
        data.get("town_discovered", []),
        "trap_state.town_discovered",
    )
    session.town.discovered_traps = _coords_set(town_discovered_raw, "trap_state.town_discovered")

    overworld_secrets_raw = _expect_list(
        data.get("overworld_secrets", []),
        "trap_state.overworld_secrets",
    )
    session.overworld.secret_rooms = _coords_set(
        overworld_secrets_raw,
        "trap_state.overworld_secrets",
    )
    overworld_discovered_secrets_raw = _expect_list(
        data.get("overworld_discovered_secrets", []),
        "trap_state.overworld_discovered_secrets",
    )
    session.overworld.discovered_secrets = _coords_set(
        overworld_discovered_secrets_raw,
        "trap_state.overworld_discovered_secrets",
    )

    town_secrets_raw = _expect_list(data.get("town_secrets", []), "trap_state.town_secrets")
    session.town.secret_rooms = _coords_set(town_secrets_raw, "trap_state.town_secrets")
    town_discovered_secrets_raw = _expect_list(
        data.get("town_discovered_secrets", []),
        "trap_state.town_discovered_secrets",
    )
    session.town.discovered_secrets = _coords_set(
        town_discovered_secrets_raw,
        "trap_state.town_discovered_secrets",
    )

    dungeon_raw = _expect_dict(data.get("dungeon", {}), "trap_state.dungeon")
    dungeon_discovered_raw = _expect_dict(
        data.get("dungeon_discovered", {}),
        "trap_state.dungeon_discovered",
    )
    dungeon_secrets_raw = _expect_dict(
        data.get("dungeon_secrets", {}),
        "trap_state.dungeon_secrets",
    )
    dungeon_discovered_secrets_raw = _expect_dict(
        data.get("dungeon_discovered_secrets", {}),
        "trap_state.dungeon_discovered_secrets",
    )
    for depth_text, coords_raw in dungeon_raw.items():
        depth = _expect_int(depth_text_to_int(depth_text), "trap_state.dungeon.depth")
        if depth < 1 or depth > len(session.dungeon_levels):
            continue
        coords_list = _expect_list(coords_raw, f"trap_state.dungeon.{depth}")
        session.dungeon_levels[depth - 1].trap_positions = _coords_set(
            coords_list,
            f"trap_state.dungeon.{depth}",
        )
        discovered_coords_raw = _expect_list(
            dungeon_discovered_raw.get(depth_text, []),
            f"trap_state.dungeon_discovered.{depth}",
        )
        session.dungeon_levels[depth - 1].discovered_traps = _coords_set(
            discovered_coords_raw,
            f"trap_state.dungeon_discovered.{depth}",
        )

        secret_coords_raw = _expect_list(
            dungeon_secrets_raw.get(depth_text, []),
            f"trap_state.dungeon_secrets.{depth}",
        )
        session.dungeon_levels[depth - 1].secret_rooms = _coords_set(
            secret_coords_raw,
            f"trap_state.dungeon_secrets.{depth}",
        )

        discovered_secret_coords_raw = _expect_list(
            dungeon_discovered_secrets_raw.get(depth_text, []),
            f"trap_state.dungeon_discovered_secrets.{depth}",
        )
        session.dungeon_levels[depth - 1].discovered_secrets = _coords_set(
            discovered_secret_coords_raw,
            f"trap_state.dungeon_discovered_secrets.{depth}",
        )


def _serialize_quest_state(session: "GameSession") -> dict[str, object]:
    quest = session.quest_state
    return {
        "quest_id": quest.quest_id,
        "stage": quest.stage,
        "accepted": quest.accepted,
        "target_kills": quest.target_kills,
        "kills_progress": quest.kills_progress,
        "deadline_turn": quest.deadline_turn,
        "completed": quest.completed,
        "failed": quest.failed,
        "turned_in": quest.turned_in,
        "journal": [*quest.journal],
    }


def _load_quest_state(session: "GameSession", raw: object) -> None:
    data = _expect_dict(raw, "quest_state")
    session.quest_state.quest_id = _expect_str(
        data.get("quest_id", "town_goblin_cull"),
        "quest_state.quest_id",
    )
    session.quest_state.stage = _expect_int(data.get("stage", 0), "quest_state.stage")
    session.quest_state.accepted = _expect_bool(
        data.get("accepted", False),
        "quest_state.accepted",
    )
    session.quest_state.target_kills = _expect_int(
        data.get("target_kills", 3),
        "quest_state.target_kills",
    )
    session.quest_state.kills_progress = _expect_int(
        data.get("kills_progress", 0),
        "quest_state.kills_progress",
    )
    session.quest_state.deadline_turn = _expect_int(
        data.get("deadline_turn", 0),
        "quest_state.deadline_turn",
    )
    session.quest_state.completed = _expect_bool(
        data.get("completed", False),
        "quest_state.completed",
    )
    session.quest_state.failed = _expect_bool(
        data.get("failed", False),
        "quest_state.failed",
    )
    session.quest_state.turned_in = _expect_bool(
        data.get("turned_in", False),
        "quest_state.turned_in",
    )
    journal_raw = _expect_list(data.get("journal", []), "quest_state.journal")
    session.quest_state.journal = [
        _expect_str(item, "quest_state.journal_item")
        for item in journal_raw
    ]


def _migrate_save_data(data: dict[str, object]) -> dict[str, object]:
    version = _expect_int(data.get("version", 2), "version")
    if version == 6:
        return data

    # Any structural migration invalidates prior checksums.
    data = dict(data)
    data.pop("integrity", None)

    if version == 2:
        migrated = dict(data)
        migrated["version"] = 3
        migrated.setdefault("regen_counter", 0)
        version = 3
        data = migrated

    if version == 3:
        migrated = dict(data)
        migrated["version"] = 4
        migrated.setdefault("quest_state", {
            "quest_id": "town_goblin_cull",
            "accepted": False,
            "target_kills": 3,
            "completed": False,
            "turned_in": False,
        })
        version = 4
        data = migrated

    if version == 4:
        migrated = dict(data)
        migrated["version"] = 5
        migrated.setdefault("faction_reputation", {"townfolk": 0})
        quest_state = _expect_dict(migrated.get("quest_state", {}), "quest_state")
        quest_state.setdefault("kills_progress", 0)
        stage = _expect_int(quest_state.get("stage", 0), "quest_state.stage")
        accepted = _expect_bool(quest_state.get("accepted", False), "quest_state.accepted")
        completed = _expect_bool(quest_state.get("completed", False), "quest_state.completed")
        turned_in = _expect_bool(quest_state.get("turned_in", False), "quest_state.turned_in")
        failed = _expect_bool(quest_state.get("failed", False), "quest_state.failed")
        if stage == 0:
            if failed:
                stage = 4
            elif turned_in:
                stage = 3
            elif completed:
                stage = 2
            elif accepted:
                stage = 1
        quest_state["stage"] = stage
        quest_state.setdefault("deadline_turn", 0)
        quest_state.setdefault("failed", False)
        quest_state.setdefault("journal", [])
        migrated["quest_state"] = quest_state
        version = 5
        data = migrated

    if version == 5:
        migrated = dict(data)
        migrated["version"] = 6
        faction_reputation = _expect_dict(
            migrated.get("faction_reputation", {"townfolk": 0}),
            "faction_reputation",
        )
        faction_reputation.setdefault("arcane_order", 0)
        faction_reputation.setdefault("wild_clans", 0)
        migrated["faction_reputation"] = faction_reputation
        return migrated

    msg = f"Unsupported save version: {version}"
    raise ValueError(msg)


def _ensure_status_components(session: "GameSession") -> None:
    for entity_id, fighter in session.ecs.entities_with(Fighter):
        if fighter.hp <= 0:
            continue
        if session.ecs.get_component(entity_id, StatusEffects) is None:
            session.ecs.add_component(entity_id, StatusEffects())


def _ensure_progression_component(session: "GameSession") -> None:
    if session.ecs.get_component(session.player_entity, Progression) is not None:
        return

    session.ecs.add_component(
        session.player_entity,
        Progression(
            level=1,
            xp=0,
            xp_to_next=session.character_class.xp_base,
        ),
    )


def _ensure_monster_xp_rewards(session: "GameSession") -> None:
    for entity_id, _ in session.ecs.entities_with(Monster):
        if session.ecs.get_component(entity_id, ExperienceReward) is None:
            session.ecs.add_component(entity_id, ExperienceReward(xp=10))


def _ensure_phase8_components(session: "GameSession") -> None:
    """Backfill Phase 6-8 components when loading older saves."""
    if session.ecs.get_component(session.player_entity, Mana) is None:
        session.ecs.add_component(
            session.player_entity,
            Mana(
                current=session.character_class.mana_base,
                max_value=session.character_class.mana_base,
            ),
        )
    if session.ecs.get_component(session.player_entity, Talents) is None:
        session.ecs.add_component(session.player_entity, Talents())
    if session.ecs.get_component(session.player_entity, Resistances) is None:
        session.ecs.add_component(session.player_entity, Resistances())
    if session.ecs.get_component(session.player_entity, Corruption) is None:
        session.ecs.add_component(session.player_entity, Corruption())

    for entity_id, _monster in session.ecs.entities_with(Monster):
        if session.ecs.get_component(entity_id, Resistances) is None:
            session.ecs.add_component(entity_id, Resistances())

    if not session.ecs.entities_with(Npc):
        session._spawn_town_npcs()

    for faction in ("townfolk", "arcane_order", "wild_clans"):
        if faction not in session.faction_reputation:
            session.faction_reputation[faction] = 0


def _coords_set(raw_list: list[object], field_name: str) -> set[tuple[int, int]]:
    result: set[tuple[int, int]] = set()
    for idx, raw in enumerate(raw_list):
        pair = _expect_list(raw, f"{field_name}[{idx}]")
        if len(pair) != 2:
            msg = f"{field_name}[{idx}] must contain exactly two coordinates."
            raise ValueError(msg)
        x = _expect_int(pair[0], f"{field_name}[{idx}][0]")
        y = _expect_int(pair[1], f"{field_name}[{idx}][1]")
        result.add((x, y))
    return result


def _compute_integrity(data: dict[str, object]) -> str:
    sanitized = {key: value for key, value in data.items() if key != "integrity"}
    payload = json.dumps(sanitized, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_integrity(data: dict[str, object]) -> None:
    integrity_value = data.get("integrity")
    if integrity_value is None:
        # Older saves migrated to v5 do not have source integrity metadata.
        return
    if not isinstance(integrity_value, str):
        msg = "save_data.integrity must be a string"
        raise ValueError(msg)

    expected = _compute_integrity(data)
    if integrity_value != expected:
        msg = "Save integrity check failed."
        raise ValueError(msg)


def _expect_str_int_dict(value: object, field_name: str) -> dict[str, int]:
    raw = _expect_dict(value, field_name)
    result: dict[str, int] = {}
    for key, item in raw.items():
        name = _expect_str(key, f"{field_name}.key")
        result[name] = _expect_int(item, f"{field_name}[{name}]")
    return result


def depth_text_to_int(raw: object) -> int:
    if isinstance(raw, int):
        return raw
    if not isinstance(raw, str):
        msg = "trap depth key must be string or integer."
        raise ValueError(msg)
    try:
        return int(raw)
    except ValueError as exc:
        msg = f"Invalid trap depth key: {raw}"
        raise ValueError(msg) from exc


def _expect_dict(value: object, field_name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        msg = f"{field_name} must be an object."
        raise ValueError(msg)
    return cast(dict[str, object], value)


def _expect_list(value: object, field_name: str) -> list[object]:
    if not isinstance(value, list):
        msg = f"{field_name} must be an array."
        raise ValueError(msg)
    return value


def _expect_str(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        msg = f"{field_name} must be a string."
        raise ValueError(msg)
    return value


def _expect_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        msg = f"{field_name} must be an integer."
        raise ValueError(msg)
    return value


def _expect_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        msg = f"{field_name} must be a boolean."
        raise ValueError(msg)
    return value


def _expect_str_list(value: object, field_name: str) -> list[str]:
    raw_list = _expect_list(value, field_name)
    result: list[str] = []
    for idx, item in enumerate(raw_list):
        result.append(_expect_str(item, f"{field_name}[{idx}]"))
    return result


def _expect_int_list(value: object, field_name: str) -> list[int]:
    raw_list = _expect_list(value, field_name)
    result: list[int] = []
    for idx, item in enumerate(raw_list):
        result.append(_expect_int(item, f"{field_name}[{idx}]"))
    return result
