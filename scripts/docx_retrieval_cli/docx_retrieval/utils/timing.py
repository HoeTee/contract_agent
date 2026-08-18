from __future__ import annotations

import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, TextIO


@dataclass
class TimingRecord:
    name: str
    elapsed_seconds: float


class TimingCollector:
    def __init__(
        self,
        enabled: bool = True,
        stream: TextIO | None = None,
        prefix: str = "[timing]",
        log_stream: TextIO | None = None,
    ) -> None:
        self.enabled = enabled
        self.stream = stream or sys.stderr
        self.prefix = prefix
        self.log_stream = log_stream
        self.records: list[TimingRecord] = []

    @contextmanager
    def stage(self, name: str) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed = round(time.perf_counter() - start, 3)
            self.records.append(TimingRecord(name=name, elapsed_seconds=elapsed))
            if self.enabled:
                print(f"{self.prefix} {name}: {elapsed:.3f}s", file=self.stream, flush=True)
            if self.log_stream:
                print(f"{self.prefix} {name}: {elapsed:.3f}s", file=self.log_stream, flush=True)

    def as_dict(self) -> dict[str, float]:
        values: dict[str, float] = {}
        counts: dict[str, int] = {}
        for record in self.records:
            count = counts.get(record.name, 0) + 1
            counts[record.name] = count
            key = record.name if count == 1 else f"{record.name}#{count}"
            values[key] = record.elapsed_seconds
        return values
