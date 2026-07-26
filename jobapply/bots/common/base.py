"""Common importable bot contract and accounting behavior."""

from __future__ import annotations

import os
import sys
from abc import ABC, abstractmethod
from dataclasses import asdict
from typing import Any, Callable

from .answers import AnswerEngine
from .applications import ApplicationCsvLogger
from .config import AutomationConfig, load_config
from .driver import create_driver
from .forms import FormFiller
from .results import AttemptOutcome, BotResult, JobInfo


DriverFactory = Callable[..., Any]


class BaseBot(ABC):
    PLATFORM = ""

    def __init__(
        self,
        config: AutomationConfig | None = None,
        *,
        driver_factory: DriverFactory = create_driver,
    ) -> None:
        if not self.PLATFORM:
            raise TypeError("Bot class must define PLATFORM")
        self.config = config or load_config(self.PLATFORM)
        self.driver_factory = driver_factory
        self.driver: Any | None = None
        self.csv: ApplicationCsvLogger | None = None
        self.result = BotResult(self.PLATFORM)
        self.profile = dict(self.config.profile)
        if not self.profile.get("email"):
            candidate_email = os.getenv("CANDIDATE_EMAIL", "").strip() or self.credential("email")
            if candidate_email:
                self.profile["email"] = candidate_email
        if not self.profile.get("phone") and os.getenv("CANDIDATE_PHONE", "").strip():
            self.profile["phone"] = os.getenv("CANDIDATE_PHONE", "").strip()
        self.answers = AnswerEngine(self.profile, self.config.filters)
        self.form_filler: FormFiller | None = None
        self.seen_jobs: set[str] = set()

    @property
    def debugger_address(self) -> str | None:
        return None

    def create_driver(self) -> Any:
        return self.driver_factory(self.config, debugger_address=self.debugger_address)

    def credential(self, field: str) -> str:
        variable = f"{self.PLATFORM.upper()}_{field.upper()}"
        return os.getenv(variable, "").strip()

    def is_relevant(self, job: JobInfo) -> bool:
        title = job.title.lower()
        excludes = [str(item).lower() for item in self.config.filters.get("excludeKeywords", [])]
        if any(excluded in title for excluded in excludes):
            return False
        if not self.config.filters.get("strictKeywordMatch", False):
            return True
        return any(keyword.lower() in title for keyword in self.config.keywords)

    @staticmethod
    def job_key(job: JobInfo) -> str:
        normalized = job.normalized()
        return (normalized.url or f"{normalized.title}|{normalized.company}").lower()

    def is_duplicate(self, job: JobInfo) -> bool:
        key = self.job_key(job)
        if key in self.seen_jobs:
            return True
        self.seen_jobs.add(key)
        return False

    def at_limit(self) -> bool:
        return self.result.reached_limit(self.config.max_applications)

    def record(self, job: JobInfo, outcome: AttemptOutcome) -> None:
        normalized = job.normalized()
        if self.csv is None:
            raise RuntimeError("CSV logger was not initialized")
        self.csv.log(self.PLATFORM, normalized, outcome.status, outcome.notes)
        self.result.record(outcome.status)
        print(
            f"[{self.PLATFORM}] {outcome.status.upper()}: {normalized.title}"
            f"{f' @ {normalized.company}' if normalized.company else ''} -- {outcome.notes}",
            flush=True,
        )

    def set_form_context(self, job: JobInfo) -> None:
        if self.form_filler:
            self.form_filler.set_context(asdict(job.normalized()))

    @abstractmethod
    def execute(self) -> None:
        """Run one browser session and record every examined job."""

    def run(self) -> BotResult:
        try:
            self.csv = ApplicationCsvLogger(self.config.applications_csv)
            self.driver = self.create_driver()
            self.form_filler = FormFiller(
                self.driver,
                self.answers,
                profile=self.profile,
                slow_mo=self.config.slow_mo,
            )
            self.execute()
        except KeyboardInterrupt:
            self.result.stop_reason = "interrupted"
            raise
        except Exception as error:
            self.result.add_session_error(error)
            print(f"[{self.PLATFORM}] Session error: {error}", file=sys.stderr, flush=True)
        finally:
            if self.driver is not None:
                try:
                    self.driver.quit()
                except Exception:
                    pass
        print(f"[{self.PLATFORM}] RESULT {self.result.to_json()}", flush=True)
        return self.result
