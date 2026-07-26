"""LinkedIn Easy Apply automation using the shared JobApply contract."""

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
    find_all_fallback,
    find_button_by_text,
    find_first,
    safe_click,
    text_of,
    wait_for_any_elements,
    wait_for_first,
)
from bots.common.workflow import complete_multistep_form


CARD_LOCATORS = (
    (By.CSS_SELECTOR, "li.jobs-search-results__list-item"),
    (By.CSS_SELECTOR, ".job-card-container"),
    (By.CSS_SELECTOR, "[data-job-id]"),
)
TITLE_LOCATORS = (
    (By.CSS_SELECTOR, "a.job-card-list__title--link"),
    (By.CSS_SELECTOR, "a.job-card-container__link"),
    (By.CSS_SELECTOR, ".job-card-list__title"),
)
DETAIL_TITLE = (
    (By.CSS_SELECTOR, ".job-details-jobs-unified-top-card__job-title h1"),
    (By.CSS_SELECTOR, ".jobs-unified-top-card__job-title"),
    (By.CSS_SELECTOR, "h1"),
)
SUCCESS_LOCATORS = (
    (By.XPATH, "//*[contains(translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'application sent')]"),
    (By.XPATH, "//*[contains(translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'application was sent')]"),
    (By.CSS_SELECTOR, ".artdeco-toast-item--success"),
)
FORM_ROOTS = (
    (By.CSS_SELECTOR, ".jobs-easy-apply-modal"),
    (By.CSS_SELECTOR, "[role='dialog']"),
)


