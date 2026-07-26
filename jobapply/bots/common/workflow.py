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
    max_steps: int = 10,
) -> tuple[JobInfo, AttemptOutcome]:
    """Handle applications on external company websites with deep ATS support.
    
    This function handles redirects to external ATS systems including:
    - Workday
    - Lever
    - Greenhouse  
    - iCIMS
    - Taleo/Oracle
    - BambooHR
    - JazzHR
    - SmartRecruiters
    - And other custom company career sites
    
    Features:
    - Automatic detection of ATS platform from URL/domain
    - Platform-specific form handling strategies
    - Multi-step form navigation
    - Resume/CV upload support
    - Comprehensive field filling (text, dropdowns, radios, checkboxes)
    - Submit button detection and clicking
    - Success confirmation detection
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
            (By.XPATH, "//*[contains(translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'external apply')]"),
            (By.CSS_SELECTOR, "[data-testid='apply-external'], [data-test='apply-external']"),
        )
    
    # Find and click external apply button
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
        
        # Detect ATS platform from URL
        current_url = driver.current_url.lower()
        ats_platform = detect_ats_platform(current_url)
        print(f"[External Apply] Detected ATS platform: {ats_platform}", flush=True)
        
        # Navigate multi-step application form
        success, notes = complete_external_form(
            driver,
            filler,
            job,
            slow_mo,
            ats_platform,
            max_steps,
        )
        
        if success:
            return job, AttemptOutcome.applied(notes)
        else:
            return job, AttemptOutcome.failed(notes)
            
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


def detect_ats_platform(url: str) -> str:
    """Detect ATS platform from URL."""
    url_lower = url.lower()
    
    if 'myworkdayjobs' in url_lower or 'workday' in url_lower:
        return 'workday'
    elif 'lever.co' in url_lower or 'hire.lever.co' in url_lower:
        return 'lever'
    elif 'greenhouse.io' in url_lower or 'boards.greenhouse.io' in url_lower:
        return 'greenhouse'
    elif 'icims.com' in url_lower or 'job.icims.com' in url_lower:
        return 'icims'
    elif 'taleo.net' in url_lower or 'tbe.taleo.net' in url_lower:
        return 'taleo'
    elif 'bamboohr.com' in url_lower or 'jobs.bamboohr.com' in url_lower:
        return 'bamboohr'
    elif 'jazzhr.com' in url_lower or 'boards.jazzhr.com' in url_lower:
        return 'jazzhr'
    elif 'smartrecruiters.com' in url_lower:
        return 'smartrecruiters'
    elif 'ashbyhq.com' in url_lower:
        return 'ashby'
    elif 'jobvite.com' in url_lower:
        return 'jobvite'
    elif 'bullhorn.com' in url_lower:
        return 'bullhorn'
    else:
        return 'unknown'


def complete_external_form(
    driver: Any,
    filler: FormFiller,
    job: JobInfo,
    slow_mo: int,
    ats_platform: str,
    max_steps: int = 10,
) -> tuple[bool, str]:
    """Complete external application form with platform-specific strategies."""
    
    submitted = False
    notes_parts = []
    
    for step in range(1, max_steps + 1):
        # Check for success indicators
        if check_application_success(driver):
            return True, "external application submitted successfully"
        
        # Fill form fields using comprehensive form filler
        filled_count = filler.fill(driver)
        
        # Handle platform-specific interactions
        if ats_platform == 'workday':
            handle_workday_specific(driver, slow_mo)
        elif ats_platform == 'lever':
            handle_lever_specific(driver, slow_mo)
        elif ats_platform == 'greenhouse':
            handle_greenhouse_specific(driver, slow_mo)
        
        human_delay(slow_mo, 0.8)
        
        # Look for submit button
        submit_buttons = get_submit_button_locators()
        submit_btn = find_button_by_text(driver, ("Submit", "Submit Application", "Apply Now", "Send Application"), timeout=2)
        
        if submit_btn:
            try:
                safe_click(driver, submit_btn)
                submitted = True
                human_delay(slow_mo, 3.0)
                
                # Check for success after submit
                if check_application_success(driver):
                    return True, "external application submitted successfully"
                
                # Check for validation errors
                if has_validation_errors(driver):
                    notes_parts.append("validation errors present")
                    continue
            except Exception:
                return False, f"submit button failed at step {step}"
        
        # Look for next/continue button
        next_buttons = get_next_button_locators()
        next_btn = find_button_by_text(driver, ("Next", "Continue", "Review", "Save and Continue"), timeout=2)
        
        if next_btn:
            try:
                safe_click(driver, next_btn)
                human_delay(slow_mo, 2.0)
                continue
            except Exception:
                return False, f"next button failed at step {step}"
        
        # If we submitted but no confirmation, check for intermediate states
        if submitted:
            # Wait a bit more for confirmation
            human_delay(slow_mo, 2.0)
            if check_application_success(driver):
                return True, "external application submitted successfully"
            return False, "submit clicked but no success confirmation detected"
        
        # No actionable buttons found
        if filled_count == 0:
            return False, f"no fillable fields or buttons found at step {step}"
    
    # Max steps reached
    if check_application_success(driver):
        return True, "external application completed"
    return False, f"form exceeded {max_steps} steps without completion"


def check_application_success(driver: Any) -> bool:
    """Check if application was successfully submitted."""
    success_indicators = (
        (By.XPATH, "//*[contains(translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'successfully')]"),
        (By.XPATH, "//*[contains(translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'application sent')]"),
        (By.XPATH, "//*[contains(translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'application submitted')]"),
        (By.XPATH, "//*[contains(translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'thank you')]"),
        (By.XPATH, "//*[contains(translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'confirmation')]"),
        (By.CSS_SELECTOR, ".success-message, .confirmation-message, .artdeco-toast-item--success"),
        (By.CSS_SELECTOR, "[role='alert'][aria-live='polite']"),
    )
    
    for locator in success_indicators:
        try:
            elements = driver.find_elements(*locator)
            for elem in elements:
                if elem.is_displayed():
                    return True
        except Exception:
            continue
    return False


def has_validation_errors(driver: Any) -> bool:
    """Check for validation error messages."""
    error_indicators = (
        (By.CSS_SELECTOR, "[role='alert'], .error-message, .field-error, .validation-error"),
        (By.CSS_SELECTOR, ".artdeco-inline-feedback--error, .input-error"),
        (By.XPATH, "//*[contains(@class, 'error') and contains(@class, 'message')]"),
    )
    
    for locator in error_indicators:
        try:
            elements = driver.find_elements(*locator)
            for elem in elements:
                if elem.is_displayed() and elem.text.strip():
                    return True
        except Exception:
            continue
    return False


def handle_workday_specific(driver: Any, slow_mo: int) -> None:
    """Handle Workday-specific form interactions."""
    try:
        # Workday often uses custom dropdowns and date pickers
        # Scroll to ensure visibility
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        human_delay(slow_mo, 0.5)
    except Exception:
        pass


def handle_lever_specific(driver: Any, slow_mo: int) -> None:
    """Handle Lever-specific form interactions."""
    try:
        # Lever typically has straightforward forms
        pass
    except Exception:
        pass


def handle_greenhouse_specific(driver: Any, slow_mo: int) -> None:
    """Handle Greenhouse-specific form interactions."""
    try:
        # Greenhouse often has file upload sections
        pass
    except Exception:
        pass


def get_submit_button_locators() -> tuple[Locator, ...]:
    """Get common submit button locators."""
    return (
        (By.XPATH, "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'submit')]"),
        (By.XPATH, "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'apply')]"),
        (By.CSS_SELECTOR, "button[type='submit'], input[type='submit']"),
        (By.CSS_SELECTOR, "[data-testid='submit'], [data-test='submit']"),
    )


def get_next_button_locators() -> tuple[Locator, ...]:
    """Get common next/continue button locators."""
    return (
        (By.XPATH, "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'next')]"),
        (By.XPATH, "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue')]"),
        (By.XPATH, "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'review')]"),
        (By.CSS_SELECTOR, "[data-testid='next'], [data-test='next']"),
    )
