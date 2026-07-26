"""
externalapply.py

Handles company-site / external apply flows after Naukri redirects away from naukri.com.
It searches for the matching job card, clicks the company-site Apply button, fills forms
from personal.json and config/questions.json, uses AI when enabled, and stops for manual
review on login/OTP/CAPTCHA/account-creation pages.
"""

import os
import time

from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException

from naukari import (
    Config,
    log_message,
    get_exact_saved_answer,
    guess_question_answer,
    _save_answered_question,
    gemini_answer_question,
    play_notification_sound,
    prompt_topmost,
)

# ════════════════════════════════════════════════════════════════════
# EXTERNAL COMPANY-SITE APPLY SUPPORT
# ════════════════════════════════════════════════════════════════════

EXTERNAL_SUCCESS_TEXT_FRAGMENTS = [
    "application submitted",
    "application received",
    "successfully submitted",
    "thank you for applying",
    "thank you for your application",
    "we have received your application",
    "your application has been submitted",
]

EXTERNAL_STOP_TEXT_FRAGMENTS = [
    "captcha",
    "otp",
    "one-time password",
    "verify your email",
    "sign in",
    "login",
    "create an account",
]

SENSITIVE_QUESTION_KEYWORDS = [
    "gender", "race", "ethnicity", "disability", "veteran", "sexual orientation",
    "date of birth", "dob", "aadhaar", "aadhar", "pan card", "passport", "ssn",
]

FINAL_SUBMIT_WORDS = ["submit application", "submit", "apply", "send application"]
NEXT_BUTTON_WORDS = ["next", "continue", "save and continue", "proceed", "review"]
APPLY_BUTTON_WORDS = ["apply", "apply now", "apply for this job", "apply on company site", "start application"]


def _txt(el) -> str:
    try:
        return (el.text or el.get_attribute("value") or el.get_attribute("aria-label") or "").strip()
    except Exception:
        return ""


def _norm_text(s: str) -> str:
    import re
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _score_text(a: str, b: str) -> int:
    """Fuzzy score with optional rapidfuzz, fallback to stdlib."""
    a, b = _norm_text(a), _norm_text(b)
    if not a or not b:
        return 0
    try:
        from rapidfuzz import fuzz
        return int(fuzz.token_set_ratio(a, b))
    except Exception:
        from difflib import SequenceMatcher
        return int(SequenceMatcher(None, a, b).ratio() * 100)


def _is_naukri_url(url: str) -> bool:
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.lower()
        return "naukri.com" in host
    except Exception:
        return False


def wait_document_ready(driver, timeout: int = 20) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            if driver.execute_script("return document.readyState") == "complete":
                return
        except Exception:
            pass
        time.sleep(0.4)


def safe_click(driver, element, label: str = "element") -> bool:
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center', inline:'center'});", element)
        time.sleep(0.25)
    except Exception:
        pass
    try:
        element.click()
        log_message(f"Clicked {label}.")
        return True
    except Exception as e1:
        try:
            driver.execute_script("arguments[0].click();", element)
            log_message(f"Clicked {label} using JavaScript fallback.")
            return True
        except Exception as e2:
            log_message(f"[WARN] Could not click {label}: {str(e1)[:80]} | JS: {str(e2)[:80]}")
            return False


def switch_to_newest_window_or_changed_url(driver, before_handles: list, before_url: str, timeout: int = 12) -> bool:
    """After a click, switch to a new tab/window if created; otherwise detect same-tab URL change."""
    end = time.time() + timeout
    before_set = set(before_handles)
    while time.time() < end:
        try:
            handles = driver.window_handles
            new_handles = [h for h in handles if h not in before_set]
            if new_handles:
                driver.switch_to.window(new_handles[-1])
                wait_document_ready(driver, timeout=timeout)
                log_message(f"Switched to new window/tab: {driver.current_url}")
                return True
            if driver.current_url != before_url:
                wait_document_ready(driver, timeout=timeout)
                log_message(f"Detected same-tab navigation: {driver.current_url}")
                return True
        except Exception:
            pass
        time.sleep(0.4)
    return False


