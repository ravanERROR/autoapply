"""
naukri_bot.py

Single-file Naukri.com job-application automation bot.

Sections in this file:
    1. CONFIG            - loads personal.json, exposes settings as properties
    2. LOGGING / UTILS    - timestamped logging, notification sound, topmost prompt
    3. GEMINI AI HELPERS  - question answering via Google Gemini (with key rotation)
    4. SELENIUM SETUP     - Chrome driver bootstrap (stealth / headless)
    5. NAUKRI AUTOMATION  - login, search with filters, open each job, apply,
                            answer screening questions, log results to CSV
    6. EXTERNAL / COMPANY-SITE APPLY - handles "Apply on company site" flow:
                            follow-through to third-party ATS, generic form fill,
                            resume upload, login-wall detection & skip
    7. MAIN               - ties everything together, with a --dry-run / "ai" CLI flag

Run:
    python naukri_bot.py            # manual mode, you answer screening questions
    python naukri_bot.py ai         # Gemini answers screening questions automatically

Requirements (pip install):
    selenium
    undetected-chromedriver   (optional, for stealth mode)
    google-generativeai       (only needed if using "ai" mode)
    pyautogui                 (fallback for prompt dialogs on non-Windows)

personal.json (expected shape - adjust to your needs):
{
  "naukri": { "username": "you@example.com", "password": "yourpassword" },
  "chrome": { "stealth_mode": true, "headless": false },
  "filters": {
    "search_terms": ["Java Full Stack Developer", "Java Developer"],
    "search_location": "Pune",
    "experience": "4",
    "easy_apply": true,
    "freshness": "Last 7 days"
  },
  "personal": {
    "first_name": "Pavan",
    "middle_name": "",
    "last_name": "Wakade",
    "phone_number": "9999999999",
    "current_city": "Pune",
    "experience_years": 4,
    "desired_salary": 1400000,
    "notice_period_days": 30,
    "resume_path": "C:/path/to/resume.pdf"
  },
  "ai": {
    "use_AI": false,
    "llm_api_keys": ["YOUR_GEMINI_API_KEY"],
    "llm_model": "gemini-2.5-flash"
  },
  "bot": {
    "file_name": "all excels/all_applied_applications_history.csv",
    "failed_file_name": "all excels/all_failed_applications_history.csv",
    "max_applications": 50
  }
}

SECURITY NOTE: never hardcode API keys or passwords in this file. Keep them
only in personal.json, and keep personal.json out of version control.
"""

import os
import sys
import csv
import json
import time
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    ElementClickInterceptedException,
    StaleElementReferenceException,
)


# ════════════════════════════════════════════════════════════════════
# 1. CONFIG
# ════════════════════════════════════════════════════════════════════

class Config:
    def __init__(self, config_path="personal.json"):
        self.config_path = config_path
        self.data = {}
        self.load_config()

    def load_config(self):
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found at {self.config_path}")

        with open(self.config_path, "r", encoding="utf-8") as f:
            self.data = json.load(f)

    # ---- Naukri credentials ----
    @property
    def naukri_username(self) -> str:
        return self.data.get("naukri", {}).get("username", "")

    @property
    def naukri_password(self) -> str:
        return self.data.get("naukri", {}).get("password", "")

    # ---- Chrome ----
    @property
    def stealth_mode(self) -> bool:
        return self.data.get("chrome", {}).get("stealth_mode", True)

    @property
    def headless(self) -> bool:
        return self.data.get("chrome", {}).get("headless", False)

    # ---- Job search filters ----
    @property
    def filters(self) -> dict:
        return self.data.get("filters", {})

    @property
    def search_terms(self) -> list:
        """List of job titles/keywords to search, one search run per term.
        Falls back to a single legacy 'keywords' string if present."""
        terms = self.filters.get("search_terms", [])
        if isinstance(terms, list) and terms:
            return [t for t in terms if isinstance(t, str) and t.strip()]
        legacy = self.filters.get("keywords", "")
        if isinstance(legacy, str) and legacy.strip():
            return [legacy.strip()]
        return [""]

    @property
    def search_location(self) -> str:
        """Free-text location to search (e.g. 'Pune'). Accepts a string or
        falls back to the first entry of a 'location' list if present."""
        loc = self.filters.get("search_location", "")
        if isinstance(loc, str) and loc.strip():
            return loc.strip()
        loc_list = self.filters.get("location", [])
        if isinstance(loc_list, list) and loc_list:
            return str(loc_list[0]).strip()
        return ""

    @property
    def search_experience(self) -> str:
        """Years of experience to filter by. Falls back to personal.experience_years."""
        exp = self.filters.get("experience", "")
        if exp not in ("", None):
            return str(exp)
        years = self.personal_details.get("experience_years", "")
        return str(years) if years not in ("", None) else ""

    @property
    def easy_apply(self) -> bool:
        return bool(self.filters.get("easy_apply", False))

    @property
    def freshness(self) -> str:
        return str(self.filters.get("freshness", "") or "")

    @property
    def salary_bands(self) -> list:
        """List of salary range strings from filters.salary, e.g. ['10-15 Lakhs']."""
        bands = self.filters.get("salary", [])
        return [b for b in bands if isinstance(b, str) and b.strip()] if isinstance(bands, list) else []

    @property
    def on_site_modes(self) -> list:
        """List of work-mode strings from filters.on_site, e.g. ['Remote']."""
        modes = self.filters.get("on_site", [])
        return [m for m in modes if isinstance(m, str) and m.strip()] if isinstance(modes, list) else []

    # ---- Personal details ----
    @property
    def personal_details(self) -> dict:
        return self.data.get("personal", {})

    @property
    def first_name(self) -> str:
        return self.personal_details.get("first_name", "")

    @property
    def middle_name(self) -> str:
        return self.personal_details.get("middle_name", "")

    @property
    def last_name(self) -> str:
        return self.personal_details.get("last_name", "")

    @property
    def phone_number(self) -> str:
        return self.personal_details.get("phone_number", "")

    @property
    def current_city(self) -> str:
        return self.personal_details.get("current_city", "")

    @property
    def experience_years(self) -> int:
        return int(self.personal_details.get("experience_years", 0))

    @property
    def desired_salary(self) -> int:
        return int(self.personal_details.get("desired_salary", 0))

    @property
    def notice_period_days(self) -> int:
        return int(self.personal_details.get("notice_period_days", 0))

    @property
    def resume_path(self) -> str:
        return self.personal_details.get("resume_path", "")

    # ---- AI settings (Gemini only) ----
    @property
    def use_AI(self) -> bool:
        """AI mode is enabled by passing 'ai' on the command line, or via personal.json,
        unless 'manual' or 'no-ai' is passed on the command line."""
        if any(arg.lower() in ("manual", "no-ai", "no_ai") for arg in sys.argv):
            return False
        if any(arg.lower() == "ai" for arg in sys.argv):
            return True
        return self.data.get("ai", {}).get("use_AI", False)

    @property
    def llm_api_keys(self) -> list:
        """Returns list of all Gemini API keys. Supports both 'llm_api_keys' (array)
        and legacy 'llm_api_key' (string)."""
        ai_cfg = self.data.get("ai", {})
        keys_list = ai_cfg.get("llm_api_keys", [])
        if isinstance(keys_list, list) and keys_list:
            return [k for k in keys_list if k and "YOUR_API_KEY" not in k]
        single = ai_cfg.get("llm_api_key", "")
        if single and "YOUR_API_KEY" not in single:
            return [single]
        return []

    @property
    def llm_api_key(self) -> str:
        """Returns the first available API key (legacy compatibility)."""
        keys = self.llm_api_keys
        return keys[0] if keys else ""

    @property
    def llm_model(self) -> str:
        return self.data.get("ai", {}).get("llm_model", "gemini-2.5-flash")

    # ---- Bot / output files ----
    @property
    def file_name(self) -> str:
        return self.data.get("bot", {}).get("file_name", "all excels/all_applied_applications_history.csv")

    @property
    def failed_file_name(self) -> str:
        return self.data.get("bot", {}).get("failed_file_name", "all excels/all_failed_applications_history.csv")

    @property
    def max_applications(self) -> int:
        return int(self.data.get("bot", {}).get("max_applications", 50))

    @property
    def question_notification_sound(self) -> str:
        default_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notify", "job.mp3")
        return self.data.get("bot", {}).get("question_notification_sound", default_path)

    @property
    def non_interactive(self) -> bool:
        """Determines if the bot runs fully automatically without showing blocking prompts/popups."""
        if any(arg.lower() in ("auto", "non-interactive", "--auto") for arg in sys.argv):
            return True
        return bool(self.data.get("bot", {}).get("non_interactive", False))

    @property
    def user_information_all(self) -> str:
        details = self.personal_details
        info = f"""
{details.get('first_name', '')} {details.get('middle_name', '')} {details.get('last_name', '')}
Java Full Stack Developer
+91 {details.get('phone_number', '')} | {details.get('current_city', '')}, India

PROFESSIONAL SUMMARY
Java Full Stack Developer with {details.get('experience_years', '')}+ years of experience in designing,
developing and deploying scalable enterprise applications using Java, Spring Boot, Microservices,
Hibernate/JPA and React.js. Strong expertise in RESTful APIs, cloud deployment on AWS, Docker
containerization, Kubernetes orchestration and Agile/Scrum methodologies.

Notice period: {details.get('notice_period_days', '')} days.
Desired salary: {details.get('desired_salary', '')}
Current city: {details.get('current_city', '')}
""".strip()
        return info


