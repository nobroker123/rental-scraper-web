from fastapi import FastAPI, Response
from playwright.async_api import async_playwright
import os
import asyncio

app = FastAPI()

@app.get("/")
async def home():
    return {"status": "Advanced Scraper Ready"}

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
            
            # Inject a "Watchdog" script that kills popups before they even render
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
            formatted_prop = prop.replace(" ", "-").lower()
            formatted_city = city.lower()
            target_url = f"https://www.nobroker.in/property/rent/{formatted_city}/{formatted_prop}"

            # 1. LOAD PAGE
            await page.goto(target_url, wait_until="networkidle", timeout=60000)

            # 2. TRIGGER REAL DATA FETCH (The "Human" Interaction)
            # We scroll, wait, and click a neutral area to wake up the site logic
            await page.mouse.wheel(0, 600)
            await asyncio.sleep(2)
            await page.mouse.click(10, 10) # Click top-left corner to trigger event listeners
            await page.mouse.wheel(0, -600)

            # 3. STRICT CONTENT CHECK
            # We wait specifically for the Rupee symbol (₹) to appear in a listing card.
            # This is the "Gold Standard" proof that the gray boxes are gone.
            try:
                # Wait for the price selector class or the Rupee text
                await page.wait_for_selector("xpath=//*[contains(text(), '₹')]", state="visible", timeout=20000)
                print("✅ Actual listing detected.")
            except:
                print("⚠️ Data taking too long, capturing fallback...")

            # 4. FINAL VIEW STABILIZATION
            await asyncio.sleep(2) 

            # 5. CAPTURE
            screenshot_bytes = await page.screenshot(full_page=False)
            
            await browser.close()
            return Response(content=screenshot_bytes, media_type="image/png")

        except Exception as e:
            if browser: await browser.close()
            return {"error": str(e)}