def find_clickable_by_words(driver, words: list[str], timeout: int = 8, visible_only: bool = True):
    """Finds a button/link/role=button whose visible text/aria/value contains any target word."""
    end = time.time() + timeout
    word_lowers = [_norm_text(w) for w in words]
    selectors = [
        "button", "a", "input[type='button']", "input[type='submit']",
        "[role='button']", "div[role='button']", "span[role='button']"
    ]
    while time.time() < end:
        candidates = []
        for css in selectors:
            try:
                candidates.extend(driver.find_elements(By.CSS_SELECTOR, css))
            except Exception:
                pass
        ranked = []
        for el in candidates:
            try:
                if visible_only and not el.is_displayed():
                    continue
                text = " ".join([
                    _txt(el),
                    el.get_attribute("aria-label") or "",
                    el.get_attribute("title") or "",
                    el.get_attribute("value") or "",
                    el.get_attribute("class") or "",
                ]).strip()
                low = _norm_text(text)
                if not low:
                    continue
                if any(w in low for w in word_lowers):
                    # Prefer exact button-ish apply/submit text over long container text.
                    length_penalty = min(len(low), 160)
                    score = 200 - length_penalty
                    if any(low == w for w in word_lowers):
                        score += 100
                    ranked.append((score, el, text))
            except StaleElementReferenceException:
                continue
            except Exception:
                continue
        if ranked:
            ranked.sort(key=lambda x: x[0], reverse=True)
            return ranked[0][1], ranked[0][2]
        time.sleep(0.5)
    return None, ""


def close_common_popups(driver) -> None:
    """Close cookie banners / popups that block apply buttons."""
    popup_words = ["accept", "accept all", "agree", "got it", "close", "no thanks", "skip"]
    for _ in range(2):
        el, text = find_clickable_by_words(driver, popup_words, timeout=1)
        if el:
            low = _norm_text(text)
            # Avoid clicking real application buttons in this generic cleanup pass.
            if "apply" not in low and "submit" not in low and "next" not in low:
                safe_click(driver, el, f"popup/cookie button '{text[:40]}'")
                time.sleep(0.5)


def click_matching_external_job_card(driver, job_title: str, company: str = "", timeout: int = 10) -> bool:
    """If company site opens a job-listing page, click the card/link matching the Naukri job title."""
    wait_document_ready(driver, timeout=timeout)
    close_common_popups(driver)

    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text[:5000]
        if _score_text(job_title, body_text) >= 85:
            # Detail page likely already loaded.
            log_message("External page already appears to contain the selected job title.")
            return True
    except Exception:
        pass

    selectors = ["a", "article", "li", "div[role='button']", "tr", "div"]
    best = None
    end = time.time() + timeout
    while time.time() < end:
        candidates = []
        for css in selectors:
            try:
                candidates.extend(driver.find_elements(By.CSS_SELECTOR, css))
            except Exception:
                pass
        for el in candidates:
            try:
                if not el.is_displayed():
                    continue
                text = _txt(el)
                if not text or len(text) < 6 or len(text) > 800:
                    continue
                title_score = _score_text(job_title, text)
                company_bonus = 5 if company and _norm_text(company) in _norm_text(text) else 0
                score = title_score + company_bonus
                if score >= 72 and (best is None or score > best[0]):
                    best = (score, el, text[:160])
            except StaleElementReferenceException:
                continue
            except Exception:
                continue
        if best:
            score, el, text = best
            before = list(driver.window_handles)
            before_url = driver.current_url
            if safe_click(driver, el, f"matching external job card score={score} text='{text[:80]}'"):
                switch_to_newest_window_or_changed_url(driver, before, before_url, timeout=8)
                wait_document_ready(driver, timeout=timeout)
                return True
        time.sleep(0.5)

    log_message("[WARN] Could not identify matching job card on external site; will try current page as-is.")
    return False


def get_label_for_field(driver, el) -> str:
    """Extract nearby label/placeholder/name/id for a form field."""
    parts = []
    try:
        for attr in ["aria-label", "placeholder", "name", "id", "title"]:
            val = el.get_attribute(attr)
            if val:
                parts.append(val)
    except Exception:
        pass
    try:
        el_id = el.get_attribute("id")
        if el_id:
            labels = driver.find_elements(By.CSS_SELECTOR, f"label[for='{el_id}']")
            parts += [_txt(l) for l in labels if _txt(l)]
    except Exception:
        pass
    try:
        # Nearest ancestor text usually contains the visible question.
        parent = el.find_element(By.XPATH, "./ancestor::*[self::label or self::div or self::fieldset][1]")
        txt = _txt(parent)
        if txt:
            parts.append(txt[:300])
    except Exception:
        pass
    return " | ".join([p.strip() for p in parts if p and p.strip()])[:500]


