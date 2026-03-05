"""Content loading for character options and spawn templates."""

import json
from dataclasses import dataclass
from importlib.resources import files
from typing import cast

from adom_clone.core.ecs.components import EquipmentSlot


@dataclass(frozen=True)
class RaceDefinition:
    id: str
    name: str
    hp_bonus: int
    power_bonus: int
    defense_bonus: int
    hunger_max: int


@dataclass(frozen=True)
class ClassDefinition:
    id: str
    name: str
    base_hp: int
    base_power: int
    base_defense: int
    starting_items: tuple[str, ...]


@dataclass(frozen=True)
class ItemTemplate:
    id: str
    name: str
    heal_amount: int | None
    nutrition: int | None
    equip_slot: EquipmentSlot | None
    power_bonus: int
    defense_bonus: int


@dataclass(frozen=True)
class MonsterTemplate:
    id: str
    name: str
    hp: int
    power: int
    defense: int


@dataclass(frozen=True)
class SpawnRule:
    template_id: str
    count: int


@dataclass(frozen=True)
class SpawnContent:
    item_templates: dict[str, ItemTemplate]
    monster_templates: dict[str, MonsterTemplate]
    overworld_items: tuple[SpawnRule, ...]
    dungeon_items: tuple[SpawnRule, ...]
    dungeon_monsters: tuple[SpawnRule, ...]


def load_character_content() -> tuple[tuple[RaceDefinition, ...], tuple[ClassDefinition, ...]]:
    raw = _load_json_resource("character_options.json")
    data = _expect_dict(raw, "character_options")

    races_raw = _expect_list(data.get("races"), "character_options.races")
    classes_raw = _expect_list(data.get("classes"), "character_options.classes")

    races = tuple(_parse_race(item) for item in races_raw)
    classes = tuple(_parse_class(item) for item in classes_raw)
    return races, classes


def load_spawn_content() -> SpawnContent:
    raw = _load_json_resource("spawns.json")
    data = _expect_dict(raw, "spawns")

    item_templates_raw = _expect_dict(data.get("item_templates"), "spawns.item_templates")
    monster_templates_raw = _expect_dict(data.get("monster_templates"), "spawns.monster_templates")

    item_templates = {
        template_id: _parse_item_template(template_id, template_raw)
        for template_id, template_raw in item_templates_raw.items()
    }
    monster_templates = {
        template_id: _parse_monster_template(template_id, template_raw)
        for template_id, template_raw in monster_templates_raw.items()
    }

    overworld_items_raw = _expect_list(data.get("overworld_items"), "spawns.overworld_items")
    dungeon_items_raw = _expect_list(data.get("dungeon_items"), "spawns.dungeon_items")
    dungeon_monsters_raw = _expect_list(data.get("dungeon_monsters"), "spawns.dungeon_monsters")

    overworld_items = tuple(
        _parse_spawn_rule(item)
        for item in overworld_items_raw
    )
    dungeon_items = tuple(
        _parse_spawn_rule(item)
        for item in dungeon_items_raw
    )
    dungeon_monsters = tuple(
        _parse_spawn_rule(item)
        for item in dungeon_monsters_raw
    )

    return SpawnContent(
        item_templates=item_templates,
        monster_templates=monster_templates,
        overworld_items=overworld_items,
        dungeon_items=dungeon_items,
        dungeon_monsters=dungeon_monsters,
    )


def _parse_race(raw: object) -> RaceDefinition:
    data = _expect_dict(raw, "race")
    return RaceDefinition(
        id=_expect_str(data.get("id"), "race.id"),
        name=_expect_str(data.get("name"), "race.name"),
        hp_bonus=_expect_int(data.get("hp_bonus"), "race.hp_bonus"),
        power_bonus=_expect_int(data.get("power_bonus"), "race.power_bonus"),
        defense_bonus=_expect_int(data.get("defense_bonus"), "race.defense_bonus"),
        hunger_max=_expect_int(data.get("hunger_max"), "race.hunger_max"),
    )


def _parse_class(raw: object) -> ClassDefinition:
    data = _expect_dict(raw, "class")
    starting_items_raw = _expect_list(data.get("starting_items"), "class.starting_items")
    starting_items = tuple(_expect_str(item, "class.starting_item") for item in starting_items_raw)
    return ClassDefinition(
        id=_expect_str(data.get("id"), "class.id"),
        name=_expect_str(data.get("name"), "class.name"),
        base_hp=_expect_int(data.get("base_hp"), "class.base_hp"),
        base_power=_expect_int(data.get("base_power"), "class.base_power"),
        base_defense=_expect_int(data.get("base_defense"), "class.base_defense"),
        starting_items=starting_items,
    )


def _parse_item_template(template_id: str, raw: object) -> ItemTemplate:
    data = _expect_dict(raw, f"item_templates.{template_id}")

    equip_slot: EquipmentSlot | None = None
    equip_slot_raw = data.get("equip_slot")
    if equip_slot_raw is not None:
        equip_slot = EquipmentSlot(
            _expect_str(equip_slot_raw, f"item_templates.{template_id}.equip_slot"),
        )

    heal_amount_raw = data.get("heal_amount")
    nutrition_raw = data.get("nutrition")
    return ItemTemplate(
        id=template_id,
        name=_expect_str(data.get("name"), f"item_templates.{template_id}.name"),
        heal_amount=(
            None if heal_amount_raw is None else _expect_int(heal_amount_raw, "heal_amount")
        ),
        nutrition=None if nutrition_raw is None else _expect_int(nutrition_raw, "nutrition"),
        equip_slot=equip_slot,
        power_bonus=_expect_int(
            data.get("power_bonus", 0),
            f"item_templates.{template_id}.power_bonus",
        ),
        defense_bonus=_expect_int(
            data.get("defense_bonus", 0),
            f"item_templates.{template_id}.defense_bonus",
        ),
    )


def _parse_monster_template(template_id: str, raw: object) -> MonsterTemplate:
    data = _expect_dict(raw, f"monster_templates.{template_id}")
    return MonsterTemplate(
        id=template_id,
        name=_expect_str(data.get("name"), f"monster_templates.{template_id}.name"),
        hp=_expect_int(data.get("hp"), f"monster_templates.{template_id}.hp"),
        power=_expect_int(data.get("power"), f"monster_templates.{template_id}.power"),
        defense=_expect_int(data.get("defense"), f"monster_templates.{template_id}.defense"),
    )


def _parse_spawn_rule(raw: object) -> SpawnRule:
    data = _expect_dict(raw, "spawn_rule")
    return SpawnRule(
        template_id=_expect_str(data.get("template"), "spawn_rule.template"),
        count=_expect_int(data.get("count"), "spawn_rule.count"),
    )


def _load_json_resource(file_name: str) -> object:
    path = files("adom_clone.content").joinpath(file_name)
    return json.loads(path.read_text(encoding="utf-8"))


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
