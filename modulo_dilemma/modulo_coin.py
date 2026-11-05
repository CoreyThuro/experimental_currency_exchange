import time
from dataclasses import dataclass
from typing import Literal, Optional

MODULUS = 20


@dataclass
class WrapAroundEvent:
    timestamp: float
    agent_id: str
    previous_balance: int
    transaction_amount: int
    resulting_balance: int
    direction: Literal["overflow", "underflow"]

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "agent_id": self.agent_id,
            "previous_balance": self.previous_balance,
            "transaction_amount": self.transaction_amount,
            "resulting_balance": self.resulting_balance,
            "direction": self.direction,
        }


class ModuloCoin:
    """
    A coin wallet with two modes:

    Modulo mode (default, unbounded=False): balance constrained to [0, modulus).
      Overflow on add wraps to the low end; both events are recorded in wraparound_log.

    Unbounded mode (unbounded=True): balance grows without limit, no wraparound.
      wraparound_log is always empty in this mode.
    """

    def __init__(
        self,
        value: int = 0,
        agent_id: str = "unknown",
        modulus: int = MODULUS,
        unbounded: bool = False,
    ):
        self.modulus = modulus
        self.agent_id = agent_id
        self.unbounded = unbounded
        self._value = value if unbounded else value % modulus
        self.wraparound_log: list[WrapAroundEvent] = []

    @property
    def value(self) -> int:
        return self._value

    def add(self, amount: int) -> Optional[WrapAroundEvent]:
        """Add coins. In modulo mode returns WrapAroundEvent on overflow, else None."""
        if amount < 0:
            raise ValueError("Use subtract() for negative amounts")
        if self.unbounded:
            self._value += amount
            return None
        prev = self._value
        raw = self._value + amount
        self._value = raw % self.modulus
        if raw >= self.modulus:
            event = WrapAroundEvent(
                timestamp=time.time(),
                agent_id=self.agent_id,
                previous_balance=prev,
                transaction_amount=amount,
                resulting_balance=self._value,
                direction="overflow",
            )
            self.wraparound_log.append(event)
            return event
        return None

    def subtract(self, amount: int) -> Optional[WrapAroundEvent]:
        """Subtract coins. In modulo mode returns WrapAroundEvent on underflow, else None."""
        if amount < 0:
            raise ValueError("Use add() for negative amounts")
        if self.unbounded:
            self._value -= amount
            return None
        prev = self._value
        raw = self._value - amount
        self._value = raw % self.modulus
        if raw < 0:
            event = WrapAroundEvent(
                timestamp=time.time(),
                agent_id=self.agent_id,
                previous_balance=prev,
                transaction_amount=amount,
                resulting_balance=self._value,
                direction="underflow",
            )
            self.wraparound_log.append(event)
            return event
        return None

    def __int__(self) -> int:
        return self._value

    def __eq__(self, other) -> bool:
        if isinstance(other, ModuloCoin):
            return self._value == other._value
        if isinstance(other, int):
            return self._value == other
        return NotImplemented

    def __lt__(self, other) -> bool:
        v = other._value if isinstance(other, ModuloCoin) else other
        return self._value < v

    def __le__(self, other) -> bool:
        v = other._value if isinstance(other, ModuloCoin) else other
        return self._value <= v

    def __gt__(self, other) -> bool:
        v = other._value if isinstance(other, ModuloCoin) else other
        return self._value > v

    def __ge__(self, other) -> bool:
        v = other._value if isinstance(other, ModuloCoin) else other
        return self._value >= v

    def __add__(self, amount: int) -> "ModuloCoin":
        result = ModuloCoin(value=self._value, agent_id=self.agent_id, modulus=self.modulus)
        result.add(amount)
        return result

    def __radd__(self, amount: int) -> "ModuloCoin":
        return self.__add__(amount)

    def __sub__(self, amount: int) -> "ModuloCoin":
        result = ModuloCoin(value=self._value, agent_id=self.agent_id, modulus=self.modulus)
        result.subtract(amount)
        return result

    def __iadd__(self, amount: int) -> "ModuloCoin":
        self.add(amount)
        return self

    def __isub__(self, amount: int) -> "ModuloCoin":
        self.subtract(amount)
        return self

    def __repr__(self) -> str:
        return f"ModuloCoin(value={self._value}, n={self.modulus})"
