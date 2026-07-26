"""
in_naukari.py

Handles all apply flows that happen inside Naukri:
- opens a Naukri job card
- clicks Apply / Apply on company site
- answers Naukri chatbot questions
- calls externalapply.py when the flow redirects to a company website
- logs application results
"""

import time
from datetime import datetime

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    ElementClickInterceptedException,
    StaleElementReferenceException,
)

from naukari import (
    Config,
    log_message,
    play_notification_sound,
    prompt_topmost,
    append_csv_row,
    get_exact_saved_answer,
    guess_question_answer,
    _save_answered_question,
    gemini_answer_question,
    JOB_TITLE_LINK_SEL,
    JOB_COMPANY_SEL,
    APPLY_BUTTON_SEL,
    APPLICATION_SUCCESS_TEXT_FRAGMENTS,
    CHATBOT_QUESTION_SEL,
    CHATBOT_INPUT_SEL,
    CHATBOT_OPTION_SEL,
    CHATBOT_SEND_SEL,
)

from externalapply import (
    APPLY_BUTTON_WORDS,
    safe_click,
    switch_to_newest_window_or_changed_url,
    wait_document_ready,
    find_clickable_by_words,
    _is_naukri_url,
    _norm_text,
    apply_on_external_company_site,
)

def handle_chatbot_question(driver, model, config: Config, job_title: str,
                             job_description: str = None, about_company: str = None) -> bool:
    """
    Handles Naukri's chat-style screening questionnaire that appears after
    clicking Apply for some listings. Loops until no more questions are found
    or a question can't be answered automatically.

    Returns True if the flow completed (all questions handled), False if it
    stalled and needs manual attention.
    """
    max_questions = 25
    asked = 0
    log_message(f"Entering handle_chatbot_question. Non-interactive mode: {config.non_interactive}")

    # Wait up to 8 seconds for chatbot question elements to appear
    chatbot_detected = False
    for i in range(8):
        try:
            question_elems = driver.find_elements(*CHATBOT_QUESTION_SEL)
            question_elems = [q for q in question_elems if q.text.strip()]
            if question_elems:
                chatbot_detected = True
                break
        except Exception:
            pass
        time.sleep(1)

    if not chatbot_detected:
        log_message("No chatbot questionnaire detected (or didn't load within 8s).")
        return True

    last_question_text = None
    same_question_count = 0

    while asked < max_questions:
        asked += 1
        try:
            question_elems = driver.find_elements(*CHATBOT_QUESTION_SEL)
            question_elems = [q for q in question_elems if q.text.strip()]
        except Exception:
            question_elems = []

        if not question_elems:
            log_message("No more chatbot questions detected.")
            return True

        question_text = question_elems[-1].text.strip()
        if not question_text:
            return True

        # Detect infinite loop: same question asked 3 times in a row without progress
        if question_text == last_question_text:
            same_question_count += 1
            if same_question_count >= 3:
                log_message(f"[WARN] Same question appeared {same_question_count} times in a row — likely stuck. Stopping.")
                return False
        else:
            same_question_count = 0
        last_question_text = question_text

        log_message(f"Chatbot question: {question_text}")

        # Wait up to 5 seconds for either visible options or a visible text/textarea input to appear
        option_elems = []
        option_texts = []
        safe_inputs = []

        for wait_attempt in range(10): # 10 * 0.5 = 5 seconds max
            # Check options
            try:
                raw_options = driver.find_elements(*CHATBOT_OPTION_SEL)
                option_elems = [o for o in raw_options if o.is_displayed() and o.text.strip() and len(o.text.strip()) < 100]
                option_texts = [o.text.strip() for o in option_elems]
            except Exception:
                option_elems = []
                option_texts = []

            # Check inputs
            try:
                raw_inputs = driver.find_elements(*CHATBOT_INPUT_SEL)
                safe_inputs = []
                for el in raw_inputs:
                    try:
                        el_type = (el.get_attribute("type") or "text").lower()
                        if el_type in ("file", "hidden", "submit", "button", "reset", "image", "radio", "checkbox"):
                            continue
                        if el.is_displayed():
                            safe_inputs.append(el)
                    except Exception:
                        pass
            except Exception:
                safe_inputs = []

            # If option elements are found, we can break immediately.
            # If only text inputs are found, we wait at least 3 attempts (1.5 seconds)
            # to allow option buttons to render.
            if option_elems:
                break
            if safe_inputs and wait_attempt >= 3:
                break
            time.sleep(0.5)

        # Fallback: if no visible input or options found, try all inputs that aren't blacklisted types
        if not option_elems and not safe_inputs:
            try:
                raw_inputs = driver.find_elements(*CHATBOT_INPUT_SEL)
                for el in raw_inputs:
                    try:
                        el_type = (el.get_attribute("type") or "text").lower()
                        if el_type in ("file", "hidden", "submit", "button", "reset", "image", "radio", "checkbox"):
                            continue
                        safe_inputs.append(el)
                    except Exception:
                        pass
            except Exception:
                pass

        # 1. First search for an exact match in questions.json
        saved_answer = get_exact_saved_answer(question_text)
        if saved_answer is not None:
            log_message(f"Found exact match in questions.json: '{question_text}' -> '{saved_answer}'")
            answer = saved_answer
        else:
            # Match not found: ask AI first when AI mode is enabled; otherwise ask the user.
            answer = None
            if config.use_AI and model is not None:
                ai_answer = gemini_answer_question(
                    model,
                    question_text,
                    options=option_texts,
                    question_type="choice" if option_texts else "text",
                    job_description=job_description,
                    about_company=about_company,
                    user_information_all=config.user_information_all,
                    non_interactive=config.non_interactive,
                )
                if ai_answer and str(ai_answer).strip().lower() != "ask user":
                    answer = str(ai_answer).strip()
                    log_message(f"AI answered Naukri question: '{question_text[:60]}' -> '{answer[:60]}'")

            if answer is None:
                if config.non_interactive:
                    answer = guess_question_answer(question_text, option_texts, config)
                    log_message(f"Non-interactive fallback answer: '{answer}'")
                else:
                    play_notification_sound(config)
                    manual_answer = prompt_topmost(
                        text=question_text,
                        title=f"Naukri question — {job_title}",
                        default="",
                    )
                    if manual_answer is None:
                        log_message("User cancelled manual prompt — stopping chatbot flow for this job.")
                        return False
                    answer = manual_answer
                _save_answered_question(question_text, answer)

        # Re-query elements to ensure they are fresh and not stale (especially if manual prompt took time)
        try:
            raw_options = driver.find_elements(*CHATBOT_OPTION_SEL)
            option_elems = [o for o in raw_options if o.is_displayed() and o.text.strip() and len(o.text.strip()) < 100]
            option_texts = [o.text.strip() for o in option_elems]
        except Exception:
            option_elems = []
            option_texts = []

        try:
            raw_inputs = driver.find_elements(*CHATBOT_INPUT_SEL)
            safe_inputs = []
            for el in raw_inputs:
                try:
                    el_type = (el.get_attribute("type") or "text").lower()
                    if el_type in ("file", "hidden", "submit", "button", "reset", "image", "radio", "checkbox"):
                        continue
                    if el.is_displayed():
                        safe_inputs.append(el)
                except Exception:
                    pass
        except Exception:
            safe_inputs = []

        # If options were presented, try clicking the matching one; else type the answer.
        clicked = False
        if option_texts:
            answer_lower = answer.strip().lower()

            # Pass 1: Exact case-insensitive match
            for opt_elem, opt_text in zip(reversed(option_elems), reversed(option_texts)):
                if opt_text.strip().lower() == answer_lower:
                    try:
                        opt_elem.click()
                        clicked = True
                        log_message(f"Clicked option (exact match): '{opt_text}'")
                        break
                    except (ElementClickInterceptedException, StaleElementReferenceException, Exception):
                        try:
                            driver.execute_script("arguments[0].click();", opt_elem)
                            clicked = True
                            log_message(f"Clicked option (JS exact match): '{opt_text}'")
                            break
                        except Exception:
                            pass

            # Pass 2: Contains/partial match
            if not clicked:
                for opt_elem, opt_text in zip(reversed(option_elems), reversed(option_texts)):
                    if answer_lower in opt_text.strip().lower() or opt_text.strip().lower() in answer_lower:
                        try:
                            opt_elem.click()
                            clicked = True
                            log_message(f"Clicked option (partial match): '{opt_text}' for answer '{answer}'")
                            break
                        except Exception:
                            try:
                                driver.execute_script("arguments[0].click();", opt_elem)
                                clicked = True
                                log_message(f"Clicked option (JS partial match): '{opt_text}' for answer '{answer}'")
                                break
                            except Exception:
                                pass

            if clicked:
                # Check if a Send/Submit button is displayed and click it if necessary
                try:
                    send_btns = driver.find_elements(*CHATBOT_SEND_SEL)
                    for send_btn in reversed(send_btns):
                        if send_btn.is_displayed():
                            try:
                                send_btn.click()
                                log_message("Clicked submit button after option selection.")
                                break
                            except Exception:
                                try:
                                    driver.execute_script("arguments[0].click();", send_btn)
                                    log_message("Clicked submit button after option selection (JS fallback).")
                                    break
                                except Exception:
                                    pass
                except Exception:
                    pass

            if not clicked:
                log_message(f"No option matched '{answer}' among {option_texts}. Will try text input.")

        if not clicked:
            try:
                if safe_inputs:
                    success = False
                    # Try from last to first (most recent input in DOM = active chatbot input)
                    for idx, input_box in enumerate(reversed(safe_inputs)):
                        try:
                            el_type = (input_box.get_attribute("type") or "text").lower()
                            el_tag = input_box.tag_name.lower()
                            log_message(f"[DEBUG] Trying input: tag={el_tag}, type={el_type}")

                            # Try to click/focus
                            try:
                                input_box.click()
                            except Exception:
                                try:
                                    driver.execute_script("arguments[0].click();", input_box)
                                except Exception:
                                    pass

                            # Try to clear and send keys
                            try:
                                is_editable = input_box.get_attribute("contenteditable") == "true" or el_tag in ("div", "span")
                                if is_editable:
                                    driver.execute_script("arguments[0].innerText = '';", input_box)
                                else:
                                    input_box.clear()
                            except Exception:
                                pass

                            try:
                                input_box.send_keys(answer)
                            except Exception as send_keys_err:
                                try:
                                    log_message(f"[DEBUG] send_keys failed, trying JavaScript input: {send_keys_err}")
                                    driver.execute_script(
                                        "if (arguments[0].tagName.toLowerCase() === 'input' || arguments[0].tagName.toLowerCase() === 'textarea') {"
                                        "    arguments[0].value = arguments[1];"
                                        "} else {"
                                        "    arguments[0].innerText = arguments[1];"
                                        "}"
                                        "arguments[0].dispatchEvent(new Event('input', { bubbles: true })); "
                                        "arguments[0].dispatchEvent(new Event('change', { bubbles: true }));",
                                        input_box, answer
                                    )
                                except Exception as js_err:
                                    log_message(f"[DEBUG] JavaScript fallback input also failed: {js_err}")
                                    raise send_keys_err

                            # Find and click send button
                            send_btns = driver.find_elements(*CHATBOT_SEND_SEL)
                            submitted = False
                            if send_btns:
                                for send_btn in reversed(send_btns):
                                    try:
                                        send_btn.click()
                                        submitted = True
                                        break
                                    except Exception:
                                        try:
                                            driver.execute_script("arguments[0].click();", send_btn)
                                            submitted = True
                                            break
                                        except Exception:
                                            pass

                            if not submitted:
                                input_box.send_keys(Keys.ENTER)

                            success = True
                            log_message(f"Successfully submitted chatbot answer using input (tag={el_tag}, type={el_type})")
                            break
                        except Exception as element_err:
                            log_message(f"[DEBUG] Skipping candidate input due to: {str(element_err)[:120]}")
                            continue

                    if not success:
                        log_message("[WARN] Failed to submit chatbot answer on all matched input elements.")
                        # Log what we found for debugging
                        all_found = driver.find_elements(*CHATBOT_INPUT_SEL)
                        log_message(f"[DEBUG] Total input elements found by selector: {len(all_found)}")
                        for i, el in enumerate(all_found):
                            try:
                                log_message(f"[DEBUG]   [{i}] tag={el.tag_name}, type={el.get_attribute('type')}, visible={el.is_displayed()}")
                            except Exception:
                                pass
                        # Debug container HTML
                        try:
                            container = driver.find_element(By.CSS_SELECTOR, "div.chatbot_InputContainer, div.chat-container, div.chatbot-container, form")
                            log_message(f"[DEBUG] Chatbot container HTML: {container.get_attribute('outerHTML')[:1200]}")
                        except Exception:
                            pass
                        return False
                else:
                    log_message("[WARN] Could not find any visible input box or matching option for this question.")
                    # Log all inputs found for debugging
                    all_found = driver.find_elements(*CHATBOT_INPUT_SEL)
                    log_message(f"[DEBUG] Total input elements found by selector: {len(all_found)}")
                    for i, el in enumerate(all_found):
                        try:
                            log_message(f"[DEBUG]   [{i}] tag={el.tag_name}, type={el.get_attribute('type')}, visible={el.is_displayed()}")
                        except Exception:
                            pass
                    # Debug container HTML
                    try:
                        container = driver.find_element(By.CSS_SELECTOR, "div.chatbot_InputContainer, div.chat-container, div.chatbot-container, form")
                        log_message(f"[DEBUG] Chatbot container HTML: {container.get_attribute('outerHTML')[:1200]}")
                    except Exception:
                        pass
                    return False
            except Exception as e:
                log_message(f"[WARN] Failed to submit chatbot answer: {e}")
                return False

        time.sleep(1.5)

    log_message("[WARN] Exceeded max chatbot question loop count — stopping to avoid an infinite loop.")
    return False



