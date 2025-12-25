from fastapi import FastAPI, Response
from playwright.async_api import async_playwright
import os
import asyncio

app = FastAPI()

async def cleanup_page(page):
    """Function to physically delete annoying overlays and unfreeze the page."""
    await page.evaluate("""() => {
        const selectors = [
            '.nb-search-along-metro-popover', '.modal-backdrop', '.modal', 
            '#common-login', '.chat-widget-container', '.tooltip', 
            '[id*="popover"]', '.active-tp', '#onBoardingStep1', '.joyride-step__container'
        ];
        selectors.forEach(s => {
            document.querySelectorAll(s).forEach(el => el.remove());
        });
        document.body.classList.remove('modal-open');
        document.body.style.overflow = 'auto';
    }""")

@app.get("/")
async def home():
    return {"status": "Scraper is ready", "url": "rental-scraper-web-nobroker.vercel.app"}

@app.get("/scrape")
async def scrape(prop: str, city: str):
    browser = None
    async with async_playwright() as p:
        try:
            raw_url = os.getenv("BROWSER_URL")
            stealth_url = raw_url.replace("/chromium", "/chromium/stealth") if "/chromium" in raw_url else raw_url
            browser = await p.chromium.connect_over_cdp(stealth_url)
            
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 800}
            )
            page = await context.new_page()

            # 1. FORMAT AND GO
            formatted_prop = prop.replace(" ", "-").lower()
            formatted_city = city.lower()
            target_url = f"https://www.nobroker.in/property/rent/{formatted_city}/{formatted_prop}"
            
            await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)

            # 2. FIRST CLEANUP (Kill initial popups)
            await cleanup_page(page)

            # 3. TRIGGER DATA (Deep Scroll)
            # We scroll down significantly to trigger the lazy-load of actual cards
            await page.evaluate("window.scrollTo(0, 1000)")
            await asyncio.sleep(2)
            await page.evaluate("window.scrollTo(0, 0)")

            # 4. WAIT FOR DATA
            try:
                # We wait for the specific listing card ID or class
                await page.wait_for_selector(".nb__2_XST", timeout=10000)
            except:
                # Fallback: Wait for prices
                await asyncio.sleep(5)

            # 5. SECOND CLEANUP (Kill popups that triggered during scroll)
            await cleanup_page(page)
            
            # Final settle
            await asyncio.sleep(2)

            # 6. CAPTURE
            screenshot_bytes = await page.screenshot(full_page=False)
            
            await browser.close()
            return Response(content=screenshot_bytes, media_type="image/png")

        except Exception as e:
            if browser:
                await browser.close()
            return {"error": str(e)}
