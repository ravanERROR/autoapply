"""Common application-form discovery and safe field filling with deep ATS support."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

from selenium.common.exceptions import ElementNotInteractableException, StaleElementReferenceException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select, WebDriverWait

from .answers import AnswerEngine
from .alerts import play_notification_sound, show_visual_alert
from .delays import human_delay, human_type
from .paths import APP_ROOT, resolve_app_path
from .selectors import (
    COMMON_BUTTON_LOCATORS,
    COMMON_CHECKBOX_LOCATORS,
    COMMON_DROPDOWN_LOCATORS,
    COMMON_FILE_UPLOAD_LOCATORS,
    COMMON_INPUT_LOCATORS,
    COMMON_LABEL_PATTERNS,
    COMMON_RADIO_GROUP_LOCATORS,
    Locator,
    find_all_fallback,
    find_button_by_text,
    find_first,
    safe_click,
)


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
        """Fill a select element (standard or custom dropdown)."""
        try:
            # Try standard HTML select
            select = Select(field)
            options = [option.text.strip() for option in select.options if option.text.strip()]
            answer = self.answers.answer(question, options=options, context=self.context)
            for option in select.options:
                if option.text.strip() == answer:
                    select.select_by_visible_text(option.text)
                    return True
        except Exception:
            # Handle custom dropdowns (div-based)
            pass
        return False

    def _fill_custom_dropdown(self, dropdown: Any, question: str) -> bool:
        """Handle custom dropdown components (React Select, etc.)."""
        try:
            # Click to open dropdown
            safe_click(self.driver, dropdown)
            human_delay(self.slow_mo, 0.5)
            
            # Find options in the opened dropdown
            option_locators = (
                (By.CSS_SELECTOR, "[role='option']"),
                (By.CSS_SELECTOR, ".react-select__option, .select-option"),
                (By.CSS_SELECTOR, "li[class*='option'], div[class*='option']"),
            )
            options = find_all_fallback(self.driver, option_locators, visible=True)
            
            if not options:
                return False
            
            option_texts = [opt.text.strip() for opt in options if opt.text.strip()]
            answer = self.answers.answer(question, options=option_texts, context=self.context)
            
            # Click the matching option
            for opt, text in zip(options, option_texts):
                if text == answer:
                    safe_click(self.driver, opt)
                    return True
            
            # Fallback: click first option
            if options:
                safe_click(self.driver, options[0])
                return True
        except Exception:
            pass
        return False

    def _fill_radios(self, root: Any) -> int:
        """Fill radio button groups with enhanced ATS support."""
        filled = 0
        groups: dict[str, list[Any]] = {}
        
        # Try multiple locator strategies for radio buttons
        all_radios = []
        for locators in [COMMON_RADIO_GROUP_LOCATORS, ((By.CSS_SELECTOR, "input[type='radio']"),)]:
            radios = find_all_fallback(root, locators)
            all_radios.extend(radios)
        
        # Remove duplicates by element ID
        seen_ids = set()
        unique_radios = []
        for radio in all_radios:
            try:
                elem_id = radio.get_attribute("id") or id(radio)
                if elem_id not in seen_ids and radio.is_enabled():
                    seen_ids.add(elem_id)
                    unique_radios.append(radio)
            except Exception:
                continue
        
        for index, radio in enumerate(unique_radios):
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

    def _fill_checkboxes(self, root: Any) -> int:
        """Fill checkbox elements with enhanced ATS support."""
        filled = 0
        
        # Try multiple locator strategies
        all_checkboxes = []
        for locators in [COMMON_CHECKBOX_LOCATORS, ((By.CSS_SELECTOR, "input[type='checkbox']"),)]:
            checkboxes = find_all_fallback(root, locators)
            all_checkboxes.extend(checkboxes)
        
        # Remove duplicates
        seen_ids = set()
        unique_checkboxes = []
        for cb in all_checkboxes:
            try:
                elem_id = cb.get_attribute("id") or id(cb)
                if elem_id not in seen_ids and cb.is_enabled() and cb.is_displayed():
                    seen_ids.add(elem_id)
                    unique_checkboxes.append(cb)
            except Exception:
                continue
        
        for checkbox in unique_checkboxes:
            try:
                if checkbox.is_selected():
                    continue
                
                question = self._question_text(checkbox)
                answer = self.answers.answer(question, options=("Yes", "No"), context=self.context)
                required = checkbox.get_attribute("required") is not None or checkbox.get_attribute("aria-required") == "true"
                
                if required or answer.lower().startswith("yes"):
                    safe_click(self.driver, checkbox)
                    filled += 1
            except (ElementNotInteractableException, StaleElementReferenceException):
                continue
            except Exception:
                continue
        
        return filled

    def _handle_file_upload(self, field: Any, resume_path: Path | None) -> bool:
        """Handle file upload fields including drop zones."""
        if not resume_path:
            return False
        
        try:
            # Standard file input
            if field.tag_name.lower() == "input" and (field.get_attribute("type") or "").lower() == "file":
                if not (field.get_attribute("value") or "").strip():
                    field.send_keys(str(resume_path))
                    return True
        except Exception:
            pass
        
        # Try to find and click drop zone to trigger file dialog
        try:
            drop_zones = find_all_fallback(self.driver, COMMON_FILE_UPLOAD_LOCATORS, visible=True)
            for zone in drop_zones:
                try:
                    # Some drop zones accept send_keys directly
                    zone.send_keys(str(resume_path))
                    return True
                except Exception:
                    continue
        except Exception:
            pass
        
        return False

    def fill(self, root: Any | None = None) -> int:
        """Fill all form fields with comprehensive ATS support."""
        search_root = root or self.driver
        filled = 0
        
        # Fill radio groups first
        filled += self._fill_radios(search_root)
        
        # Fill checkboxes
        filled += self._fill_checkboxes(search_root)
        
        # Get resume path for file uploads
        resume_path = self._resume_path()
        
        # Process all input types using comprehensive locators
        processed_elements = set()
        
        for locators in [COMMON_INPUT_LOCATORS, COMMON_DROPDOWN_LOCATORS, COMMON_FILE_UPLOAD_LOCATORS]:
            try:
                fields = find_all_fallback(search_root, locators)
            except Exception:
                continue
            
            for field in fields:
                try:
                    # Skip already processed elements
                    elem_id = field.get_attribute("id") or field.get_attribute("name") or id(field)
                    if elem_id in processed_elements:
                        continue
                    processed_elements.add(elem_id)
                    
                    tag = field.tag_name.lower()
                    field_type = (field.get_attribute("type") or "").lower()
                    
                    # Skip non-interactable types
                    if field_type in _SKIP_INPUT_TYPES or not field.is_enabled():
                        continue
                    
                    # Skip hidden elements (but allow file inputs that may be styled)
                    if field_type != "file" and not field.is_displayed():
                        continue
                    
                    # Handle file uploads
                    if field_type == "file":
                        if self._handle_file_upload(field, resume_path):
                            filled += 1
                        continue
                    
                    # Get question/label text
                    question = self._question_text(field)
                    
                    # Handle selects (standard HTML)
                    if tag == "select":
                        if self._fill_select(field, question):
                            filled += 1
                        continue
                    
                    # Handle custom dropdowns (div-based)
                    if tag == "div" and ("select" in field.get_attribute("class") or 
                                        field.get_attribute("role") in ["listbox", "combobox"]):
                        if self._fill_custom_dropdown(field, question):
                            filled += 1
                        continue
                    
                    # Handle checkboxes (already handled above, but double-check)
                    if field_type == "checkbox":
                        if field.is_selected():
                            continue
                        answer = self.answers.answer(question, options=("Yes", "No"), context=self.context)
                        required = field.get_attribute("required") is not None or field.get_attribute("aria-required") == "true"
                        if required or answer.lower().startswith("yes"):
                            safe_click(self.driver, field)
                            filled += 1
                        continue
                    
                    # Skip if already has value
                    existing = field.get_attribute("value") if tag != "div" else field.text
                    if existing and str(existing).strip():
                        continue
                    
                    # Get answer from engine
                    answer = self.answers.answer(question, context=self.context)
                    
                    # Validate numeric fields
                    if field_type in {"number", "range"} and not answer.replace(".", "", 1).isdigit():
                        answer = "0"
                    
                    # Validate email fields
                    if field_type == "email" and "@" not in answer:
                        fallback_email = os.getenv("CANDIDATE_EMAIL") or _nested_profile_value(self.profile, ("email",))
                        if fallback_email:
                            answer = fallback_email
                    
                    # Clear and type
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
