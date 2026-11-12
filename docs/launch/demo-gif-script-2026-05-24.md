# Demo GIF / Screencast script — 2026-05-24

**Purpose**: unblock HN readiness § 1 "Demo GIF or 15s screencast embedded above the fold".

**Owner**: founder (recording + ffmpeg conversion), this doc is the spec.

**Final artifact**: `site/demo.gif` (≤ 5 MB, ≤ 15s, 800×500, ≤ 12 fps) + `site/demo.mp4`
(fallback for HN markdown that prefers video).

The GIF is what people see when they click the HN link before reading any words.
It has to load in < 2 s on a US/EU broadband connection and tell a story without
sound.

---

## 1. Story (15 s, 6 beats)

| t (s) | Visual | Caption (burned in, 20px sans, bottom center) |
|---|---|---|
| 0.0 – 1.5 | Cursor lands on `beta.structural.bytedance.city`; search box has placeholder *"e.g. neural avalanches"* | "One pipeline. Thirteen domains." |
| 1.5 – 3.0 | User types `bank runs` into the search box; results panel slides in | "Search any domain…" |
| 3.0 – 5.5 | Result card: **Bank runs ↔ Neural avalanches** with shared equation `P(s) ~ s^(-α)`, α=1.5±0.1 | "…get cross-domain matches." |
| 5.5 – 8.5 | Click → opens detail page with three panels: equation, variable mapping table, KS-CI band plot | "Pre-registered exponent band, KS-bootstrap CI." |
| 8.5 – 11.5 | Scroll to "verdict ledger": green PASS rows + red FAIL rows visible (4 fails out of 17 pre-registered) | "13 pass. 4 fail. Pre-registered." |
| 11.5 – 14.5 | Switch tab to `phase.bytedance.city`; show 6-company grid coloured by phase (stable / near-critical / reversed) | "Phase detector: same pipeline, 500 tickers." |
| 14.5 – 15.0 | Fade to repo URL + `pip install structural-soc-pipeline` | "MIT. CC-BY. Reproducible." |

Total: 15 s exact. Frames at 12 fps = 180 frames.

---

## 2. Pre-recording checklist

Run on a 13" laptop screen (Retina off / 1× scale) so file size stays small:

```bash
# 1. Browser setup
# Chrome new profile (no extensions / bookmark bar hidden / DevTools closed)
# Window size: exactly 1280 × 800 (use the resize bookmarklet:
#   javascript:window.resizeTo(1280,800);void(0))
# Zoom: 100% (Cmd+0)

# 2. Site warmup (so first paint is fast)
curl -s https://beta.structural.bytedance.city > /dev/null
curl -s https://phase.bytedance.city > /dev/null

# 3. Disable system notifications + Do Not Disturb on
# 4. Hide menu bar clutter; mouse pointer set to default
# 5. Pre-clear search box; pre-scroll detail page to top
```

---

## 3. Two recording paths

### Path A — Playwright (deterministic, preferred)

Pros: replayable, no human latency variance, can be re-shot if site changes.
Cons: needs Playwright already installed; cursor motion looks robotic without easing.

```bash
# Setup (~30 sec)
cd ~/Projects/structural-isomorphism
npm i -D playwright@latest
npx playwright install chromium

# Run demo recorder
node tools/record-demo.mjs
# Produces: tools/demo-raw.webm (1280x800, 30fps, ~1MB)
```

`tools/record-demo.mjs` (to be written — outline below):

```js
import { chromium } from 'playwright';
import { setTimeout as sleep } from 'node:timers/promises';

const browser = await chromium.launch({ headless: false });
const ctx = await browser.newContext({
  viewport: { width: 1280, height: 800 },
  recordVideo: { dir: 'tools/', size: { width: 1280, height: 800 } },
});
const page = await ctx.newPage();

// Beat 1-2: search
await page.goto('https://beta.structural.bytedance.city');
await sleep(1500);
await page.locator('input[type="search"]').click();
for (const c of 'bank runs') {
  await page.keyboard.type(c, { delay: 90 });
}
await sleep(500);

// Beat 3: result card visible
await page.locator('text=Bank runs').first().waitFor();
await sleep(1500);
await page.locator('text=Bank runs').first().click();

// Beat 4: detail panels (assume CSS anchor #verdict-ledger exists)
await sleep(2000);
await page.locator('#verdict-ledger').scrollIntoViewIfNeeded();
await sleep(2500);

// Beat 5: switch tab
const page2 = await ctx.newPage();
await page2.goto('https://phase.bytedance.city');
await sleep(2500);
await page2.bringToFront();
await sleep(500);

await ctx.close();
await browser.close();
```

### Path B — manual QuickTime + scripted overlays

Pros: human-natural motion. Cons: one-shot, no replay.

```bash
# 1. QuickTime > File > New Screen Recording
# 2. Crop to 1280x800 with the selection tool
# 3. Record the 6 beats following the script above (rehearse 2× first)
# 4. Save as demo-raw.mov
```

---

## 4. Post-processing — raw → GIF + MP4