# ════════════════════════════════════════════════════════════════════
# 2. LOGGING / UTILS
# ════════════════════════════════════════════════════════════════════

def log_message(message: str):
    """Print formatted message with a timestamp and save to file."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{timestamp}] {message}"
    try:
        sys.stdout.buffer.write((formatted + "\n").encode("utf-8", errors="replace"))
        sys.stdout.buffer.flush()
    except Exception:
        try:
            print(formatted.encode("ascii", "replace").decode())
        except Exception:
            pass
    try:
        with open("naukri_bot.log", "a", encoding="utf-8") as f:
            f.write(formatted + "\n")
    except Exception:
        pass


def play_notification_sound(config: "Config") -> None:
    """Plays a notification sound on Windows when a manual question input is required."""
    sound_path = config.question_notification_sound

    if sound_path and not os.path.exists(sound_path):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        alt_path = os.path.join(script_dir, "notify", "job.mp3")
        if os.path.exists(alt_path):
            sound_path = alt_path
        else:
            parent_alt = os.path.abspath(os.path.join(script_dir, "..", "notify", "job.mp3"))
            if os.path.exists(parent_alt):
                sound_path = parent_alt

    if sound_path and os.path.exists(sound_path):
        try:
            sound_path_abs = os.path.abspath(sound_path)
            if sound_path_abs.lower().endswith(".mp3"):
                import ctypes
                ctypes.windll.winmm.mciSendStringW("close my_sound", None, 0, 0)
                ctypes.windll.winmm.mciSendStringW(f'open "{sound_path_abs}" type mpegvideo alias my_sound', None, 0, 0)
                ctypes.windll.winmm.mciSendStringW("play my_sound", None, 0, 0)
                return
            else:
                import winsound
                winsound.PlaySound(sound_path_abs, winsound.SND_FILENAME | winsound.SND_ASYNC)
                return
        except Exception as e:
            log_message(f"Error playing custom notification sound: {e}")
    elif sound_path:
        log_message(f"Notification sound file not found at: {sound_path}")

    try:
        import winsound
        winsound.MessageBeep(winsound.MB_ICONASTERISK)
        winsound.Beep(1000, 500)
    except Exception as e:
        log_message(f"Fallback beep failed: {e}")
        try:
            sys.stdout.write("\a")
            sys.stdout.flush()
        except Exception:
            pass


def prompt_topmost(text: str, title: str, default: str = "") -> str | None:
    """Displays a prompt dialog that is forced to stay on top of all windows.
    Used when AI mode is off, or AI returned 'ask user'."""
    try:
        import tkinter as tk
        from tkinter import simpledialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        root.lift()
        root.focus_force()
        ans = simpledialog.askstring(title, text, initialvalue=default, parent=root)
        root.destroy()
        return ans
    except Exception as e:
        log_message(f"Error in topmost prompt dialog: {e}")
        try:
            import pyautogui
            return pyautogui.prompt(text=text, title=title, default=default)
        except Exception as e2:
            log_message(f"pyautogui prompt fallback also failed: {e2}")
            return input(f"{title} - {text}: ")


def ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def append_csv_row(path: str, row: dict) -> None:
    """Append a row to a CSV file, writing the header if the file is new."""
    ensure_parent_dir(path)
    file_exists = os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


# ════════════════════════════════════════════════════════════════════
# 3. GEMINI AI HELPERS
# ════════════════════════════════════════════════════════════════════

ai_answer_prompt = """
You are an expert job application assistant helping a real candidate fill out Naukri forms.
Your goal is to give the BEST, most accurate answer based strictly on the candidate's profile and previously answered questions.

═══════════════════════════════════
 CANDIDATE PROFILE
═══════════════════════════════════
{}
═══════════════════════════════════

═══════════════════════════════════
 PREVIOUSLY ANSWERED QUESTIONS (DATABASE)
═══════════════════════════════════
{}
═══════════════════════════════════

INSTRUCTIONS — follow these EXACTLY:

1. NUMERIC / YEARS OF EXPERIENCE → Return ONLY an integer (e.g. 4) or decimal if appropriate (e.g. 1.5). No units, no words.
2. YES / NO → Return ONLY "Yes" or "No" (capitalised exactly like that).
3. SALARY / CTC → Return only the number in the currency asked (e.g. 1400000 for INR or 14 for LPA).
4. NOTICE PERIOD → Return only the number of days (e.g. 21).
5. LOCATION → Return the city name only (e.g. Pune).
6. SELECT FROM OPTIONS → Return the text of EXACTLY ONE option that best matches the profile or previously answered questions.
7. SHORT TEXT (< 100 chars) → One concise sentence, no filler words.
8. LONG TEXT / DESCRIBE → Well-structured, professional, human-like answer. Max 400 characters. Do NOT start with "I" if avoidable.
9. UNKNOWN / IRRELEVANT / MISSING DETAILS → If the question asks for any other details NOT mentioned in the Candidate Profile or Previously Answered Questions, or if you cannot analyze or determine the answer, return EXACTLY the phrase "ask user".
10. DO NOT repeat the question. DO NOT add explanations or apologies.
11. DO NOT add quotes around the answer unless they are part of the answer.

