"""Indeed Apply automation using explicit waits and bounded form traversal."""

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
    find_first,
    safe_click,
    text_of,
    wait_for_any_elements,
    wait_for_first,
)
from bots.common.workflow import complete_multistep_form


CARD_LOCATORS = (
    (By.CSS_SELECTOR, ".job_seen_beacon"),
    (By.CSS_SELECTOR, "li[data-testid='slider_item']"),
    (By.CSS_SELECTOR, "div.cardOutline"),
)
CARD_TITLE = (
    (By.CSS_SELECTOR, "h2.jobTitle a"),
    (By.CSS_SELECTOR, "a[data-jk]"),
    (By.CSS_SELECTOR, "a.jcs-JobTitle"),
)
FORM_ROOTS = (
    (By.CSS_SELECTOR, "main"),
    (By.CSS_SELECTOR, "[role='dialog']"),
    (By.CSS_SELECTOR, ".ia-ApplyFormScreen"),
)
SUCCESS_LOCATORS = (
    (By.XPATH, "//*[contains(translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'application submitted')]"),
    (By.XPATH, "//*[contains(translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'application has been submitted')]"),
    (By.XPATH, "//*[contains(translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'your application was sent')]"),
    (By.CSS_SELECTOR, "[data-testid='application-submitted']"),
)


