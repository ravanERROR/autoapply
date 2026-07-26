"""Resilient selector fallbacks built on explicit Selenium waits."""

from __future__ import annotations

import re
from typing import Any, Sequence

from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait


Locator = tuple[str, str]


# Extended locator strategies for modern ATS systems (Workday, Lever, Greenhouse, iCIMS, Taleo, etc.)
COMMON_INPUT_LOCATORS: tuple[Locator, ...] = (
    # Standard inputs
    (By.CSS_SELECTOR, "input[type='text'], input[type='email'], input[type='tel'], input[type='number'], input:not([type]), input[type='password']"),
    # Textareas
    (By.CSS_SELECTOR, "textarea"),
    # Selects
    (By.CSS_SELECTOR, "select"),
    # File uploads
    (By.CSS_SELECTOR, "input[type='file']"),
    # Checkboxes and radios
    (By.CSS_SELECTOR, "input[type='checkbox'], input[type='radio']"),
    # Content editable divs
    (By.CSS_SELECTOR, "div[contenteditable='true'], div.textArea, div.rich-text-editor"),
    # Modern framework inputs (React, Angular, Vue)
    (By.CSS_SELECTOR, "input[class*='input'], input[class*='field'], input[data-testid], input[aria-label]"),
    (By.CSS_SELECTOR, "div[class*='input'] input, div[class*='field'] input, div[class*='form'] input"),
    # Workday specific
    (By.CSS_SELECTOR, "input[id*='wd'], div[id*='wd'] input, span[id*='wd'] input"),
    (By.XPATH, "//input[contains(@id, 'wd-')] | //div[contains(@id, 'wd-')]//input"),
    # Lever specific
    (By.CSS_SELECTOR, "input[name*='lever'], div.lever-input input"),
    (By.XPATH, "//input[contains(@name, 'lever')]"),
    # Greenhouse specific
    (By.CSS_SELECTOR, "input[name*='greenhouse'], div.gh-field input"),
    (By.XPATH, "//input[contains(@name, 'greenhouse')] | //div[contains(@class, 'gh-field')]//input"),
    # iCIMS specific
    (By.CSS_SELECTOR, "input[name*='icims'], div.icims-input input"),
    # Taleo/Oracle specific
    (By.CSS_SELECTOR, "input[name*='taleo'], div.taleo-input input"),
    # BambooHR specific
    (By.CSS_SELECTOR, "input[name*='bamboo'], div.bamboo-input input"),
    # JazzHR specific
    (By.CSS_SELECTOR, "input[name*='jazzhr'], div.jazz-input input"),
    # SmartRecruiters specific
    (By.CSS_SELECTOR, "input[name*='smartrecruiter'], div.smart-input input"),
    # Generic class-based patterns
    (By.CSS_SELECTOR, "input[class*='form-control'], input[class*='text-field'], input[class*='input-field']"),
    (By.CSS_SELECTOR, "input[class*='resume'], input[class*='cv'], input[class*='upload']"),
    # Aria-based patterns
    (By.CSS_SELECTOR, "input[aria-label], input[aria-labelledby], input[role='textbox']"),
    # Data attribute patterns
    (By.CSS_SELECTOR, "input[data-label], input[data-field], input[data-name]"),
)

COMMON_BUTTON_LOCATORS: tuple[Locator, ...] = (
    # Standard buttons
    (By.CSS_SELECTOR, "button, input[type='submit'], input[type='button']"),
    # Link buttons
    (By.CSS_SELECTOR, "a[role='button'], span[role='button'], div[role='button']"),
    # Class-based patterns
    (By.CSS_SELECTOR, "button[class*='btn'], button[class*='button'], button[class*='submit'], button[class*='apply']"),
    (By.CSS_SELECTOR, "div[class*='btn'], div[class*='button'], a[class*='btn'], a[class*='button']"),
    # Workday specific
    (By.CSS_SELECTOR, "button[id*='wd'], div[id*='wd'] button, a[id*='wd'][role='button']"),
    (By.XPATH, "//button[contains(@id, 'wd-')] | //a[contains(@id, 'wd-') and @role='button']"),
    # Lever specific
    (By.CSS_SELECTOR, "button[class*='lever'], a[class*='lever']"),
    # Greenhouse specific
    (By.CSS_SELECTOR, "button[class*='greenhouse'], .gh-btn, .gh-button"),
    (By.XPATH, "//button[contains(@class, 'gh-')] | //a[contains(@class, 'gh-btn')]"),
    # iCIMS specific
    (By.CSS_SELECTOR, "button[class*='icims'], .icims-btn"),
    # Common action buttons
    (By.CSS_SELECTOR, "button[data-action], button[data-testid*='submit'], button[data-testid*='next']"),
    # Aria-based patterns
    (By.CSS_SELECTOR, "button[aria-label*='submit'], button[aria-label*='next'], button[aria-label*='continue']"),
    # Text content patterns (fallback)
    (By.XPATH, "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'submit')]"),
    (By.XPATH, "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'next')]"),
    (By.XPATH, "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'continue')]"),
    (By.XPATH, "//button[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'apply')]"),
    (By.XPATH, "//a[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'submit')]"),
    (By.XPATH, "//span[contains(@role, 'button') and contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'submit')]"),
)

