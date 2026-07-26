"""Reusable bounded Next/Review/Submit application workflow."""

from __future__ import annotations

from typing import Any, Sequence

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from .delays import human_delay
from .forms import FormFiller
from .results import AttemptOutcome, JobInfo
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


def handle_external_application(
    driver: Any,
    filler: FormFiller,
    job: JobInfo,
    slow_mo: int,
    external_button_locators: Sequence[Locator] = (),
) -> tuple[JobInfo, AttemptOutcome]:
    """Handle applications on external company websites by navigating and attempting to apply.
    
    This function is inspired by browser-use approach for handling multi-site workflows.
    """
    from selenium.common.exceptions import TimeoutException
    
    # Default external button locators if not provided
    if not external_button_locators:
        external_button_locators = (
            (By.ID, "company-site-button"),
            (By.XPATH, "//*[contains(., 'Apply on company site')]"),
            (By.XPATH, "//*[contains(@href, 'apply')]"),
            (By.CSS_SELECTOR, "a[href*='apply'], button[href*='apply']"),
            (By.XPATH, "//*[contains(translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'apply now')]"),
        )
    
    external_btn = find_first(driver, external_button_locators, visible=True)
    if not external_btn:
        return job, AttemptOutcome.failed("no external apply button found")
    
    try:
        # Store original window handle
        original_window = driver.current_window_handle
        
        # Click the external apply button
        safe_click(driver, external_btn)
        human_delay(slow_mo, 3.0)
        
        # Wait for new tab/window or navigation
        WebDriverWait(driver, 10).until(
            lambda d: len(d.window_handles) > 1 or d.current_url != job.url
        )
        
        # Switch to new tab if opened
        if len(driver.window_handles) > 1:
            for handle in driver.window_handles:
                if handle != original_window:
                    driver.switch_to.window(handle)
                    break
        
        human_delay(slow_mo, 2.0)
        
        # Now we're on the company website - try to find and fill application form
        # Look for common application form elements
        form_indicators = (
            (By.CSS_SELECTOR, "form"),
            (By.CSS_SELECTOR, "input[type='file']"),
            (By.CSS_SELECTOR, "input[name*='resume'], input[id*='resume']"),
            (By.CSS_SELECTOR, "input[name*='cv'], input[id*='cv']"),
            (By.XPATH, "//*[contains(translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'upload resume')]"),
            (By.XPATH, "//*[contains(translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'upload cv')]"),
            (By.XPATH, "//*[contains(translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'apply')]"),
        )
        
        form_element = find_first(driver, form_indicators, visible=True)
        if not form_element:
            # No form found, might be a redirect to login or different flow
            current_url = driver.current_url
            return job, AttemptOutcome.skipped(f"redirected to external site: {current_url[:100]}")
        
        # Fill the form using the form filler
        filler.fill(driver)
        human_delay(slow_mo, 1.5)
        
        # Look for submit buttons on the external site
        submit_buttons = (
            (By.XPATH, "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'submit')]"),
            (By.XPATH, "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'apply')]"),
            (By.XPATH, "//input[@type='submit']"),
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.CSS_SELECTOR, "input[type='submit']"),
        )
        
        submit_btn = find_first(driver, submit_buttons, visible=True, clickable=True)
        if submit_btn:
            safe_click(driver, submit_btn)
            human_delay(slow_mo, 3.0)
            
            # Check for success indicators
            success_indicators = (
                (By.XPATH, "//*[contains(translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'successfully')]"),
                (By.XPATH, "//*[contains(translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'application submitted')]"),
                (By.XPATH, "//*[contains(translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'thank you')]"),
                (By.CSS_SELECTOR, ".success-message, .confirmation-message"),
            )
            
            if confirmation_present(driver, success_indicators):
                return job, AttemptOutcome.applied("external application submitted successfully")
            else:
                return job, AttemptOutcome.applied("external application form filled and submitted (confirmation pending)")
        else:
            return job, AttemptOutcome.applied("external application form filled (manual submit required)")
            
    except TimeoutException:
        return job, AttemptOutcome.failed("timeout waiting for external site navigation")
    except Exception as error:
        return job, AttemptOutcome.failed(f"external application failed: {type(error).__name__}")
    finally:
        # Close extra tabs and return to original window if needed
        if 'original_window' in locals() and len(driver.window_handles) > 1:
            for handle in driver.window_handles:
                if handle != original_window:
                    try:
                        driver.switch_to.window(handle)
                        driver.close()
                    except Exception:
                        pass
            try:
                driver.switch_to.window(original_window)
            except Exception:
                pass
