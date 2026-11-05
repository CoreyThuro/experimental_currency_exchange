from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class LedgerEntry:
    tick: int
    event_type: Literal["transfer", "work", "death"]
    agent_id: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"tick": self.tick, "event_type": self.event_type, "agent_id": self.agent_id, **self.details}


class PublicLedger:
    """
    Shared ledger visible to all agents.
    Records: transfers (sender, receiver, amount), work (agent_id, effort), deaths.
    Does NOT record: buy_energy, coin balances, energy levels.
    """

    def __init__(self):
        self._entries: list[LedgerEntry] = []

    def append(self, entry: LedgerEntry) -> None:
        self._entries.append(entry)

    def get_recent(self, n: int = 10) -> list[dict]:
        return [e.to_dict() for e in self._entries[-n:]]

    def get_all(self) -> list[dict]:
        return [e.to_dict() for e in self._entries]

    def get_transfers_to(self, agent_id: str) -> list[dict]:
        return [
            e.to_dict()
            for e in self._entries
            if e.event_type == "transfer" and e.details.get("target_id") == agent_id
        ]

    def get_recent_work_by(self, agent_id: str, since_tick: int) -> list[dict]:
        return [
            e.to_dict()
            for e in self._entries
            if e.agent_id == agent_id and e.event_type == "work" and e.tick >= since_tick
        ]

    def get_recent_buys_by(self, agent_id: str, since_tick: int) -> list[dict]:
        """Only useful for agents tracking their own private ledger; not in public view."""
        return [
            e.to_dict()
            for e in self._entries
            if e.agent_id == agent_id and e.event_type == "buy_energy" and e.tick >= since_tick
        ]

    def __len__(self) -> int:
        return len(self._entries)