COMMON_DROPDOWN_LOCATORS: tuple[Locator, ...] = (
    # Standard selects
    (By.CSS_SELECTOR, "select"),
    # Custom dropdowns (div-based)
    (By.CSS_SELECTOR, "div[class*='dropdown'], div[class*='select'], div[class*='combo']"),
    (By.CSS_SELECTOR, "div[role='listbox'], div[role='combobox'], div[role='menu']"),
    # Workday specific
    (By.CSS_SELECTOR, "div[id*='wd'] select, div[id*='wd'][role='listbox']"),
    # Lever specific
    (By.CSS_SELECTOR, "select[name*='lever'], div[class*='lever'][role='listbox']"),
    # Greenhouse specific
    (By.CSS_SELECTOR, "select[name*='greenhouse'], .gh-dropdown, .gh-select"),
    # Aria-based patterns
    (By.CSS_SELECTOR, "div[aria-haspopup='listbox'], div[aria-expanded][role='button']"),
    # Data attribute patterns
    (By.CSS_SELECTOR, "div[data-role='dropdown'], div[data-component='select']"),
)

COMMON_RADIO_GROUP_LOCATORS: tuple[Locator, ...] = (
    # Standard radio groups
    (By.CSS_SELECTOR, "fieldset input[type='radio'], div[role='radiogroup'] input[type='radio']"),
    (By.CSS_SELECTOR, "input[type='radio']"),
    # Class-based patterns
    (By.CSS_SELECTOR, "div[class*='radio'] input[type='radio'], div[class*='option'] input[type='radio']"),
    # Workday specific
    (By.CSS_SELECTOR, "div[id*='wd'] input[type='radio']"),
    # Lever/Greenhouse specific
    (By.CSS_SELECTOR, "div[class*='lever'] input[type='radio'], div[class*='greenhouse'] input[type='radio']"),
    # Aria-based patterns
    (By.CSS_SELECTOR, "div[role='radio'] input[type='radio'], input[type='radio'][role='radio']"),
)

COMMON_CHECKBOX_LOCATORS: tuple[Locator, ...] = (
    # Standard checkboxes
    (By.CSS_SELECTOR, "input[type='checkbox']"),
    # Custom checkboxes (div/span-based)
    (By.CSS_SELECTOR, "div[class*='checkbox'], span[class*='checkbox'], div[role='checkbox']"),
    # Workday specific
    (By.CSS_SELECTOR, "div[id*='wd'] input[type='checkbox'], div[id*='wd'][role='checkbox']"),
    # Lever/Greenhouse specific
    (By.CSS_SELECTOR, "div[class*='lever'] input[type='checkbox'], div[class*='greenhouse'] input[type='checkbox']"),
    # Aria-based patterns
    (By.CSS_SELECTOR, "div[aria-checked], span[aria-checked], input[aria-checked]"),
    # Data attribute patterns
    (By.CSS_SELECTOR, "div[data-checkbox], span[data-checkbox]"),
)

COMMON_FILE_UPLOAD_LOCATORS: tuple[Locator, ...] = (
    # Standard file inputs
    (By.CSS_SELECTOR, "input[type='file']"),
    # Drop zones
    (By.CSS_SELECTOR, "div[class*='dropzone'], div[class*='upload'], div[class*='file-upload']"),
    (By.CSS_SELECTOR, "div[role='button'][aria-label*='upload'], div[role='button'][data-testid*='upload']"),
    # Workday specific
    (By.CSS_SELECTOR, "div[id*='wd'] input[type='file'], div[id*='wd'][role='button'][aria-label*='upload']"),
    # Lever specific
    (By.CSS_SELECTOR, "input[type='file'][name*='lever'], div[class*='lever'][role='button'][aria-label*='upload']"),
    # Greenhouse specific
    (By.CSS_SELECTOR, "input[type='file'][name*='greenhouse'], .gh-file-upload, .gh-upload"),
    # Label patterns
    (By.XPATH, "//label[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'upload')]"),
    (By.XPATH, "//div[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'resume')]"),
    (By.XPATH, "//div[contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'cv')]"),
    # Aria-based patterns
    (By.CSS_SELECTOR, "button[aria-label*='upload'], button[aria-label*='resume'], button[aria-label*='cv']"),
    (By.CSS_SELECTOR, "div[aria-label*='upload'], div[aria-label*='resume'], div[aria-label*='cv']"),
)

