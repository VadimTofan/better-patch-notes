from __future__ import annotations

import argparse
from collections.abc import Mapping
from copy import deepcopy
import json
import os
from pathlib import Path
import re
from threading import Lock
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


Translator = Callable[[str, str], str]
GeminiRequest = Callable[[str, str, str], str]

GEMINI_KEY_NAMES = ("GEMINI_API_KEY", "GEMINI_API_KEY2")
GEMINI_INTERACTIONS_URL = (
    "https://generativelanguage.googleapis.com/v1beta/interactions"
)
GEMINI_MODEL = "gemini-3.5-flash-lite"
GEMINI_BATCH_MODEL = "gemini-3.5-flash-lite"
GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
GEMINI_REQUESTS_PER_MINUTE = 5
PROJECT_ROOT = Path(__file__).resolve().parents[3]

LANGUAGE_NAMES = {
    "de": "German",
    "es-ES": "Spanish (Spain)",
    "es-MX": "Spanish (Latin America)",
    "fr": "French",
    "it": "Italian",
    "ko": "Korean",
    "pt": "Brazilian Portuguese",
    "ru": "Russian",
    "zh-CN": "Simplified Chinese",
    "zh-TW": "Traditional Chinese",
}

SPACE_DELIMITED_LANGUAGES = {
    "de",
    "es-ES",
    "es-MX",
    "fr",
    "it",
    "pt",
    "ru",
}

TARGET_LANGUAGE_CODES = {
    "deDE": "de",
    "esES": "es-ES",
    "esMX": "es-MX",
    "frFR": "fr",
    "itIT": "it",
    "koKR": "ko",
    "ptBR": "pt",
    "ruRU": "ru",
    "zhCN": "zh-CN",
    "zhTW": "zh-TW",
}

GENERIC_SENTENCE_STARTS = {
    "Added",
    "Addressed",
    "Additionally",
    "Adjusted",
    "All",
    "Cast",
    "Chance",
    "Cooldown",
    "Current",
    "Damage",
    "Developers'",
    "Developers’",
    "Developers' notes",
    "Developers’ notes",
    "Fixed",
    "General",
    "Health",
    "If",
    "Increased",
    "Melee",
    "Much",
    "New Talent",
    "Now",
    "Physical",
    "Reduced",
    "Removed",
    "Significantly",
    "Spell",
    "There",
    "They",
    "This",
    "Time",
    "Timer",
    "To",
    "We",
    "We'd",
    "We’d",
    "We're",
    "We’re",
}

CAPITALIZED_TERM_PATTERN = re.compile(
    r"\b[A-Z][A-Za-z’'\-]*(?:\s+(?:(?:of|the|and|By|is)\s+)?"
    r"[A-Z][A-Za-z’'\-]*)*"
)
NUMERIC_LITERAL_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_])\d+(?:[.,]\d+)?(?:\s*%)?"
)
NUMERIC_WORD_PATTERN = re.compile(
    r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|"
    r"tenth|primary|secondary)\b",
    re.IGNORECASE,
)
PLACEHOLDER_PATTERN = re.compile(r"(__BPN\d{4}__)")
PLACEHOLDER_INSENSITIVE_PATTERN = re.compile(
    r"__BPN\d{4}__",
    re.IGNORECASE,
)


def _read_env_values(env_path: Path) -> dict[str, str]:
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        name, separator, raw_value = line.partition("=")
        name = name.strip()
        if not separator or name not in GEMINI_KEY_NAMES:
            continue

        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[name] = value

    return values


def load_gemini_api_keys(
    env_path: Path,
    environment: Mapping[str, str] | None = None,
) -> tuple[str, ...]:
    selected_environment = os.environ if environment is None else environment
    file_values = _read_env_values(env_path)
    keys: list[str] = []

    for name in GEMINI_KEY_NAMES:
        value = selected_environment.get(name) or file_values.get(name, "")
        value = value.strip()
        if value and value not in keys:
            keys.append(value)

    if not keys:
        raise RuntimeError(
            "Gemini API credentials are missing; configure "
            "GEMINI_API_KEY or GEMINI_API_KEY2."
        )

    return tuple(keys)