QUESTION:
{}
"""

# Global key rotation state
_api_keys: list = []
_active_key_index: int = 0


def _get_model_for_key(api_key: str, model_name: str):
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(model_name)


def gemini_get_models_list(api_key: str = None):
    try:
        import google.generativeai as genai
        if api_key:
            genai.configure(api_key=api_key)
        log_message("Getting Gemini models list...")
        return [m.name for m in genai.list_models() if "generateContent" in m.supported_generation_methods]
    except Exception as e:
        log_message(f"Error getting Gemini models list: {e}")
        return ["error", str(e)]


def gemini_create_client(config: Config):
    """Configure Gemini client with multiple API key support. Tries all keys,
    returns a model object for the first working key."""
    global _api_keys, _active_key_index
    keys = config.llm_api_keys
    if not keys:
        log_message("[ERROR] No Gemini API keys configured. Set 'llm_api_keys' in personal.json.")
        return None

    _api_keys = keys
    target_model = config.llm_model
    log_message(f"Gemini client: {len(keys)} API key(s) loaded. Model: {target_model}")

    for i, key in enumerate(keys):
        try:
            log_message(f"  Trying API key [{i+1}/{len(keys)}]: ...{key[-6:]}")
            models = gemini_get_models_list(key)
            if "error" in models:
                log_message(f"  Key [{i+1}] rejected: {models[1]}")
                continue
            if not any(target_model in m for m in models):
                log_message(f"  Key [{i+1}] OK but model '{target_model}' not found — still using it.")
            model = _get_model_for_key(key, target_model)
            _active_key_index = i
            log_message(f"---- GEMINI CLIENT READY! Key [{i+1}/{len(keys)}] | Model: {target_model} ----")
            return model
        except Exception as e:
            log_message(f"  Key [{i+1}] failed during init: {e}")

    log_message("[ERROR] All Gemini API keys failed during initialization.")
    return None


def gemini_completion(model, prompt: str, is_json: bool = False) -> dict | str:
    """Generate content using Gemini with automatic API key rotation fallback."""
    global _api_keys, _active_key_index
    import google.generativeai as genai

    if not model:
        raise ValueError("Gemini client is not available!")

    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]

    def _clean_and_parse(result_text: str):
        if result_text.startswith("```json"):
            result_text = result_text[7:]
        if result_text.endswith("```"):
            result_text = result_text[:-3]
        return json.loads(result_text.strip())

    if not _api_keys:
        try:
            log_message("Calling Gemini API (single key mode)...")
            response = model.generate_content(prompt, safety_settings=safety_settings)
            if not response.parts:
                raise ValueError("Gemini API returned an empty response.")
            result = response.text
            return _clean_and_parse(result) if is_json else result.strip()
        except Exception as e:
            log_message(f"Error getting Gemini completion: {e}")
            return {"error": str(e)}

    num_keys = len(_api_keys)
    max_rounds = 2  # extra round to allow retry-after-wait
    last_error = None

    def _extract_retry_delay(error_str: str) -> int:
        """Extract retry_delay seconds from a Gemini 429 error message."""
        import re
        m = re.search(r'retry_delay\s*\{[^}]*seconds:\s*(\d+)', error_str)
        if m:
            return int(m.group(1))
        m2 = re.search(r'Please retry in (\d+)', error_str)
        if m2:
            return int(m2.group(1))
        return 0

    _waited_429 = False  # track if we already waited once

    for round_num in range(1, max_rounds + 1):
        for attempt in range(num_keys):
            key_index = (_active_key_index + attempt) % num_keys
            api_key = _api_keys[key_index]
            key_label = f"key [{key_index + 1}/{num_keys}] (round {round_num}/{max_rounds})"
            try:
                log_message(f"Calling Gemini API with {key_label} ...{api_key[-6:]}")
                genai.configure(api_key=api_key)
                response = model.generate_content(prompt, safety_settings=safety_settings)
                if not response.parts:
                    raise ValueError("Gemini API returned an empty response.")
                result = response.text
                _active_key_index = key_index
                return _clean_and_parse(result) if is_json else result.strip()
            except Exception as e:
                last_error = e
                err_str = str(e)
                log_message(f"  [WARN] Gemini {key_label} failed: {err_str[:200]}")

                # If 429 quota error and we haven't waited yet, respect the retry_delay
                if "429" in err_str and not _waited_429:
                    delay = _extract_retry_delay(err_str)
                    if delay > 0:
                        wait_secs = min(delay + 2, 65)  # cap at 65s
                        log_message(f"  [QUOTA] Rate-limited. Waiting {wait_secs}s before retrying (API suggested {delay}s)...")
                        time.sleep(wait_secs)
                        _waited_429 = True
                        break  # break inner loop to retry from round start
                    else:
                        log_message("  Rotating to next key...")
                else:
                    log_message("  Rotating to next key...")

    log_message(f"[ERROR] All {num_keys} API key(s) failed after {max_rounds} rounds. Last error: {last_error}")
    return {"error": str(last_error)}


def _load_past_questions() -> str:
    import json as _json
    past_questions_str = "No previously answered questions recorded yet."
    try:
        questions_json_path = os.path.join("config", "questions.json")
        if os.path.exists(questions_json_path):
            with open(questions_json_path, "r", encoding="utf-8") as f:
                q_data = _json.load(f)
                if q_data:
                    formatted_qa = [f"- {k}: {v}" for k, v in q_data.items() if v]
                    if formatted_qa:
                        past_questions_str = "\n".join(formatted_qa)
    except Exception as err:
        log_message(f"Error loading questions.json: {err}")
    return past_questions_str


def _save_answered_question(question: str, answer: str) -> None:
    """Persist a Q&A pair so future prompts include it as context."""
    import json as _json
    questions_json_path = os.path.join("config", "questions.json")
    os.makedirs(os.path.dirname(questions_json_path), exist_ok=True)
    data = {}
    if os.path.exists(questions_json_path):
        try:
            with open(questions_json_path, "r", encoding="utf-8") as f:
                data = _json.load(f)
        except Exception:
            data = {}
    data[question.strip()] = answer
    with open(questions_json_path, "w", encoding="utf-8") as f:
        _json.dump(data, f, indent=2, ensure_ascii=False)


def gemini_answer_question(model, question: str, options: list | None = None,
                            question_type: str = "text",
                            job_description: str = None, about_company: str = None,
                            user_information_all: str = None,
                            non_interactive: bool = False) -> str:
    """Answer a form question using Gemini AI."""
    try:
        log_message(f"Answering question using Gemini AI: {question}")
        user_info = user_information_all or ""
        past_questions_str = _load_past_questions()

        prompt = ai_answer_prompt.format(user_info, past_questions_str, question)
        if options and question_type in ["single_select", "multiple_select", "choice"]:
            options_str = "OPTIONS:\n" + "\n".join([f"- {o}" for o in options])
            prompt += f"\n\n{options_str}"
            prompt += ("\n\nPlease select exactly ONE option from the list above."
                       if question_type in ["single_select", "choice"]
                       else "\n\nYou may select MULTIPLE options from the list above if appropriate.")
        if job_description:
            prompt += f"\n\nJOB DESCRIPTION:\n{job_description}"
        if about_company:
            prompt += f"\n\nABOUT COMPANY:\n{about_company}"

        if non_interactive:
            prompt += "\n\nCRITICAL: Do NOT return 'ask user'. You MUST make a best guess based on the profile, previously answered questions, or context. If no information is present, output a standard positive default (e.g., 'Yes' for yes/no questions, '21' for notice period, '4' for experience, '1400000' for expected CTC)."

        res = gemini_completion(model, prompt)
        if isinstance(res, dict) and "error" in res:
            return "ask user"
        answer = str(res)
        if answer.lower() != "ask user":
            _save_answered_question(question, answer)
        return answer
    except Exception as e:
        log_message(f"Error answering question with Gemini: {e}")
        return "ask user"


# ════════════════════════════════════════════════════════════════════
# 4. SELENIUM SETUP
# ════════════════════════════════════════════════════════════════════

def build_chrome_options(config: Config):
    """Build ChromeOptions for standard chromedriver."""
    stealth = config.stealth_mode
    headless = config.headless

    if stealth:
        try:
            import undetected_chromedriver as uc
            options = uc.ChromeOptions()
        except ImportError:
            log_message("Warning: 'undetected_chromedriver' not installed. Falling back to standard Selenium.")
            stealth = False
            options = Options()
    else:
        options = Options()

    options.add_argument("--disable-popup-blocking")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--start-maximized")

    if headless:
        options.add_argument("--headless")

    return options, stealth


def get_chrome_driver(config: Config):
    """Initialize and return a Chrome webdriver session with robust fallback mechanisms."""
    log_message("Starting Chrome setup...")

    driver_executable_path = None
    if sys.platform.startswith("win"):
        appdata = os.environ.get("APPDATA", "")
        path_candidate = os.path.join(appdata, "undetected_chromedriver", "undetected_chromedriver.exe")
        if os.path.exists(path_candidate):
            driver_executable_path = path_candidate
            log_message(f"Found cached ChromeDriver: {driver_executable_path}")

    options, stealth = build_chrome_options(config)

    # 1. Attempt stealth mode with use_subprocess=False (prevents WinError 6 in many environments)
    if stealth:
        try:
            import undetected_chromedriver as uc
            log_message("Attempting undetected-chromedriver with use_subprocess=False...")
            if driver_executable_path:
                driver = uc.Chrome(options=options, driver_executable_path=driver_executable_path, use_subprocess=False)
            else:
                driver = uc.Chrome(options=options, use_subprocess=False)
            log_message("Chrome driver (stealth, use_subprocess=False) successfully initialized!")
            return driver
        except Exception as e1:
            log_message(f"Stealth initialization with use_subprocess=False failed: {e1}")

        # 2. Attempt stealth mode with default subprocess options
        try:
            import undetected_chromedriver as uc
            log_message("Attempting undetected-chromedriver (default)...")
            if driver_executable_path:
                driver = uc.Chrome(options=options, driver_executable_path=driver_executable_path)
            else:
                driver = uc.Chrome(options=options)
            log_message("Chrome driver (stealth, default) successfully initialized!")
            return driver
        except Exception as e2:
            log_message(f"Stealth initialization failed: {e2}")

    # 3. Fallback to standard Selenium webdriver
    log_message("Falling back to standard Selenium Chrome driver...")
    try:
        from selenium.webdriver.chrome.options import Options as StdOptions
        std_options = StdOptions()
        std_options.add_argument("--disable-popup-blocking")
        std_options.add_argument("--no-sandbox")
        std_options.add_argument("--disable-dev-shm-usage")
        std_options.add_argument("--start-maximized")
        if config.headless:
            std_options.add_argument("--headless")

        driver = webdriver.Chrome(options=std_options)
        log_message("Standard Chrome driver successfully initialized!")
        return driver
    except Exception as e:
        log_message(f"Unhandled error starting Chrome driver: {e}")
        raise e


# ════════════════════════════════════════════════════════════════════
# 5. NAUKRI AUTOMATION
# ════════════════════════════════════════════════════════════════════
#
# NOTE ON SELECTORS:
# Naukri's DOM/CSS classes change periodically. The selectors below reflect
# commonly-used Naukri markup patterns at time of writing, but you MUST verify
# them against the live site (right-click an element -> Inspect) before
# relying on this for unattended runs. Update the *_SEL constants below if
# something stops matching — you should not need to touch the logic itself.

NAUKRI_LOGIN_URL = "https://www.naukri.com/nlogin/login"

# Naukri's real search URL embeds BOTH the keyword and (if set) the primary
# city in the path slug, then repeats them as query params, e.g.:
#   https://www.naukri.com/java-developer-jobs-in-pune?k=java+developer&l=pune&experience=4
#   https://www.naukri.com/data-jobs?k=data&wfhType=2&jobAge=30
#   https://www.naukri.com/data-jobs?k=data&ctcFilter=6to10
# Confirmed against real captured Naukri search URLs (incl. multi-city
# "l=bengaluru, hyderabad" and freshness via jobAge, salary via ctcFilter).
NAUKRI_SEARCH_URL_TEMPLATE = "https://www.naukri.com/{slug}-jobs"

# Naukri's "posted within" filter uses the jobAge query param, in days.
FRESHNESS_DAY_MAP = {
    "last 1 day": "1",
    "last 3 days": "3",
    "last 7 days": "7",
    "last 15 days": "15",
    "last 30 days": "30",
}

# Naukri's salary sidebar filter uses ctcFilter band strings like this.
# Map your personal.json "salary" filter entries (e.g. "10-15 Lakhs") to these.
SALARY_BAND_MAP = {
    "0-3 lakhs": "0to3",
    "3-6 lakhs": "3to6",
    "6-10 lakhs": "6to10",
    "10-15 lakhs": "10to15",
    "15-25 lakhs": "15to25",
    "25-50 lakhs": "25to50",
    "50-75 lakhs": "50to75",
    "75-100 lakhs": "75to100",
}

# Naukri's work-mode sidebar filter ("on_site" in personal.json) uses wfhType.
WFH_TYPE_MAP = {
    "remote": "2",
    "hybrid": "3",
    "work from office": "0",
}

LOGIN_USERNAME_SEL = (By.ID, "usernameField")
LOGIN_PASSWORD_SEL = (By.ID, "passwordField")
LOGIN_SUBMIT_SEL = (By.XPATH, "//button[@type='submit']")

JOB_CARD_SEL = (By.CSS_SELECTOR, "div.srp-jobtuple-wrapper")
JOB_TITLE_LINK_SEL = (By.CSS_SELECTOR, "a.title")
JOB_COMPANY_SEL = (By.CSS_SELECTOR, "a.comp-name")

APPLY_BUTTON_SEL = (By.ID, "apply-button")
EASY_APPLY_TEXT = "apply"  # button text fragment check, case-insensitive
# Sidebar "Easy Apply" filter checkbox — unverified against the live DOM,
# update after inspecting Naukri's filter sidebar (right-click -> Inspect).
EASY_APPLY_CHECKBOX_SEL = (By.XPATH, "//*[contains(translate(text(), 'EASY APPLY', 'easy apply'), 'easy apply')]")

# "Apply on company site" — Naukri's external-ATS apply button. Distinct from
# APPLY_BUTTON_SEL (id="apply-button", Naukri's own Easy Apply / native apply).
# This button text is fairly stable on Naukri's job-detail page; matched by
# text fragment rather than id since no stable id has been confirmed for it.
EXTERNAL_APPLY_BUTTON_SEL = (By.XPATH, (
    "//button[contains(translate(normalize-space(.), "
    "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'apply on company site')] | "
    "//a[contains(translate(normalize-space(.), "
    "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'apply on company site')]"
))

CHATBOT_QUESTION_SEL = (By.CSS_SELECTOR, "div.chatbot_MessageContainer span, .chatbot_MessageContainer span, .chatbot_MessageContainer, div.chatbot_Question, .chatbot_Question, .chatbot-question, .chatbot_Message, div.chat-message-text")
# Explicitly exclude file/hidden/submit/button/reset/image/radio/checkbox inputs — only target text-like inputs and textareas
CHATBOT_INPUT_SEL = (By.CSS_SELECTOR, (
    "div.chatbot_InputContainer textarea, "
    "div.chatbot_InputContainer input:not([type='file']):not([type='hidden']):not([type='submit']):not([type='button']):not([type='reset']):not([type='image']):not([type='radio']):not([type='checkbox']), "
    "textarea[placeholder*='Type'], "
    "input[placeholder*='Type']:not([type='file']):not([type='hidden']):not([type='submit']):not([type='button']):not([type='reset']):not([type='image']):not([type='radio']):not([type='checkbox']), "
    "textarea, "
    "input[type='text'], input[type='number'], input[type='email'], input[type='tel'], "
    "div[contenteditable='true'], span[contenteditable='true'], [contenteditable='true']"
))
CHATBOT_OPTION_SEL = (By.XPATH, (
    "//div[contains(@class, 'chatbot')]//label | "
    "//div[contains(@class, 'chatbot')]//button | "
    "//div[contains(@class, 'chatbot')]//*[contains(@class, 'option') or contains(@class, 'Option') or contains(@class, 'SingleSelect') or contains(@class, 'chip') or contains(@class, 'choice')] | "
    "//*[contains(@class, 'SingleSelect')] | "
    "//*[contains(@class, 'option')] | "
    "//*[contains(@class, 'Option')]"
))
CHATBOT_SEND_SEL = (By.CSS_SELECTOR, "div.chatbot_SendMsgIcon, button.sendMsg, svg[class*='send'], button[class*='send'], .sendMsg")

APPLICATION_SUCCESS_TEXT_FRAGMENTS = [
    "application has been sent",
    "successfully applied",
    "you have already applied",
]


def naukri_login(driver, config: Config, wait_seconds: int = 20) -> bool:
    """Logs into Naukri using credentials from config. Returns True on success."""
    log_message("Navigating to Naukri login page...")
    driver.get(NAUKRI_LOGIN_URL)
    wait = WebDriverWait(driver, wait_seconds)

    try:
        username_field = wait.until(EC.presence_of_element_located(LOGIN_USERNAME_SEL))
        password_field = driver.find_element(*LOGIN_PASSWORD_SEL)

        username_field.clear()
        username_field.send_keys(config.naukri_username)
        password_field.clear()
        password_field.send_keys(config.naukri_password)

        driver.find_element(*LOGIN_SUBMIT_SEL).click()
        log_message("Submitted login form. Waiting for homepage to load...")

        try:
            wait.until(EC.url_contains("mnjuser"))
        except TimeoutException:
            wait.until(EC.title_contains("Naukri"))
        time.sleep(3)
        log_message("Login appears successful.")
        return True

    except TimeoutException:
        log_message("[ERROR] Timed out waiting for login page elements. "
                    "Naukri may show a captcha — log in manually once to clear it.")
        return False
    except Exception as e:
        log_message(f"[ERROR] Login failed: {e}")
        return False


def _slugify(text: str) -> str:
    """Converts free text into Naukri's URL-slug format,
    e.g. 'Java Full Stack Developer' -> 'java-full-stack-developer'."""
    import re
    slug = text.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def build_search_url(config: Config, search_term: str) -> str:
    """Builds a Naukri search-results URL for one search term, applying every
    filter from personal.json that Naukri's URL format supports:
      - keyword            -> slug + k=
      - location           -> slug suffix "-in-<city>" + l=
      - experience         -> experience=
      - freshness          -> jobAge= (days)
      - salary band        -> ctcFilter= (repeated per band)
      - on_site / work mode-> wfhType=
    Filters Naukri doesn't expose via URL (department, role_category,
    education, posted_by, industry, top_companies, company_type, job_type)
    are not applied here — see the NOTE above search_jobs() for why.
    """
    from urllib.parse import urlencode

    keyword_slug = _slugify(search_term) or "jobs"
    location = config.search_location
    location_slug = f"-in-{_slugify(location)}" if location else ""
    slug = f"{keyword_slug}{location_slug}"
    base_url = NAUKRI_SEARCH_URL_TEMPLATE.format(slug=slug)

    params = []  # list of tuples so repeated keys (ctcFilter) are preserved
    params.append(("k", search_term.strip() or "jobs"))

    if location:
        params.append(("l", location))

    exp = config.search_experience
    if exp:
        params.append(("experience", exp))

    freshness_key = config.freshness.strip().lower()
    if freshness_key in FRESHNESS_DAY_MAP:
        params.append(("jobAge", FRESHNESS_DAY_MAP[freshness_key]))

    for band in config.salary_bands:
        band_key = band.strip().lower()
        if band_key in SALARY_BAND_MAP:
            params.append(("ctcFilter", SALARY_BAND_MAP[band_key]))
        else:
            log_message(f"[WARN] Unrecognized salary band '{band}' in filters.salary — skipping. "
                        f"Valid values: {list(SALARY_BAND_MAP.keys())}")

    for mode in config.on_site_modes:
        mode_key = mode.strip().lower()
        if mode_key in WFH_TYPE_MAP:
            params.append(("wfhType", WFH_TYPE_MAP[mode_key]))
        else:
            log_message(f"[WARN] Unrecognized on_site value '{mode}' in filters.on_site — skipping. "
                        f"Valid values: {list(WFH_TYPE_MAP.keys())}")

    return f"{base_url}?{urlencode(params)}"


# NOTE ON FILTERS NAUKRI DOESN'T EXPOSE VIA URL:
# easy_apply, department, role_category, education, posted_by, industry,
# top_companies, and company_type either don't have a confirmed public query
# parameter, or Naukri applies them via sidebar checkboxes whose underlying
# param names aren't documented anywhere I could verify. Rather than guess
# wrong param names again (which is what broke this earlier), apply_sidebar_
# filters() below clicks the actual sidebar checkbox in the browser for
# easy_apply after the page loads. The rest remain unapplied — if you need
# them, the most reliable fix is: perform the search + filter manually once
# on naukri.com, copy the resulting URL, and tell me what query params it
# added for that filter so I can wire it in correctly.
def apply_sidebar_filters(driver, config: Config, wait_seconds: int = 8) -> None:
    """Clicks sidebar filter checkboxes that aren't reliably controllable via
    URL query params alone (currently: Easy Apply)."""
    if not config.easy_apply:
        return
    try:
        wait = WebDriverWait(driver, wait_seconds)
        checkbox = wait.until(EC.element_to_be_clickable(EASY_APPLY_CHECKBOX_SEL))
        is_checked = "true" in (checkbox.get_attribute("aria-checked") or "").lower()
        if not is_checked:
            try:
                checkbox.click()
            except ElementClickInterceptedException:
                driver.execute_script("arguments[0].click();", checkbox)
            log_message("Applied 'Easy Apply' sidebar filter.")
            time.sleep(2)
    except TimeoutException:
        log_message("[WARN] Could not find the 'Easy Apply' sidebar checkbox — "
                    "selector may be stale, verify EASY_APPLY_CHECKBOX_SEL against the live page.")
    except Exception as e:
        log_message(f"[WARN] Failed applying 'Easy Apply' sidebar filter: {e}")


def search_jobs(driver, config: Config, search_term: str, wait_seconds: int = 20) -> None:
    url = build_search_url(config, search_term)
    log_message(f"Navigating to job search results for '{search_term}': {url}")
    driver.get(url)

    # Detect Naukri's own 404 page so a bad slug/URL fails loudly instead of
    # silently returning zero job cards.
    try:
        page_title = driver.title or ""
        body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
        if "404" in page_title or "page not found" in body_text or "error 404" in body_text:
            log_message(f"[ERROR] Naukri returned a 404 for this search URL: {url}")
            log_message("[ERROR] The slug or query format may have changed — "
                        "open this URL manually in a browser to confirm Naukri's current search format.")
            return
    except Exception:
        pass

    wait = WebDriverWait(driver, wait_seconds)
    try:
        wait.until(EC.presence_of_element_located(JOB_CARD_SEL))
        log_message("Job listings loaded.")
    except TimeoutException:
        log_message("[WARN] No job cards found with current selector — "
                    "the search page layout may have changed, or there are no results.")
        return

    apply_sidebar_filters(driver, config)


def collect_job_cards(driver) -> list:
    try:
        return driver.find_elements(*JOB_CARD_SEL)
    except Exception as e:
        log_message(f"Error collecting job cards: {e}")
        return []


def _normalize_question(q: str) -> str:
    """Normalizes a question string for fuzzy matching: lowercase, strip, collapse whitespace."""
    import re
    return re.sub(r'\s+', ' ', q.strip().lower())


def get_exact_saved_answer(question: str) -> str | None:
    """Checks for a match of the question in config/questions.json.
    Match priority: 1. exact string  2. case-insensitive  3. normalized whitespace.
    Returns the answer if found, otherwise None."""
    try:
        questions_json_path = os.path.join("config", "questions.json")
        if os.path.exists(questions_json_path):
            with open(questions_json_path, "r", encoding="utf-8") as f:
                q_data = json.load(f)
                if q_data:
                    q_stripped = question.strip()
                    q_lower = q_stripped.lower()
                    q_norm = _normalize_question(q_stripped)

                    # 1. Exact match check
                    if q_stripped in q_data:
                        log_message(f"[Q-MATCH] Exact match found for: '{q_stripped[:60]}'")
                        return q_data[q_stripped]

                    # 2. Case-insensitive match check on stripped strings
                    for k, v in q_data.items():
                        if k.strip().lower() == q_lower:
                            log_message(f"[Q-MATCH] Case-insensitive match found for: '{q_stripped[:60]}'")
                            return v

                    # 3. Normalized whitespace match (handles extra spaces/newlines in DOM text)
                    for k, v in q_data.items():
                        if _normalize_question(k) == q_norm:
                            log_message(f"[Q-MATCH] Normalized match found for: '{q_stripped[:60]}'")
                            return v
    except Exception as e:
        log_message(f"Error checking questions.json for exact match: {e}")
    return None


def guess_question_answer(question_text: str, option_texts: list, config: Config) -> str:
    """Provides a programmatic best guess for screening questions in non-interactive mode."""
    q_lower = question_text.lower()

    # 1. Option-based guessing (radio / chips / checkboxes)
    if option_texts:
        # Check for Yes / No questions
        has_yes = any(o.strip().lower() in ("yes", "y") for o in option_texts)
        has_no = any(o.strip().lower() in ("no", "n") for o in option_texts)

        if has_yes and has_no:
            # relational/bond constraints -> usually "No"
            if "bond" in q_lower or "agreement" in q_lower or "contractual obligation" in q_lower:
                for o in option_texts:
                    if o.strip().lower() in ("no", "n"):
                        return o
            # default relocation / readiness questions -> usually "Yes"
            for o in option_texts:
                if o.strip().lower() in ("yes", "y"):
                    return o

        # Relocation questions
        if "relocate" in q_lower or "willing to relocate" in q_lower or "open to relocate" in q_lower:
            for o in option_texts:
                if o.strip().lower() in ("yes", "y", "relocate"):
                    return o

        # Education / Degree questions
        if "degree" in q_lower or "education" in q_lower or "qualification" in q_lower or "btech" in q_lower or "b.e" in q_lower:
            for o in option_texts:
                if any(x in o.lower() for x in ("b.e", "b.tech", "be", "btech", "degree", "graduate", "mca", "m.tech", "post graduate")):
                    return o

        # Notice period option matching
        if "notice" in q_lower or "period" in q_lower or "join" in q_lower:
            for o in option_texts:
                if "immediate" in o.lower() or "15 days" in o.lower() or "30 days" in o.lower() or "1 month" in o.lower():
                    return o

        # If no smart match, default to first option
        return option_texts[0]

    # 2. Text-based guessing
    # Notice Period
    if "notice" in q_lower or "period" in q_lower or "join" in q_lower or "days required" in q_lower:
        return str(config.notice_period_days)

    # Salary / CTC
    if "ctc" in q_lower or "salary" in q_lower or "expected" in q_lower or "compensation" in q_lower:
        if "lpa" in q_lower or "lakhs" in q_lower:
            val = config.desired_salary / 100000
            return str(int(val))
        return str(config.desired_salary)

    # Experience
    if "experience" in q_lower or "years" in q_lower or "exp" in q_lower:
        return str(config.experience_years)

    # Location / City
    if "location" in q_lower or "city" in q_lower or "reside" in q_lower or "current address" in q_lower:
        return config.current_city

    # Phone number
    if "phone" in q_lower or "mobile" in q_lower or "contact" in q_lower or "number" in q_lower:
        return config.phone_number

    # Name
    if "first name" in q_lower:
        return config.first_name
    if "last name" in q_lower:
        return config.last_name
    if "full name" in q_lower or "name" in q_lower:
        return f"{config.first_name} {config.last_name}"

    # Default description
    if "why" in q_lower or "describe" in q_lower or "skills" in q_lower or "summary" in q_lower:
        return "Experienced Java Full Stack Developer with 4+ years of expertise in Spring Boot, Microservices, and RESTful APIs, looking to contribute to scalable solutions."

    return "Yes"


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
            # Match not found: prompt the user for input and do not automatically input anything
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
    Opens a single job card (usually in a new tab), attempts to apply, answers
    any screening questions, and returns a result dict for CSV logging.

    Handles two distinct apply paths found on Naukri job-detail pages:
      - Native/Easy Apply  (APPLY_BUTTON_SEL, id="apply-button") -> handled
        in-page via handle_chatbot_question(), as before.
      - "Apply on company site" (EXTERNAL_APPLY_BUTTON_SEL) -> hands off to
        apply_on_company_site() in section 6, which follows through to the
        third-party ATS tab and attempts a generic form fill there.
    """
    result = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "job_title": "",
        "company": "",
        "status": "",
        "notes": "",
    }

    try:
        title_elem = card.find_element(*JOB_TITLE_LINK_SEL)
        result["job_title"] = title_elem.text.strip()
    except NoSuchElementException:
        result["job_title"] = "Unknown"

    try:
        company_elem = card.find_element(*JOB_COMPANY_SEL)
        result["company"] = company_elem.text.strip()
    except NoSuchElementException:
        result["company"] = "Unknown"

    log_message(f"Opening job: {result['job_title']} @ {result['company']}")

    main_window = driver.current_window_handle
    try:
        title_elem.click()
    except Exception:
        driver.execute_script("arguments[0].click();", title_elem)

    time.sleep(2)

    # Naukri often opens the job detail in a new tab
    all_windows = driver.window_handles
    job_window = all_windows[-1] if len(all_windows) > 1 else main_window
    driver.switch_to.window(job_window)

    wait = WebDriverWait(driver, wait_seconds)
    job_description = ""
    about_company = ""
    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text
        job_description = body_text[:4000]  # rough capture for AI context
    except Exception:
        pass

    # Decide which apply path this job-detail page offers. Native Easy Apply
    # takes priority if both happen to be present; otherwise fall back to the
    # external "Apply on company site" path.
    native_btn = None
    external_btn = None
    try:
        native_btn = WebDriverWait(driver, 4).until(EC.element_to_be_clickable(APPLY_BUTTON_SEL))
    except TimeoutException:
        native_btn = None
    if native_btn is None:
        try:
            external_btn = WebDriverWait(driver, 4).until(EC.element_to_be_clickable(EXTERNAL_APPLY_BUTTON_SEL))
        except TimeoutException:
            external_btn = None

    try:
        if native_btn is not None:
            btn_text = native_btn.text.strip().lower()

            if "already applied" in btn_text:
                result["status"] = "already_applied"
                log_message("Already applied to this job — skipping.")
            else:
                try:
                    native_btn.click()
                except ElementClickInterceptedException:
                    driver.execute_script("arguments[0].click();", native_btn)

                time.sleep(2)

                # Some applies are instant; others trigger Naukri's chatbot questionnaire.
                completed = handle_chatbot_question(
                    driver, model, config,
                    job_title=result["job_title"],
                    job_description=job_description,
                    about_company=about_company,
                )

                time.sleep(1.5)
                page_text_lower = driver.find_element(By.TAG_NAME, "body").text.lower()
                if any(frag in page_text_lower for frag in APPLICATION_SUCCESS_TEXT_FRAGMENTS):
                    result["status"] = "applied"
                elif completed:
                    result["status"] = "applied"
                else:
                    result["status"] = "needs_manual_review"
                    result["notes"] = "Chatbot flow stalled or needs manual attention."

        elif external_btn is not None:
            log_message("Detected 'Apply on company site' button — handing off to external apply flow.")
            ext_result = apply_on_company_site(
                driver, model, config,
                external_btn=external_btn,
                job_title=result["job_title"],
                company=result["company"],
                main_window=main_window,
                job_window=job_window,
                job_description=job_description,
            )
            result["status"] = ext_result["status"]
            result["notes"] = ext_result["notes"]
            # apply_on_company_site() may have switched windows/tabs around;
            # re-resolve job_window/main_window references below regardless.

        else:
            result["status"] = "failed"
            result["notes"] = "Neither native Apply nor 'Apply on company site' button found (selectors may be stale)."
            log_message(f"[WARN] {result['notes']}")

    except TimeoutException:
        result["status"] = "failed"
        result["notes"] = "Apply button not found/clickable (selector may be stale, or job uses external apply)."
        log_message(f"[WARN] {result['notes']}")
    except Exception as e:
        result["status"] = "failed"
        result["notes"] = str(e)[:200]
        log_message(f"[ERROR] Unexpected error applying to job: {e}")

    # Close any extra tabs opened along the way, return to the listing tab.
    try:
        while len(driver.window_handles) > 1 and main_window in driver.window_handles:
            current_handles = driver.window_handles
            extra = [h for h in current_handles if h != main_window]
            if not extra:
                break
            driver.switch_to.window(extra[-1])
            try:
                driver.close()
            except Exception:
                break
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
    success_statuses = ("applied", "already_applied", "applied_external")
    target_file = config.file_name if result["status"] in success_statuses else config.failed_file_name
    append_csv_row(target_file, result)
    log_message(f"Logged result to: {target_file} ({result['status']})")


