"""Naukri automation with optional Chrome CDP attachment and multi-step forms."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import quote_plus

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from bots.common.base import BaseBot
from bots.common.config import AutomationConfig
from bots.common.delays import human_delay, human_type
from bots.common.results import AttemptOutcome, BotResult, JobInfo
from bots.common.selectors import (
    attribute_of,
    confirmation_present,
    find_all_fallback,
    find_button_by_text,
    find_first,
    safe_click,
    text_of,
    wait_for_any_elements,
    wait_for_first,
)
from bots.common.workflow import wait_for_confirmation


CARD_LOCATORS = (
    (By.CSS_SELECTOR, ".srp-jobtuple-wrapper"),
    (By.CSS_SELECTOR, ".jobTuple"),
    (By.CSS_SELECTOR, "[data-job-id]"),
)
CARD_TITLE = (
    (By.CSS_SELECTOR, "a.title"),
    (By.CSS_SELECTOR, "a[title][href*='job-listings']"),
    (By.CSS_SELECTOR, "a[title][href*='job']"),
)
SUCCESS_LOCATORS = (
    (By.ID, "already-applied"),
    (By.CSS_SELECTOR, ".apply-status-header.green"),
    (By.XPATH, "//*[contains(translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'successfully applied')]"),
    (By.XPATH, "//*[contains(translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'application submitted')]"),
)
FORM_ROOTS = (
    (By.CSS_SELECTOR, "[class*='chatbot']"),
    (By.CSS_SELECTOR, "[id*='chatList']"),
    (By.CSS_SELECTOR, "[class*='apply-form']"),
    (By.CSS_SELECTOR, "[role='dialog']"),
)


class NaukriBot(BaseBot):
    PLATFORM = "naukri"

    @property
    def debugger_address(self) -> str | None:
        return os.getenv("CHROME_DEBUGGER_ADDRESS", "").strip() or None

    def login(self) -> None:
        assert self.driver is not None
        self.driver.get("https://www.naukri.com/")
        human_delay(self.config.slow_mo, 2.0)
        logged_in = find_first(
            self.driver,
            (
                (By.CSS_SELECTOR, "[title='View and update your profile']"),
                (By.CSS_SELECTOR, ".user-name"),
                (By.CSS_SELECTOR, "a[href*='mnjuser/profile']"),
            ),
            visible=True,
        )
        if logged_in:
            return
        email, password = self.credential("email"), self.credential("password")
        if not email or not password:
            raise RuntimeError("Naukri login is required; configure NAUKRI_EMAIL and NAUKRI_PASSWORD or attach a logged-in Chrome session")
        self.driver.get("https://www.naukri.com/nlogin/login")
        username = wait_for_first(
            self.driver,
            ((By.ID, "usernameField"), (By.CSS_SELECTOR, "input[type='email']"), (By.NAME, "email")),
            timeout=15,
        )
        password_field = wait_for_first(
            self.driver,
            ((By.ID, "passwordField"), (By.CSS_SELECTOR, "input[type='password']")),
            timeout=15,
        )
        username.clear()
        human_type(username, email, self.config.slow_mo)
        password_field.clear()
        human_type(password_field, password, self.config.slow_mo)
        submit = wait_for_first(
            self.driver,
            ((By.CSS_SELECTOR, "button[type='submit']"), (By.CSS_SELECTOR, ".loginButton")),
            timeout=10,
            clickable=True,
        )
        safe_click(self.driver, submit)
        try:
            WebDriverWait(self.driver, 20).until(lambda driver: "login" not in driver.current_url.lower())
        except TimeoutException as error:
            raise RuntimeError("Naukri login did not complete; verify credentials or use CHROME_DEBUGGER_ADDRESS") from error

    def search_url(self, keyword: str, location: str, page: int = 1) -> str:
        slug_keyword = "-".join(keyword.lower().split())
        slug_location = "-".join(location.lower().split())
        remote = "remote-" if self.config.filters.get("remoteOnly", False) else ""
        url = f"https://www.naukri.com/{remote}{slug_keyword}-jobs-in-{slug_location}"
        parameters = [
            f"k={quote_plus(keyword)}",
            f"l={quote_plus(location)}",
            f"jobAge={int(self.config.filters.get('postedWithinDays', 7))}",
        ]
        if page > 1:
            url += f"-{page}"
        return url + "?" + "&".join(parameters)

    def card_job(self, card: object) -> JobInfo:
        title = text_of(card, CARD_TITLE, "Unknown Naukri role")
        company = text_of(
            card,
            ((By.CSS_SELECTOR, ".comp-name"), (By.CSS_SELECTOR, ".companyName"), (By.CSS_SELECTOR, "a.comp-name")),
        )
        location = text_of(
            card,
            ((By.CSS_SELECTOR, ".locWdth"), (By.CSS_SELECTOR, ".location"), (By.CSS_SELECTOR, ".loc-wrap")),
        )
        url = attribute_of(card, CARD_TITLE, "href")
        if url.startswith("/"):
            url = "https://www.naukri.com" + url
        return JobInfo(title, company, location, url)

    def detail_job(self, fallback: JobInfo) -> JobInfo:
        assert self.driver is not None
        return JobInfo(
            text_of(
                self.driver,
                ((By.CSS_SELECTOR, "h1.styles_jd-header-title__rZwM1"), (By.CSS_SELECTOR, "h1.jd-header-title"), (By.CSS_SELECTOR, "h1")),
                fallback.title,
            ),
            text_of(
                self.driver,
                ((By.CSS_SELECTOR, ".styles_jd-header-comp-name__MvqAI"), (By.CSS_SELECTOR, ".jd-header-comp-name"), (By.CSS_SELECTOR, "[class*='company-name']")),
                fallback.company,
            ),
            text_of(
                self.driver,
                ((By.CSS_SELECTOR, ".styles_jhc__location__W_pVs"), (By.CSS_SELECTOR, ".location"), (By.CSS_SELECTOR, "[class*='location']")),
                fallback.location,
            ),
            fallback.url or self.driver.current_url,
        )

    def advance_naukri_form(self) -> tuple[bool, str]:
        assert self.driver is not None and self.form_filler is not None
        final_terms = ("Submit application", "Update and Apply", "Save and Apply", "Apply now")
        progress_terms = ("Next", "Continue", "Review", "Save", "Send", "Proceed")
        clicked_final = False
        for step in range(1, self.config.max_form_steps + 1):
            if confirmation_present(self.driver, SUCCESS_LOCATORS):
                return True, "submission confirmed"
            root = find_first(self.driver, FORM_ROOTS, visible=True)
            self.form_filler.fill(root or self.driver)
            human_delay(self.config.slow_mo, 0.8)
            action = find_button_by_text(self.driver, final_terms, root=root, timeout=1)
            if action:
                clicked_final = True
            else:
                action = find_button_by_text(self.driver, progress_terms, root=root, timeout=1)
            if not action:
                break
            try:
                safe_click(self.driver, action)
            except Exception:
                return False, f"form action failed at Naukri step {step}"
            human_delay(self.config.slow_mo, 1.5)
            if wait_for_confirmation(self.driver, SUCCESS_LOCATORS, timeout=4):
                return True, "submission confirmed"
        if confirmation_present(self.driver, SUCCESS_LOCATORS):
            return True, "submission confirmed"
        if clicked_final:
            return False, "submit clicked but Naukri success confirmation was not detected"
        return False, "Naukri form could not reach a confirmed submission"

    def attempt(self, initial: JobInfo) -> tuple[JobInfo, AttemptOutcome]:
        assert self.driver is not None
        if not initial.url:
            return initial, AttemptOutcome.failed("job URL was missing")
        try:
            self.driver.get(initial.url)
            human_delay(self.config.slow_mo, 2.0)
            job = self.detail_job(initial)
            self.set_form_context(job)
            if confirmation_present(self.driver, ((By.ID, "already-applied"),)):
                return job, AttemptOutcome.skipped("already applied")
            if confirmation_present(
                self.driver,
                (
                    (By.CSS_SELECTOR, "[class*='alert-message-text']"),
                    (By.XPATH, "//*[contains(translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'job is no longer available')]"),
                ),
            ):
                return job, AttemptOutcome.skipped("job is expired or unavailable")
            if find_first(
                self.driver,
                ((By.ID, "company-site-button"), (By.XPATH, "//*[contains(., 'Apply on company site')]")),
                visible=True,
            ):
                return job, AttemptOutcome.skipped("external company application")
            try:
                apply_button = wait_for_first(
                    self.driver,
                    (
                        (By.ID, "apply-button"),
                        (By.CSS_SELECTOR, "button.apply-message"),
                        (By.CSS_SELECTOR, ".apply-button"),
                        (By.XPATH, "//button[normalize-space()='Apply' or contains(., 'Apply now')]"),
                    ),
                    timeout=8,
                    clickable=True,
                )
            except TimeoutException:
                return job, AttemptOutcome.skipped("Naukri Apply button was unavailable")
            if "already" in (apply_button.text or "").lower():
                return job, AttemptOutcome.skipped("already applied")
            safe_click(self.driver, apply_button)
            human_delay(self.config.slow_mo, 1.5)
            if wait_for_confirmation(self.driver, SUCCESS_LOCATORS, timeout=3):
                return job, AttemptOutcome.applied("submission confirmed")
            success, notes = self.advance_naukri_form()
            return job, AttemptOutcome.applied(notes) if success else AttemptOutcome.failed(notes)
        except TimeoutException:
            return initial, AttemptOutcome.failed("Naukri application timed out")
        except Exception as error:
            return initial, AttemptOutcome.failed(f"application interaction failed: {type(error).__name__}")

    def execute(self) -> None:
        assert self.driver is not None
        self.login()
        for keyword in self.config.keywords:
            for location in self.config.locations:
                for page in range(1, self.config.max_pages + 1):
                    if self.at_limit():
                        return
                    self.driver.get(self.search_url(keyword, location, page))
                    human_delay(self.config.slow_mo, 2.0)
                    try:
                        cards = wait_for_any_elements(self.driver, CARD_LOCATORS, timeout=12)
                    except TimeoutException:
                        break
                    jobs = [self.card_job(card) for card in cards]
                    if not jobs:
                        break
                    for initial in jobs:
                        if self.at_limit():
                            return
                        if self.is_duplicate(initial):
                            continue
                        if not self.is_relevant(initial):
                            self.record(initial, AttemptOutcome.skipped("excluded by platform filter"))
                            continue
                        job, outcome = self.attempt(initial)
                        self.record(job, outcome)
                        human_delay(self.config.slow_mo, 1.0)


def run(config: AutomationConfig | None = None) -> BotResult:
    return NaukriBot(config).run()


def main() -> int:
    return 0 if run().ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