```bash
# Trim to exactly 15s and clamp width
ffmpeg -i tools/demo-raw.webm -ss 0 -t 15 -vf "scale=800:-2,fps=12" \
  -c:v libx264 -preset slow -crf 23 -pix_fmt yuv420p \
  -movflags +faststart site/demo.mp4

# GIF via two-pass palette (much smaller than ffmpeg default)
ffmpeg -i site/demo.mp4 -vf "fps=12,scale=800:-2,palettegen=stats_mode=diff" \
  -y tools/palette.png
ffmpeg -i site/demo.mp4 -i tools/palette.png -lavfi \
  "fps=12,scale=800:-2[v];[v][1:v]paletteuse=dither=bayer:bayer_scale=5" \
  -y site/demo.gif

# Validate target sizes
ls -lh site/demo.gif site/demo.mp4
# Expect:
#   demo.gif  ≤ 5.0 MB  (HN markdown image inline)
#   demo.mp4  ≤ 2.0 MB  (HN doesn't render mp4, but blog/Twitter does)

# If GIF > 5 MB, drop to 10 fps or scale=640
```

### Caption burn-in (optional, but recommended)

The 7 captions in §1 should be burned into the video so the GIF tells the story
on muted-autoplay social previews.

```bash
# drawtext requires libfreetype-enabled ffmpeg
ffmpeg -i tools/demo-raw.webm -vf "\
  drawtext=fontfile=/System/Library/Fonts/Helvetica.ttc:fontsize=22:fontcolor=white:box=1:boxcolor=black@0.55:boxborderw=8:x=(w-text_w)/2:y=h-60:\
  text='One pipeline. Thirteen domains.':enable='between(t,0,1.5)',\
  drawtext=fontfile=/System/Library/Fonts/Helvetica.ttc:fontsize=22:fontcolor=white:box=1:boxcolor=black@0.55:boxborderw=8:x=(w-text_w)/2:y=h-60:\
  text='Search any domain…':enable='between(t,1.5,3.0)',\
  drawtext=fontfile=/System/Library/Fonts/Helvetica.ttc:fontsize=22:fontcolor=white:box=1:boxcolor=black@0.55:boxborderw=8:x=(w-text_w)/2:y=h-60:\
  text='…get cross-domain matches.':enable='between(t,3.0,5.5)',\
  drawtext=fontfile=/System/Library/Fonts/Helvetica.ttc:fontsize=22:fontcolor=white:box=1:boxcolor=black@0.55:boxborderw=8:x=(w-text_w)/2:y=h-60:\
  text='Pre-registered band\\, KS-bootstrap CI.':enable='between(t,5.5,8.5)',\
  drawtext=fontfile=/System/Library/Fonts/Helvetica.ttc:fontsize=22:fontcolor=white:box=1:boxcolor=black@0.55:boxborderw=8:x=(w-text_w)/2:y=h-60:\
  text='13 pass. 4 fail. Pre-registered.':enable='between(t,8.5,11.5)',\
  drawtext=fontfile=/System/Library/Fonts/Helvetica.ttc:fontsize=22:fontcolor=white:box=1:boxcolor=black@0.55:boxborderw=8:x=(w-text_w)/2:y=h-60:\
  text='Phase detector\\, same pipeline.':enable='between(t,11.5,14.5)',\
  drawtext=fontfile=/System/Library/Fonts/Helvetica.ttc:fontsize=20:fontcolor=#eaeaea:box=1:boxcolor=black@0.6:boxborderw=8:x=(w-text_w)/2:y=h-60:\
  text='pip install structural-soc-pipeline':enable='between(t,14.5,15)'\
  " -c:v libx264 -preset slow -crf 23 -pix_fmt yuv420p -t 15 \
  -movflags +faststart site/demo.mp4
```

---

## 5. Still-frame fallback (PNG)

For HN markdown / Reddit which sometimes doesn't render GIF in preview:

```bash
# Take the 6 key frames as stills
for t in 0.5 2.0 4.0 7.0 10.0 13.0; do
  ffmpeg -ss $t -i site/demo.mp4 -frames:v 1 -q:v 2 \
    site/demo-still-$t.png
done

# Optional: make a 2×3 contact sheet
ffmpeg -i site/demo.mp4 -vf "select='eq(n,6)+eq(n,24)+eq(n,48)+eq(n,84)+eq(n,120)+eq(n,156)',scale=400:-2,tile=2x3" \
  -frames:v 1 site/demo-contact-sheet.png
```

---

## 6. Where the GIF gets embedded

- README.md, line 1 after the title H1 — `![Demo](site/demo.gif)`
- The Show HN linkpost target (GitHub repo) auto-renders the README GIF above the fold
- `docs/launch/blog-post-arxiv-2026-05-24.md` (hero image)
- `docs/launch/pypi-launch-post-2026-05-24.md` (3 stills inline)
- Twitter thread tweet #1 attaches `demo.mp4` (X auto-converts to GIF preview)
- LinkedIn post attaches a 4-still contact sheet (LinkedIn handles stills better than GIF)

---

## 7. Acceptance criteria

- [ ] `site/demo.gif` exists, ≤ 5 MB, exactly 15 s
- [ ] `site/demo.mp4` exists, ≤ 2 MB, H.264, faststart, plays muted-autoplay in Chrome + Safari
- [ ] All 7 captions burned in, readable at GIF resolution (no `…` truncation)
- [ ] No cursor in awkward position at the freeze frame (t=14.9)
- [ ] No flash of unstyled content / no console errors visible during the recording
- [ ] Plausible event `Demo Recording Used` fires on the live pages during the recording (so we know the recording itself isn't using a stale cache)

If any acceptance item fails, re-record. Estimated time: 45 minutes for first
clean take, 15 min for re-takes.
