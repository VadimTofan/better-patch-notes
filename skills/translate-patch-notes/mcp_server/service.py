from __future__ import annotations

from copy import deepcopy
from datetime import date
import json
from pathlib import Path
from urllib.parse import urlparse

from audit import audit_translation
from workspace import SUPPORTED_TRANSLATION_LOCALES, TranslationWorkspace


ALLOWED_TERM_TYPES = {
    "ability",
    "boss",
    "class",
    "dungeon",
    "encounter",
    "item",
    "raid",
    "specialization",
    "system",
}

BLIZZARD_HOSTS = {
    "news.blizzard.com",
    "worldofwarcraft.blizzard.com",
}


class TranslationService:
    """Coordinate resumable, locale-by-locale patch-note translation work."""

    def __init__(
        self,
        canonical_path: Path,
        terminology_path: Path,
        work_dir: Path,
    ) -> None:
        self.canonical_path = canonical_path
        self.terminology_path = terminology_path
        self.workspace = TranslationWorkspace(canonical_path, work_dir)

    def prepare_locale(self, locale: str) -> dict[str, object]:
        self._require_locale(locale)
        self.workspace.begin()

        canonical = self._read_json(self.canonical_path)
        terminology = self._read_json(self.terminology_path)
        records: list[dict[str, object]] = []

        for raw_record in canonical.get("changes", []):
            if not isinstance(raw_record, dict):
                continue

            localizations = raw_record.get("localizations", {})
            if not isinstance(localizations, dict):
                localizations = {}

            records.append(
                {
                    "id": raw_record.get("id", ""),
                    "channel": raw_record.get("channel", ""),
                    "category": raw_record.get("category", ""),
                    "date": raw_record.get("date", ""),
                    "patch": raw_record.get("patch", ""),
                    "english": deepcopy(localizations.get("en", {})),
                    "existing": deepcopy(localizations.get(locale, {})),
                }
            )

        locale_terms: dict[str, object] = {}
        locale_documents = terminology.get("locales", {})
        if isinstance(locale_documents, dict):
            locale_document = locale_documents.get(locale, {})
            if isinstance(locale_document, dict):
                raw_terms = locale_document.get("terms", {})
                if isinstance(raw_terms, dict):
                    locale_terms = deepcopy(raw_terms)

        return {
            "locale": locale,
            "records": records,
            "terminology": locale_terms,
        }

    def record_terminology(
        self,
        locale: str,
        terms: list[dict[str, str]],
    ) -> dict[str, object]:
        self._require_locale(locale)
        validated_terms = [self._validate_term(term) for term in terms]
        state = self.workspace.begin()

        terminology = state.get("terminology")
        if not isinstance(terminology, dict):
            terminology = {}
            state["terminology"] = terminology

        locale_terms = terminology.setdefault(locale, {})
        if not isinstance(locale_terms, dict):
            raise ValueError(f"workspace terminology for {locale} is invalid")

        for term in validated_terms:
            english = term.pop("english")
            locale_terms[english] = term

        self.workspace.save(state)
        return {"locale": locale, "recorded": len(validated_terms)}

    def submit_locale(
        self,
        locale: str,
        records: list[dict[str, object]],
        outcome: str = "agent",
        fallback_reason: str = "",
    ) -> dict[str, object]:
        self._require_locale(locale)
        if outcome not in {"agent", "official", "english-fallback"}:
            raise ValueError(f"unsupported locale outcome: {outcome}")
        if outcome == "english-fallback":
            if not fallback_reason.strip():
                raise ValueError("English fallback reason must be documented")
            if records:
                raise ValueError(
                    "English fallback must not include localized records"
                )

            state = self.workspace.begin()
            locale_state = self._locale_state(state, locale)
            locale_state.update(
                {
                    "status": "fallback",
                    "fallbackReason": fallback_reason.strip(),
                    "records": {},
                    "audit": {},
                }
            )
            self.workspace.save(state)
            return {"locale": locale, "status": "fallback", "recorded": 0}

        canonical = self._read_json(self.canonical_path)
        english_by_id = self._english_by_id(canonical)
        submitted_by_id: dict[str, dict[str, object]] = {}
        for record in records:
            if not isinstance(record, dict):
                raise ValueError("each submitted record must be an object")

            record_id = record.get("id")
            if not isinstance(record_id, str) or record_id not in english_by_id:
                raise ValueError(f"unknown patch-note record ID: {record_id}")
            if record_id in submitted_by_id:
                raise ValueError(f"duplicate patch-note record ID: {record_id}")

            submitted_by_id[record_id] = self._normalize_localization(
                record,
                english_by_id[record_id],
                outcome,
            )

        missing_ids = sorted(set(english_by_id) - set(submitted_by_id))
        if missing_ids:
            raise ValueError(
                "locale submission is missing record IDs: "
                + ", ".join(missing_ids)
            )

        state = self.workspace.begin()
        locale_state = self._locale_state(state, locale)
        locale_state.update(
            {
                "status": "staged",
                "fallbackReason": "",
                "records": submitted_by_id,
                "audit": {},
            }
        )
        self.workspace.save(state)
        return {
            "locale": locale,
            "status": "staged",
            "recorded": len(submitted_by_id),
        }

    def audit_locale(self, locale: str) -> dict[str, object]:
        self._require_locale(locale)
        state = self.workspace.begin()
        locale_state = self._locale_state(state, locale)
        if locale_state.get("status") == "fallback":
            return {
                "locale": locale,
                "passed": True,
                "outcome": "english-fallback",
                "records": [],
            }

        raw_records = locale_state.get("records")
        if not isinstance(raw_records, dict) or not raw_records:
            raise ValueError(f"{locale} has no staged records to audit")

        canonical = self._read_json(self.canonical_path)
        english_by_id = self._english_by_id(canonical)
        peer_records = self._regional_peer_records(state, locale)
        locale_terms = self._locale_terminology(state, locale)
        record_reports: list[dict[str, object]] = []
        for record_id, english in english_by_id.items():
            localized = raw_records.get(record_id)
            if not isinstance(localized, dict):
                raise ValueError(
                    f"{locale} is missing staged record {record_id}"
                )

            regional_peer = peer_records.get(record_id)
            if not isinstance(regional_peer, dict):
                regional_peer = None
            report = audit_translation(
                locale,
                english,
                localized,
                regional_peer,
                locale_terms,
            )
            report["id"] = record_id
            record_reports.append(report)

        passed = all(bool(report.get("passed")) for report in record_reports)
        locale_state["status"] = "passed" if passed else "needs-review"
        locale_state["audit"] = {"passed": passed, "records": record_reports}
        self.workspace.save(state)
        return {
            "locale": locale,
            "passed": passed,
            "records": record_reports,
        }

    def compare_locale(self, locale: str) -> dict[str, object]:
        self._require_locale(locale)
        state = self.workspace.begin()
        locale_state = self._locale_state(state, locale)
        raw_records = locale_state.get("records", {})
        if not isinstance(raw_records, dict):
            raw_records = {}

        canonical = self._read_json(self.canonical_path)
        records: list[dict[str, object]] = []
        for record_id, english in self._english_by_id(canonical).items():
            records.append(
                {
                    "id": record_id,
                    "english": deepcopy(english),
                    "localized": deepcopy(raw_records.get(record_id, {})),
                }
            )

        return {
            "locale": locale,
            "status": locale_state.get("status", "pending"),
            "records": records,
        }

    def translation_status(self) -> dict[str, object]:
        state = self.workspace.begin()
        locales = state.get("locales")
        if not isinstance(locales, dict):
            raise ValueError("translation workspace locale matrix is invalid")

        status_counts: dict[str, int] = {}
        for raw_locale_state in locales.values():
            if not isinstance(raw_locale_state, dict):
                continue
            status = str(raw_locale_state.get("status", "pending"))
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "sourceUpdatedAt": state.get("sourceUpdatedAt", ""),
            "locales": deepcopy(locales),
            "counts": status_counts,
        }

    def finalize_translations(self) -> dict[str, object]:
        state = self.workspace.begin()
        locales = state.get("locales")
        if not isinstance(locales, dict):
            raise ValueError("translation workspace locale matrix is invalid")

        failed_final_audits: list[str] = []
        for locale in SUPPORTED_TRANSLATION_LOCALES:
            locale_state = locales.get(locale)
            if (
                isinstance(locale_state, dict)
                and locale_state.get("status") == "passed"
                and not self.audit_locale(locale).get("passed")
            ):
                failed_final_audits.append(locale)
        if failed_final_audits:
            raise ValueError(
                "failed final audit: " + ", ".join(failed_final_audits)
            )

        state = self.workspace.load()
        locales = state.get("locales")
        if not isinstance(locales, dict):
            raise ValueError("translation workspace locale matrix is invalid")

        incomplete = sorted(
            locale
            for locale in SUPPORTED_TRANSLATION_LOCALES
            if not isinstance(locales.get(locale), dict)
            or locales[locale].get("status") not in {"passed", "fallback"}
        )
        if incomplete:
            raise ValueError("incomplete locales: " + ", ".join(incomplete))

        batch = deepcopy(self._read_json(self.canonical_path))
        changes = batch.get("changes")
        if not isinstance(changes, list):
            raise ValueError("canonical changes must be an array")

        fallback_reasons: dict[str, str] = {}
        completed_locales: list[str] = []
        for locale in SUPPORTED_TRANSLATION_LOCALES:
            raw_locale_state = locales[locale]
            if not isinstance(raw_locale_state, dict):
                raise ValueError(f"invalid locale state for {locale}")
            if raw_locale_state.get("status") == "fallback":
                fallback_reasons[locale] = str(
                    raw_locale_state.get("fallbackReason", "")
                )
                continue

            raw_records = raw_locale_state.get("records")
            if not isinstance(raw_records, dict):
                raise ValueError(f"invalid staged records for {locale}")
            for change in changes:
                if not isinstance(change, dict):
                    continue
                record_id = change.get("id")
                localizations = change.get("localizations")
                if not isinstance(record_id, str) or not isinstance(
                    localizations,
                    dict,
                ):
                    raise ValueError(
                        "canonical change has invalid localizations"
                    )
                localizations[locale] = deepcopy(raw_records[record_id])
            completed_locales.append(locale)

        batch["localeCompletion"] = {
            "localized": completed_locales,
            "fallbacks": fallback_reasons,
        }
        terminology = self._merged_terminology(state)
        batch_path = self.workspace.work_dir / "translation-batch.json"
        terminology_path = self.workspace.work_dir / "terminology.json"
        self._write_json_atomic(batch_path, batch)
        self._write_json_atomic(terminology_path, terminology)

        return {
            "batchPath": str(batch_path),
            "terminologyPath": str(terminology_path),
            "localized": completed_locales,
            "fallbacks": fallback_reasons,
        }

    @staticmethod
    def _read_json(path: Path) -> dict[str, object]:
        document = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(document, dict):
            raise ValueError(f"{path.name} must contain a JSON object")

        return document

    @staticmethod
    def _english_by_id(
        canonical: dict[str, object],
    ) -> dict[str, dict[str, object]]:
        changes = canonical.get("changes")
        if not isinstance(changes, list):
            raise ValueError("canonical changes must be an array")

        english_by_id: dict[str, dict[str, object]] = {}
        for change in changes:
            if not isinstance(change, dict):
                raise ValueError("each canonical change must be an object")
            record_id = change.get("id")
            localizations = change.get("localizations")
            if not isinstance(record_id, str) or not isinstance(
                localizations,
                dict,
            ):
                raise ValueError(
                    "canonical change is missing ID or localizations"
                )
            english = localizations.get("en")
            if not isinstance(english, dict):
                raise ValueError(f"canonical change {record_id} is missing en")
            english_by_id[record_id] = english

        return english_by_id

    @staticmethod
    def _locale_state(
        state: dict[str, object],
        locale: str,
    ) -> dict[str, object]:
        locales = state.get("locales")
        if not isinstance(locales, dict):
            raise ValueError("translation workspace locale matrix is invalid")
        locale_state = locales.get(locale)
        if not isinstance(locale_state, dict):
            raise ValueError(f"translation workspace is missing {locale}")

        return locale_state

    @staticmethod
    def _normalize_localization(
        record: dict[str, object],
        english: dict[str, object],
        outcome: str,
    ) -> dict[str, object]:
        name = record.get("name")
        specialization = record.get("specialization")
        changes = record.get("change")
        if not isinstance(name, str) or not name.strip():
            raise ValueError("localized name must be a non-empty string")
        if not isinstance(specialization, str) or not specialization.strip():
            raise ValueError(
                "localized specialization must be a non-empty string"
            )
        if (
            not isinstance(changes, list)
            or not changes
            or not all(
                isinstance(change, str) and change.strip()
                for change in changes
            )
        ):
            raise ValueError(
                "localized change must be a non-empty string array"
            )

        translation_type = record.get("translationType", outcome)
        if translation_type != outcome:
            raise ValueError("translationType must match the submitted outcome")
        terminology_urls = record.get("terminologySourceUrls", [])
        uncertain_terms = record.get("uncertainTerms", [])
        if not isinstance(terminology_urls, list):
            raise ValueError("terminologySourceUrls must be an array")
        if not isinstance(uncertain_terms, list):
            raise ValueError("uncertainTerms must be an array")

        source_url = english.get("sourceUrl", "")
        if outcome == "official":
            source_url = record.get("sourceUrl")
            parsed_source = (
                urlparse(source_url)
                if isinstance(source_url, str)
                else None
            )
            if (
                parsed_source is None
                or parsed_source.scheme != "https"
                or parsed_source.hostname not in BLIZZARD_HOSTS
            ):
                raise ValueError("official sourceUrl must be a Blizzard URL")

        return {
            "name": name.strip(),
            "specialization": specialization.strip(),
            "change": [str(change).strip() for change in changes],
            "source": english.get("source", "Blizzard"),
            "sourceUrl": source_url,
            "translationType": translation_type,
            "translatedFrom": "" if outcome == "official" else "en",
            "terminologySourceUrls": deepcopy(terminology_urls),
            "uncertainTerms": deepcopy(uncertain_terms),
        }

    @staticmethod
    def _regional_peer_records(
        state: dict[str, object],
        locale: str,
    ) -> dict[str, object]:
        peer_by_locale = {
            "esES": "esMX",
            "esMX": "esES",
            "zhCN": "zhTW",
            "zhTW": "zhCN",
        }
        peer = peer_by_locale.get(locale)
        if peer is None:
            return {}
        locales = state.get("locales")
        if not isinstance(locales, dict):
            return {}
        peer_state = locales.get(peer)
        if not isinstance(peer_state, dict):
            return {}
        peer_records = peer_state.get("records")

        return peer_records if isinstance(peer_records, dict) else {}

    def _merged_terminology(
        self,
        state: dict[str, object],
    ) -> dict[str, object]:
        terminology = deepcopy(self._read_json(self.terminology_path))
        locales = terminology.setdefault("locales", {})
        if not isinstance(locales, dict):
            raise ValueError("canonical terminology locales must be an object")
        staged = state.get("terminology", {})
        if not isinstance(staged, dict):
            raise ValueError("staged terminology must be an object")

        for locale, raw_terms in staged.items():
            if not isinstance(raw_terms, dict):
                raise ValueError(f"staged terminology for {locale} is invalid")
            locale_document = locales.setdefault(locale, {"terms": {}})
            if not isinstance(locale_document, dict):
                raise ValueError(
                    f"canonical terminology for {locale} is invalid"
                )
            terms = locale_document.setdefault("terms", {})
            if not isinstance(terms, dict):
                raise ValueError(
                    f"canonical terminology terms for {locale} are invalid"
                )
            terms.update(deepcopy(raw_terms))

        return terminology

    def _locale_terminology(
        self,
        state: dict[str, object],
        locale: str,
    ) -> dict[str, object]:
        terminology = self._merged_terminology(state)
        locales = terminology.get("locales")
        if not isinstance(locales, dict):
            raise ValueError("terminology locales must be an object")
        locale_document = locales.get(locale)
        if not isinstance(locale_document, dict):
            raise ValueError(f"terminology is missing locale {locale}")
        terms = locale_document.get("terms")
        if not isinstance(terms, dict):
            raise ValueError(
                f"terminology terms for {locale} must be an object"
            )

        return terms

    @staticmethod
    def _write_json_atomic(path: Path, document: dict[str, object]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(path.suffix + ".tmp")
        serialized = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
        temporary_path.write_text(serialized, encoding="utf-8")
        temporary_path.replace(path)

    @staticmethod
    def _require_locale(locale: str) -> None:
        if locale not in SUPPORTED_TRANSLATION_LOCALES:
            raise ValueError(f"unsupported locale: {locale}")

    @staticmethod
    def _validate_term(term: dict[str, str]) -> dict[str, str]:
        if not isinstance(term, dict):
            raise ValueError("each terminology entry must be an object")

        required_fields = (
            "english",
            "localized",
            "type",
            "sourceUrl",
            "reviewedAt",
        )
        validated: dict[str, str] = {}
        for field in required_fields:
            value = term.get(field)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(
                    f"terminology {field} must be a non-empty string"
                )
            validated[field] = value.strip()

        if validated["type"] not in ALLOWED_TERM_TYPES:
            raise ValueError(
                f"unsupported terminology type: {validated['type']}"
            )

        source = urlparse(validated["sourceUrl"])
        if source.scheme != "https" or source.hostname not in BLIZZARD_HOSTS:
            raise ValueError(
                "terminology sourceUrl must be an official Blizzard URL"
            )

        try:
            date.fromisoformat(validated["reviewedAt"])
        except ValueError as error:
            raise ValueError(
                "terminology reviewedAt must use YYYY-MM-DD"
            ) from error

        return validated
