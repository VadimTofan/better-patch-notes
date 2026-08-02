# Better Patch Notes — Web

The public Vue 3 companion to the Better Patch Notes World of Warcraft addon.
It presents the same curated Retail class, dungeon, and raid changes in a
responsive browser interface with Live/PTR switching and 11 locales.

## Local development

Requirements: Node.js 24.15 or newer within the Node 24 release line.

```sh
npm install
npm run dev
```

The `predev` and `prebuild` scripts validate and copy the repository's
canonical `../data/retail-patch-notes.json` into an ignored generated folder.
Do not edit the generated copy.

## Validation

```sh
npm test
npm run build
```

## Netlify

Connect the repository to Netlify. The root `netlify.toml` sets the base
directory, production command, publish directory, Node version, and SPA route
fallback. Class URLs such as `/druid` therefore work when opened directly.