def answer_from_profile_or_questions(question: str, options: list[str] | None, model, config: Config,
                                     job_description: str = "", about_company: str = "") -> str | None:
    """Question priority: questions.json exact match -> profile mapping -> AI -> user prompt."""
    question = question.strip()
    q_low = _norm_text(question)
    options = options or []

    saved = get_exact_saved_answer(question)
    if saved is not None:
        return str(saved)

    # Do not hallucinate sensitive government/identity/EEO answers. Prefer official opt-out if present.
    if any(k in q_low for k in SENSITIVE_QUESTION_KEYWORDS):
        for opt in options:
            if any(x in _norm_text(opt) for x in ["prefer not", "do not wish", "decline", "not disclose", "choose not"]):
                _save_answered_question(question, opt)
                return opt
        if config.non_interactive:
            log_message(f"[WARN] Sensitive question needs manual answer, skipping auto-answer: {question[:100]}")
            return None

    # Deterministic profile answers first.
    deterministic = guess_question_answer(question, options, config)
    if deterministic and deterministic != "Yes":
        _save_answered_question(question, deterministic)
        return deterministic

    if config.use_AI and model is not None:
        ai_ans = gemini_answer_question(
            model,
            question,
            options=options,
            question_type="choice" if options else "text",
            job_description=job_description,
            about_company=about_company,
            user_information_all=config.user_information_all,
            non_interactive=config.non_interactive,
        )
        if ai_ans and str(ai_ans).strip().lower() != "ask user":
            return str(ai_ans).strip()

    if config.non_interactive:
        auto_answer = guess_question_answer(question, options, config)
        _save_answered_question(question, auto_answer)
        return auto_answer

    play_notification_sound(config)
    manual = prompt_topmost(text=question, title="External company-site question", default="")
    if manual is not None:
        _save_answered_question(question, manual)
        return manual
    return None


def value_for_known_field(label: str, config: Config) -> str | None:
    """Direct fill mapping for common company-site fields."""
    l = _norm_text(label)
    if any(x in l for x in ["first name", "given name"]):
        return config.first_name
    if any(x in l for x in ["middle name"]):
        return config.middle_name
    if any(x in l for x in ["last name", "surname", "family name"]):
        return config.last_name
    if "full name" in l or l == "name":
        return f"{config.first_name} {config.last_name}".strip()
    if "email" in l:
        return config.email
    if any(x in l for x in ["phone", "mobile", "contact number", "telephone"]):
        return config.phone_number
    if any(x in l for x in ["city", "current location", "current address", "location"]):
        return config.current_city
    if any(x in l for x in ["linkedin"]):
        return config.linkedin_url
    if any(x in l for x in ["github"]):
        return config.github_url
    if any(x in l for x in ["portfolio", "website"]):
        return config.portfolio_url
    if any(x in l for x in ["notice", "joining", "join"]):
        return str(config.notice_period_days)
    if any(x in l for x in ["experience", "years of experience", "total exp"]):
        return str(config.experience_years)
    if any(x in l for x in ["expected ctc", "expected salary", "salary expectation"]):
        return str(config.desired_salary)
    return None


def set_input_value(driver, el, value: str) -> bool:
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    except Exception:
        pass
    try:
        el.click()
    except Exception:
        pass
    try:
        el.clear()
    except Exception:
        pass
    try:
        el.send_keys(value)
        return True
    except Exception:
        try:
            driver.execute_script(
                "arguments[0].value = arguments[1];"
                "arguments[0].dispatchEvent(new Event('input', {bubbles:true}));"
                "arguments[0].dispatchEvent(new Event('change', {bubbles:true}));",
                el, value,
            )
            return True
        except Exception as e:
            log_message(f"[WARN] Could not set input value: {str(e)[:120]}")
            return False


