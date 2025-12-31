from fastapi import FastAPI, Response
from playwright.async_api import async_playwright
import os
import asyncio

app = FastAPI()

async def cleanup_overlays(page):
    """Removes annoying popups that block the view or interactions."""
    await page.evaluate("""() => {
        const selectors = [
            '.nb-search-along-metro-popover', '.modal', '.chat-widget-container', 
            '.tooltip', '.nb-tp-container', '#common-login', '.joyride-step__container'
        ];
        selectors.forEach(s => {
            document.querySelectorAll(s).forEach(el => el.remove());
        });
        document.body.classList.remove('modal-open');
        document.body.style.overflow = 'auto';
    }""")

@app.get("/")
async def home():
    return {"status": "Society Search Scraper Ready"}

@app.get("/scrape")
async def scrape(prop: str, city: str):
    browser = None
    async with async_playwright() as p:
        try:
            raw_url = os.getenv("BROWSER_URL")
            stealth_url = raw_url.replace("/chromium", "/chromium/stealth") if "/chromium" in raw_url else raw_url
            browser = await p.chromium.connect_over_cdp(stealth_url)
            
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 800}
            )
            page = await context.new_page()

            # 1. GO TO HOME PAGE INSTEAD OF DIRECT LINK
            await page.goto("https://www.nobroker.in/", wait_until="networkidle", timeout=60000)
            await cleanup_overlays(page)

            # 2. SELECT RENT TAB
            await page.click("text=Rent")

            # 3. TYPE SOCIETY NAME
            # We type the property name into the search box
            search_input = "input#listPageSearchLocality"
            await page.fill(search_input, prop)
            await asyncio.sleep(2) # Wait for dropdown results

            # 4. SELECT FIRST RESULT FROM DROPDOWN
            # This ensures we get the correct society page
            await page.keyboard.press("ArrowDown")
            await page.keyboard.press("Enter")

            # 5. CLICK SEARCH
            await page.click("button.prop-search-button")

            # 6. WAIT FOR LISTINGS TO LOAD
            # We wait for the price symbol to confirm real listings are visible
            try:
                await page.wait_for_selector("xpath=//*[contains(text(), '₹')]", timeout=20000)
                print("✅ Listings loaded.")
            except:
                print("⚠️ Search taking time, attempting cleanup and capture...")

            # 7. FINAL CLEANUP & SCREENSHOT
            await cleanup_overlays(page)
            await asyncio.sleep(2)
            screenshot_bytes = await page.screenshot(full_page=False)
            
            await browser.close()
            return Response(content=screenshot_bytes, media_type="image/png")

        except Exception as e:
            if browser: await browser.close()
            return {"error": str(e)}

