"""Agent registry and agent cards.

Generalized from the ConBot model registry. Every agent under governance
declares a card: who it is, what it is for, which action kinds it may take,
what data it touches, which policy governs it, and a reliability signal so a
drifting or warming-up agent cannot pass itself off as fully trusted.

An unregistered agent is unknown, and unknown means denied by default.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class AgentStatus(str, Enum):
    WARMING_UP = "warming_up"
    ACTIVE = "active"
    HALTED = "halted"
    RETIRED = "retired"


@dataclass
class AgentCard:
    agent_id: str
    purpose: str = ""
    allowed_kinds: list[str] = field(default_factory=list)
    data_sources: list[str] = field(default_factory=list)
    policy: str = "default"
    status: AgentStatus = AgentStatus.WARMING_UP
    calibration: float = 0.0           # reliability 0..1, like ConBot's calibration tier
    created_ts: float = field(default_factory=time.time)


class AgentRegistry:
    """Thread-safe store of agent cards plus a per-agent halt set."""

    def __init__(self):
        self._cards: dict[str, AgentCard] = {}
        self._halted: set[str] = set()
        self._lock = threading.Lock()

    def register(self, card: AgentCard) -> AgentCard:
        with self._lock:
            self._cards[card.agent_id] = card
        return card

    def get(self, agent_id: str) -> Optional[AgentCard]:
        return self._cards.get(agent_id)

    def is_known(self, agent_id: str) -> bool:
        return agent_id in self._cards

    def list(self) -> list[AgentCard]:
        return list(self._cards.values())

    def set_status(self, agent_id: str, status: AgentStatus) -> None:
        with self._lock:
            if agent_id in self._cards:
                self._cards[agent_id].status = status

    def halt(self, agent_id: str) -> None:
        """Bench one agent. Survives until explicitly resumed."""
        with self._lock:
            self._halted.add(agent_id)
            if agent_id in self._cards:
                self._cards[agent_id].status = AgentStatus.HALTED

    def resume(self, agent_id: str) -> None:
        with self._lock:
            self._halted.discard(agent_id)
            if agent_id in self._cards:
                self._cards[agent_id].status = AgentStatus.ACTIVE

    def is_halted(self, agent_id: str) -> bool:
        return agent_id in self._halted

    def halted_agents(self) -> set[str]:
        return set(self._halted)
