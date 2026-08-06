from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from service import TranslationService


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SERVICE = TranslationService(
    canonical_path=PROJECT_ROOT / "data" / "retail-patch-notes.json",
    terminology_path=(
        PROJECT_ROOT
        / "skills"
        / "translate-patch-notes"
        / "references"
        / "terminology.json"
    ),
    work_dir=PROJECT_ROOT / ".bpn-work",
)

mcp = FastMCP(
    "BetterPatchNotes Translation",
    instructions=(
        "Coordinate locale-by-locale World of Warcraft patch-note translation. "
        "Prefer official Blizzard localizations, preserve whole bullets and "
        "verified terminology, audit each locale separately, and finalize only "
        "after every locale passes or has a documented English fallback."
    ),
    json_response=True,
)


@mcp.tool()
def prepare_locale(locale: str) -> dict[str, object]:
    """Return English, existing locale text, and verified terminology."""

    return SERVICE.prepare_locale(locale)


@mcp.tool()
def record_terminology(
    locale: str,
    terms: list[dict[str, str]],
) -> dict[str, object]:
    """Stage locale terminology backed by direct official Blizzard URLs."""

    return SERVICE.record_terminology(locale, terms)


@mcp.tool()
def submit_locale(
    locale: str,
    records: list[dict[str, object]],
    outcome: str = "agent",
    fallback_reason: str = "",
) -> dict[str, object]:
    """Stage one complete locale or classify a documented English fallback."""

    return SERVICE.submit_locale(
        locale,
        records,
        outcome=outcome,
        fallback_reason=fallback_reason,
    )


@mcp.tool()
def audit_locale(locale: str) -> dict[str, object]:
    """Run the deterministic 30-check review for every staged locale record."""

    return SERVICE.audit_locale(locale)


@mcp.tool()
def compare_locale(locale: str) -> dict[str, object]:
    """Return English and staged locale records aligned by stable record ID."""

    return SERVICE.compare_locale(locale)


@mcp.tool()
def translation_status() -> dict[str, object]:
    """Report resumable progress for all ten required translation locales."""

    return SERVICE.translation_status()


@mcp.tool()
def finalize_translations() -> dict[str, object]:
    """Write reviewed batch artifacts without modifying canonical addon data."""

    return SERVICE.finalize_translations()


if __name__ == "__main__":
    mcp.run(transport="stdio")
