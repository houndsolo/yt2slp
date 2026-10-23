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
class StockRules:
    """Explicit stock count and whole-minute countdown; other rules retain defaults."""
    seconds: int = 480
    stocks: int = 4

    def __post_init__(self) -> None:
        _integer('seconds', self.seconds, 60, 600)
        _integer('stocks', self.stocks, 1, 4)
        if self.seconds % 60:raise ValueError('stock timer requires whole minutes')

    def native_argument(self) -> str:
        return f'{self.seconds} {self.stocks}'


@dataclass(frozen=True)
class MatchConfig:
    """Two players on Yoshi's Story (8), Battlefield (31) or Final Destination (32).

    External IDs and zero-based physical ports. Other slots are empty. Optional
    stock rules replace only match kind, countdown and stocks; other rules retain
    defaults. This is match setup, not a savestate constructor.
    """
    stage: int = 31
    players: tuple[PlayerConfig, PlayerConfig] = (PlayerConfig(2), PlayerConfig(20))
    ports: tuple[int, int] = (0, 1)
    stock_rules: StockRules | None = None
    spawn_points: tuple[int, int] | None = None

    def __post_init__(self) -> None:
        _integer("stage", self.stage, 0, 32)
        if self.stage not in (8, 31, 32):raise ValueError('unsupported retail stage')
        if type(self.players) is not tuple or len(self.players) != 2 or any(not isinstance(p, PlayerConfig) for p in self.players):
            raise ValueError("players must be a tuple of two PlayerConfig values")
        if type(self.ports) is not tuple or len(self.ports) != 2:
            raise ValueError('ports must be a tuple of two distinct zero-based ports')
        for port in self.ports:_integer('port', port, 0, 3)
        if self.ports[0] == self.ports[1]:raise ValueError('player ports must differ')
        if self.stock_rules is not None and not isinstance(self.stock_rules, StockRules):
            raise ValueError('stock_rules requires StockRules or None')
        if self.spawn_points is not None:
            if (type(self.spawn_points) is not tuple or len(self.spawn_points)!=2
                    or any(type(s) is not int or not 0<=s<=3 for s in self.spawn_points)
                    or len(set(self.spawn_points))!=2):
                raise ValueError('spawn_points requires two distinct stage start-point indices in 0..3')

    def native_argument(self) -> str:
        values = [self.stage]
        for p in self.players:
            values.extend((p.character, p.costume, p.cpu, p.cpu_level))
        result = " ".join(map(str, values))
        if self.ports != (0, 1):result += f' ports {self.ports[0]} {self.ports[1]}'
        if self.spawn_points is not None:result += f' spawns {self.spawn_points[0]} {self.spawn_points[1]}'
        return result

    def neutral_pads(self) -> tuple['PadInput', ...]:
        return tuple(PadInput(err=0 if i in self.ports else -1) for i in range(4))


def match_from_document(document: dict) -> MatchConfig:
    """Read an explicit JSON match recipe; physical ports/rule choices are required."""
    if (not isinstance(document,dict) or not {'stage','players','ports','stock_rules'}<=set(document)
            or not set(document)<={'stage','players','ports','stock_rules','spawn_points'}
            or not isinstance(document['players'],list) or len(document['players'])!=2
            or not isinstance(document['ports'],list)):
        raise ValueError('explicit stage, two players, ports and stock_rules are required')
    players=[]
    for player in document['players']:
        if (not isinstance(player,dict) or 'character' not in player
                or not set(player)<=set(PlayerConfig.__dataclass_fields__)):
            raise ValueError('unsupported explicit player configuration')
        players.append(PlayerConfig(**player))
    rules=document['stock_rules']
    if rules is not None and (not isinstance(rules,dict) or set(rules)!={'seconds','stocks'}):
        raise ValueError('stock rules need seconds/stocks or explicit null')
    points=document.get('spawn_points')
    if points is not None and not isinstance(points,list):raise ValueError('spawn_points needs a JSON array or null')
    return MatchConfig(document['stage'],tuple(players),tuple(document['ports']),
        None if rules is None else StockRules(**rules),None if points is None else tuple(points))


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