class IndeedBot(BaseBot):
    PLATFORM = "indeed"

    @property
    def domain(self) -> str:
        return str(self.config.filters.get("domain", "in.indeed.com")).strip()

    def login(self) -> None:
        assert self.driver is not None
        self.driver.get("https://secure.indeed.com/account/view")
        human_delay(self.config.slow_mo, 2.0)
        if "auth" not in self.driver.current_url.lower() and "login" not in self.driver.current_url.lower():
            return
        email, password = self.credential("email"), self.credential("password")
        if not email or not password:
            raise RuntimeError("Indeed login is required; configure INDEED_EMAIL and INDEED_PASSWORD or a logged-in Chrome profile")
        email_field = wait_for_first(
            self.driver,
            (
                (By.ID, "ifl-InputFormField-3"),
                (By.CSS_SELECTOR, "input[type='email']"),
                (By.NAME, "__email"),
            ),
            timeout=15,
        )
        email_field.clear()
        human_type(email_field, email, self.config.slow_mo)
        continue_button = find_first(
            self.driver,
            ((By.CSS_SELECTOR, "button[type='submit']"), (By.XPATH, "//button[contains(., 'Continue')]")),
            visible=True,
        )
        if continue_button:
            safe_click(self.driver, continue_button)
        password_field = wait_for_first(
            self.driver,
            ((By.CSS_SELECTOR, "input[type='password']"), (By.NAME, "__password")),
            timeout=15,
        )
        password_field.clear()
        human_type(password_field, password, self.config.slow_mo)
        submit = wait_for_first(
            self.driver,
            ((By.CSS_SELECTOR, "button[type='submit']"), (By.XPATH, "//button[contains(., 'Sign in')]")),
            timeout=10,
            clickable=True,
        )
        safe_click(self.driver, submit)
        try:
            WebDriverWait(self.driver, 20).until(lambda driver: "auth" not in driver.current_url.lower())
        except TimeoutException as error:
            raise RuntimeError("Indeed login requires additional verification; complete it in a reusable Chrome profile") from error

    def search_url(self, keyword: str, location: str, start: int = 0) -> str:
        parameters: dict[str, object] = {
            "q": keyword,
            "l": location,
            "fromage": int(self.config.filters.get("postedWithinDays", 7)),
            "sort": "date",
            "start": start,
        }
        if self.config.filters.get("remoteOnly", False):
            parameters["sc"] = "0kf:attr(DSQF7);"
        return f"https://{self.domain}/jobs?" + urlencode(parameters)

    def card_job(self, card: object) -> JobInfo:
        return JobInfo(
            text_of(card, CARD_TITLE, "Unknown Indeed role"),
            text_of(card, ((By.CSS_SELECTOR, "[data-testid='company-name']"), (By.CSS_SELECTOR, ".companyName"))),
            text_of(card, ((By.CSS_SELECTOR, "[data-testid='text-location']"), (By.CSS_SELECTOR, ".companyLocation"))),
            attribute_of(card, CARD_TITLE, "href"),
        )

    def detail_job(self, fallback: JobInfo) -> JobInfo:
        assert self.driver is not None
        url = fallback.url
        if url.startswith("/"):
            url = f"https://{self.domain}{url}"
        return JobInfo(
            text_of(self.driver, ((By.CSS_SELECTOR, "h1.jobsearch-JobInfoHeader-title"), (By.CSS_SELECTOR, "h1")), fallback.title),
            text_of(self.driver, ((By.CSS_SELECTOR, "[data-testid='inlineHeader-companyName']"), (By.CSS_SELECTOR, ".jobsearch-InlineCompanyRating")), fallback.company),
            text_of(self.driver, ((By.CSS_SELECTOR, "[data-testid='job-location']"), (By.CSS_SELECTOR, ".jobsearch-JobInfoHeader-subtitle div")), fallback.location),
            url or self.driver.current_url,
        )

    def attempt(self, card: object, initial: JobInfo) -> tuple[JobInfo, AttemptOutcome]:
        assert self.driver is not None and self.form_filler is not None
        original_handle = self.driver.current_window_handle
        handles_before = set(self.driver.window_handles)
        entered_frame = False
        opened_handle: str | None = None
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
                        (By.ID, "indeedApplyButton"),
                        (By.CSS_SELECTOR, "button[id*='indeedApply']"),
                        (By.CSS_SELECTOR, ".ia-IndeedApplyButton"),
                        (By.CSS_SELECTOR, "button.jobsearch-IndeedApplyButton-newDesign"),
                    ),
                    timeout=8,
                    clickable=True,
                )
            except TimeoutException:
                return job, AttemptOutcome.skipped("Indeed Apply is unavailable or redirects externally")
            safe_click(self.driver, apply_button)
            human_delay(self.config.slow_mo, 2.5)
            new_handles = [handle for handle in self.driver.window_handles if handle not in handles_before]
            if new_handles:
                opened_handle = new_handles[-1]
                self.driver.switch_to.window(opened_handle)
                human_delay(self.config.slow_mo, 1.5)
            elif "smartapply" not in self.driver.current_url.lower():
                frame = find_first(
                    self.driver,
                    (
                        (By.CSS_SELECTOR, "iframe[title*='Indeed']"),
                        (By.CSS_SELECTOR, "iframe[name*='indeedapply']"),
                        (By.CSS_SELECTOR, "iframe[src*='smartapply']"),
                    ),
                )
                if frame:
                    self.driver.switch_to.frame(frame)
                    entered_frame = True
            success, notes = complete_multistep_form(
                self.driver,
                self.form_filler,
                success_locators=SUCCESS_LOCATORS,
                form_roots=FORM_ROOTS,
                max_steps=self.config.max_form_steps,
                slow_mo=self.config.slow_mo,
                submit_terms=("Submit your application", "Submit application", "Submit"),
                next_terms=("Continue", "Next", "Review your application", "Review"),
            )
            return job, AttemptOutcome.applied(notes) if success else AttemptOutcome.failed(notes)
        except TimeoutException:
            return job, AttemptOutcome.failed("Indeed application timed out")
        except Exception as error:
            return job, AttemptOutcome.failed(f"application interaction failed: {type(error).__name__}")
        finally:
            try:
                if entered_frame:
                    self.driver.switch_to.default_content()
                if opened_handle and opened_handle in self.driver.window_handles:
                    self.driver.close()
                if original_handle in self.driver.window_handles:
                    self.driver.switch_to.window(original_handle)
            except Exception:
                pass

    def execute(self) -> None:
        assert self.driver is not None
        self.login()
        for keyword in self.config.keywords:
            for location in self.config.locations:
                for page in range(self.config.max_pages):
                    if self.at_limit():
                        return
                    self.driver.get(self.search_url(keyword, location, page * 10))
                    human_delay(self.config.slow_mo, 2.0)
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
    return IndeedBot(config).run()


def main() -> int:
    return 0 if run().ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