# ════════════════════════════════════════════════════════════════════
# 6. EXTERNAL / COMPANY-SITE APPLY
# ════════════════════════════════════════════════════════════════════
#
# IMPORTANT CONTEXT — read before tuning this section:
#
# "Apply on company site" sends the candidate to a third-party page that
# could be almost anything: a Workday/Taleo/SuccessFactors/iCIMS portal, a
# Greenhouse/Lever/SmartRecruiters board, or a fully custom in-house careers
# page. There is no single DOM contract across these, so everything here is
# *heuristic, best-effort* matching by visible text, label text, name/id/
# placeholder attributes, and input types — not a guaranteed-correct parser.
#
# Decisions baked in per your instructions:
#   - If the destination requires account creation / login before the
#     application form is reachable -> SKIP the job entirely (status:
#     "skipped_login_required"). Never attempts to fill a signup/login form.
#   - Resume file (personal.resume_path) is auto-attached to any file input
#     that looks like a resume/CV upload field.
#   - If the company's own board shows multiple job listings, only an EXACT
#     (case-insensitive, whitespace-normalized) title match is clicked. If no
#     exact match is found, the job is logged as "needs_manual_review" rather
#     than guessing at the wrong listing.
#   - Every question seen on the external form is checked against
#     config/questions.json first (same store the Naukri chatbot uses), then
#     falls back to Gemini AI (if use_AI) or a manual topmost prompt — reusing
#     gemini_answer_question() / prompt_topmost() so answers stay consistent
#     and get persisted for next time.

