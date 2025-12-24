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
        # Instead of just /chromium, we use /chromium/stealth
        raw_url = os.getenv("BROWSER_URL")
        stealth_url = raw_url.replace("/chromium", "/chromium/stealth") if "/chromium" in raw_url else raw_url
        
        browser = await p.chromium.connect_over_cdp(stealth_url)
        
        # 2. ADD HUMAN FINGERPRINTS
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 800},
            device_scale_factor=1,
            is_mobile=False,
            has_touch=False
        )
        
        page = await context.new_page()

        try:
            # 3. DIRECT SEARCH (Bypasses the search engine captcha)
            # NoBroker search URLs are predictable!
            formatted_prop = prop.replace(" ", "-").lower()
            formatted_city = city.lower()
            target_url = f"https://www.nobroker.in/property/rent/{formatted_city}/{formatted_prop}"
            
            print(f"Heading to: {target_url}")
            await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
            
            # 4. WAIT FOR HUMAN TIMING
            await asyncio.sleep(5) 

            # 5. REMOVE OVERLAYS (Login popups that block the screenshot)
            await page.evaluate("() => { document.querySelectorAll('.modal, .popup, #login-signup-form').forEach(el => el.remove()); }")

            screenshot_bytes = await page.screenshot(full_page=False)
            
            await browser.close()
            return Response(content=screenshot_bytes, media_type="image/png")

        except Exception as e:
            await browser.close()
            return {"error": str(e)}
