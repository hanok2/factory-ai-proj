from dataclasses import dataclass


class GameAction:
    pass


@dataclass(slots=True)
class MoveAction(GameAction):
    dx: int
    dy: int


@dataclass(slots=True)
class PickupAction(GameAction):
    pass


@dataclass(slots=True)
class UseItemAction(GameAction):
    slot_index: int


@dataclass(slots=True)
class DropLastItemAction(GameAction):
    pass


@dataclass(slots=True)
class WaitAction(GameAction):
    pass
