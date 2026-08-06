from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOC_PATH = PROJECT_ROOT / "BetterPatchNotes.toc"


def _toc_files() -> list[str]:
    lines = TOC_PATH.read_text(encoding="utf-8-sig").splitlines()

    return [line for line in lines if line and not line.startswith("##")]


# Describe: WoW addon manifest and shared namespace
class AddonManifestTests(unittest.TestCase):
    def test_manifest_declares_retail_metadata_and_load_order(self) -> None:
        # Given the required Retail addon metadata and module dependency order
        expected_files = [
            "Addon.lua",
            "Localization.lua",
            "PatchNotesData.lua",
            "Data.lua",
            "State.lua",
            "Window.lua",
            "MinimapButton.lua",
            "Core.lua",
        ]

        # When the table of contents is inspected
        self.assertTrue(TOC_PATH.exists())
        toc_text = TOC_PATH.read_text(encoding="utf-8-sig")

        # Then WoW loads every module in its dependency order
        self.assertIn("## Interface: 120007", toc_text)
        self.assertIn("## SavedVariables: BetterPatchNotesDB", toc_text)
        self.assertEqual(expected_files, _toc_files())

    def test_each_lua_module_uses_the_shared_addon_namespace(self) -> None:
        # Given every handwritten Lua module in the manifest
        module_names = [
            "Addon.lua",
            "Localization.lua",
            "Data.lua",
            "State.lua",
            "Window.lua",
            "MinimapButton.lua",
            "Core.lua",
        ]

        # When their module headers are inspected
        module_text = {}
        for name in module_names:
            module_path = PROJECT_ROOT / name
            self.assertTrue(module_path.exists(), name)
            module_text[name] = module_path.read_text(encoding="utf-8-sig")

        # Then each module receives the same private namespace table
        for name, text in module_text.items():
            with self.subTest(module=name):
                self.assertIn("local _, addon = ...", text)


# Describe: localized addon interface labels
class LocalizationContractTests(unittest.TestCase):
    def test_all_wow_locales_define_every_visible_label(self) -> None:
        # Given all supported WoW clients and the visible addon labels
        locales = (
            "deDE",
            "en",
            "esES",
            "esMX",
            "frFR",
            "itIT",
            "koKR",
            "ptBR",
            "ruRU",
            "zhCN",
            "zhTW",
        )
        label_keys = (
            "TITLE",
            "LIVE",
            "PTR",
            "CLASS_CHANGES",
            "CLASS_WIDE",
            "OTHER_SPECIALIZATIONS",
            "DUNGEON_CHANGES",
            "RAID_CHANGES",
            "NO_CHANGES",
            "ENGLISH_FALLBACK",
            "OPEN_ADDON",
            "HIDE_MINIMAP_BUTTON",
            "CLOSE",
            "NEW",
            "SOURCE",
            "COPY_SOURCE_INSTRUCTION",
        )

        # When the localization module is inspected
        localization_text = (
            PROJECT_ROOT / "Localization.lua"
        ).read_text(encoding="utf-8-sig")

        # Then every locale owns a complete explicit label table
        for locale in locales:
            marker = f'["{locale}"] = {{'
            with self.subTest(locale=locale):
                self.assertIn(marker, localization_text)
                locale_start = localization_text.index(marker)
                locale_end = localization_text.index(
                    "\n    },",
                    locale_start,
                )
                locale_block = localization_text[locale_start:locale_end]
                for key in label_keys:
                    self.assertIn(f"{key} =", locale_block)

    def test_runtime_locale_has_english_and_key_fallbacks(self) -> None:
        # Given a client locale whose translation may be missing a future key
        localization_text = (
            PROJECT_ROOT / "Localization.lua"
        ).read_text(encoding="utf-8-sig")

        # When the runtime lookup contract is inspected
        # Then the real client locale uses English and key fallbacks
        self.assertIn("local locale = GetLocale()", localization_text)
        self.assertIn(
            'locale == "enUS" or locale == "enGB"',
            localization_text,
        )
        self.assertIn(
            "local selected = translations[locale] or translations.en",
            localization_text,
        )
        self.assertIn("translations.en[key]", localization_text)
        self.assertIn("or key", localization_text)


