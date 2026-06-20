from __future__ import annotations
from dataclasses import dataclass


class TON:
    """On-delay timer. Q goes true once IN has been true for PT milliseconds."""

    def __init__(self) -> None:
        self.Q = False
        self.ET = 0  # elapsed time, ms

    def __call__(self, IN: bool, PT: int, dt: int) -> bool:
        if IN:
            self.ET = min(PT, self.ET + dt)
            self.Q = self.ET >= PT
        else:
            self.ET = 0
            self.Q = False
        return self.Q


class TOF:
    """Off-delay timer. Q stays true for PT milliseconds after IN goes false."""

    def __init__(self) -> None:
        self.Q = False
        self.ET = 0
        self._prev = False

    def __call__(self, IN: bool, PT: int, dt: int) -> bool:
        if IN:
            self.Q = True
            self.ET = 0
        else:
            self.ET = min(PT, self.ET + dt)
            self.Q = self.ET < PT
        return self.Q


def load_pou(python_code: str, class_name: str) -> type:
    ns: dict = {}
    exec(compile(python_code, "<plcpy-pou>", "exec"), ns)
    return ns[class_name]


@dataclass
class ScanTrace:
    cycle: int
    outputs: dict


def run_scans(instance, inputs_per_cycle: list[dict], output_names: list[str],
              dt_ms: int = 100) -> list[ScanTrace]:
    traces: list[ScanTrace] = []
    for cycle, inputs in enumerate(inputs_per_cycle):
        instance._dt_ms = dt_ms              # scan period for timers
        for name, value in inputs.items():   # read inputs
            setattr(instance, name, value)
        instance.scan()                      # execute logic
        snap = {n: getattr(instance, n) for n in output_names}  # write/snapshot outputs
        traces.append(ScanTrace(cycle, snap))
    return traces
