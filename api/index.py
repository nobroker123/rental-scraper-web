from fastapi import FastAPI, Response
from playwright.async_api import async_playwright
import os
import asyncio

app = FastAPI()

async def cleanup_overlays(page):
    """Physically removes popups so they don't block the data."""
    await page.evaluate("""() => {
        const selectors = [
            '.nb-search-along-metro-popover', '.modal', '.chat-widget-container', 
            '.tooltip', '.nb-tp-container', '#common-login', '.joyride-step__container',
            '.modal-backdrop', '.p-4.text-center'
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
                viewport={'width': 1280, 'height': 900} # Increased height slightly to see more
            )
            page = await context.new_page()

            # 1. SEARCH PROCESS
            await page.goto("https://www.nobroker.in/", wait_until="networkidle", timeout=60000)
            await cleanup_overlays(page)
            await page.click("text=Rent")
            
            search_input = "input#listPageSearchLocality"
            await page.fill(search_input, prop)
            await asyncio.sleep(2) 

            # 2. SELECT AND SEARCH
            await page.keyboard.press("ArrowDown")
            await page.keyboard.press("Enter")
            await page.click("button.prop-search-button")

            # 3. WAIT FOR REAL DATA
            try:
                await page.wait_for_selector("xpath=//*[contains(text(), '₹')]", timeout=20000)
            except:
                pass

            # 4. THE FIX: CLEAN AND RESET VIEW
            # Kill the popups first
            await cleanup_overlays(page)
            
            # Scroll down to load images, then scroll back to EXACT TOP
            await page.evaluate("window.scrollTo(0, 400)")
            await asyncio.sleep(2)
            await page.evaluate("window.scrollTo(0, 0)") # Reset to top of page
            
            # Final cleanup just in case
            await cleanup_overlays(page)
            await asyncio.sleep(1)

            # 5. CAPTURE
            screenshot_bytes = await page.screenshot(full_page=False)
            
            await browser.close()
            return Response(content=screenshot_bytes, media_type="image/png")

        except Exception as e:
            if browser: await browser.close()
            return {"error": str(e)}
