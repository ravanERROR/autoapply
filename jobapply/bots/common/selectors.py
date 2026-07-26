"""Resilient selector fallbacks built on explicit Selenium waits."""

from __future__ import annotations

import re
from typing import Any, Iterable, Sequence

from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import WebDriverWait


Locator = tuple[str, str]


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