EXTERNAL_RESUME_FIELD_HINTS = (
    "resume", "cv", "curriculum vitae", "attach resume", "upload resume", "upload cv",
)

EXTERNAL_LOGIN_WALL_HINTS = (
    "create account", "sign up", "sign in", "log in", "login", "register",
    "create a profile", "create your profile", "i already have an account",
    "forgot password", "set a password", "create password",
)

# Generic "this is an application form" signal — used to confirm we landed
# somewhere worth filling rather than a marketing/job-description page.
EXTERNAL_FORM_PRESENCE_HINTS = (
    "apply for this job", "submit application", "application form", "personal information",
)

EXTERNAL_SUBMIT_BUTTON_HINTS = (
    "submit application", "submit", "apply now", "send application", "review and submit",
    "finish application", "apply",
)

EXTERNAL_JOB_LISTING_SEL = (By.XPATH, (
    "//a[contains(@href, 'job') or contains(@href, 'requisition') or contains(@href, 'position')] | "
    "//*[contains(@class, 'job-title') or contains(@class, 'jobTitle') or contains(@class, 'posting-title')]"
))


def _page_text_lower(driver) -> str:
    try:
        return driver.find_element(By.TAG_NAME, "body").text.lower()
    except Exception:
        return ""


def _detect_login_wall(driver) -> bool:
    """Best-effort check for whether the current page requires creating an
    account or logging in before an application can be submitted.
    Looks for password fields (strong signal) plus login/signup phrasing."""
    try:
        password_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
        if password_inputs and any(p.is_displayed() for p in password_inputs):
            return True
    except Exception:
        pass

    text = _page_text_lower(driver)
    hits = sum(1 for hint in EXTERNAL_LOGIN_WALL_HINTS if hint in text)
    # Require at least one hit AND absence of generic form-presence language,
    # to avoid false-positives on pages that merely mention "sign in with
    # LinkedIn to autofill" as an optional convenience.
    return hits > 0 and not any(h in text for h in EXTERNAL_FORM_PRESENCE_HINTS)


