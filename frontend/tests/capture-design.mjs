import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { chromium } from "playwright";

const base = process.env.WOODZY_TEST_URL ?? "http://localhost:3000";
const output = process.env.WOODZY_CAPTURE_DIR ?? "../docs/readiness-captures";
const screens = [
  ["home", "/", "1:2226"], ["products", "/products", "1:4233"],
  ["product", "/products/arta-sofa", "1:1635"], ["categories", "/categories", "1:611"],
  ["living", "/categories/living", "1:3573"], ["search", "/search?q=مبل", "1:2"],
  ["favorites", "/favorites", "1:3011"], ["about", "/about", "1:1103"],
];
const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_EXECUTABLE, args: ["--no-sandbox", "--disable-dev-shm-usage"] });
await mkdir(output, { recursive: true });
const geometry = [];
try {
  for (const [device, width, height] of [["desktop", 1280, 900], ["mobile", 390, 844]]) {
    const context = await browser.newContext({ viewport: { width, height } });
    const page = await context.newPage();
    for (const [name, route, frame] of screens) {
      if (name === "favorites") {
        await page.goto(base + "/products/arta-sofa");
        await page.locator(".product-detail").getByRole("button", { name: "افزودن به علاقه‌مندی‌ها" }).click();
        await page.waitForLoadState("networkidle");
      }
      const response = await page.goto(base + route, { waitUntil: "networkidle" });
      assert.equal(response.status(), 200);
      await page.locator("main h1").waitFor();
      await page.evaluate(() => document.fonts.ready);
      const dimensions = await page.evaluate(() => {
        const measure = selector => {
          const rect = document.querySelector(selector)?.getBoundingClientRect();
          return rect ? Object.fromEntries(["x","y","width","height"].map(key => [key, Math.round(rect[key] * 100) / 100])) : null;
        };
        return {
          documentWidth: document.documentElement.scrollWidth, documentHeight: document.documentElement.scrollHeight,
          header: measure("body > header"), footer: measure("body > footer"),
          main: measure("body > main"), container: measure("main .container"),
          headline: measure("main h1"), sidebar: measure("main aside"),
          primaryImage: measure(".hero-visual, .gallery-stage, .category-hero > .picture"),
        };
      });
      assert.ok(dimensions.documentWidth <= width + 1);
      await page.screenshot({ path: output + "/" + name + "-" + device + ".jpg", type: "jpeg", quality: 48 });
      geometry.push({ name, frame, route, device, width, height, ...dimensions });
    }
    await context.close();
  }
  await writeFile(output + "/geometry.json", JSON.stringify(geometry, null, 2) + "\n");
  console.log("Captured " + geometry.length + " viewport images and matching geometry records.");
} finally {
  await browser.close();
}
