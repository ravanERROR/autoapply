"""Shared configuration, browser, form, and logging helpers."""

from .config import AutomationConfig, ConfigError, deep_merge, load_config
from .results import AttemptOutcome, BotResult, JobInfo

__all__ = [
    "AttemptOutcome",
    "AutomationConfig",
    "BotResult",
    "ConfigError",
    "JobInfo",
    "deep_merge",
    "load_config",
]
