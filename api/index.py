from fastapi import FastAPI, Response
from playwright.async_api import async_playwright
import os
import asyncio

app = FastAPI()

@app.get("/")
async def home():
    return {"status": "Scraper is ready"}

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

            # 1. URL Generation
            formatted_prop = prop.replace(" ", "-").lower()
            formatted_city = city.lower()
            target_url = f"https://www.nobroker.in/property/rent/{formatted_city}/{formatted_prop}"
            
            # Go to page and wait for the network to be quiet
            await page.goto(target_url, wait_until="networkidle", timeout=60000)

            # 2. FORCE DATA LOAD (The "Human" Scroll)
            # We scroll down 1000 pixels and wait for the API to respond
            await page.evaluate("window.scrollTo(0, 1000)")
            await asyncio.sleep(3)
            await page.evaluate("window.scrollTo(0, 0)")

            # 3. SMART WAIT: Wait for the Rupee symbol to appear
            # This ensures the gray boxes have been replaced by real prices
            try:
                await page.wait_for_selector("text=₹", timeout=15000)
            except:
                # If Rupee isn't found, wait for any text that isn't part of the skeleton
                await asyncio.sleep(5)

            # 4. FINAL CLEANUP (Remove any lingering tooltips)
            await page.evaluate("""() => {
                const badOnes = ['.nb-search-along-metro-popover', '.modal', '.chat-widget-container', '.tooltip', '.nb-tp-container'];
                badOnes.forEach(s => document.querySelectorAll(s).forEach(el => el.remove()));
                document.body.style.overflow = 'auto';
            }""")

            # 5. CAPTURE
            await asyncio.sleep(1)
            screenshot_bytes = await page.screenshot(full_page=False)
            
            await browser.close()
            return Response(content=screenshot_bytes, media_type="image/png")

        except Exception as e:
            if browser: await browser.close()
            return {"error": str(e)}
