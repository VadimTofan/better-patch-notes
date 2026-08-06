from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
README_PATH = PROJECT_ROOT / "README.md"
LICENSE_PATH = PROJECT_ROOT / "LICENSE"


# Describe: public GitHub documentation
class ReadmeContractTests(unittest.TestCase):
    def test_readme_explains_the_addon_and_how_to_use_it(self) -> None:
        # Given the approved user-facing README content
        required_phrases = (
            "# Better Patch Notes",
            "## Features",
            "## Installation",
            "## Usage",
            "## How patch-note updates work",
            "## Localization",
            "## Current status",
            "## Support",
            "## Maintainer",
            "## License",
            "Live and PTR",
            "class, dungeon, and raid",
            "`/bpn`",
            "`/betterpatchnotes`",
            "`/bpn minimap`",
            "minimap button",
            "Left-click",
            "Right-click",
            "Escape",
            "does not access the internet",
            "English fallback",
            "unofficial translations",
            "translated from English",
            "https://github.com/VadimTofan/better-patch-notes/issues",
            "VadimTofan",
            "MIT License",
        )
        forbidden_phrases = (
            "### Manual installation",
            "GitHub Releases",
            "automatically generated source archive",
        )

        # When the repository README is inspected
        self.assertTrue(README_PATH.exists())
        readme = README_PATH.read_text(encoding="utf-8")

        # Then it contains complete usage and project information
        for phrase in required_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, readme)
        for phrase in forbidden_phrases:
            with self.subTest(forbidden_phrase=phrase):
                self.assertNotIn(phrase, readme)
        self.assertNotIn("TODO", readme)
        self.assertNotIn("TBD", readme)

    def test_license_contains_the_standard_mit_grant(self) -> None:
        # Given the approved MIT licensing choice
        required_phrases = (
            "MIT License",
            "Copyright (c) 2026 Vadim Tofan",
            "Permission is hereby granted, free of charge",
            'THE SOFTWARE IS PROVIDED "AS IS"',
        )

        # When the root license file is inspected
        self.assertTrue(LICENSE_PATH.exists())
        license_text = LICENSE_PATH.read_text(encoding="utf-8")

        # Then it contains the complete identifying MIT terms
        for phrase in required_phrases:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, license_text)


if __name__ == "__main__":
    unittest.main()
