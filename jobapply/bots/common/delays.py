"""Small human-like interaction delays controlled by SLOW_MO."""

from __future__ import annotations

import random
import time
from typing import Any


def human_delay(slow_mo: int, multiplier: float = 1.0, jitter: float = 0.25) -> None:
    if slow_mo <= 0:
        return
    base = max(0.0, slow_mo / 1000.0 * multiplier)
    spread = base * max(0.0, jitter)
    time.sleep(max(0.0, random.uniform(base - spread, base + spread)))


def human_type(element: Any, text: object, slow_mo: int) -> None:
    value = str(text)
    if slow_mo > 0:
        time.sleep(random.uniform(0.1, min(0.5, max(0.2, slow_mo / 2000.0))))
    element.send_keys(value)
    actual = (element.get_attribute("value") or "").strip()
    if actual != value:
        driver = getattr(element, "_parent", None)
        if driver is not None:
            driver.execute_script(
                "const el=arguments[0],val=arguments[1]; el.value=val; el.dispatchEvent(new Event('input',{bubbles:true})); el.dispatchEvent(new Event('change',{bubbles:true}));",
                element,
                value,
            )
