"""Glassdoor Easy Apply automation using the shared JobApply contract."""

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
    (By.CSS_SELECTOR, "li[data-test='jobListing']"),
    (By.CSS_SELECTOR, "[data-test='jobListing']"),
    (By.CSS_SELECTOR, "li[class*='JobsList_jobListItem']"),
    (By.CSS_SELECTOR, "div[class*='JobCard_jobCard']"),
)
CARD_TITLE = (
    (By.CSS_SELECTOR, "a[data-test='job-title']"),
    (By.CSS_SELECTOR, "[class*='JobCard_jobTitle']"),
    (By.CSS_SELECTOR, "a[href*='/job-listing/']"),
)
FORM_ROOTS = (
    (By.CSS_SELECTOR, "[role='dialog']"),
    (By.CSS_SELECTOR, "[class*='EasyApply']"),
    (By.CSS_SELECTOR, "form"),
)
SUCCESS_LOCATORS = (
    (By.XPATH, "//*[contains(translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'application submitted')]"),
    (By.XPATH, "//*[contains(translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'application was sent')]"),
    (By.XPATH, "//*[contains(translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'successfully applied')]"),
    (By.CSS_SELECTOR, "[data-test='application-success']"),
)


class GlassdoorBot(BaseBot):
    PLATFORM = "glassdoor"

    @property
    def domain(self) -> str:
        return str(self.config.filters.get("domain", "www.glassdoor.co.in")).strip()

    def login(self) -> None:
        assert self.driver is not None
        self.driver.get(f"https://{self.domain}/member/home/index.htm")
        human_delay(self.config.slow_mo, 2.0)
        email_field = find_first(
            self.driver,
            ((By.ID, "inlineUserEmail"), (By.CSS_SELECTOR, "input[type='email']"), (By.NAME, "username")),
            visible=True,
        )
        if not email_field and "login" not in self.driver.current_url.lower():
            return
        email, password = self.credential("email"), self.credential("password")
        if not email or not password:
            raise RuntimeError("Glassdoor login is required; configure GLASSDOOR_EMAIL and GLASSDOOR_PASSWORD or a logged-in Chrome profile")
        if not email_field:
            self.driver.get(f"https://{self.domain}/profile/login_input.htm")
            email_field = wait_for_first(
                self.driver,
                ((By.ID, "inlineUserEmail"), (By.CSS_SELECTOR, "input[type='email']"), (By.NAME, "username")),
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
            ((By.CSS_SELECTOR, "input[type='password']"), (By.NAME, "password")),
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
            WebDriverWait(self.driver, 20).until(
                lambda driver: not find_first(driver, ((By.CSS_SELECTOR, "input[type='password']"),), visible=True)
            )
        except TimeoutException as error:
            raise RuntimeError("Glassdoor login did not complete; verify credentials or reuse a verified Chrome profile") from error

    def search_url(self, keyword: str, location: str, page: int) -> str:
        parameters: dict[str, object] = {
            "sc.keyword": keyword,
            "locKeyword": location,
            "fromAge": int(self.config.filters.get("postedWithinDays", 7)),
            "sortBy": "date_desc",
            "p": page,
        }
        if self.config.filters.get("remoteOnly", False):
            parameters["remoteWorkType"] = 1
        return f"https://{self.domain}/Job/jobs.htm?" + urlencode(parameters)

    def card_job(self, card: object) -> JobInfo:
        url = attribute_of(card, CARD_TITLE, "href")
        if url.startswith("/"):
            url = f"https://{self.domain}{url}"
        return JobInfo(
            text_of(card, CARD_TITLE, "Unknown Glassdoor role"),
            text_of(card, ((By.CSS_SELECTOR, "[data-test='employer-name']"), (By.CSS_SELECTOR, "[class*='EmployerProfile_employerName']"), (By.CSS_SELECTOR, "[class*='JobCard_companyName']"))),
            text_of(card, ((By.CSS_SELECTOR, "[data-test='emp-location']"), (By.CSS_SELECTOR, "[class*='JobCard_location']"))),
            url,
        )

    def detail_job(self, fallback: JobInfo) -> JobInfo:
        assert self.driver is not None
        return JobInfo(
            text_of(self.driver, ((By.CSS_SELECTOR, "[data-test='job-title']"), (By.CSS_SELECTOR, "h1")), fallback.title),
            text_of(self.driver, ((By.CSS_SELECTOR, "[data-test='employer-name']"), (By.CSS_SELECTOR, "[class*='EmployerProfile_employerName']")), fallback.company),
            text_of(self.driver, ((By.CSS_SELECTOR, "[data-test='location']"), (By.CSS_SELECTOR, "[class*='JobDetails_location']")), fallback.location),
            fallback.url or self.driver.current_url,
        )

    def attempt(self, card: object, initial: JobInfo) -> tuple[JobInfo, AttemptOutcome]:
        assert self.driver is not None and self.form_filler is not None
        original_handle = self.driver.current_window_handle
        handles_before = set(self.driver.window_handles)
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
                        (By.CSS_SELECTOR, "button[data-test='easyApply']"),
                        (By.CSS_SELECTOR, "button[class*='EasyApplyButton']"),
                        (By.XPATH, "//button[contains(normalize-space(.), 'Easy Apply')]"),
                    ),
                    timeout=8,
                    clickable=True,
                )
            except TimeoutException:
                return job, AttemptOutcome.skipped("Glassdoor Easy Apply is unavailable")
            safe_click(self.driver, apply_button)
            human_delay(self.config.slow_mo, 2.0)
            new_handles = [handle for handle in self.driver.window_handles if handle not in handles_before]
            if new_handles:
                opened_handle = new_handles[-1]
                self.driver.switch_to.window(opened_handle)
                if self.domain not in self.driver.current_url:
                    return job, AttemptOutcome.skipped("application redirects to an external employer site")
            success, notes = complete_multistep_form(
                self.driver,
                self.form_filler,
                success_locators=SUCCESS_LOCATORS,
                form_roots=FORM_ROOTS,
                max_steps=self.config.max_form_steps,
                slow_mo=self.config.slow_mo,
                submit_terms=("Submit application", "Submit"),
                next_terms=("Continue", "Next", "Review application", "Review"),
            )
            return job, AttemptOutcome.applied(notes) if success else AttemptOutcome.failed(notes)
        except TimeoutException:
            return job, AttemptOutcome.failed("Glassdoor application timed out")
        except Exception as error:
            return job, AttemptOutcome.failed(f"application interaction failed: {type(error).__name__}")
        finally:
            try:
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
                for page in range(1, self.config.max_pages + 1):
                    if self.at_limit():
                        return
                    self.driver.get(self.search_url(keyword, location, page))
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
    return GlassdoorBot(config).run()


def main() -> int:
    return 0 if run().ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
