from fastapi import FastAPI, Response
from playwright.async_api import async_playwright
import os
import asyncio

app = FastAPI()

@app.get("/")
async def home():
    return {"status": "Scraper is ready", "url": "rental-scraper-web-nobroker.vercel.app"}

@app.get("/scrape")
async def scrape(prop: str, city: str):
    async with async_playwright() as p:
        # 1. USE THE STEALTH ENDPOINT
        raw_url = os.getenv("BROWSER_URL")
        stealth_url = raw_url.replace("/chromium", "/chromium/stealth") if "/chromium" in raw_url else raw_url
        
        browser = await p.chromium.connect_over_cdp(stealth_url)
        
        # 2. ADD HUMAN FINGERPRINTS
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 800},
            device_scale_factor=1
        )
        
        page = await context.new_page()

        try:
            # 3. DIRECT SEARCH
            formatted_prop = prop.replace(" ", "-").lower()
            formatted_city = city.lower()
            target_url = f"https://www.nobroker.in/property/rent/{formatted_city}/{formatted_prop}"
            
            # Use 'networkidle' to ensure the page is mostly loaded
            await page.goto(target_url, wait_until="networkidle", timeout=60000)
            
            # 4. WAIT FOR CONTENT (Wait for actual property cards to replace gray boxes)
            # We try to wait for the property card class. If it doesn't find it, it moves on after 10s.
            try:
                await page.wait_for_selector(".nb__2_XST", timeout=10000)
            except:
                await asyncio.sleep(5) 

            # 5. CLEAN THE PAGE (Hide popups, chat bots, and tooltips)
            await page.evaluate("""() => {
                const selectors = [
                    '.nb-search-along-metro-popover', 
                    '.modal-content', 
                    '#common-login', 
                    '.p-4.tooltip-inner',
                    '.chat-widget-container',
                    '#onBoardingStep1',
                    '.active-tp'
                ];
                selectors.forEach(s => {
                    document.querySelectorAll(s).forEach(el => el.style.display = 'none');
                });
            }""")

            # Extra second to let any layout shifts settle
            await asyncio.sleep(2)

            # 6. TAKE THE SCREENSHOT
            screenshot_bytes = await page.screenshot(full_page=False)
            
            await browser.close()
            return Response(content=screenshot_bytes, media_type="image/png")

        except Exception as e:
            if browser:
                await browser.close()
            return {"error": str(e)}