# Describe: patch-note selection and account-wide seen state
class DataAndStateContractTests(unittest.TestCase):
    def test_data_module_exposes_locale_and_section_selection(self) -> None:
        # Given generated changes tagged with class and specialization IDs
        data_text = (PROJECT_ROOT / "Data.lua").read_text("utf-8-sig")

        # When the runtime data API is inspected
        # Then it supports localized fallback and ordered class/content groups
        required_contract = (
            "function addon.GetLocalizedChange",
            "function addon.GetSourceUrl",
            'sourceUrl:match("^https://")',
            "change.localizations[locale]",
            "local locale = GetLocale()",
            'locale == "enUS" or locale == "enGB"',
            "change.localizations.en",
            "function addon.GetSections",
            'change.category == "Class"',
            'change.category == "Dungeon"',
            'change.category == "Raid"',
            "change.classToken == classToken",
            "change.specializationId == specializationId",
        )
        for phrase in required_contract:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, data_text)

    def test_data_module_supports_browsing_all_class_specializations(self) -> None:
        # Given a player browsing a class other than their own
        data_text = (PROJECT_ROOT / "Data.lua").read_text("utf-8-sig")

        # When the class-section API is inspected
        # Then it can detect available notes and combine all class changes
        required_contract = (
            "function addon.HasClassChanges",
            "function addon.GetSections(",
            "allSpecializations",
            "local allClassChanges = {}",
            "table.insert(allClassChanges, change)",
            '"all-specializations"',
            'addon.GetText("CLASS_CHANGES")',
        )
        for phrase in required_contract:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, data_text)

    def test_state_module_tracks_versions_per_class_and_channel(self) -> None:
        # Given an account-wide SavedVariables table
        state_text = (PROJECT_ROOT / "State.lua").read_text("utf-8-sig")

        # When the state contract is inspected
        # Then it sanitizes defaults and exposes version-based seen behavior
        required_contract = (
            "function addon.InitializeState",
            "BetterPatchNotesDB",
            "schemaVersion = 1",
            "seen = {}",
            'point = "CENTER"',
            "minimap = {",
            "hidden = false",
            "angle = 220",
            "sanitizeMinimap",
            "function addon.HasUnseen",
            "classChannelVersions[classToken]",
            "function addon.MarkAllSeen",
            "function addon.SelectInitialChannel",
            'return "live"',
        )
        for phrase in required_contract:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, state_text)


