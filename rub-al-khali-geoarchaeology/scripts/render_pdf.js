// Render the Arabic HTML deck to PDF (and one PNG per slide for checking) with the
// pre-installed Playwright Chromium. Usage: node render_pdf.js deck.html deck.pdf png_dir
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

(async () => {
  const [html, pdf, pngDir] = process.argv.slice(2);
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
  await page.goto("file://" + path.resolve(html), { waitUntil: "load" });
  await page.evaluate(() => document.fonts.ready);
  await page.pdf({ path: pdf, width: "1280px", height: "720px", printBackground: true,
    margin: { top: 0, right: 0, bottom: 0, left: 0 } });
  if (pngDir) {
    fs.mkdirSync(pngDir, { recursive: true });
    const slides = await page.$$("section.slide");
    for (let i = 0; i < slides.length; i++) {
      await slides[i].screenshot({ path: path.join(pngDir, `slide_${String(i + 1).padStart(2, "0")}.png`) });
    }
  }
  await browser.close();
})();
