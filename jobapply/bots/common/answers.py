"""Profile-aware deterministic answers with Gemini only for unknown questions."""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from gemini.gemini_api import GeminiClient, is_safe_form_answer


def _flatten(value: Mapping[str, Any], prefix: str = "") -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, child in value.items():
        normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
        path = f"{prefix}{normalized}"
        if isinstance(child, Mapping):
            flattened.update(_flatten(child, path))
        elif child is not None and str(child).strip():
            flattened[path] = child
            flattened.setdefault(normalized, child)
    return flattened


class AnswerEngine:
    def __init__(
        self,
        profile: Mapping[str, Any] | None,
        filter_config: Mapping[str, Any] | None,
        *,
        gemini_client: GeminiClient | None = None,
    ) -> None:
        self.profile = dict(profile or {})
        self.filter_config = dict(filter_config or {})
        self.flat_profile = _flatten(self.profile)
        saved = self.filter_config.get("savedAnswers", {})
        profile_saved = self.profile.get("savedAnswers", {})
        self.saved_answers = {
            str(key).lower(): value
            for source in (saved, profile_saved)
            if isinstance(source, Mapping)
            for key, value in source.items()
        }
        defaults = self.filter_config.get("defaultAnswers", {})
        self.defaults = dict(defaults) if isinstance(defaults, Mapping) else {}
        self.gemini = gemini_client or GeminiClient()
        self._cache: dict[tuple[str, tuple[str, ...]], str] = {}

    def _profile_value(self, *keys: str) -> str | None:
        for key in keys:
            normalized = re.sub(r"[^a-z0-9]", "", key.lower())
            if normalized in self.flat_profile:
                return str(self.flat_profile[normalized])
            for path, value in self.flat_profile.items():
                if path.endswith(normalized):
                    return str(value)
        return None

    def _known_answer(self, question: str) -> tuple[bool, str]:
        q = " ".join(question.lower().split())
        for keyword, answer in self.saved_answers.items():
            if keyword in q:
                return True, str(answer)

        rules: list[tuple[tuple[str, ...], tuple[str, ...], str]] = [
            (("email", "e-mail"), ("email",), ""),
            (("phone", "mobile", "contact number"), ("phone", "mobile"), ""),
            (("first name",), ("firstname", "first"), ""),
            (("last name", "surname"), ("lastname", "surname", "last"), ""),
            (("full name", "your name", "candidate name"), ("fullname", "name"), ""),
            (("current city", "current location", "where are you located"), ("location", "city"), ""),
            (("linkedin",), ("linkedin", "linkedinurl"), ""),
            (("github",), ("github", "githuburl"), ""),
            (("portfolio", "website"), ("portfolio", "website"), ""),
            (("date of birth", "dob"), ("dateofbirth", "dob"), ""),
            (("street address", "home address", "mailing address", "address line"), ("address", "streetaddress"), ""),
            (("postal code", "zip code", "pin code", "pincode"), ("postalcode", "zipcode", "pincode"), ""),
            (("country", "country of residence"), ("country",), ""),
            (("nationality", "citizenship"), ("nationality", "citizenship"), ""),
            (("gender", "pronouns"), ("gender", "pronouns"), ""),
            (("current company", "current employer"), ("currentcompany", "employer"), ""),
            (("current job title", "current title"), ("currenttitle", "jobtitle"), ""),
            (("highest education", "highest degree", "education level"), ("highesteducation", "degree", "education"), ""),
            (("cover letter", "why are you interested"), ("coverletter", "summary"), ""),
            (("notice period", "how soon", "start date", "available to start", "joining"), ("noticeperiod", "availability"), str(self.defaults.get("noticePeriod", "Immediately"))),
            (("salary", "ctc", "compensation", "expected pay"), ("expectedsalary", "salary", "ctc"), str(self.defaults.get("salary", "0"))),
            (("years of experience", "year of experience", "how many years", "total experience"), ("yearsofexperience", "experienceyears", "experience"), str(self.defaults.get("experienceYears", "0"))),
            (("authorized to work", "work authorization", "legally authorized"), ("workauthorized", "workauthorization"), str(self.defaults.get("workAuthorized", "Yes"))),
            (("sponsorship", "sponsor a visa", "require visa"), ("requiresponsorship", "visasponsorship"), str(self.defaults.get("requiresSponsorship", "No"))),
            (("relocate", "relocation"), ("willingtorelocate", "relocate"), str(self.defaults.get("willingToRelocate", "Yes"))),
        ]
        for phrases, profile_keys, default in rules:
            if any(phrase in q for phrase in phrases):
                value = self._profile_value(*profile_keys) or default
                # The question category is known even when the candidate has not
                # configured that value. This prevents Gemini from inventing
                # common identity/profile data; the deterministic fallback below
                # is used instead.
                return True, value or ""

        if any(q.startswith(prefix) for prefix in ("are you", "do you", "have you", "can you", "will you", "would you")):
            return True, str(self.defaults.get("yesNo", "Yes"))
        return False, ""

    @staticmethod
    def _match_option(answer: str, options: Sequence[str]) -> str | None:
        normalized_answer = " ".join(answer.lower().split())
        for option in options:
            if " ".join(option.lower().split()) == normalized_answer:
                return option
        for option in options:
            normalized_option = " ".join(option.lower().split())
            if normalized_answer in normalized_option or normalized_option in normalized_answer:
                return option
        if normalized_answer in {"yes", "no"}:
            for option in options:
                if normalized_answer in option.lower():
                    return option
        return None

    def answer(
        self,
        question: str,
        *,
        options: Sequence[str] | None = None,
        context: Mapping[str, Any] | str | None = None,
    ) -> str:
        clean_question = " ".join((question or "Application question").split())
        clean_options = tuple(option.strip() for option in (options or ()) if option and option.strip())
        cache_key = (clean_question.lower(), clean_options)
        if cache_key in self._cache:
            return self._cache[cache_key]

        known, answer = self._known_answer(clean_question)
        if not known and self.gemini.enabled:
            generated = self.gemini.answer_question(
                clean_question,
                profile=self.profile,
                context=context,
                options=clean_options or None,
            )
            if is_safe_form_answer(generated):
                answer = generated or ""

        if not answer:
            answer = str(self.defaults.get("unknown", self.profile.get("defaultAnswer", "Not applicable")))
        if clean_options:
            matched = self._match_option(answer, clean_options)
            if matched:
                answer = matched
            else:
                usable = [
                    option for option in clean_options
                    if not any(marker in option.lower() for marker in ("select", "choose", "please"))
                ]
                non_disclosure = next(
                    (
                        option for option in usable
                        if any(marker in option.lower() for marker in ("prefer not", "decline", "not applicable", "n/a"))
                    ),
                    None,
                )
                answer = non_disclosure or (usable[0] if usable else clean_options[0])
        if not is_safe_form_answer(answer):
            answer = "Not applicable"
        self._cache[cache_key] = answer
        return answer
