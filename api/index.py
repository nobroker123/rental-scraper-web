from fastapi import FastAPI, Response
from playwright.async_api import async_playwright
import os
import asyncio

app = FastAPI()

# Site-specific selectors to handle different layouts
SITE_CONFIG = {
    "nobroker": {
        "url": "https://www.nobroker.in/",
        "search_input": "input#listPageSearchLocality",
        "btn": "button.prop-search-button",
        "wait_for": "xpath=//*[contains(text(), '₹')]"
    },
    "magicbricks": {
        "url": "https://www.magicbricks.com/",
        "search_input": "input#keyword",
        "btn": ".search-button",
        "wait_for": ".mb-srp__card"
    },
    "housing": {
        "url": "https://housing.com/",
        "search_input": "input.search-box",
        "btn": "button.search-btn",
        "wait_for": "article.card"
    }
    # Note: 99acres and Makaan often require specialized headers to avoid blocks
}

async def cleanup_overlays(page):
    """Kills popups on all sites to ensure data is visible."""
    await page.evaluate("""() => {
        const selectors = ['.modal', '.popup', '.tooltip', '.nb-tp-container', '.banner-container', '#common-login'];
        selectors.forEach(s => document.querySelectorAll(s).forEach(el => el.remove()));
        document.body.style.overflow = 'auto';
    }""")

@app.get("/scrape")
async def scrape(site: str, prop: str, city: str):
    browser = None
    if site.lower() not in SITE_CONFIG:
        return {"error": f"Site {site} not supported yet."}
    
    config = SITE_CONFIG[site.lower()]
    
    async with async_playwright() as p:
        try:
            raw_url = os.getenv("BROWSER_URL")
            stealth_url = raw_url.replace("/chromium", "/chromium/stealth") if "/chromium" in raw_url else raw_url
            browser = await p.chromium.connect_over_cdp(stealth_url)
            context = await browser.new_context(viewport={'width': 1280, 'height': 900})
            page = await context.new_page()

            # 1. NAVIGATE
            await page.goto(config["url"], wait_until="networkidle", timeout=60000)
            await cleanup_overlays(page)

            # 2. PERFORM SEARCH
            await page.fill(config["search_input"], f"{prop} {city}")
            await asyncio.sleep(2)
            await page.keyboard.press("ArrowDown")
            await page.keyboard.press("Enter")
            
            # Try clicking the search button if Enter didn't trigger it
            try:
                await page.click(config["btn"], timeout=5000)
            except:
                pass

            # 3. WAIT FOR RESULTS
            try:
                await page.wait_for_selector(config["wait_for"], timeout=20000)
            except:
                pass

            # 4. VIEWPORT STABILIZATION
            await cleanup_overlays(page)
            await page.evaluate("window.scrollTo(0, 0)") # Ensure we see the top listing
            await asyncio.sleep(2)

            # 5. CAPTURE
            screenshot_bytes = await page.screenshot(full_page=False)
            await browser.close()
            return Response(content=screenshot_bytes, media_type="image/png")

        except Exception as e:
            if browser: await browser.close()
            return {"error": str(e)}