def apply_to_job_card(driver, card, model, config: Config, wait_seconds: int = 15) -> dict:
    """
    Opens a single job card, clicks Naukri Apply / Apply on company site,
    continues on external company websites when applicable, answers questions,
    and returns a result dict for CSV logging.
    """
    result = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "job_title": "",
        "company": "",
        "status": "",
        "notes": "",
        "source_url": "",
        "external_url": "",
    }

    try:
        title_elem = card.find_element(*JOB_TITLE_LINK_SEL)
        result["job_title"] = title_elem.text.strip()
    except NoSuchElementException:
        result["job_title"] = "Unknown"
        title_elem = None

    try:
        company_elem = card.find_element(*JOB_COMPANY_SEL)
        result["company"] = company_elem.text.strip()
    except NoSuchElementException:
        result["company"] = "Unknown"

    log_message(f"Opening job: {result['job_title']} @ {result['company']}")

    main_window = driver.current_window_handle
    job_window = main_window
    external_window = None

    try:
        if title_elem is None:
            raise NoSuchElementException("Job title link not found")
        before_handles = list(driver.window_handles)
        before_url = driver.current_url
        if not safe_click(driver, title_elem, "Naukri job title/card"):
            raise Exception("Could not open job detail")
        switch_to_newest_window_or_changed_url(driver, before_handles, before_url, timeout=8)

        # Naukri often opens the job detail in a new tab
        all_windows = driver.window_handles
        job_window = all_windows[-1] if len(all_windows) > 1 else driver.current_window_handle
        driver.switch_to.window(job_window)
        wait_document_ready(driver, timeout=wait_seconds)
        result["source_url"] = driver.current_url

        job_description = ""
        about_company = ""
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text
            job_description = body_text[:4000]
        except Exception:
            pass

        # Robustly find the Naukri apply button. Some pages use ID apply-button;
        # others only expose text like "Apply on company site".
        wait = WebDriverWait(driver, wait_seconds)
        apply_btn = None
        btn_text = ""
        try:
            apply_btn = wait.until(EC.element_to_be_clickable(APPLY_BUTTON_SEL))
            btn_text = apply_btn.text.strip()
        except TimeoutException:
            apply_btn, btn_text = find_clickable_by_words(driver, APPLY_BUTTON_WORDS, timeout=8)

        if not apply_btn:
            result["status"] = "failed"
            result["notes"] = "Naukri Apply / Apply on company site button not found or not clickable."
            log_message(f"[WARN] {result['notes']}")
            return result

        btn_text_lower = _norm_text(btn_text)
        if "already applied" in btn_text_lower:
            result["status"] = "already_applied"
            log_message("Already applied to this job — skipping.")
            return result

        before_apply_handles = list(driver.window_handles)
        before_apply_url = driver.current_url
        if not safe_click(driver, apply_btn, f"Naukri apply button '{btn_text[:60]}'"):
            result["status"] = "failed"
            result["notes"] = "Could not click Naukri apply button."
            return result

        # Give Naukri/external redirect time to open.
        navigated = switch_to_newest_window_or_changed_url(driver, before_apply_handles, before_apply_url, timeout=12)
        time.sleep(2)
        result["external_url"] = driver.current_url

        # Case A: Apply on company site: new external URL or same-tab external redirect.
        if config.external_apply_enabled and not _is_naukri_url(driver.current_url):
            external_window = driver.current_window_handle
            status, notes = apply_on_external_company_site(
                driver, model, config,
                job_title=result["job_title"],
                company=result["company"],
                job_description=job_description,
            )
            result["status"] = status
            result["notes"] = notes
            result["external_url"] = driver.current_url
            log_message(f"External apply result: {status} — {notes}")
            return result

        # Case B: Naukri easy-apply/chatbot or instant Naukri application.
        completed = handle_chatbot_question(
            driver, model, config,
            job_title=result["job_title"],
            job_description=job_description,
            about_company=about_company,
        )

        time.sleep(1.5)
        try:
            page_text_lower = driver.find_element(By.TAG_NAME, "body").text.lower()
        except Exception:
            page_text_lower = ""

        if any(frag in page_text_lower for frag in APPLICATION_SUCCESS_TEXT_FRAGMENTS):
            result["status"] = "applied"
        elif completed:
            result["status"] = "applied"
        else:
            result["status"] = "needs_manual_review"
            result["notes"] = "Naukri chatbot flow stalled or needs manual attention."

    except TimeoutException:
        result["status"] = "failed"
        result["notes"] = "Apply button not found/clickable; selector may be stale or page did not load."
        log_message(f"[WARN] {result['notes']}")
    except Exception as e:
        result["status"] = "failed"
        result["notes"] = str(e)[:200]
        log_message(f"[ERROR] Unexpected error applying to job: {e}")

    finally:
        # Close any job/external tab if separate, return to the original listing tab.
        try:
            handles = driver.window_handles
            for h in list(handles):
                if h != main_window and h in driver.window_handles:
                    try:
                        driver.switch_to.window(h)
                        driver.close()
                    except Exception:
                        pass
            if main_window in driver.window_handles:
                driver.switch_to.window(main_window)
            elif driver.window_handles:
                driver.switch_to.window(driver.window_handles[0])
        except Exception as e:
            log_message(f"[WARN] Error restoring window handle: {e}")
            try:
                if driver.window_handles:
                    driver.switch_to.window(driver.window_handles[0])
            except Exception:
                pass

    return result


def log_application_result(config: Config, result: dict) -> None:
    target_file = config.file_name if result["status"] in ("applied", "already_applied", "applied_external") else config.failed_file_name
    append_csv_row(target_file, result)
    log_message(f"Logged result to: {target_file} ({result['status']})")
