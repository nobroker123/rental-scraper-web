from fastapi import FastAPI, Response
from playwright.async_api import async_playwright
import os
import asyncio

app = FastAPI()

@app.get("/")
async def home():
    return {"status": "Interactive Scraper Ready"}

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

            # 1. GO TO PAGE
            formatted_prop = prop.replace(" ", "-").lower()
            formatted_city = city.lower()
            target_url = f"https://www.nobroker.in/property/rent/{formatted_city}/{formatted_prop}"
            
            await page.goto(target_url, wait_until="networkidle", timeout=60000)

            # 2. INTERACT WITH POPUPS (The Magic Step)
            # Instead of just deleting them, we click the 'Skip' button on the Metro popup
            try:
                # This 'Skip' button is what triggers the data load in many cases
                await page.click("text=Skip", timeout=5000)
            except:
                pass

            # 3. FORCE A HUMAN SCROLL
            # We scroll down slowly, then back up
            await page.mouse.wheel(0, 500)
            await asyncio.sleep(2)
            await page.mouse.wheel(0, -500)

            # 4. WAIT FOR ACTUAL LISTING
            # We wait for the 'Rent' label which only appears when data is real
            try:
                await page.wait_for_selector(".nb__2_XST", timeout=15000)
            except:
                await asyncio.sleep(5)

            # 5. CLEAN THE VIEW (Final sweep to remove remaining boxes)
            await page.evaluate("""() => {
                const badOnes = ['.nb-search-along-metro-popover', '.modal', '.chat-widget-container', '.tooltip'];
                badOnes.forEach(s => document.querySelectorAll(s).forEach(el => el.remove()));
            }""")

            # 6. CAPTURE
            await asyncio.sleep(1)
            screenshot_bytes = await page.screenshot(full_page=False)
            
            await browser.close()
            return Response(content=screenshot_bytes, media_type="image/png")

        except Exception as e:
            if browser: await browser.close()
            return {"error": str(e)}
