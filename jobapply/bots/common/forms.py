"""Common application-form discovery and safe field filling."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping, Sequence

from selenium.common.exceptions import ElementNotInteractableException, StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select

from .answers import AnswerEngine
from .delays import human_delay, human_type
from .paths import APP_ROOT, resolve_app_path
from .selectors import safe_click


_SKIP_INPUT_TYPES = {"hidden", "submit", "button", "reset", "image"}


def _nested_profile_value(profile: Mapping[str, Any], names: Sequence[str]) -> str | None:
    wanted = {name.lower().replace("_", "") for name in names}
    stack: list[Mapping[str, Any]] = [profile]
    while stack:
        current = stack.pop()
        for key, value in current.items():
            normalized = str(key).lower().replace("_", "")
            if isinstance(value, Mapping):
                stack.append(value)
            elif normalized in wanted and value and str(value).strip():
                return str(value).strip()
    return None


class FormFiller:
    def __init__(
        self,
        driver: Any,
        answer_engine: AnswerEngine,
        *,
        profile: Mapping[str, Any],
        slow_mo: int,
    ) -> None:
        self.driver = driver
        self.answers = answer_engine
        self.profile = profile
        self.slow_mo = slow_mo
        self.context: Mapping[str, Any] | str = {}

    def set_context(self, context: Mapping[str, Any] | str) -> None:
        self.context = context

    def _question_text(self, field: Any) -> str:
        for attribute in ("aria-label", "data-testid", "placeholder", "name", "id"):
            try:
                value = field.get_attribute(attribute)
                if value and str(value).strip():
                    candidate = str(value).replace("_", " ").replace("-", " ").strip()
                    if attribute in {"aria-label", "placeholder"}:
                        return candidate
            except StaleElementReferenceException:
                return "Application question"
        try:
            label = self.driver.execute_script(
                "return arguments[0].labels && arguments[0].labels.length "
                "? Array.from(arguments[0].labels).map(x => x.innerText).join(' ') : '';",
                field,
            )
            if label and str(label).strip():
                return str(label).strip()
        except Exception:
            pass
        try:
            container = field.find_element(
                By.XPATH,
                "./ancestor::*[self::fieldset or self::div or self::li][.//label or .//legend][1]",
            )
            labels = container.find_elements(By.XPATH, ".//legend | .//label | .//*[@role='heading']")
            text = " ".join(element.text for element in labels[:2] if element.text).strip()
            if text:
                return text
        except Exception:
            pass
        try:
            nearby = field.find_element(
                By.XPATH,
                "(./preceding::*[self::label or self::legend or contains(@class, 'question') "
                "or contains(@class, 'botItem')][normalize-space(.)])[last()]",
            )
            if nearby.text and nearby.text.strip():
                return nearby.text.strip()[:500]
        except Exception:
            pass
        for attribute in ("name", "id", "type"):
            try:
                value = field.get_attribute(attribute)
                if value:
                    return str(value).replace("_", " ").replace("-", " ")
            except Exception:
                pass
        return "Application question"

    @staticmethod
    def _option_text(field: Any) -> str:
        try:
            text = field.find_element(
                By.XPATH,
                "./following-sibling::label[1] | ./ancestor::label[1] | ./parent::*//label[1]",
            ).text
            if text:
                return text.strip()
        except Exception:
            pass
        return (field.get_attribute("value") or "").strip()

    def _resume_path(self) -> Path | None:
        configured = os.getenv("RESUME_PATH") or _nested_profile_value(
            self.profile,
            ("resumePath", "resume", "cvPath"),
        )
        if not configured:
            return None
        path = resolve_app_path(configured, configured, app_root=APP_ROOT)
        return path if path.is_file() else None

    def _fill_select(self, field: Any, question: str) -> bool:
        select = Select(field)
        options = [option.text.strip() for option in select.options if option.text.strip()]
        answer = self.answers.answer(question, options=options, context=self.context)
        for option in select.options:
            if option.text.strip() == answer:
                select.select_by_visible_text(option.text)
                return True
        return False

    def _fill_radios(self, root: Any) -> int:
        filled = 0
        groups: dict[str, list[Any]] = {}
        try:
            radios = root.find_elements(By.CSS_SELECTOR, "input[type='radio']")
        except Exception:
            return 0
        for index, radio in enumerate(radios):
            try:
                if not radio.is_enabled():
                    continue
                key = radio.get_attribute("name") or radio.get_attribute("aria-labelledby")
                if not key:
                    try:
                        group = radio.find_element(
                            By.XPATH,
                            "./ancestor::*[self::fieldset or @role='radiogroup' or contains(@class, 'radio')][1]",
                        )
                        key = f"group-{group.id}"
                    except Exception:
                        key = f"radio-{index}"
                groups.setdefault(key, []).append(radio)
            except StaleElementReferenceException:
                continue
        for fields in groups.values():
            if any(field.is_selected() for field in fields):
                continue
            question = self._question_text(fields[0])
            option_pairs = [(field, self._option_text(field)) for field in fields]
            option_labels = [label for _, label in option_pairs if label]
            answer = self.answers.answer(question, options=option_labels, context=self.context)
            chosen = next((field for field, label in option_pairs if label == answer), fields[0])
            try:
                safe_click(self.driver, chosen)
                filled += 1
            except Exception:
                continue
        return filled

    def fill(self, root: Any | None = None) -> int:
        search_root = root or self.driver
        filled = self._fill_radios(search_root)
        try:
            fields = search_root.find_elements(
                By.CSS_SELECTOR,
                "input:not([type='radio']), select, textarea, [contenteditable='true'], div.textArea",
            )
        except Exception:
            return filled
        resume_path = self._resume_path()
        for field in fields:
            try:
                tag = field.tag_name.lower()
                field_type = (field.get_attribute("type") or "").lower()
                if field_type in _SKIP_INPUT_TYPES or not field.is_enabled():
                    continue
                if field_type == "file":
                    if resume_path and not (field.get_attribute("value") or "").strip():
                        field.send_keys(str(resume_path))
                        filled += 1
                    continue
                if not field.is_displayed():
                    continue
                question = self._question_text(field)
                if tag == "select":
                    if self._fill_select(field, question):
                        filled += 1
                    continue
                if field_type == "checkbox":
                    if field.is_selected():
                        continue
                    answer = self.answers.answer(question, options=("Yes", "No"), context=self.context)
                    required = field.get_attribute("required") is not None or field.get_attribute("aria-required") == "true"
                    if required or answer.lower().startswith("yes"):
                        safe_click(self.driver, field)
                        filled += 1
                    continue
                existing = field.get_attribute("value") if tag != "div" else field.text
                if existing and str(existing).strip():
                    continue
                answer = self.answers.answer(question, context=self.context)
                if field_type in {"number", "range"} and not answer.replace(".", "", 1).isdigit():
                    answer = "0"
                if field_type == "email" and "@" not in answer:
                    fallback_email = os.getenv("CANDIDATE_EMAIL") or _nested_profile_value(self.profile, ("email",))
                    if fallback_email:
                        answer = fallback_email
                try:
                    field.clear()
                except Exception:
                    field.send_keys(Keys.CONTROL, "a")
                human_type(field, answer, self.slow_mo)
                human_delay(self.slow_mo, 0.3)
                filled += 1
            except (ElementNotInteractableException, StaleElementReferenceException):
                continue
            except Exception:
                continue
        return filled
