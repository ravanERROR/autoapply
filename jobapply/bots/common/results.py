"""Structured job metadata, attempt outcomes, and bot counters."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Literal


AttemptStatus = Literal["applied", "skipped", "failed"]


@dataclass(slots=True)
class JobInfo:
    title: str
    company: str = ""
    location: str = ""
    url: str = ""

    def normalized(self) -> "JobInfo":
        return JobInfo(
            title=(self.title or "Unknown role").strip(),
            company=(self.company or "").strip(),
            location=(self.location or "").strip(),
            url=(self.url or "").strip(),
        )


@dataclass(frozen=True, slots=True)
class AttemptOutcome:
    status: AttemptStatus
    notes: str = ""

    @classmethod
    def applied(cls, notes: str = "submission confirmed") -> "AttemptOutcome":
        return cls("applied", notes)

    @classmethod
    def skipped(cls, notes: str) -> "AttemptOutcome":
        return cls("skipped", notes)

    @classmethod
    def failed(cls, notes: str) -> "AttemptOutcome":
        return cls("failed", notes)


@dataclass(slots=True)
class BotResult:
    platform: str
    applied: int = 0
    skipped: int = 0
    failed: int = 0
    examined: int = 0
    stop_reason: str = "completed"
    session_errors: list[str] = field(default_factory=list)

    def record(self, status: AttemptStatus) -> None:
        if status not in {"applied", "skipped", "failed"}:
            raise ValueError(f"Invalid attempt status: {status}")
        self.examined += 1
        setattr(self, status, getattr(self, status) + 1)

    def add_session_error(self, error: BaseException | str) -> None:
        self.session_errors.append(str(error))
        self.stop_reason = "session_error"

    def reached_limit(self, maximum: int) -> bool:
        if self.applied >= maximum:
            self.stop_reason = "max_applications_reached"
            return True
        return False

    @property
    def ok(self) -> bool:
        return not self.session_errors

    def as_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.as_dict(), ensure_ascii=False, sort_keys=True)
