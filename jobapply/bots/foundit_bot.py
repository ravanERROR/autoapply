"""Foundit job application automation with confirmation-based accounting."""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlencode

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
    find_first,
    safe_click,
    text_of,
    wait_for_any_elements,
    wait_for_first,
)
from bots.common.workflow import complete_multistep_form, wait_for_confirmation


CARD_LOCATORS = (
    (By.CSS_SELECTOR, ".srpResultCard"),
    (By.CSS_SELECTOR, ".job-tuple"),
    (By.CSS_SELECTOR, "[class*='jobCard']"),
    (By.CSS_SELECTOR, "[data-job-id]"),
)
CARD_TITLE = (
    (By.CSS_SELECTOR, "a.jobTitle"),
    (By.CSS_SELECTOR, ".jobTitle a"),
    (By.CSS_SELECTOR, "h3 a"),
    (By.CSS_SELECTOR, "a[href*='/job/']"),
)
FORM_ROOTS = (
    (By.CSS_SELECTOR, "[role='dialog']"),
    (By.CSS_SELECTOR, "[class*='applyForm']"),
    (By.CSS_SELECTOR, "[class*='apply-form']"),
    (By.CSS_SELECTOR, "form"),
)
SUCCESS_LOCATORS = (
    (By.XPATH, "//*[contains(translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'successfully applied')]"),
    (By.XPATH, "//*[contains(translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'application submitted')]"),
    (By.XPATH, "//*[contains(translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'application sent')]"),
    (By.CSS_SELECTOR, ".toast-success, [class*='successToast'], [data-testid='application-success']"),
)