def _looks_like_job_listing_page(driver) -> bool:
    """Heuristic: a company's own job board/search page (multiple postings)
    vs. a direct single-job application form."""
    try:
        candidates = driver.find_elements(*EXTERNAL_JOB_LISTING_SEL)
        visible_candidates = [c for c in candidates if c.is_displayed() and c.text.strip()]
        return len(visible_candidates) >= 2
    except Exception:
        return False


def _normalize_title(text: str) -> str:
    import re
    return re.sub(r"\s+", " ", text.strip().lower())


def _find_and_click_matching_job_listing(driver, job_title: str, wait_seconds: int = 10) -> bool:
    """On a company job-board/listing page, find the posting whose title is
    an EXACT match (case-insensitive, whitespace-normalized) to job_title and
    click it. Returns True if a match was found and clicked, False otherwise."""
    target = _normalize_title(job_title)
    if not target:
        return False

    wait = WebDriverWait(driver, wait_seconds)
    try:
        wait.until(EC.presence_of_element_located(EXTERNAL_JOB_LISTING_SEL))
    except TimeoutException:
        log_message("[WARN] No job listing links found on company board within timeout.")
        return False

    candidates = driver.find_elements(*EXTERNAL_JOB_LISTING_SEL)
    for el in candidates:
        try:
            if not el.is_displayed():
                continue
            el_text = _normalize_title(el.text)
            if el_text == target:
                log_message(f"Exact title match found on company board: '{el.text.strip()}'")
                try:
                    el.click()
                except (ElementClickInterceptedException, Exception):
                    driver.execute_script("arguments[0].click();", el)
                time.sleep(2)
                return True
        except StaleElementReferenceException:
            continue
        except Exception:
            continue

    log_message(f"[WARN] No EXACT title match for '{job_title}' found among "
                f"{len(candidates)} listing(s) on company board. Will not guess.")
    return False


