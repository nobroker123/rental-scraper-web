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
    browser = None
    async with async_playwright() as p:
        try:
            # 1. CONNECT VIA STEALTH
            raw_url = os.getenv("BROWSER_URL")
            stealth_url = raw_url.replace("/chromium", "/chromium/stealth") if "/chromium" in raw_url else raw_url
            browser = await p.chromium.connect_over_cdp(stealth_url)
            
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 800}
            )
            page = await context.new_page()

            # 2. TARGET URL
            formatted_prop = prop.replace(" ", "-").lower()
            formatted_city = city.lower()
            target_url = f"https://www.nobroker.in/property/rent/{formatted_city}/{formatted_prop}"
            
            # Navigate and wait for the initial structure
            await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)

            # 3. TRIGGER DATA LOADING (Scroll Down & Up)
            # Many sites won't replace "Gray Boxes" until they detect movement
            await page.mouse.wheel(0, 600)
            await asyncio.sleep(1)
            await page.mouse.wheel(0, -600)

            # 4. WAIT FOR REAL DATA
            # We wait for the Rupee symbol (₹) which only appears when real prices load
            try:
                await page.wait_for_selector("xpath=//*[contains(text(), '₹')]", timeout=12000)
            except:
                # Backup: wait for the card class you had before
                await asyncio.sleep(4) 

            # 5. AGGRESSIVE CLEANUP
            # This hides the Metro popup, the Map tooltip, and the Natasha bot
            await page.evaluate("""() => {
                const selectors = [
                    '.nb-search-along-metro-popover', 
                    '.modal-backdrop', 
                    '.modal', 
                    '#common-login', 
                    '.chat-widget-container',
                    '.tooltip',
                    '[id*="popover"]',
                    '.active-tp',
                    '#onBoardingStep1'
                ];
                selectors.forEach(s => {
                    document.querySelectorAll(s).forEach(el => el.remove());
                });
                // Unfreeze the page background
                document.body.classList.remove('modal-open');
                document.body.style.overflow = 'auto';
            }""")

            # 6. FINAL SETTLE
            await asyncio.sleep(2)

            # 7. CAPTURE
            screenshot_bytes = await page.screenshot(full_page=False)
            
            await browser.close()
            return Response(content=screenshot_bytes, media_type="image/png")

        except Exception as e:
            if browser:
                await browser.close()
            return {"error": str(e)}
