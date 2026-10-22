"""Validated retail match choices and raw GameCube controller samples."""
from dataclasses import dataclass


def _integer(name: str, value: int, low: int, high: int) -> None:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer in {low}..{high}")


@dataclass(frozen=True)
class PlayerConfig:
    """External CharacterKind (Fox=2, Falco=20), not internal FighterKind.

    Costumes 0..3 are the common retail subset. CPU level is retained for humans
    but only used by the game for cpu=1.
    """
    character: int = 2
    costume: int = 0
    cpu: int = 0
    cpu_level: int = 9

    def __post_init__(self) -> None:
        for name, low, high in (("character", 0, 25), ("costume", 0, 3), ("cpu", 0, 1), ("cpu_level", 1, 9)):
            _integer(name, getattr(self, name), low, high)


@dataclass(frozen=True)
class MatchConfig:
    """Two players on Battlefield (31) or Final Destination (32), external IDs.

    Remaining slots are empty. Stock/time/item/team rules retain the booted
    game's defaults; these are not arbitrary rules or a savestate constructor.
    """
    stage: int = 31
    players: tuple[PlayerConfig, PlayerConfig] = (PlayerConfig(2), PlayerConfig(20))

    def __post_init__(self) -> None:
        _integer("stage", self.stage, 31, 32)
        if type(self.players) is not tuple or len(self.players) != 2 or any(not isinstance(p, PlayerConfig) for p in self.players):
            raise ValueError("players must be a tuple of two PlayerConfig values")

    def native_argument(self) -> str:
        values = [self.stage]
        for p in self.players:
            values.extend((p.character, p.costume, p.cpu, p.cpu_level))
        return " ".join(map(str, values))


@dataclass(frozen=True)
class PadInput:
    """Raw PADStatus, held until the next step. err=-1 disconnects the port.

    Values are not normalized or filtered here; the game's ordinary PAD polling
    and input processing retain their timing, including any pipeline latency.
    """
    button: int = 0
    stick_x: int = 0
    stick_y: int = 0
    sub_x: int = 0
    sub_y: int = 0
    trigger_l: int = 0
    trigger_r: int = 0
    analog_a: int = 0
    analog_b: int = 0
    err: int = 0

    def __post_init__(self) -> None:
        for name, low, high in (("button", 0, 65535), ("stick_x", -128, 127), ("stick_y", -128, 127),
                                ("sub_x", -128, 127), ("sub_y", -128, 127), ("trigger_l", 0, 255),
                                ("trigger_r", 0, 255), ("analog_a", 0, 255), ("analog_b", 0, 255), ("err", -1, 0)):
            _integer(name, getattr(self, name), low, high)

    def native_argument(self) -> str:
        return " ".join(str(getattr(self, name)) for name in self.__dataclass_fields__)


NEUTRAL_PADS = (PadInput(), PadInput(), PadInput(err=-1), PadInput(err=-1))
