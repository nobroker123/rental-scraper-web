from fastapi import FastAPI, Response
from playwright.async_api import async_playwright
import os
import asyncio

app = FastAPI()

@app.get("/")
async def home():
    return {"status": "Society-Specific Scraper Active"}

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

            # 1. THE WATCHDOG: This kills popups instantly as they appear
            await context.add_init_script("""
                const observer = new MutationObserver(() => {
                    const selectors = [
                        '.nb-search-along-metro-popover', '.modal', '.chat-widget-container', 
                        '.tooltip', '.nb-tp-container', '#common-login', '.joyride-step__container'
                    ];
                    selectors.forEach(s => {
                        document.querySelectorAll(s).forEach(el => el.remove());
                    });
                    document.body.classList.remove('modal-open');
                    document.body.style.overflow = 'auto';
                });
                observer.observe(document, { childList: true, subtree: true });
            """)
            
            page = await context.new_page()

            # 2. GO TO THE CITY RENT PAGE
            # This ensures we are on the right search interface immediately
            await page.goto(f"https://www.nobroker.in/property/rent/{city.lower()}/", wait_until="networkidle", timeout=60000)

            # 3. TYPE AND SELECT SOCIETY
            search_input = "input[placeholder*='Search'], input#listPageSearchLocality"
            await page.wait_for_selector(search_input)
            await page.fill(search_input, prop)
            
            # Wait for dropdown and select the specific society
            await asyncio.sleep(2.5) 
            await page.keyboard.press("ArrowDown")
            await page.keyboard.press("Enter")
            
            # 4. CLICK SEARCH
            # We use a flexible selector to find the search button
            try:
                await page.click("button:has-text('Search'), .prop-search-button", timeout=5000)
            except:
                await page.keyboard.press("Enter")

            # 5. WAIT FOR ACTUAL LISTINGS
            # We wait for the Rupee symbol (₹) to confirm data is fully loaded
            try:
                await page.wait_for_selector("xpath=//*[contains(text(), '₹')]", state="visible", timeout=20000)
                print(f"✅ Listings for {prop} found.")
            except:
                print("⚠️ Loading took too long, capturing best available view.")

            # 6. FINAL SETTLE
            # Scroll slightly to trigger image loading for the screenshot
            await page.mouse.wheel(0, 300)
            await asyncio.sleep(2)
            
            # 7. CAPTURE
            screenshot_bytes = await page.screenshot(full_page=False)
            
            await browser.close()
            return Response(content=screenshot_bytes, media_type="image/png")

        except Exception as e:
            if browser: await browser.close()
            return {"error": str(e)}