COMMON_LABEL_PATTERNS: tuple[str, ...] = (
    "label", "legend", "*[role='heading']", "*[class*='label']", "*[class*='question']",
    "*[data-label]", "*[aria-label]", "*[placeholder]", "fieldset legend", ".form-label",
    ".field-label", ".input-label", ".question-text", ".question-title"
)


def find_first(root: Any, locators: Sequence[Locator], *, visible: bool = False) -> WebElement | None:
    for by, selector in locators:
        try:
            for element in root.find_elements(by, selector):
                if not visible or element.is_displayed():
                    return element
        except (NoSuchElementException, StaleElementReferenceException):
            continue
    return None


def find_all_fallback(root: Any, locators: Sequence[Locator], *, visible: bool = False) -> list[WebElement]:
    for by, selector in locators:
        try:
            elements = [element for element in root.find_elements(by, selector) if not visible or element.is_displayed()]
            if elements:
                return elements
        except (NoSuchElementException, StaleElementReferenceException):
            continue
    return []


def wait_for_first(
    driver: Any,
    locators: Sequence[Locator],
    *,
    timeout: float = 10,
    visible: bool = True,
    clickable: bool = False,
    root: Any | None = None,
) -> WebElement:
    search_root = root or driver

    def locate(_: Any) -> WebElement | bool:
        element = find_first(search_root, locators, visible=visible)
        if not element:
            return False
        if clickable:
            try:
                return element if element.is_enabled() else False
            except StaleElementReferenceException:
                return False
        return element

    return WebDriverWait(
        driver,
        timeout,
        ignored_exceptions=(NoSuchElementException, StaleElementReferenceException),
    ).until(locate)


def wait_for_any_elements(
    driver: Any,
    locators: Sequence[Locator],
    *,
    timeout: float = 10,
    visible: bool = False,
) -> list[WebElement]:
    return WebDriverWait(driver, timeout).until(
        lambda _: find_all_fallback(driver, locators, visible=visible) or False
    )


def safe_click(driver: Any, element: WebElement) -> None:
    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
    try:
        element.click()
    except Exception:
        driver.execute_script("arguments[0].click();", element)


def text_of(root: Any, locators: Sequence[Locator], default: str = "") -> str:
    element = find_first(root, locators)
    if not element:
        return default
    try:
        return (element.text or element.get_attribute("textContent") or default).strip()
    except StaleElementReferenceException:
        return default


def attribute_of(root: Any, locators: Sequence[Locator], attribute: str, default: str = "") -> str:
    element = find_first(root, locators)
    if not element:
        return default
    try:
        return (element.get_attribute(attribute) or default).strip()
    except StaleElementReferenceException:
        return default


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().lower()


def find_button_by_text(
    driver: Any,
    terms: Iterable[str],
    *,
    root: Any | None = None,
    timeout: float = 3,
) -> WebElement | None:
    wanted = tuple(normalize_text(term) for term in terms)
    search_root = root or driver

    def locate(_: Any) -> WebElement | bool:
        try:
            candidates = search_root.find_elements(
                By.CSS_SELECTOR,
                "button, input[type='submit'], input[type='button'], a[role='button'], [role='button'], "
                "div[class*='button'], div[class*='Button'], div[class*='btn'], div[class*='send'], div[class*='save']",
            )
        except (NoSuchElementException, StaleElementReferenceException):
            return False
        partial: WebElement | None = None
        for candidate in candidates:
            try:
                if not candidate.is_displayed() or not candidate.is_enabled():
                    continue
                if candidate.get_attribute("disabled") is not None or candidate.get_attribute("aria-disabled") == "true":
                    continue
                combined = normalize_text(
                    " ".join(
                        filter(
                            None,
                            [candidate.text, candidate.get_attribute("value"), candidate.get_attribute("aria-label"), candidate.get_attribute("data-testid")],
                        )
                    )
                )
                if combined in wanted:
                    return candidate
                if partial is None and any(term in combined for term in wanted):
                    partial = candidate
            except StaleElementReferenceException:
                continue
        return partial or False

    try:
        return WebDriverWait(driver, timeout).until(locate)
    except TimeoutException:
        return None


def confirmation_present(root: Any, locators: Sequence[Locator]) -> bool:
    for by, selector in locators:
        try:
            if any(element.is_displayed() for element in root.find_elements(by, selector)):
                return True
        except (NoSuchElementException, StaleElementReferenceException):
            continue
    return False
