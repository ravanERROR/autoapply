"""CLI registry and launcher for every supported JobApply Selenium bot."""

from __future__ import annotations

import argparse
import ast
import importlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bots import SUPPORTED_PLATFORMS
from bots.common.config import AutomationConfig, ConfigError, load_config
from bots.common.results import BotResult


@dataclass(frozen=True, slots=True)
class BotRegistration:
    module: str
    script: Path


BOTS_DIR = Path(__file__).resolve().parent
BOT_REGISTRY: dict[str, BotRegistration] = {
    platform: BotRegistration(f"bots.{platform}_bot", BOTS_DIR / f"{platform}_bot.py")
    for platform in SUPPORTED_PLATFORMS
}
# Backwards-compatible path registry used by older callers and simple checks.
BOTS: dict[str, Path] = {name: registration.script for name, registration in BOT_REGISTRY.items()}


def selected_platforms(platform: str) -> tuple[str, ...]:
    return SUPPORTED_PLATFORMS if platform == "all" else (platform,)


def _source_contract(path: Path) -> tuple[bool, str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError) as error:
        return False, str(error)
    functions = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    missing = {"run", "main"} - functions
    return (not missing, "" if not missing else f"missing entry points: {', '.join(sorted(missing))}")


def validate_registry(platforms: Sequence[str]) -> list[tuple[str, AutomationConfig]]:
    if tuple(BOT_REGISTRY) != tuple(SUPPORTED_PLATFORMS):
        raise ConfigError("Bot registry must contain all five supported platforms in canonical order")
    validated: list[tuple[str, AutomationConfig]] = []
    validating_all = tuple(platforms) == tuple(SUPPORTED_PLATFORMS)
    for platform in platforms:
        registration = BOT_REGISTRY.get(platform)
        if registration is None:
            raise ConfigError(f"No bot is registered for {platform}")
        if not registration.script.is_file():
            raise ConfigError(f"Registered bot script does not exist: {registration.script}")
        valid_contract, detail = _source_contract(registration.script)
        if not valid_contract:
            raise ConfigError(f"Invalid {platform} bot contract: {detail}")
        validated.append(
            (
                platform,
                load_config(platform, runtime_overrides={"platform": "all"} if validating_all else None),
            )
        )
    return validated


def run_bot(platform: str, config: AutomationConfig | None = None) -> BotResult:
    registration = BOT_REGISTRY[platform]
    print(f"[orchestrator] Starting {platform}", flush=True)
    module = importlib.import_module(registration.module)
    entry = getattr(module, "run", None)
    if not callable(entry):
        raise RuntimeError(f"{registration.module} does not expose callable run(config=None)")
    result = entry(config or load_config(platform))
    if not isinstance(result, BotResult):
        raise RuntimeError(f"{registration.module}.run() returned {type(result).__name__}, expected BotResult")
    print(f"[orchestrator] Finished {platform}: {result.to_json()}", flush=True)
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run one or all JobApply platform bots")
    parser.add_argument("--platform", required=True, choices=[*SUPPORTED_PLATFORMS, "all"])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate the registry and effective configuration without importing Selenium bots or launching browsers",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    platforms = selected_platforms(args.platform)
    try:
        validated = validate_registry(platforms)
    except ConfigError as error:
        print(f"[orchestrator] Configuration error: {error}", file=sys.stderr, flush=True)
        return 2

    if args.dry_run:
        for platform, config in validated:
            print(
                "[orchestrator] DRY-RUN "
                + json.dumps(config.public_summary(), ensure_ascii=False, sort_keys=True),
                flush=True,
            )
        print(f"[orchestrator] Dry-run validation passed for: {', '.join(platforms)}", flush=True)
        return 0

    exit_code = 0
    for platform, config in validated:
        try:
            result = run_bot(platform, config)
            if not result.ok:
                exit_code = 1
        except KeyboardInterrupt:
            print(f"[orchestrator] Interrupted while running {platform}", file=sys.stderr, flush=True)
            return 130
        except Exception as error:
            exit_code = 1
            print(f"[orchestrator] {platform} failed: {error}", file=sys.stderr, flush=True)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
