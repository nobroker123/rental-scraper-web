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
            
            # Start loading
            await page.goto(target_url, wait_until="domcontentloaded", timeout=60000)

            # 3. TRIGGER DATA (The Scroll-Shake)
            # This tricks the site into thinking a human is browsing, which loads the real cards
            await page.mouse.wheel(0, 800)
            await asyncio.sleep(2)
            await page.mouse.wheel(0, -800)

            # 4. WAIT FOR DATA TO REPLACE GRAY BOXES
            # We wait for the Rupee symbol (₹) to appear in the code
            try:
                await page.wait_for_selector("xpath=//*[contains(text(), '₹')]", timeout=15000)
            except:
                print("Rupee symbol not found, waiting a few more seconds...")
                await asyncio.sleep(5)

            # 5. THE CLEANUP (Removing those specific popups from your screenshot)
            await page.evaluate("""() => {
                const selectors = [
                    '.nb-search-along-metro-popover', // The 'Search along Metro' box
                    '.modal-backdrop',                // The dark background
                    '.modal',                         // Any open windows
                    '#common-login',                  // Login popup
                    '.chat-widget-container',         // Natasha Bot
                    '.tooltip',                       // Any 'Got it' tooltips
                    '[id*="popover"]',                // MAP feature popover
                    '.active-tp',                     // Other tooltips
                    '#onBoardingStep1'                // Tutorial step 1
                ];
                selectors.forEach(s => {
                    document.querySelectorAll(s).forEach(el => el.remove());
                });
                
                // Fix the scroll if a modal was blocking it
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
