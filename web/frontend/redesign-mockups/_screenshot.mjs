// Standalone Playwright screenshot driver — captures 3 states × 2 variants × 2 viewports = 12.
// Run from project root: `node web/frontend/redesign-mockups/_screenshot.mjs`
import { chromium } from 'playwright';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SHOT_DIR = path.join(__dirname, 'screenshots');

const VARIANTS = [
  { id: 'a', file: 'variant-a-perplexity-white.html' },
  { id: 'b', file: 'variant-b-perplexity-ink.html' },
];

const SAMPLE_QUESTION = '为什么硅谷银行挤兑后市场反应这么剧烈？还有哪些类似的级联系统？';

const VIEWPORTS = [
  { name: 'desktop', w: 1440, h: 900 },
  { name: 'mobile',  w: 390,  h: 844, deviceScaleFactor: 2 },
];

const STATES = ['empty', 'focused', 'filled'];

async function shoot(browser, variant, viewport) {
  const ctx = await browser.newContext({
    viewport: { width: viewport.w, height: viewport.h },
    deviceScaleFactor: viewport.deviceScaleFactor || 2,
    reducedMotion: 'no-preference',
  });
  const page = await ctx.newPage();
  const fileUrl = pathToFileURL(path.join(__dirname, variant.file)).href;
  await page.goto(fileUrl, { waitUntil: 'networkidle' });

  for (const state of STATES) {
    // reset
    await page.evaluate(() => {
      const i = document.getElementById('ask-input');
      if (i) { i.value = ''; i.blur(); i.dispatchEvent(new Event('input', { bubbles: true })); }
    });
    await page.waitForTimeout(50);

    if (state === 'focused') {
      await page.focus('#ask-input');
    } else if (state === 'filled') {
      await page.focus('#ask-input');
      await page.fill('#ask-input', SAMPLE_QUESTION);
      // ensure auto-grow + is-filled class settled
      await page.evaluate(() => {
        document.getElementById('ask-input').dispatchEvent(new Event('input', { bubbles: true }));
      });
    }
    await page.waitForTimeout(220); // allow transitions to settle

    const fname = `variant-${variant.id}-${viewport.name}-${state}.png`;
    const fpath = path.join(SHOT_DIR, fname);
    await page.screenshot({ path: fpath, fullPage: false });
    console.log('  ✓', fname);
  }
  await ctx.close();
}

(async () => {
  console.log('Launching chromium...');
  const browser = await chromium.launch();
  for (const v of VARIANTS) {
    for (const vp of VIEWPORTS) {
      console.log(`Variant ${v.id.toUpperCase()} — ${vp.name} (${vp.w}×${vp.h})`);
      await shoot(browser, v, vp);
    }
  }
  await browser.close();
  console.log('Done. Screenshots in:', SHOT_DIR);
})();