class FounditBot(BaseBot):
    PLATFORM = "foundit"

    def login(self) -> None:
        assert self.driver is not None
        self.driver.get("https://www.foundit.in/seeker/profile")
        human_delay(self.config.slow_mo, 2.0)
        if "login" not in self.driver.current_url.lower() and "rio" not in self.driver.current_url.lower():
            return
        email, password = self.credential("email"), self.credential("password")
        if not email or not password:
            raise RuntimeError("Foundit login is required; configure FOUNDIT_EMAIL and FOUNDIT_PASSWORD or a logged-in Chrome profile")
        self.driver.get("https://www.foundit.in/rio/login")
        email_field = wait_for_first(
            self.driver,
            (
                (By.CSS_SELECTOR, "input[type='email']"),
                (By.CSS_SELECTOR, "input[type='text'][name*='email']"),
                (By.ID, "signInName"),
                (By.NAME, "username"),
            ),
            timeout=15,
        )
        email_field.clear()
        human_type(email_field, email, self.config.slow_mo)
        password_field = find_first(
            self.driver,
            ((By.CSS_SELECTOR, "input[type='password']"), (By.NAME, "password")),
            visible=True,
        )
        if not password_field:
            continue_button = find_first(
                self.driver,
                ((By.CSS_SELECTOR, "button[type='submit']"), (By.XPATH, "//button[contains(., 'Continue')]")),
                visible=True,
            )
            if continue_button:
                safe_click(self.driver, continue_button)
            password_field = wait_for_first(
                self.driver,
                ((By.CSS_SELECTOR, "input[type='password']"), (By.NAME, "password")),
                timeout=15,
            )
        password_field.clear()
        human_type(password_field, password, self.config.slow_mo)
        submit = wait_for_first(
            self.driver,
            ((By.CSS_SELECTOR, "button[type='submit']"), (By.XPATH, "//button[contains(., 'Login') or contains(., 'Sign in')]")),
            timeout=10,
            clickable=True,
        )
        safe_click(self.driver, submit)
        try:
            WebDriverWait(self.driver, 20).until(lambda driver: "login" not in driver.current_url.lower())
        except TimeoutException as error:
            raise RuntimeError("Foundit login did not complete; verify credentials or reuse a verified Chrome profile") from error

    def search_url(self, keyword: str, location: str, page: int) -> str:
        parameters: dict[str, object] = {
            "query": keyword,
            "locations": location,
            "time": int(self.config.filters.get("timeFilter", 1)),
            "page": page,
        }
        if self.config.filters.get("remoteOnly", False):
            parameters["workFromHome"] = "true"
        return "https://www.foundit.in/srp/results?" + urlencode(parameters)

    def card_job(self, card: object) -> JobInfo:
        url = attribute_of(card, CARD_TITLE, "href")
        if url.startswith("/"):
            url = "https://www.foundit.in" + url
        return JobInfo(
            text_of(card, CARD_TITLE, "Unknown Foundit role"),
            text_of(card, ((By.CSS_SELECTOR, ".companyName"), (By.CSS_SELECTOR, "[class*='company']"))),
            text_of(card, ((By.CSS_SELECTOR, ".location"), (By.CSS_SELECTOR, "[class*='location']"))),
            url,
        )

    def detail_job(self, fallback: JobInfo) -> JobInfo:
        assert self.driver is not None
        return JobInfo(
            text_of(self.driver, ((By.CSS_SELECTOR, "h1"), (By.CSS_SELECTOR, "[class*='jobTitle']")), fallback.title),
            text_of(self.driver, ((By.CSS_SELECTOR, "[class*='companyName']"), (By.CSS_SELECTOR, "[class*='company-name']")), fallback.company),
            text_of(self.driver, ((By.CSS_SELECTOR, "[class*='location']"),), fallback.location),
            fallback.url or self.driver.current_url,
        )

    def attempt(self, card: object, initial: JobInfo) -> tuple[JobInfo, AttemptOutcome]:
        assert self.driver is not None and self.form_filler is not None
        job = initial
        try:
            safe_click(self.driver, card)  # type: ignore[arg-type]
            human_delay(self.config.slow_mo, 1.5)
            job = self.detail_job(initial)
            self.set_form_context(job)
            try:
                apply_button = wait_for_first(
                    self.driver,
                    (
                        (By.CSS_SELECTOR, "button[class*='apply']"),
                        (By.CSS_SELECTOR, "[class*='applyBtn']"),
                        (By.XPATH, "//button[contains(normalize-space(.), 'Apply')]"),
                    ),
                    timeout=8,
                    clickable=True,
                )
            except TimeoutException:
                return job, AttemptOutcome.skipped("Foundit Apply button was unavailable")
            initial_text = (apply_button.text or "").strip().lower()
            if "applied" in initial_text:
                return job, AttemptOutcome.skipped("already applied")
            safe_click(self.driver, apply_button)
            human_delay(self.config.slow_mo, 1.5)
            if wait_for_confirmation(self.driver, SUCCESS_LOCATORS, timeout=4):
                return job, AttemptOutcome.applied("submission confirmed")
            try:
                current_text = (apply_button.text or "").strip().lower()
                if current_text == "applied" or "already applied" in current_text:
                    return job, AttemptOutcome.applied("Apply control changed to Applied")
            except Exception:
                pass
            if not find_first(self.driver, FORM_ROOTS, visible=True):
                return job, AttemptOutcome.failed("Apply was clicked but no success confirmation or application form appeared")
            success, notes = complete_multistep_form(
                self.driver,
                self.form_filler,
                success_locators=SUCCESS_LOCATORS,
                form_roots=FORM_ROOTS,
                max_steps=self.config.max_form_steps,
                slow_mo=self.config.slow_mo,
                submit_terms=("Submit application", "Submit", "Apply now"),
                next_terms=("Continue", "Next", "Review", "Save and continue"),
            )
            return job, AttemptOutcome.applied(notes) if success else AttemptOutcome.failed(notes)
        except TimeoutException:
            return job, AttemptOutcome.failed("Foundit application timed out")
        except Exception as error:
            return job, AttemptOutcome.failed(f"application interaction failed: {type(error).__name__}")

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
                    self.driver.execute_script("window.scrollBy(0, 900);")
                    try:
                        cards = wait_for_any_elements(self.driver, CARD_LOCATORS, timeout=12)
                    except TimeoutException:
                        break
                    for card in cards:
                        if self.at_limit():
                            return
                        initial = self.card_job(card)
                        if self.is_duplicate(initial):
                            continue
                        if not self.is_relevant(initial):
                            self.record(initial, AttemptOutcome.skipped("excluded by platform filter"))
                            continue
                        job, outcome = self.attempt(card, initial)
                        self.record(job, outcome)
                        human_delay(self.config.slow_mo, 1.0)


def run(config: AutomationConfig | None = None) -> BotResult:
    return FounditBot(config).run()


def main() -> int:
    return 0 if run().ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
