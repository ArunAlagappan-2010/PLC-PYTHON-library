from __future__ import annotations
from dataclasses import dataclass


def load_pou(python_code: str, class_name: str) -> type:
    ns: dict = {}
    exec(compile(python_code, "<plcpy-pou>", "exec"), ns)
    return ns[class_name]


@dataclass
class ScanTrace:
    cycle: int
    outputs: dict


def run_scans(instance, inputs_per_cycle: list[dict], output_names: list[str]) -> list[ScanTrace]:
    traces: list[ScanTrace] = []
    for cycle, inputs in enumerate(inputs_per_cycle):
        for name, value in inputs.items():   # read inputs
            setattr(instance, name, value)
        instance.scan()                      # execute logic
        snap = {n: getattr(instance, n) for n in output_names}  # write/snapshot outputs
        traces.append(ScanTrace(cycle, snap))
    return traces
