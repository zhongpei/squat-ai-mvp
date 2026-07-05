from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from squat_ai_mvp.core.alert.tts import AlertCommand
from squat_ai_mvp.core.biomechanics.schemas import FaultEvent


class AlertPolicy:
    def __init__(
        self,
        enabled: bool = True,
        same_fault_cooldown_ms: int = 2500,
        max_alerts_per_rep: int = 2,
        max_alerts_per_set: int = 30,
    ) -> None:
        self.enabled = enabled
        self.same_fault_cooldown_ms = same_fault_cooldown_ms
        self.max_alerts_per_rep = max_alerts_per_rep
        self.max_alerts_per_set = max_alerts_per_set
        self.last_by_key: dict[str, int] = {}
        self.count_by_rep: dict[int, int] = defaultdict(int)
        self.total = 0

    def filter_faults(self, faults: Iterable[FaultEvent]) -> list[AlertCommand]:
        if not self.enabled:
            return []
        commands: list[AlertCommand] = []
        for fault in faults:
            if fault.severity == "low":
                # Keep low severity in logs, but do not speak in MVP by default.
                continue
            if self.total >= self.max_alerts_per_set:
                continue
            if self.count_by_rep[fault.rep_id] >= self.max_alerts_per_rep:
                continue
            key = f"{fault.exercise}.{fault.code}"
            last = self.last_by_key.get(key)
            if last is not None and fault.start_ms - last < self.same_fault_cooldown_ms:
                continue
            self.last_by_key[key] = fault.start_ms
            self.count_by_rep[fault.rep_id] += 1
            self.total += 1
            commands.append(AlertCommand(text=fault.message, priority=fault.severity, cooldown_key=key))
        return commands