def fill_external_form_once(driver, model, config: Config, job_title: str, job_description: str = "") -> bool:
    """Fill visible fields on current external page. Returns True if it filled at least one field."""
    filled_any = False
    close_common_popups(driver)

    # File uploads: resume/CV.
    try:
        for file_input in driver.find_elements(By.CSS_SELECTOR, "input[type='file']"):
            try:
                label = get_label_for_field(driver, file_input)
                if any(x in _norm_text(label) for x in ["resume", "cv", "curriculum", "upload"]):
                    resume_path = config.resume_path
                    if resume_path and os.path.exists(resume_path):
                        file_input.send_keys(os.path.abspath(resume_path))
                        log_message(f"Uploaded resume to external site: {resume_path}")
                        filled_any = True
                    else:
                        log_message(f"[WARN] Resume path missing or not found: {resume_path}")
            except Exception as e:
                log_message(f"[WARN] Resume upload failed: {str(e)[:120]}")
    except Exception:
        pass

    # Text/number/email/tel/url inputs and textareas.
    input_css = (
        "input:not([type='hidden']):not([type='file']):not([type='submit']):not([type='button'])"
        ":not([type='checkbox']):not([type='radio']), textarea"
    )
    try:
        fields = driver.find_elements(By.CSS_SELECTOR, input_css)
    except Exception:
        fields = []

    for el in fields:
        try:
            if not el.is_displayed() or not el.is_enabled():
                continue
            current = (el.get_attribute("value") or "").strip()
            if current:
                continue
            label = get_label_for_field(driver, el)
            answer = value_for_known_field(label, config)
            if answer is None:
                answer = answer_from_profile_or_questions(label, [], model, config, job_description=job_description)
            if answer is not None and set_input_value(driver, el, str(answer)):
                log_message(f"Filled external field: {label[:80]} -> {str(answer)[:60]}")
                filled_any = True
                time.sleep(0.15)
        except StaleElementReferenceException:
            continue
        except Exception as e:
            log_message(f"[WARN] Skipped external text field: {str(e)[:100]}")

    # Select dropdowns.
    try:
        selects = driver.find_elements(By.CSS_SELECTOR, "select")
    except Exception:
        selects = []
    for sel in selects:
        try:
            if not sel.is_displayed() or not sel.is_enabled():
                continue
            from selenium.webdriver.support.ui import Select
            select_obj = Select(sel)
            options = [o.text.strip() for o in select_obj.options if o.text.strip()]
            if not options:
                continue
            label = get_label_for_field(driver, sel)
            answer = answer_from_profile_or_questions(label, options, model, config, job_description=job_description)
            if not answer:
                continue
            # Best option match; avoid placeholder options.
            best = None
            for opt_text in options:
                if _norm_text(opt_text) in ["select", "please select", "choose", "-- select --"]:
                    continue
                score = _score_text(answer, opt_text)
                if best is None or score > best[0]:
                    best = (score, opt_text)
            if best and best[0] >= 45:
                select_obj.select_by_visible_text(best[1])
                log_message(f"Selected dropdown: {label[:80]} -> {best[1]}")
                filled_any = True
        except Exception as e:
            log_message(f"[WARN] Skipped external dropdown: {str(e)[:100]}")

    # Radio groups and visible checkbox groups.
    try:
        choice_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='radio'], input[type='checkbox']")
    except Exception:
        choice_inputs = []

    groups = {}
    for el in choice_inputs:
        try:
            if not el.is_displayed() or not el.is_enabled():
                continue
            name = el.get_attribute("name") or el.get_attribute("id") or str(id(el))
            groups.setdefault(name, []).append(el)
        except Exception:
            continue

    for name, elems in groups.items():
        try:
            labels = [get_label_for_field(driver, e) for e in elems]
            group_question = " / ".join(labels)[:600]
            option_texts = []
            for i, e in enumerate(elems):
                opt = labels[i]
                if not opt:
                    opt = e.get_attribute("value") or ""
                option_texts.append(opt[:160])
            answer = answer_from_profile_or_questions(group_question, option_texts, model, config, job_description=job_description)
            if not answer:
                continue
            best_idx = None
            best_score = -1
            for i, opt in enumerate(option_texts):
                score = _score_text(answer, opt)
                if score > best_score:
                    best_idx, best_score = i, score
            if best_idx is not None and best_score >= 45:
                target = elems[best_idx]
                if not target.is_selected():
                    safe_click(driver, target, f"choice option '{option_texts[best_idx][:50]}'")
                    filled_any = True
        except Exception as e:
            log_message(f"[WARN] Skipped external choice group: {str(e)[:100]}")

    return filled_any