class GeminiApiError(RuntimeError):
    def __init__(self, status_code: int, code: str) -> None:
        super().__init__(f"Gemini API request failed with {code} ({status_code}).")
        self.status_code = status_code
        self.code = code


class GeminiBatchTimeoutError(RuntimeError):
    """Raised when an accepted Gemini batch does not finish in time."""


class GeminiRequestRateLimiter:
    def __init__(
        self,
        requests_per_minute: int,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if requests_per_minute < 1:
            raise ValueError("requests_per_minute must be positive")

        self._minimum_interval = 60 / requests_per_minute
        self._monotonic = monotonic
        self._sleep = sleep
        self._next_request_time = 0.0
        self._lock = Lock()

    def wait(self) -> None:
        with self._lock:
            current_time = self._monotonic()
            delay = max(0.0, self._next_request_time - current_time)
            if delay:
                self._sleep(delay)
                current_time = self._monotonic()

            self._next_request_time = (
                max(self._next_request_time, current_time)
                + self._minimum_interval
            )


GEMINI_REQUEST_LIMITER = GeminiRequestRateLimiter(
    GEMINI_REQUESTS_PER_MINUTE,
)


def _gemini_error_code(error: HTTPError) -> str:
    try:
        payload = json.loads(error.read().decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return "http_error"

    error_details = payload.get("error", {})
    if not isinstance(error_details, dict):
        return "http_error"

    status = error_details.get("status", "http_error")
    return str(status).lower()


def _gemini_output_text(payload: object) -> str:
    if not isinstance(payload, dict):
        raise RuntimeError("Gemini returned an invalid translation response.")

    steps = payload.get("steps", [])
    if not isinstance(steps, list):
        raise RuntimeError("Gemini returned an invalid translation response.")

    for step in reversed(steps):
        if not isinstance(step, dict) or step.get("type") != "model_output":
            continue

        content = step.get("content", [])
        if not isinstance(content, list):
            continue

        text_parts = [
            item["text"]
            for item in content
            if isinstance(item, dict)
            and item.get("type") == "text"
            and isinstance(item.get("text"), str)
        ]
        translated = "".join(text_parts).strip()
        if translated:
            return translated

    raise RuntimeError("Gemini returned no translation text.")


def _request_gemini_output(
    api_key: str,
    prompt: str,
    timeout: int = 30,
    model: str = GEMINI_MODEL,
) -> str:
    request_body = {
        "model": model,
        "input": prompt,
        "generation_config": {
            "thinking_level": (
                "minimal" if model == GEMINI_BATCH_MODEL else "low"
            ),
        },
    }
    request = Request(
        GEMINI_INTERACTIONS_URL,
        data=json.dumps(request_body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )

    try:
        GEMINI_REQUEST_LIMITER.wait()
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise GeminiApiError(error.code, _gemini_error_code(error)) from error
    except (TimeoutError, URLError) as error:
        raise GeminiApiError(503, "network_error") from error
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RuntimeError(
            "Gemini returned an invalid translation response."
        ) from error

    return _gemini_output_text(payload)


def request_gemini_translation(
    api_key: str,
    text: str,
    language: str,
) -> str:
    language_name = LANGUAGE_NAMES.get(language, language)
    required_placeholders = ", ".join(
        PLACEHOLDER_PATTERN.findall(text)
    ) or "none"
    prompt = (
        "Translate this World of Warcraft patch-note fragment from English "
        f"to {language_name}. Return only the translated fragment. Preserve "
        "all __BPN0000__-style placeholders exactly. Preserve mechanical "
        "meaning and the direction of the change. "
        f"Required placeholders: {required_placeholders}. Do not add, remove, "
        "rename, split, or duplicate them. Do not add numeric literals; "
        "numbers are already protected by placeholders.\n\n"
        f"{text}"
    )
    return _request_gemini_output(api_key, prompt)


def request_gemini_translation_batch(
    api_key: str,
    serialized_texts: str,
    language: str,
) -> str:
    language_name = LANGUAGE_NAMES.get(language, language)
    prompt = (
        "Translate every World of Warcraft patch-note string in the JSON "
        f"array from English to {language_name}. Return only a valid JSON "
        "array of translated strings in the original order. Preserve every "
        "__BPN0000__-style placeholder exactly. Preserve mechanical meaning "
        "and the direction of every change. Do not add numeric literals; "
        "numbers are already protected by placeholders. Do not add "
        "explanations or Markdown fences.\n\n"
        f"{serialized_texts}"
    )
    return _request_gemini_output(
        api_key,
        prompt,
        timeout=120,
        model=GEMINI_BATCH_MODEL,
    )


class GeminiTranslator:
    _TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}

    def __init__(
        self,
        api_keys: tuple[str, ...],
        request_translation: GeminiRequest,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 4,
    ) -> None:
        self._api_keys = api_keys
        self._request_translation = request_translation
        self._sleep = sleep
        self._max_attempts = max_attempts
        self._disabled_key_indexes: set[int] = set()
        self._disabled_key_statuses: dict[int, int] = {}
        self._lock = Lock()

    def _is_disabled(self, key_index: int) -> bool:
        with self._lock:
            return key_index in self._disabled_key_indexes

    def _disabled_status(self, key_index: int) -> int | None:
        with self._lock:
            return self._disabled_key_statuses.get(key_index)

    def _disable(self, key_index: int, status_code: int) -> None:
        with self._lock:
            self._disabled_key_indexes.add(key_index)
            self._disabled_key_statuses[key_index] = status_code

    def __call__(self, text: str, language: str) -> str:
        failures: list[str] = []
        for key_index, api_key in enumerate(self._api_keys):
            if self._is_disabled(key_index):
                status_code = self._disabled_status(key_index)
                failures.append(
                    f"key {key_index + 1}: {status_code or 'unavailable'}"
                )
                continue

            last_status_code: int | None = None
            for attempt in range(self._max_attempts):
                try:
                    return self._request_translation(
                        api_key,
                        text,
                        language,
                    )
                except GeminiApiError as error:
                    last_status_code = error.status_code
                    if error.status_code in {401, 403}:
                        self._disable(key_index, error.status_code)
                        break
                    if error.status_code not in self._TRANSIENT_STATUS_CODES:
                        raise RuntimeError(
                            "Gemini translation stopped after a "
                            f"non-retryable API error ({error.status_code})."
                        ) from error
                    if attempt + 1 < self._max_attempts:
                        self._sleep(2**attempt)

            if last_status_code is not None:
                failures.append(
                    f"key {key_index + 1}: {last_status_code}"
                )

        failure_summary = ", ".join(failures) or "no usable keys"
        raise RuntimeError(
            "All configured Gemini API keys failed; translation stopped "
            f"({failure_summary})."
        )


def translate_text_batch(
    texts: tuple[str, ...],
    language: str,
    translator: Translator,
    batch_size: int = 40,
    repair_translator: Translator | None = None,
    repair_attempts: int = 3,
) -> tuple[str, ...]:
    if batch_size < 1:
        raise ValueError("translation batch size must be positive")
    if repair_attempts < 1:
        raise ValueError("repair_attempts must be positive")

    all_translations: list[str] = []
    for start in range(0, len(texts), batch_size):
        chunk = texts[start : start + batch_size]
        serialized_texts = json.dumps(chunk, ensure_ascii=False)
        raw_translation = translator(serialized_texts, language).strip()
        translated = _parse_translation_array(
            raw_translation,
            len(chunk),
        )

        for item_offset, (source_text, localized_text) in enumerate(
            zip(chunk, translated, strict=True),
        ):
            normalized = _normalize_translation_placeholders(
                source_text,
                localized_text,
            )
            if normalized is None:
                for _attempt in range(repair_attempts):
                    if repair_translator is None:
                        repair_input = json.dumps(
                            [source_text],
                            ensure_ascii=False,
                        )
                        repair_output = translator(repair_input, language)
                        repaired = _parse_translation_array(
                            repair_output,
                            1,
                        )[0]
                    else:
                        repaired = repair_translator(source_text, language)
                    normalized = _normalize_translation_placeholders(
                        source_text,
                        repaired,
                    )
                    if normalized is not None:
                        break
            if normalized is None:
                raise RuntimeError(
                    "Gemini changed protected translation placeholders "
                    f"for locale {language}, item "
                    f"{start + item_offset + 1}."
                )
            all_translations.append(normalized)

    return tuple(all_translations)


def _parse_translation_array(
    raw_translation: str,
    expected_length: int,
) -> list[str]:
    normalized = raw_translation.strip()
    if normalized.startswith("```"):
        lines = normalized.splitlines()
        normalized = "\n".join(lines[1:-1]).strip()

    try:
        translated = json.loads(normalized)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            "Gemini returned an invalid translation batch."
        ) from error

    if (
        not isinstance(translated, list)
        or len(translated) != expected_length
        or not all(isinstance(item, str) and item for item in translated)
    ):
        raise RuntimeError(
            "Gemini returned an incomplete translation batch."
        )

    return translated


def _normalize_translation_placeholders(
    source_text: str,
    translated_text: str,
) -> str | None:
    expected = sorted(PLACEHOLDER_PATTERN.findall(source_text))
    normalized = PLACEHOLDER_INSENSITIVE_PATTERN.sub(
        lambda match: match.group(0).upper(),
        translated_text,
    )
    actual = sorted(PLACEHOLDER_PATTERN.findall(normalized))
    if actual != expected:
        return None

    source_without_placeholders = PLACEHOLDER_PATTERN.sub("", source_text)
    translated_without_placeholders = PLACEHOLDER_PATTERN.sub("", normalized)
    source_numbers = sorted(
        NUMERIC_LITERAL_PATTERN.findall(source_without_placeholders)
    )
    translated_numbers = sorted(
        NUMERIC_LITERAL_PATTERN.findall(translated_without_placeholders)
    )
    if translated_numbers != source_numbers:
        return None

    return normalized


def _whole_bullet_prompt(text: str, language_name: str) -> str:
    return (
        "Translate this complete World of Warcraft patch-note bullet from "
        f"English to {language_name}. Return only the translated bullet. "
        "Preserve every __BPN0000__-style placeholder exactly. Preserve "
        "mechanical meaning and the direction of the change.\n\n"
        f"{text}"
    )


def build_inline_batch_requests(
    protected_texts: tuple[str, ...],
    languages: Mapping[str, str],
) -> list[dict[str, object]]:
    requests: list[dict[str, object]] = []
    for language, language_name in languages.items():
        for text_index, text in enumerate(protected_texts):
            requests.append(
                {
                    "request": {
                        "contents": [
                            {
                                "role": "user",
                                "parts": [
                                    {
                                        "text": _whole_bullet_prompt(
                                            text,
                                            language_name,
                                        )
                                    }
                                ],
                            }
                        ]
                    },
                    "metadata": {"key": f"{language}:{text_index}"},
                }
            )

    return requests


def _inline_response_text(inline_response: object) -> str:
    if not isinstance(inline_response, dict):
        raise RuntimeError("Gemini returned an invalid batch response.")
    if inline_response.get("error"):
        raise RuntimeError("Gemini batch contained a failed request.")

    response = inline_response.get("response")
    if not isinstance(response, dict):
        raise RuntimeError("Gemini batch response is missing output.")
    candidates = response.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise RuntimeError("Gemini batch response is missing candidates.")
    candidate = candidates[0]
    if not isinstance(candidate, dict):
        raise RuntimeError("Gemini batch response has an invalid candidate.")
    content = candidate.get("content")
    if not isinstance(content, dict):
        raise RuntimeError("Gemini batch response is missing content.")
    parts = content.get("parts")
    if not isinstance(parts, list):
        raise RuntimeError("Gemini batch response is missing text parts.")

    text = "".join(
        part["text"]
        for part in parts
        if isinstance(part, dict) and isinstance(part.get("text"), str)
    ).strip()
    if not text:
        raise RuntimeError("Gemini batch response contains empty text.")

    return text


def parse_inline_batch_results(
    batch_job: object,
    expected_keys: tuple[str, ...],
) -> dict[str, str]:
    if not isinstance(batch_job, dict):
        raise RuntimeError("Gemini returned an invalid batch job.")
    destination = batch_job.get("dest")
    if not isinstance(destination, dict):
        raise RuntimeError("Gemini batch job is missing inline results.")
    responses = destination.get("inlinedResponses")
    if not isinstance(responses, list):
        raise RuntimeError("Gemini batch job is missing inline responses.")

    translations: dict[str, str] = {}
    for inline_response in responses:
        if not isinstance(inline_response, dict):
            raise RuntimeError("Gemini returned an invalid inline response.")
        metadata = inline_response.get("metadata")
        if not isinstance(metadata, dict) or not isinstance(
            metadata.get("key"),
            str,
        ):
            raise RuntimeError("Gemini inline response is missing its key.")
        key = metadata["key"]
        translations[key] = _inline_response_text(inline_response)

    if set(translations) != set(expected_keys):
        raise RuntimeError("Gemini batch returned incomplete keyed results.")

    return translations


def _open_json_request(request: Request, timeout: int = 30) -> dict[str, object]:
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        raise GeminiApiError(error.code, _gemini_error_code(error)) from error
    except (TimeoutError, URLError) as error:
        raise GeminiApiError(503, "network_error") from error
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RuntimeError("Gemini returned invalid batch JSON.") from error

    if not isinstance(payload, dict):
        raise RuntimeError("Gemini returned an invalid batch payload.")
    return payload


def submit_inline_batch(
    api_keys: tuple[str, ...],
    requests: list[dict[str, object]],
) -> tuple[str, str]:
    endpoint = (
        f"{GEMINI_API_BASE_URL}/models/"
        f"{GEMINI_BATCH_MODEL}:batchGenerateContent"
    )
    request_body = {
        "batch": {
            "display_name": "BetterPatchNotes translations",
            "input_config": {
                "requests": {"requests": requests},
            },
        }
    }
    failures: list[str] = []
    for key_index, api_key in enumerate(api_keys):
        request = Request(
            endpoint,
            data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
            method="POST",
        )
        try:
            GEMINI_REQUEST_LIMITER.wait()
            response = _open_json_request(request, timeout=120)
        except GeminiApiError as error:
            failures.append(f"key {key_index + 1}: {error.status_code}")
            if error.status_code in {401, 403, 429}:
                continue
            raise

        job_name = response.get("name")
        if not isinstance(job_name, str) or not job_name.startswith("batches/"):
            raise RuntimeError("Gemini did not return a valid batch job name.")
        return job_name, api_key

    raise RuntimeError(
        "Gemini Batch API submission failed; translation stopped "
        f"({', '.join(failures)})."
    )


def wait_for_inline_batch(
    job_name: str,
    api_key: str,
    poll_interval: int = 30,
    timeout_seconds: int = 600,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    if poll_interval < 1:
        raise ValueError("batch poll interval must be positive")
    if timeout_seconds < 1:
        raise ValueError("batch timeout must be positive")

    completed_states = {
        "JOB_STATE_SUCCEEDED",
        "JOB_STATE_FAILED",
        "JOB_STATE_CANCELLED",
        "JOB_STATE_EXPIRED",
    }
    endpoint = f"{GEMINI_API_BASE_URL}/{job_name}"
    deadline = monotonic() + timeout_seconds

    def wait_for_next_poll() -> None:
        remaining_seconds = deadline - monotonic()
        if remaining_seconds <= 0:
            raise GeminiBatchTimeoutError(
                "Gemini batch did not finish within "
                f"{timeout_seconds} seconds."
            )

        sleep(min(poll_interval, remaining_seconds))

    while True:
        request = Request(
            endpoint,
            headers={"x-goog-api-key": api_key},
        )
        try:
            batch_job = _open_json_request(request)
        except GeminiApiError as error:
            if error.status_code in {429, 500, 502, 503, 504}:
                wait_for_next_poll()
                continue
            raise

        state = batch_job.get("state")
        if state in completed_states:
            if state != "JOB_STATE_SUCCEEDED":
                raise RuntimeError(
                    f"Gemini batch ended in {state}; translation stopped."
                )
            return batch_job

        wait_for_next_poll()


def _generate_interactive_translations(
    api_keys: tuple[str, ...],
    protected_texts: tuple[str, ...],
    languages: Mapping[str, str],
) -> tuple[dict[tuple[str, str], str], str]:
    translator = GeminiTranslator(
        api_keys,
        request_translation=request_gemini_translation_batch,
    )
    repair_translator = GeminiTranslator(
        api_keys,
        request_translation=request_gemini_translation,
    )
    translations: dict[tuple[str, str], str] = {}
    for language in languages:
        try:
            localized_texts = translate_text_batch(
                protected_texts,
                language,
                translator,
                repair_translator=repair_translator,
            )
        except RuntimeError:
            continue

        for source_text, localized_text in zip(
            protected_texts,
            localized_texts,
            strict=True,
        ):
            translations[(language, source_text)] = localized_text

    return translations, "interactive"


def generate_protected_translations(
    api_keys: tuple[str, ...],
    protected_texts: tuple[str, ...],
    languages: Mapping[str, str],
) -> tuple[dict[tuple[str, str], str], str]:
    inline_requests = build_inline_batch_requests(
        protected_texts,
        languages,
    )
    expected_keys = tuple(
        request["metadata"]["key"]
        for request in inline_requests
    )

    try:
        job_name, job_api_key = submit_inline_batch(
            api_keys,
            inline_requests,
        )
    except GeminiApiError as error:
        if error.status_code != 400 or error.code != "failed_precondition":
            raise

        return _generate_interactive_translations(
            api_keys,
            protected_texts,
            languages,
        )

    print(f"Gemini batch submitted: {job_name}")
    try:
        batch_job = wait_for_inline_batch(job_name, job_api_key)
    except GeminiBatchTimeoutError:
        print("Gemini batch timed out; using interactive translation.")
        return _generate_interactive_translations(
            api_keys,
            protected_texts,
            languages,
        )

    keyed_translations = parse_inline_batch_results(
        batch_job,
        expected_keys,
    )
    translations = {
        (language, source_text): keyed_translations[f"{language}:{text_index}"]
        for language in languages
        for text_index, source_text in enumerate(protected_texts)
    }
    return translations, "batch"


def classify_locale_outcomes(
    translations: Mapping[tuple[str, str], str],
    locale_languages: Mapping[str, str],
) -> tuple[dict[str, str], dict[str, str]]:
    successful_languages = {
        language for language, _source_text in translations
    }
    successful_locales = {
        locale: language
        for locale, language in locale_languages.items()
        if language in successful_languages
    }
    fallback_reasons = {
        locale: "automatic translation generation failed"
        for locale, language in locale_languages.items()
        if language not in successful_languages
    }

    return successful_locales, fallback_reasons


def _candidate_terms(text: str) -> tuple[str, ...]:
    candidates: list[str] = []
    prefix, separator, _remainder = text.partition(":")
    if separator:
        candidates.extend(part.strip() for part in prefix.split(" – "))

    candidates.extend(CAPITALIZED_TERM_PATTERN.findall(text))

    terms: list[str] = []
    for candidate in candidates:
        candidate = candidate.strip(" .,:;()")
        if candidate in GENERIC_SENTENCE_STARTS:
            continue

        words = candidate.split()
        while len(words) > 1 and words[0] in GENERIC_SENTENCE_STARTS:
            words.pop(0)
        candidate = " ".join(words)

        if not candidate or candidate in GENERIC_SENTENCE_STARTS:
            continue
        if candidate not in terms:
            terms.append(candidate)

    return tuple(terms)


def translate_guarded_text(
    text: str,
    language: str,
    translator: Translator,
) -> tuple[str, tuple[str, ...]]:
    protected_text, replacements, terms = _protect_text(text)
    translated = translator(protected_text, language)

    for placeholder, original in replacements:
        translated = _restore_protected_text(
            translated,
            placeholder,
            original,
            language,
        )

    return translated, terms


def _restore_protected_text(
    translated: str,
    placeholder: str,
    original: str,
    language: str,
) -> str:
    def restore(match: re.Match[str]) -> str:
        prefix = ""
        suffix = ""

        if language in SPACE_DELIMITED_LANGUAGES:
            before = translated[match.start() - 1 : match.start()]
            after = translated[match.end() : match.end() + 1]

            if before and before.isalnum() and original[:1].isalnum():
                prefix = " "
            if after and after.isalnum() and original[-1:].isalnum():
                suffix = " "

        return f"{prefix}{original}{suffix}"

    return re.sub(re.escape(placeholder), restore, translated)


def _translation_core(segment: str) -> tuple[str, str, str]:
    match = re.fullmatch(r"(\s*)(.*?)(\s*)", segment, re.DOTALL)
    if match is None:
        return "", segment, ""

    return match.group(1), match.group(2), match.group(3)


def _translation_segments(
    text: str,
) -> tuple[list[tuple[bool, str]], tuple[str, ...]]:
    protected_text, replacements, terms = _protect_text(text)
    originals = dict(replacements)
    segments: list[tuple[bool, str]] = []

    for part in PLACEHOLDER_PATTERN.split(protected_text):
        if not part:
            continue
        original = originals.get(part)
        if original is None:
            segments.append((False, part))
        else:
            segments.append((True, original))

    return segments, terms


def _protect_text(
    text: str,
) -> tuple[str, list[tuple[str, str]], tuple[str, ...]]:
    terms = _candidate_terms(text)
    protected_text = text
    replacements: list[tuple[str, str]] = []
    protected_terms: set[str] = set()

    for term in sorted(terms, key=len, reverse=True):
        if term not in protected_text:
            continue
        placeholder = f"__BPN{len(replacements):04d}__"
        protected_text = protected_text.replace(term, placeholder)
        replacements.append((placeholder, term))
        protected_terms.add(term)

    placeholder_index = len(replacements)

    def replace_numeric_word(match: re.Match[str]) -> str:
        nonlocal placeholder_index
        placeholder = f"__BPN{placeholder_index:04d}__"
        placeholder_index += 1
        replacements.append((placeholder, match.group(0)))
        return placeholder

    protected_text = NUMERIC_WORD_PATTERN.sub(
        replace_numeric_word,
        protected_text,
    )

    def replace_number(match: re.Match[str]) -> str:
        nonlocal placeholder_index
        placeholder = f"__BPN{placeholder_index:04d}__"
        placeholder_index += 1
        replacements.append((placeholder, match.group(0)))
        return placeholder

    protected_text = NUMERIC_LITERAL_PATTERN.sub(
        replace_number,
        protected_text,
    )

    actual_terms = tuple(term for term in terms if term in protected_terms)
    return protected_text, replacements, actual_terms


def _terminology_url(terminology: dict[str, object], locale: str) -> str:
    locale_data = terminology["locales"][locale]
    druid = locale_data["terms"]["Druid"]
    return druid["sourceUrl"]


def _localized_term(
    terminology: dict[str, object],
    locale: str,
    english_term: str,
) -> str:
    locale_data = terminology["locales"][locale]
    entry = locale_data["terms"].get(english_term)
    if entry is None:
        return english_term

    return entry["localized"]


def build_translation_batch(
    document: dict[str, object],
    locale_languages: dict[str, str],
    translator: Translator,
    terminology: dict[str, object] | None = None,
) -> dict[str, object]:
    if terminology is None:
        terminology = {
            "locales": {
                locale: {
                    "terms": {
                        "Druid": {
                            "localized": "Druid",
                            "sourceUrl": (
                                "https://worldofwarcraft.blizzard.com/"
                                "en-us/game/classes/druid"
                            ),
                        }
                    }
                }
                for locale in locale_languages
            }
        }

    batch = {
        "retrievedAt": document["updatedAt"],
        "changes": [],
    }
    for raw_change in document["changes"]:
        change = {
            "channel": raw_change["channel"],
            "category": raw_change["category"],
            "date": raw_change["date"],
            "patch": raw_change["patch"],
            "localizations": deepcopy(raw_change["localizations"]),
            "replacesSourceUrl": "",
        }
        english = change["localizations"]["en"]

        for locale, language in locale_languages.items():
            translated_changes: list[str] = []
            uncertain_terms: list[str] = []
            for bullet in english["change"]:
                translated, bullet_terms = translate_guarded_text(
                    bullet,
                    language,
                    translator,
                )
                translated_changes.append(translated)
                for term in bullet_terms:
                    if term not in uncertain_terms:
                        uncertain_terms.append(term)

            localization = {
                "name": _localized_term(
                    terminology,
                    locale,
                    english["name"],
                ),
                "specialization": _localized_term(
                    terminology,
                    locale,
                    english["specialization"],
                ),
                "change": translated_changes,
                "source": english["source"],
                "sourceUrl": english["sourceUrl"],
                "translationType": "agent",
                "translatedFrom": "en",
                "terminologySourceUrls": [
                    _terminology_url(terminology, locale)
                ],
            }
            if uncertain_terms:
                localization["uncertainTerms"] = uncertain_terms

            change["localizations"][locale] = localization

        batch["changes"].append(change)

    return batch


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate guarded unofficial WoW patch-note translations.",
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--terminology", required=True, type=Path)
    parser.add_argument("--workers", default=8, type=int)
    arguments = parser.parse_args()

    document = json.loads(arguments.input.read_text(encoding="utf-8"))
    terminology = json.loads(arguments.terminology.read_text(encoding="utf-8"))
    api_keys = load_gemini_api_keys(PROJECT_ROOT / ".env")
    unique_bullets = {
        bullet
        for change in document["changes"]
        for bullet in change["localizations"]["en"]["change"]
    }
    protected_texts = tuple(
        sorted(_protect_text(bullet)[0] for bullet in unique_bullets)
    )
    batch_languages = {
        language: LANGUAGE_NAMES[language]
        for language in dict.fromkeys(TARGET_LANGUAGE_CODES.values())
    }
    translated_cache, transport = generate_protected_translations(
        api_keys,
        protected_texts,
        batch_languages,
    )
    print(f"Gemini translation transport: {transport}")
    successful_locales, fallback_reasons = classify_locale_outcomes(
        translated_cache,
        TARGET_LANGUAGE_CODES,
    )

    def cached_translator(text: str, language: str) -> str:
        return translated_cache[(language, text)]

    batch = build_translation_batch(
        document,
        successful_locales,
        cached_translator,
        terminology,
    )
    if fallback_reasons:
        batch["fallbackReasons"] = fallback_reasons
    arguments.output.write_text(
        json.dumps(batch, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
