# Better Patch Notes

Better Patch Notes shows recent World of Warcraft Retail class, dungeon, and
raid changes inside the game. It keeps Live and PTR notes in one movable window
and opens automatically when new notes affect your class.

When a patch lands, use `/bpn` to see what changed without digging through long
articles or leaving the game.

## Features

- Opens automatically when the installed data contains changes you have not
  viewed for your class.
- Separates Live and PTR patch notes.
- Focuses your class view on the current specialization and class-wide notes.
- Provides icons for all 13 classes so you can browse every specialization.
- Groups related bullets into one change instead of separate cards.
- Organizes class, dungeon, and raid changes into collapsible sections.
- Uses a movable, scrollable in-game window.
- Provides a draggable minimap button with remembered visibility and position.
- Remembers viewed versions per class and channel across the account.
- Keeps source and research details out of the player-facing interface.

## Requirements

- World of Warcraft Retail
- No external addon libraries or dependencies

## Installation

### CurseForge

Install **Better Patch Notes** through the CurseForge app. Once installed,
CurseForge can deliver new addon releases and their bundled patch-note data.

## Usage

Better Patch Notes opens automatically when there are unseen notes for the
class you log in with. To open it manually, use `/bpn` or
`/betterpatchnotes`.

Left-click the minimap button to open Better Patch Notes. Right-click it to
open the addon or hide the button, and drag it to move it around the minimap.
Use `/bpn minimap` to toggle the button after hiding it. Press **Escape** to
close the patch-note window.

Use the **Live** and **PTR** tabs to change channels. Select a class icon to
browse that class; other classes show their class-wide and specialization
changes together. Dungeon and raid sections remain available regardless of
the selected class.

Closing the window marks notes as viewed only for your character's actual
class. Browsing another class does not affect its unseen status, and reopening
the window resets the selection to your own class.

## How patch-note updates work

Patch-note data is bundled into each addon release.
Better Patch Notes does not access the internet while WoW is running. It does
not scrape websites or download data during play.

Install an updated addon release to receive newer notes. Live entries target
the installed Retail patch, while PTR entries may target a newer test build.
The packaged history is intentionally limited to recent, relevant changes.

## Localization

The interface supports these official WoW client locales:

`deDE`, `enGB`, `enUS`, `esES`, `esMX`, `frFR`, `itIT`, `koKR`, `ptBR`,
`ruRU`, `zhCN`, and `zhTW`.

Localized patch-note text is included only when an official localized version
is available. Otherwise, the addon displays an English fallback instead of an
unofficial translation.

## Current status

- **Addon version:** 0.2.5
- **Game:** World of Warcraft Retail
- **Interface version:** 120007
- **Bundled data:** Live 12.0.7 and PTR 12.1
- **Status:** Active development

See [changelog.txt](changelog.txt) for release details.

## Support

Report bugs or request features through
[GitHub Issues](https://github.com/VadimTofan/better-patch-notes/issues).
Include your WoW client version, locale, class, specialization, and the steps
needed to reproduce the problem.

## Maintainer

Better Patch Notes is maintained by
[VadimTofan](https://github.com/VadimTofan).

## License

Better Patch Notes is available under the [MIT License](LICENSE).