class LinkedInBot(BaseBot):
    PLATFORM = "linkedin"

    def login(self) -> None:
        assert self.driver is not None
        self.driver.get("https://www.linkedin.com/feed/")
        human_delay(self.config.slow_mo, 2.0)
        current = self.driver.current_url.lower()
        if "/feed" in current and "/login" not in current and "/checkpoint" not in current:
            return

        email, password = self.credential("email"), self.credential("password")
        if not email or not password:
            raise RuntimeError("LinkedIn login is required; configure LINKEDIN_EMAIL and LINKEDIN_PASSWORD or a logged-in Chrome profile")
        self.driver.get("https://www.linkedin.com/login")
        username = wait_for_first(self.driver, ((By.ID, "username"), (By.NAME, "session_key")), timeout=15)
        password_field = wait_for_first(self.driver, ((By.ID, "password"), (By.NAME, "session_password")), timeout=15)
        username.clear()
        human_type(username, email, self.config.slow_mo)
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
            WebDriverWait(self.driver, 20).until(lambda driver: "/login" not in driver.current_url.lower())
        except TimeoutException as error:
            raise RuntimeError("LinkedIn did not leave the login page; verify credentials or complete account verification") from error
        if "/checkpoint" in self.driver.current_url.lower():
            raise RuntimeError("LinkedIn requires an interactive checkpoint; complete it in a reusable Chrome profile")

    def search_url(self, keyword: str, location: str) -> str:
        parameters = {
            "keywords": keyword,
            "location": location,
            "f_TPR": f"r{int(self.config.filters.get('postedWithinDays', 7)) * 86400}",
            "sortBy": "DD",
        }
        if self.config.filters.get("easyApplyOnly", True):
            parameters["f_AL"] = "true"
        if self.config.filters.get("remoteOnly", False):
            parameters["f_WT"] = "2"
        return "https://www.linkedin.com/jobs/search/?" + urlencode(parameters)

    def card_job(self, card: object) -> JobInfo:
        title = text_of(card, TITLE_LOCATORS, "Unknown LinkedIn role")
        company = text_of(
            card,
            (
                (By.CSS_SELECTOR, ".artdeco-entity-lockup__subtitle"),
                (By.CSS_SELECTOR, ".job-card-container__primary-description"),
            ),
        )
        location = text_of(
            card,
            ((By.CSS_SELECTOR, ".job-card-container__metadata-item"), (By.CSS_SELECTOR, ".artdeco-entity-lockup__caption")),
        )
        url = attribute_of(card, TITLE_LOCATORS, "href")
        return JobInfo(title, company, location, url)

    def detail_job(self, fallback: JobInfo) -> JobInfo:
        assert self.driver is not None
        title = text_of(self.driver, DETAIL_TITLE, fallback.title)
        company = text_of(
            self.driver,
            (
                (By.CSS_SELECTOR, ".job-details-jobs-unified-top-card__company-name"),
                (By.CSS_SELECTOR, ".jobs-unified-top-card__company-name"),
            ),
            fallback.company,
        )
        location = text_of(
            self.driver,
            (
                (By.CSS_SELECTOR, ".job-details-jobs-unified-top-card__tertiary-description-container"),
                (By.CSS_SELECTOR, ".jobs-unified-top-card__bullet"),
            ),
            fallback.location,
        )
        return JobInfo(title, company, location, fallback.url or self.driver.current_url)

    def close_modal(self) -> None:
        assert self.driver is not None
        dismiss = find_first(
            self.driver,
            (
                (By.CSS_SELECTOR, "button[aria-label='Dismiss']"),
                (By.CSS_SELECTOR, "button[aria-label='Cancel']"),
                (By.CSS_SELECTOR, "[role='dialog'] button.artdeco-modal__dismiss"),
            ),
            visible=True,
        )
        if dismiss:
            try:
                safe_click(self.driver, dismiss)
                discard = find_button_by_text(self.driver, ("Discard", "Discard application"), timeout=1)
                if discard:
                    safe_click(self.driver, discard)
            except Exception:
                pass

    def attempt(self, card: object, initial: JobInfo) -> tuple[JobInfo, AttemptOutcome]:
        assert self.driver is not None and self.form_filler is not None
        try:
            safe_click(self.driver, card)  # type: ignore[arg-type]
            human_delay(self.config.slow_mo, 1.5)
            wait_for_first(self.driver, DETAIL_TITLE, timeout=10)
            job = self.detail_job(initial)
            self.set_form_context(job)
            if confirmation_present(
                self.driver,
                ((By.XPATH, "//*[contains(translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'already applied')]") ,),
            ):
                return job, AttemptOutcome.skipped("already applied")
            try:
                apply_button = wait_for_first(
                    self.driver,
                    (
                        (By.CSS_SELECTOR, "button.jobs-apply-button[aria-label*='Easy Apply']"),
                        (By.CSS_SELECTOR, ".jobs-s-apply button"),
                        (By.XPATH, "//button[contains(normalize-space(.), 'Easy Apply')]"),
                    ),
                    timeout=8,
                    clickable=True,
                )
            except TimeoutException:
                return job, AttemptOutcome.skipped("LinkedIn Easy Apply is unavailable")
            if "easy apply" not in (apply_button.text or apply_button.get_attribute("aria-label") or "").lower():
                return job, AttemptOutcome.skipped("LinkedIn Easy Apply is unavailable")
            safe_click(self.driver, apply_button)
            wait_for_first(self.driver, FORM_ROOTS, timeout=10)
            success, notes = complete_multistep_form(
                self.driver,
                self.form_filler,
                success_locators=SUCCESS_LOCATORS,
                form_roots=FORM_ROOTS,
                max_steps=self.config.max_form_steps,
                slow_mo=self.config.slow_mo,
                submit_terms=("Submit application", "Submit"),
                next_terms=("Continue to next step", "Next", "Review your application", "Review"),
            )
            if success:
                return job, AttemptOutcome.applied(notes)
            self.close_modal()
            return job, AttemptOutcome.failed(notes)
        except TimeoutException:
            self.close_modal()
            return initial, AttemptOutcome.failed("LinkedIn job detail or application form timed out")
        except Exception as error:
            self.close_modal()
            return initial, AttemptOutcome.failed(f"application interaction failed: {type(error).__name__}")

    def execute(self) -> None:
        assert self.driver is not None
        self.login()
        for keyword in self.config.keywords:
            for location in self.config.locations:
                self.driver.get(self.search_url(keyword, location))
                human_delay(self.config.slow_mo, 2.5)
                for page in range(1, self.config.max_pages + 1):
                    if self.at_limit():
                        return
                    try:
                        cards = wait_for_any_elements(self.driver, CARD_LOCATORS, timeout=12)
                    except TimeoutException:
                        break
                    self.driver.execute_script(
                        "document.querySelector('.jobs-search-results-list')?.scrollBy(0, 1000);"
                    )
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
                    if page >= self.config.max_pages:
                        break
                    next_page = find_first(
                        self.driver,
                        ((By.CSS_SELECTOR, "button[aria-label='View next page']"), (By.XPATH, "//button[contains(@aria-label, 'next page')]")),
                        visible=True,
                    )
                    if not next_page or not next_page.is_enabled():
                        break
                    safe_click(self.driver, next_page)
                    human_delay(self.config.slow_mo, 2.0)


def run(config: AutomationConfig | None = None) -> BotResult:
    return LinkedInBot(config).run()


def main() -> int:
    return 0 if run().ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