def click_next_or_submit_external(driver, config: Config) -> tuple[bool, str]:
    """Click Next/Continue, or final Submit only when enabled."""
    # Prefer Next/Continue over final Submit while pages remain.
    for words, kind in [(NEXT_BUTTON_WORDS, "next"), (FINAL_SUBMIT_WORDS, "submit")]:
        el, text = find_clickable_by_words(driver, words, timeout=3)
        if not el:
            continue
        low = _norm_text(text)
        if kind == "submit" and not config.external_auto_submit:
            log_message("External form filled. Final submit found, but external_auto_submit=false. Leaving page for manual review.")
            return False, "filled_waiting_manual_submit"
        before_handles = list(driver.window_handles)
        before_url = driver.current_url
        if safe_click(driver, el, f"external {kind} button '{text[:50]}'"):
            switch_to_newest_window_or_changed_url(driver, before_handles, before_url, timeout=8)
            wait_document_ready(driver, timeout=config.external_wait_seconds)
            return True, kind
    return False, "no_next_or_submit_found"


def external_page_status(driver) -> str | None:
    try:
        text = driver.find_element(By.TAG_NAME, "body").text.lower()
    except Exception:
        return None
    if any(s in text for s in EXTERNAL_SUCCESS_TEXT_FRAGMENTS):
        return "success"
    if any(s in text for s in EXTERNAL_STOP_TEXT_FRAGMENTS):
        return "blocked_login_or_verification"
    return None


def apply_on_external_company_site(driver, model, config: Config, job_title: str, company: str,
                                   job_description: str = "") -> tuple[str, str]:
    """
    Continue after Naukri's Apply-on-company-site redirect.
    Returns (status, notes).
    """
    if not config.external_apply_enabled:
        return "external_skipped", "External company-site apply is disabled in personal.json."

    wait_document_ready(driver, timeout=config.external_wait_seconds)
    external_url = driver.current_url
    log_message(f"External apply flow started: {external_url}")

    if _is_naukri_url(external_url):
        return "not_external", "Apply click did not leave Naukri."

    # If company website displays multiple job cards, click the same selected job.
    click_matching_external_job_card(driver, job_title=job_title, company=company, timeout=10)
    close_common_popups(driver)

    # Find and click the company's own Apply button, if the external page is a job-detail page.
    before_handles = list(driver.window_handles)
    before_url = driver.current_url
    apply_el, apply_text = find_clickable_by_words(driver, APPLY_BUTTON_WORDS, timeout=10)
    if apply_el:
        safe_click(driver, apply_el, f"company-site apply button '{apply_text[:60]}'")
        switch_to_newest_window_or_changed_url(driver, before_handles, before_url, timeout=10)
        wait_document_ready(driver, timeout=config.external_wait_seconds)
    else:
        log_message("[WARN] Company-site apply button not found; trying to fill current page directly.")

    # Multi-step application forms.
    for step in range(1, 9):
        log_message(f"External form step {step}/8: {driver.current_url}")
        status = external_page_status(driver)
        if status == "success":
            return "applied_external", "External company-site application submitted successfully."
        if status == "blocked_login_or_verification":
            return "external_needs_manual_review", "External site requires login, OTP, captcha, or account verification."

        filled = fill_external_form_once(driver, model, config, job_title, job_description=job_description)
        clicked, action = click_next_or_submit_external(driver, config)

        status = external_page_status(driver)
        if status == "success":
            return "applied_external", "External company-site application submitted successfully."

        if action == "filled_waiting_manual_submit":
            return "external_filled_manual_submit", "External form filled; final submit left for manual confirmation."
        if not filled and not clicked:
            return "external_needs_manual_review", "Could not find more fillable fields or next/submit buttons on external site."
        time.sleep(1.2)

    return "external_needs_manual_review", "External form exceeded 8 steps; stopping to avoid wrong submission."
