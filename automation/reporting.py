from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
from pathlib import Path
import re


ISSUE_MARKER = "<!-- better-patch-notes-automation -->"
ISSUE_TITLE = "Automatic patch-note refresh is blocked"
_SECRET_PATTERNS = (
    re.compile(r"AIza[A-Za-z0-9_-]{16,}"),
    re.compile(r"AQ\.[A-Za-z0-9_-]{16,}"),
    re.compile(
        r"(?i)\b(?:GEMINI_API_KEY2?|CF_API_TOKEN|auth|token)"
        r"\s*[:=]\s*[^\s]+",
    ),
)


@dataclass(frozen=True, slots=True)
class TerminologyWarningSummary:
    total: int
    by_locale: dict[str, int]
    changelog_text: str


def summarize_terminology_warnings(
    warnings: tuple[str, ...],
) -> TerminologyWarningSummary:
    counts = Counter(
        warning.partition(":")[0].strip()
        for warning in warnings
        if warning.partition(":")[0].strip()
    )
    by_locale = dict(sorted(counts.items()))
    breakdown = "; ".join(
        f"{locale}: {count}" for locale, count in by_locale.items()
    )
    total = sum(by_locale.values())
    changelog_text = (
        f"{total} preserved English terminology warnings ({breakdown})"
        if total
        else "No preserved English terminology warnings"
    )

    return TerminologyWarningSummary(
        total=total,
        by_locale=by_locale,
        changelog_text=changelog_text,
    )


def redact_secrets(value: str) -> str:
    redacted = value
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)

    return redacted


def build_issue_payload(
    *,
    stage: str,
    error: str,
    workflow_url: str,
    artifact_name: str,
    source_urls: tuple[str, ...],
) -> tuple[str, str]:
    safe_stage = redact_secrets(stage)
    safe_error = redact_secrets(error)
    safe_workflow_url = redact_secrets(workflow_url)
    safe_artifact_name = redact_secrets(artifact_name)
    safe_sources = tuple(redact_secrets(url) for url in source_urls)
    source_lines = "\n".join(f"- {url}" for url in safe_sources)
    if not source_lines:
        source_lines = "- No source URL was reached before the failure."

    body = (
        f"{ISSUE_MARKER}\n"
        "The unattended Blizzard patch-note refresh stopped without "
        "publishing.\n\n"
        f"- Stage: `{safe_stage}`\n"
        f"- Error: {safe_error}\n"
        f"- Workflow: {safe_workflow_url}\n"
        f"- Audit artifact: `{safe_artifact_name}`\n\n"
        "Official source URLs reached:\n\n"
        f"{source_lines}\n"
    )

    return ISSUE_TITLE, body


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a redacted automatic-refresh issue payload.",
    )
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--stage", required=True)
    parser.add_argument("--workflow-url", required=True)
    parser.add_argument("--artifact-name", required=True)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()

    result = json.loads(arguments.result.read_text(encoding="utf-8"))
    raw_urls = result.get("sourceUrls", [])
    source_urls = tuple(
        str(url) for url in raw_urls if isinstance(url, str)
    )
    title, body = build_issue_payload(
        stage=arguments.stage,
        error=str(result.get("reason", "workflow validation failed")),
        workflow_url=arguments.workflow_url,
        artifact_name=arguments.artifact_name,
        source_urls=source_urls,
    )
    arguments.output.write_text(
        json.dumps({"title": title, "body": body}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
