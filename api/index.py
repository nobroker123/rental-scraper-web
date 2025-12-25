from fastapi import FastAPI, Response
from playwright.async_api import async_playwright
import os
import asyncio

app = FastAPI()

@app.get("/")
async def home():
    return {"status": "Society-Specific Scraper Ready"}

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
            
            # Watchdog script to kill popups instantly as they appear
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

            # 1. START AT THE SEARCH PAGE
            # We go to the main rent search page to ensure the search bar is present
            await page.goto(f"https://www.nobroker.in/property/rent/{city.lower()}/", wait_until="networkidle", timeout=60000)

            # 2. TYPE THE SOCIETY NAME
            # We find the search box and type the property name
            search_input = "input#listPageSearchLocality"
            await page.wait_for_selector(search_input)
            await page.fill(search_input, prop)
            
            # 3. SELECT FROM DROPDOWN
            # We wait for the dropdown to appear and select the first suggestion
            # This is the secret to getting the correct society listings
            await asyncio.sleep(2) 
            await page.keyboard.press("ArrowDown")
            await page.keyboard.press("Enter")
            
            # 4. CLICK SEARCH BUTTON
            await page.click("button.prop-search-button")

            # 5. WAIT FOR ACTUAL LISTINGS
            # We wait for the Rupee symbol to ensure the "Skeleton" boxes are gone
            try:
                await page.wait_for_selector("xpath=//*[contains(text(), '₹')]", state="visible", timeout=20000)
                print(f"✅ Listings for {prop} loaded successfully.")
            except:
                print("⚠️ Listings taking time to load, capturing current state...")

            # 6. FINAL SETTLE AND CAPTURE
            await page.mouse.wheel(0, 400) # Slight scroll to trigger lazy images
            await asyncio.sleep(2)
            screenshot_bytes = await page.screenshot(full_page=False)
            
            await browser.close()
            return Response(content=screenshot_bytes, media_type="image/png")

        except Exception as e:
            if browser: await browser.close()
            return {"error": str(e)}
