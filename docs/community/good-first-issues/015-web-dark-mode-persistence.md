# [web] Add dark-mode toggle with `localStorage` persistence on beta search page

## What

The beta search page at `https://structural-isomorphism.bytedance.city/search` currently has no dark-mode option, and the `meta[name="theme-color"]` is hard-coded to `#FAFAF9` (light). Add a toggle button in the top-right corner that flips between light and dark themes, and persist the choice across reloads via `localStorage`.

## Why

A meaningful fraction of our visitors read at night or have an OS-wide dark preference. We already render heavy text — a dark theme improves accessibility and signals UI polish on the public beta. `localStorage` persistence is the standard expectation (every time they reload should not reset their choice).

## Where

- HTML: `web/frontend/search.html`
- CSS: `web/frontend/assets/css/search.css`
- JS: `web/frontend/assets/js/search.js`
- Constraint: vanilla JS / vanilla CSS only — no framework added for this change

## How to start

1. Add a `<button id="theme-toggle">🌙</button>` in the top nav of `search.html`.
2. In `search.css`, define a `[data-theme="dark"]` selector overriding the existing palette tokens (background, text, link, border). Pick the dark palette consistent with the existing brand (likely `#0F0F0F` bg / `#EAEAEA` text — confirm with maintainer if there's a brand-book).
3. In `search.js`:
   - On load, read `localStorage.getItem("theme")`. If `dark`, set `document.documentElement.dataset.theme = "dark"`.
   - Otherwise respect `prefers-color-scheme: dark` media query.
   - On toggle click, flip the dataset attribute and `localStorage.setItem("theme", next)`.
4. Update `<meta name="theme-color">` dynamically via JS when theme changes.
5. Test on Chrome + Safari + Firefox; verify no FOUC (flash of unstyled content) on reload.

## Definition of done

- [ ] Toggle button visible on `search.html`
- [ ] Theme persists across reloads via `localStorage`
- [ ] Initial paint respects `prefers-color-scheme` if no localStorage value
- [ ] No FOUC (toggle script runs in `<head>` before body paint, or use a tiny inline script)
- [ ] Screenshots of light + dark mode attached to PR
- [ ] `meta[name="theme-color"]` updates with the theme change

## Difficulty

★★ (vanilla DOM + careful FOUC handling)
