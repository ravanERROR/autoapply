"""Small Gemini REST client whose failures are always represented by ``None``."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import requests
from dotenv import load_dotenv


APP_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(APP_ROOT / ".env", override=False)

DEFAULT_MODEL = "gemini-2.0-flash"
_UNSAFE_OUTPUT = re.compile(
    r"\b(sorry|apolog(?:y|ize|ise)|error|request failed|unable to|cannot (?:answer|help)|could(?: not|n't) process)\b",
    re.IGNORECASE,
)


def is_safe_form_answer(value: str | None) -> bool:
    if not value or not value.strip():
        return False
    return not _UNSAFE_OUTPUT.search(value.strip())


class GeminiClient:
    def __init__(
        self,
        api_key: str | None = None,
        *,
        model: str | None = None,
        timeout: float = 30,
        session: requests.Session | None = None,
    ) -> None:
        configured_key = (api_key if api_key is not None else os.getenv("GEMINI_API_KEY", "")).strip()
        self.api_key = "" if configured_key.lower() in {
            "your_gemini_api_key",
            "your_gemini_api_key_here",
            "changeme",
            "replace_me",
        } else configured_key
        self.model = (model or os.getenv("GEMINI_MODEL") or DEFAULT_MODEL).strip()
        self.timeout = timeout
        self.session = session or requests.Session()

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _failure(self, code: str, detail: str) -> None:
        event = {"component": "gemini", "status": "failed", "code": code, "detail": detail[:500]}
        print(json.dumps(event, ensure_ascii=False), file=sys.stderr, flush=True)

    def generate_content(self, prompt: str, *, max_tokens: int = 256, temperature: float = 0.2) -> str | None:
        if not self.enabled:
            return None
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens, "temperature": temperature},
        }
        try:
            response = self.session.post(
                url,
                params={"key": self.api_key},
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as error:
            self._failure("request_error", str(error))
            return None
        except (ValueError, TypeError) as error:
            self._failure("invalid_json", str(error))
            return None

        try:
            parts = data["candidates"][0]["content"]["parts"]
            text = " ".join(str(part.get("text", "")) for part in parts).strip()
        except (KeyError, IndexError, TypeError, AttributeError) as error:
            self._failure("invalid_response", str(error))
            return None
        cleaned = self._clean_answer(text)
        if not is_safe_form_answer(cleaned):
            self._failure("unsafe_or_empty_answer", "Model returned no usable form value")
            return None
        return cleaned

    @staticmethod
    def _clean_answer(value: str) -> str:
        cleaned = value.strip().strip("`\"'")
        cleaned = re.sub(r"^(?:answer|value)\s*:\s*", "", cleaned, flags=re.IGNORECASE)
        return " ".join(cleaned.split())

    def answer_question(
        self,
        question: str,
        *,
        profile: Mapping[str, Any] | None = None,
        context: Mapping[str, Any] | str | None = None,
        options: Sequence[str] | None = None,
    ) -> str | None:
        if not self.enabled:
            return None
        prompt = (
            "Answer one job-application question using only the candidate profile and job context. "
            "Be truthful, concise, and return only the literal field value. Never return an apology, "
            "an error message, commentary, Markdown, or invented credentials.\n"
            f"Candidate profile: {json.dumps(dict(profile or {}), ensure_ascii=False, default=str)}\n"
            f"Job context: {json.dumps(context or {}, ensure_ascii=False, default=str)}\n"
            f"Question: {question.strip()}\n"
        )
        if options:
            prompt += f"Allowed options: {json.dumps(list(options), ensure_ascii=False)}\nChoose one allowed option exactly.\n"
        return self.generate_content(prompt, max_tokens=100, temperature=0.1)


def generate_content(prompt: str, max_tokens: int = 256) -> str | None:
    return GeminiClient().generate_content(prompt, max_tokens=max_tokens)


def answer_question(
    question: str,
    profile: Mapping[str, Any] | None = None,
    context: Mapping[str, Any] | str | None = None,
    options: Sequence[str] | None = None,
) -> str | None:
    return GeminiClient().answer_question(question, profile=profile, context=context, options=options)


def fill_form_field(field_html: str, form_context: str) -> str | None:
    return GeminiClient().answer_question(
        f"Provide the value for this form field: {field_html}",
        context=form_context,
    )


if __name__ == "__main__":
    print(generate_content("Return only: JobApply Gemini integration works"))