def _collect_external_form_fields(driver) -> list:
    """Collects visible, fillable form fields (text-like inputs, textareas,
    selects, and radio/checkbox groups) along with a best-guess label for
    each, using <label for>, aria-label, placeholder, name, and preceding
    text as fallbacks, in that priority order."""
    fields = []
    try:
        elements = driver.find_elements(
            By.CSS_SELECTOR,
            "input:not([type='hidden']):not([type='submit']):not([type='button']):not([type='reset']):not([type='image']), "
            "textarea, select"
        )
    except Exception:
        elements = []

    for el in elements:
        try:
            if not el.is_displayed():
                continue
            el_type = (el.get_attribute("type") or "text").lower()
            el_tag = el.tag_name.lower()

            label_text = ""
            el_id = el.get_attribute("id")
            if el_id:
                try:
                    label_el = driver.find_element(By.CSS_SELECTOR, f"label[for='{el_id}']")
                    label_text = label_el.text.strip()
                except Exception:
                    pass
            if not label_text:
                label_text = (el.get_attribute("aria-label") or "").strip()
            if not label_text:
                label_text = (el.get_attribute("placeholder") or "").strip()
            if not label_text:
                # Fall back to nearest preceding text via simple DOM walk.
                try:
                    parent = el.find_element(By.XPATH, "./..")
                    label_text = parent.text.strip().split("\n")[0][:120]
                except Exception:
                    pass
            if not label_text:
                label_text = (el.get_attribute("name") or "").strip()

            fields.append({
                "element": el,
                "tag": el_tag,
                "type": el_type,
                "label": label_text or "(unlabeled field)",
            })
        except StaleElementReferenceException:
            continue
        except Exception:
            continue

    return fields


def _is_resume_field(field: dict) -> bool:
    if field["type"] != "file":
        return False
    label_lower = field["label"].lower()
    return any(hint in label_lower for hint in EXTERNAL_RESUME_FIELD_HINTS) or not label_lower or label_lower == "(unlabeled field)"


def _answer_external_question(question_label: str, model, config: Config,
                               job_title: str, job_description: str,
                               options: list | None = None) -> str | None:
    """Resolves an answer for one external-form field label, in priority order:
    1. config/questions.json exact/fuzzy match (shared store with Naukri chatbot)
    2. Gemini AI (if config.use_AI and a model is available)
    3. Manual topmost prompt (with notification sound), same as Naukri flow
    Returns None if the user cancels the manual prompt (caller should treat
    that job as needs_manual_review / abort this form)."""
    saved = get_exact_saved_answer(question_label)
    if saved is not None:
        log_message(f"[EXTERNAL] Using saved answer for '{question_label[:60]}': '{saved}'")
        return saved

    if config.use_AI and model is not None:
        question_type = "single_select" if options else "text"
        ai_answer = gemini_answer_question(
            model, question_label,
            options=options, question_type=question_type,
            job_description=job_description,
            user_information_all=config.user_information_all,
            non_interactive=config.non_interactive,
        )
        if ai_answer and ai_answer.strip().lower() != "ask user":
            log_message(f"[EXTERNAL] Gemini answered '{question_label[:60]}': '{ai_answer}'")
            return ai_answer
        log_message(f"[EXTERNAL] Gemini returned 'ask user' for '{question_label[:60]}' — falling back to manual prompt.")

    play_notification_sound(config)
    manual_answer = prompt_topmost(
        text=question_label,
        title=f"Company site question — {job_title}",
        default="",
    )
    if manual_answer is None:
        log_message("[EXTERNAL] User cancelled manual prompt.")
        return None
    _save_answered_question(question_label, manual_answer)
    return manual_answer


def _fill_external_field(driver, field: dict, answer: str) -> bool:
    """Fills a single resolved field with the given answer, handling text
    inputs/textareas, select dropdowns, and radio/checkbox groups generically."""
    el = field["element"]
    tag = field["tag"]
    el_type = field["type"]

    try:
        try:
            el.click()
        except Exception:
            driver.execute_script("arguments[0].click();", el)

        if tag == "select":
            from selenium.webdriver.support.ui import Select
            select = Select(el)
            answer_lower = answer.strip().lower()
            for opt in select.options:
                if opt.text.strip().lower() == answer_lower:
                    select.select_by_visible_text(opt.text)
                    return True
            for opt in select.options:
                if answer_lower in opt.text.strip().lower():
                    select.select_by_visible_text(opt.text)
                    return True
            log_message(f"[EXTERNAL] No matching <option> for '{answer}' in select '{field['label'][:60]}'.")
            return False

        if el_type in ("radio", "checkbox"):
            # Single radio/checkbox element passed directly — click if the
            # answer affirms it (Yes/the field's own label matches answer).
            answer_lower = answer.strip().lower()
            if answer_lower in ("yes", "y", "true", "1") or answer_lower in field["label"].lower():
                el.click()
                return True
            return False

        # Text-like input or textarea
        try:
            el.clear()
        except Exception:
            pass
        el.send_keys(answer)
        return True

    except Exception as e:
        log_message(f"[EXTERNAL] Failed filling field '{field['label'][:60]}': {e}")
        try:
            driver.execute_script(
                "arguments[0].value = arguments[1]; "
                "arguments[0].dispatchEvent(new Event('input', { bubbles: true })); "
                "arguments[0].dispatchEvent(new Event('change', { bubbles: true }));",
                el, answer
            )
            return True
        except Exception as e2:
            log_message(f"[EXTERNAL] JS fallback fill also failed: {e2}")
            return False


def _attach_resume_file(field: dict, config: Config) -> bool:
    resume_path = config.resume_path
    if not resume_path:
        log_message("[EXTERNAL] No resume_path configured — cannot auto-attach resume.")
        return False
    if not os.path.exists(resume_path):
        log_message(f"[EXTERNAL] resume_path does not exist on disk: {resume_path}")
        return False
    try:
        field["element"].send_keys(os.path.abspath(resume_path))
        log_message(f"[EXTERNAL] Attached resume file: {resume_path}")
        time.sleep(1.5)
        return True
    except Exception as e:
        log_message(f"[EXTERNAL] Failed to attach resume file: {e}")
        return False


def _click_external_submit(driver) -> bool:
    """Finds and clicks a submit/apply button on the external form by text
    match. Tries the most specific phrasing first."""
    for hint in EXTERNAL_SUBMIT_BUTTON_HINTS:
        try:
            xpath = (
                f"//button[contains(translate(normalize-space(.), "
                f"'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{hint}')] | "
                f"//input[@type='submit' and contains(translate(@value, "
                f"'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{hint}')] | "
                f"//a[contains(translate(normalize-space(.), "
                f"'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{hint}')]"
            )
            buttons = driver.find_elements(By.XPATH, xpath)
            visible = [b for b in buttons if b.is_displayed()]
            if visible:
                btn = visible[0]
                try:
                    btn.click()
                except ElementClickInterceptedException:
                    driver.execute_script("arguments[0].click();", btn)
                log_message(f"[EXTERNAL] Clicked submit button matching '{hint}'.")
                return True
        except Exception:
            continue
    log_message("[WARN] [EXTERNAL] Could not find a submit/apply button to finalize the external application.")
    return False


