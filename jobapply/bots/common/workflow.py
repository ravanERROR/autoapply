"""Reusable bounded Next/Review/Submit application workflow."""

from __future__ import annotations

from typing import Any, Sequence

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from .delays import human_delay
from .forms import FormFiller
from .selectors import Locator, confirmation_present, find_button_by_text, find_first, safe_click


DEFAULT_VALIDATION_ERRORS: tuple[Locator, ...] = (
    (By.CSS_SELECTOR, "[role='alert'], .artdeco-inline-feedback--error, .field-error, .error-message"),
)


def wait_for_confirmation(driver: Any, locators: Sequence[Locator], timeout: float = 7) -> bool:
    try:
        return bool(WebDriverWait(driver, timeout).until(lambda _: confirmation_present(driver, locators)))
    except TimeoutException:
        return False


def complete_multistep_form(
    driver: Any,
    filler: FormFiller,
    *,
    success_locators: Sequence[Locator],
    max_steps: int,
    slow_mo: int,
    form_roots: Sequence[Locator] = (),
    submit_terms: Sequence[str] = ("Submit application", "Submit"),
    next_terms: Sequence[str] = ("Next", "Continue", "Review your application", "Review"),
    validation_error_locators: Sequence[Locator] = DEFAULT_VALIDATION_ERRORS,
) -> tuple[bool, str]:
    """Fill and advance a form, returning success only after visible confirmation."""

    submitted = False
    for step in range(1, max_steps + 1):
        if confirmation_present(driver, success_locators):
            return True, "submission confirmed"
        root = find_first(driver, form_roots, visible=True) if form_roots else None
        filler.fill(root or driver)
        human_delay(slow_mo, 0.8)

        submit = find_button_by_text(driver, submit_terms, root=root, timeout=1.5)
        if submit:
            try:
                safe_click(driver, submit)
                submitted = True
                human_delay(slow_mo, 2.0)
                if wait_for_confirmation(driver, success_locators):
                    return True, "submission confirmed"
                if confirmation_present(driver, validation_error_locators):
                    filler.fill(root or driver)
                    continue
            except Exception:
                return False, f"submit control failed at form step {step}"

        action = find_button_by_text(driver, next_terms, root=root, timeout=1.5)
        if action:
            try:
                safe_click(driver, action)
                human_delay(slow_mo, 1.5)
                continue
            except Exception:
                return False, f"next/review control failed at form step {step}"

        if submitted:
            return False, "submit clicked but no success confirmation was detected"
        return False, f"no Next, Review, or Submit control at form step {step}"
    if confirmation_present(driver, success_locators):
        return True, "submission confirmed"
    return False, f"form exceeded {max_steps} steps without confirmation"
