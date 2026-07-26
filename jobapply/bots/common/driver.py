"""Central Chrome creation with optional profile reuse and CDP attachment."""

from __future__ import annotations

import os

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from .config import AutomationConfig
from .paths import APP_ROOT, resolve_app_path


def chrome_options(config: AutomationConfig, *, debugger_address: str | None = None) -> Options:
    options = Options()
    if debugger_address:
        options.add_experimental_option("debuggerAddress", debugger_address.strip())
        return options

    if config.headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--disable-session-crashed-bubble")
    options.add_argument("--window-size=1440,1000")
    options.add_argument("--lang=en-US")
    options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
    options.add_experimental_option("useAutomationExtension", False)

    browser = config.browser
    configured_user_data = os.getenv("CHROME_USER_DATA_DIR") or browser.get("userDataDir")
    if configured_user_data:
        user_data = resolve_app_path(str(configured_user_data), "configs/chrome-profile", app_root=APP_ROOT)
        user_data.mkdir(parents=True, exist_ok=True)
        options.add_argument(f"--user-data-dir={user_data}")
        profile_directory = os.getenv("CHROME_PROFILE_DIRECTORY") or browser.get("profileDirectory")
        if profile_directory:
            options.add_argument(f"--profile-directory={profile_directory}")

    user_agent = os.getenv("CHROME_USER_AGENT") or browser.get("userAgent")
    if user_agent:
        options.add_argument(f"--user-agent={user_agent}")
    binary = os.getenv("CHROME_BINARY") or browser.get("binary")
    if binary:
        options.binary_location = str(resolve_app_path(str(binary), str(binary), app_root=APP_ROOT))
    return options


def create_driver(
    config: AutomationConfig,
    *,
    debugger_address: str | None = None,
) -> webdriver.Chrome:
    """Create Chrome normally or attach to an existing Chrome CDP endpoint."""

    options = chrome_options(config, debugger_address=debugger_address)
    driver_path = os.getenv("CHROMEDRIVER_PATH") or config.browser.get("driverPath")
    service = (
        Service(executable_path=str(resolve_app_path(str(driver_path), str(driver_path), app_root=APP_ROOT)))
        if driver_path
        else Service()
    )
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(int(config.browser.get("pageLoadTimeout", 60)))
    driver.set_script_timeout(int(config.browser.get("scriptTimeout", 30)))
    if not debugger_address:
        try:
            driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {
                    "source": (
                        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
                        "Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});"
                    )
                },
            )
        except Exception:
            pass
    return driver