def fill_external_application_form(driver, model, config: Config, job_title: str,
                                    job_description: str, max_fields: int = 40) -> dict:
    """
    Generic best-effort form filler for a third-party ATS / company careers
    page. Walks visible form fields, resolves each via questions.json -> AI
    -> manual prompt, fills them, attaches resume to file inputs, then
    attempts to click submit.

    Returns a dict: {"filled": bool, "notes": str}
    """
    fields = _collect_external_form_fields(driver)
    if not fields:
        return {"filled": False, "notes": "No fillable form fields detected on the page."}

    log_message(f"[EXTERNAL] Detected {len(fields)} fillable field(s) on company application form.")
    fields = fields[:max_fields]

    any_field_failed = False
    for field in fields:
        try:
            if not field["element"].is_displayed():
                continue
        except Exception:
            continue

        if field["type"] == "file":
            if _is_resume_field(field):
                ok = _attach_resume_file(field, config)
                if not ok:
                    any_field_failed = True
            continue

        # Skip fields that already have a value (e.g. pre-filled by the site
        # from a LinkedIn import or similar) to avoid clobbering good data.
        try:
            existing_val = (field["element"].get_attribute("value") or "").strip()
            if existing_val and field["tag"] != "select":
                continue
        except Exception:
            pass

        options = None
        if field["tag"] == "select":
            try:
                from selenium.webdriver.support.ui import Select
                options = [o.text.strip() for o in Select(field["element"]).options if o.text.strip()]
            except Exception:
                options = None

        answer = _answer_external_question(
            field["label"], model, config,
            job_title=job_title, job_description=job_description,
            options=options,
        )
        if answer is None:
            return {"filled": False, "notes": "User cancelled a manual prompt during form fill."}

        filled_ok = _fill_external_field(driver, field, answer)
        if not filled_ok:
            any_field_failed = True
            log_message(f"[EXTERNAL] Could not confidently fill field '{field['label'][:60]}' — leaving as-is.")

    submitted = _click_external_submit(driver)
    if not submitted:
        return {"filled": False, "notes": "Form fields were processed but no submit button could be confirmed/clicked."}

    time.sleep(2)
    return {
        "filled": True,
        "notes": "Some fields may not have been confidently filled — review recommended." if any_field_failed else "",
    }


def apply_on_company_site(driver, model, config: Config, external_btn, job_title: str,
                           company: str, main_window: str, job_window: str,
                           job_description: str, wait_seconds: int = 15) -> dict:
    """
    Handles the full "Apply on company site" flow:
      1. Click the button, follow the new tab to the company's site.
      2. If a login/signup wall is detected -> skip (per configured behavior).
      3. If it's a job listing/search board (not a direct form) -> find the
         EXACT title match and click into it.
      4. Attempt a generic form fill (resume auto-attach, AI/manual Q&A,
         submit).
    Returns {"status": ..., "notes": ...} for CSV logging.
    """
    try:
        try:
            external_btn.click()
        except ElementClickInterceptedException:
            driver.execute_script("arguments[0].click();", external_btn)
    except Exception as e:
        return {"status": "failed", "notes": f"Could not click 'Apply on company site': {e}"}

    time.sleep(3)

    all_windows = driver.window_handles
    ext_window = all_windows[-1] if len(all_windows) > len(set([main_window, job_window])) else (
        all_windows[-1] if all_windows[-1] not in (main_window, job_window) else None
    )
    if ext_window is None and len(all_windows) > 1:
        ext_window = all_windows[-1]
    if ext_window:
        driver.switch_to.window(ext_window)

    try:
        WebDriverWait(driver, wait_seconds).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
    except TimeoutException:
        pass
    time.sleep(2)

    log_message(f"[EXTERNAL] Landed on company site: {driver.current_url}")

    # 1. Login/signup wall -> skip per configured policy.
    if _detect_login_wall(driver):
        log_message("[EXTERNAL] Login/account-creation wall detected on company site — skipping this job.")
        return {"status": "skipped_login_required", "notes": f"Company site ({driver.current_url}) requires account creation/login."}

    # 2. If this looks like a job board/listing page rather than a direct
    #    application form, find the exact-title match and click through.
    if _looks_like_job_listing_page(driver) and not any(
        h in _page_text_lower(driver) for h in EXTERNAL_FORM_PRESENCE_HINTS
    ):
        log_message("[EXTERNAL] Company page looks like a job listing board — searching for exact title match.")
        matched = _find_and_click_matching_job_listing(driver, job_title)
        if not matched:
            return {"status": "needs_manual_review",
                    "notes": f"Landed on company job board ({driver.current_url}) but no EXACT title match for "
                             f"'{job_title}' was found among the listings."}
        # Re-check for a login wall on the actual job's apply page too.
        if _detect_login_wall(driver):
            log_message("[EXTERNAL] Login/account-creation wall detected after opening matched listing — skipping.")
            return {"status": "skipped_login_required",
                    "notes": f"Company site ({driver.current_url}) requires account creation/login after selecting the job."}

    # 3. Attempt the generic form fill.
    fill_result = fill_external_application_form(
        driver, model, config, job_title=job_title, job_description=job_description,
    )

    if fill_result["filled"]:
        status = "applied_external" if not fill_result["notes"] else "needs_manual_review"
        notes = fill_result["notes"] or f"Applied via company site: {driver.current_url}"
        return {"status": status, "notes": notes}
    else:
        return {"status": "needs_manual_review", "notes": fill_result["notes"]}


# ════════════════════════════════════════════════════════════════════
# 7. MAIN
# ════════════════════════════════════════════════════════════════════

def run_bot(config_path: str = "personal.json") -> None:
    config = Config(config_path)

    log_message("════════════════════════════════════════")
    log_message("  Naukri Auto-Apply Bot — starting run")
    log_message(f"  AI mode (Gemini): {'ENABLED' if config.use_AI else 'disabled (manual prompts)'}")
    log_message(f"  Non-Interactive: {'ENABLED' if config.non_interactive else 'disabled (manual prompts)'}")
    log_message("════════════════════════════════════════")

    model = None
    if config.use_AI:
        model = gemini_create_client(config)
        if model is None:
            log_message("[WARN] AI mode requested but Gemini client failed to initialize. "
                        "Falling back to manual prompts for screening questions.")

    driver = None
    if config.stealth_mode:
        try:
            import undetected_chromedriver as uc
            original_quit = uc.Chrome.quit
            def patched_quit(self, *args, **kwargs):
                try:
                    original_quit(self, *args, **kwargs)
                except (OSError, Exception) as e:
                    if "WinError 6" in str(e) or (isinstance(e, OSError) and e.errno == 6):
                        pass
                    else:
                        raise
            uc.Chrome.quit = patched_quit
            log_message("Monkey-patched uc.Chrome.quit to suppress WinError 6 on exit.")
        except Exception as e:
            log_message(f"[WARN] Failed to patch uc.Chrome.quit: {e}")

    driver = get_chrome_driver(config)
    applied_count = 0

    try:
        if not naukri_login(driver, config):
            log_message("[FATAL] Could not log in to Naukri. Aborting run.")
            return

        search_terms = config.search_terms
        log_message(f"Will search {len(search_terms)} term(s): {search_terms}")

        for term in search_terms:
            if applied_count >= config.max_applications:
                log_message(f"Reached max_applications limit ({config.max_applications}). Stopping.")
                break

            # Verify driver is still responsive before starting next keyword search
            try:
                _ = driver.window_handles
            except Exception as e:
                log_message(f"[FATAL] Browser session was closed or lost: {e}. Terminating run.")
                break

            log_message(f"═══ Searching: '{term}' ═══")
            try:
                search_jobs(driver, config, term)
            except Exception as e:
                log_message(f"[ERROR] Failed searching jobs for '{term}': {e}")
                if "invalid session id" in str(e).lower() or "disconnected" in str(e).lower():
                    log_message("[FATAL] Browser connection was lost. Terminating run.")
                    break
                continue

            job_cards = collect_job_cards(driver)
            log_message(f"Found {len(job_cards)} job card(s) for '{term}'.")

            for idx, card in enumerate(job_cards):
                if applied_count >= config.max_applications:
                    log_message(f"Reached max_applications limit ({config.max_applications}). Stopping.")
                    break

                # Verify driver is still responsive before each job application
                try:
                    _ = driver.window_handles
                except Exception as e:
                    log_message(f"[FATAL] Browser session was closed or lost: {e}. Terminating run.")
                    break

                log_message(f"--- Processing job {idx + 1}/{len(job_cards)} (term: '{term}') ---")
                try:
                    result = apply_to_job_card(driver, card, model, config)
                    log_application_result(config, result)
                    if result["status"] in ("applied", "applied_external"):
                        applied_count += 1
                except StaleElementReferenceException:
                    log_message("[WARN] Job card went stale (page likely re-rendered) — skipping.")
                    continue
                except Exception as e:
                    log_message(f"[ERROR] Failed processing job card {idx + 1}: {e}")
                    if "invalid session id" in str(e).lower() or "disconnected" in str(e).lower():
                        log_message("[FATAL] Browser connection was lost. Terminating run.")
                        break
                    continue

                time.sleep(2)

        log_message(f"Run complete. Total applications submitted this run: {applied_count}")

    finally:
        try:
            driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    cfg_path = "personal.json"
    for arg in sys.argv[1:]:
        if arg.lower().endswith(".json"):
            cfg_path = arg
    run_bot(cfg_path)