# Describe: player-facing patch-note window and lifecycle
class WindowAndCoreContractTests(unittest.TestCase):
    def test_window_is_movable_scrollable_tabbed_and_collapsible(self) -> None:
        # Given the approved patch-note window behavior
        window_text = (PROJECT_ROOT / "Window.lua").read_text("utf-8-sig")

        # When the window implementation is inspected
        # Then it provides the required interaction and rendering contracts
        required_contract = (
            "local frame = CreateFrame(",
            '"BetterPatchNotesWindow"',
            '"UIPanelScrollFrameTemplate"',
            "SetMovable(true)",
            'CreateTab("live"',
            'CreateTab("ptr"',
            "addon.GetSections",
            "addon.GetLocalizedChange",
            'table.concat(localized.change, "\\n• ")',
            'addon.GetText("ENGLISH_FALLBACK")',
            "function addon.ShowWindow",
            "function addon.RefreshWindow",
            "addon.MarkAllSeen",
            "StartMoving",
            "StopMovingOrSizing",
            "UISpecialFrames",
            "frame:GetName()",
            '"BetterPatchNotesSourceDialog"',
            '"InputBoxTemplate"',
            'addon.GetText("SOURCE")',
            'addon.GetText("COPY_SOURCE_INSTRUCTION")',
            "addon.GetSourceUrl(change)",
            "sourceDialog.editBox:SetText(sourceUrl)",
            "sourceDialog.editBox:SetFocus()",
            "sourceDialog.editBox:HighlightText()",
            'SetScript("OnEscapePressed"',
            "sourceDialog:GetName()",
        )
        for phrase in required_contract:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, window_text)

    def test_window_browses_all_classes_with_transient_icon_selection(self) -> None:
        # Given all playable Retail classes and a player-specific seen state
        window_text = (PROJECT_ROOT / "Window.lua").read_text("utf-8-sig")

        # When the class-browser implementation is inspected
        # Then all class icons are localized, selectable, and session-only
        required_contract = (
            "local CLASS_COUNT = 13",
            "for classId = 1, CLASS_COUNT do",
            "GetClassInfo(classId)",
            '"classicon-" .. classToken:lower()',
            "CLASS_ICON_TCOORDS[classToken]",
            "GameTooltip:SetText(className)",
            "addon.HasClassChanges(activeChannel, classToken)",
            "selectedClassToken = classToken",
            "selectedClassToken == playerClassToken",
            "showAllSpecializations",
            "selectedClassToken = playerClassToken",
        )
        for phrase in required_contract:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, window_text)

        # And closing the browser still records only the real player class
        self.assertIn("local classToken = addon.GetPlayerContext()", window_text)
        self.assertIn("addon.MarkAllSeen(classToken)", window_text)

    def test_core_handles_login_combat_deferral_and_slash_reopen(self) -> None:
        # Given automatic first-login display and manual reopen behavior
        core_text = (PROJECT_ROOT / "Core.lua").read_text("utf-8-sig")

        # When the lifecycle module is inspected
        # Then it initializes safely, defers combat, and registers both commands
        required_contract = (
            'RegisterEvent("ADDON_LOADED")',
            'RegisterEvent("PLAYER_LOGIN")',
            'RegisterEvent("PLAYER_SPECIALIZATION_CHANGED")',
            'RegisterEvent("PLAYER_REGEN_ENABLED")',
            "addon.InitializeState()",
            "addon.InitializeMinimapButton()",
            "InCombatLockdown()",
            "addon.HasUnseen",
            "addon.SelectInitialChannel",
            "addon.ShowWindow",
            'SLASH_BETTERPATCHNOTES1 = "/bpn"',
            'SLASH_BETTERPATCHNOTES2 = "/betterpatchnotes"',
            "SlashCmdList.BETTERPATCHNOTES",
            'message == "minimap"',
            "addon.ToggleMinimapButton()",
        )
        for phrase in required_contract:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, core_text)

    def test_minimap_button_opens_hides_toggles_and_remembers_position(
        self,
    ) -> None:
        # Given the approved dependency-free minimap launcher behavior
        minimap_path = PROJECT_ROOT / "MinimapButton.lua"

        # When the minimap module is inspected
        self.assertTrue(minimap_path.exists())
        minimap_text = minimap_path.read_text("utf-8-sig")
        required_contract = (
            'CreateFrame("Button", "BetterPatchNotesMinimapButton", Minimap)',
            'RegisterForClicks("LeftButtonUp", "RightButtonUp")',
            'RegisterForDrag("LeftButton")',
            'mouseButton == "LeftButton"',
            'mouseButton == "RightButton"',
            "addon.ShowWindow(addon.SelectInitialChannel(classToken))",
            "MenuUtil.CreateContextMenu",
            'addon.GetText("OPEN_ADDON")',
            'addon.GetText("HIDE_MINIMAP_BUTTON")',
            "addon.db.minimap.hidden",
            "addon.db.minimap.angle",
            "GetCursorPosition()",
            "Minimap:GetCenter()",
            'SetScript("OnDragStart"',
            'SetScript("OnDragStop"',
            "function addon.InitializeMinimapButton",
            "function addon.ToggleMinimapButton",
        )

        # Then every click, menu, drag, and persistence contract is explicit
        for phrase in required_contract:
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, minimap_text)


if __name__ == "__main__":
    unittest.main()
