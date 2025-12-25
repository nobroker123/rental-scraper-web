from fastapi import FastAPI, Response
from playwright.async_api import async_playwright
import os
import asyncio

app = FastAPI()

@app.get("/")
async def home():
    return {"status": "Retry-Enabled Scraper Ready"}

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

            formatted_prop = prop.replace(" ", "-").lower()
            formatted_city = city.lower()
            target_url = f"https://www.nobroker.in/property/rent/{formatted_city}/{formatted_prop}"

            # --- RETRY LOOP START ---
            max_attempts = 2
            data_loaded = False

            for attempt in range(max_attempts):
                print(f"Attempt {attempt + 1}: Loading {target_url}")
                await page.goto(target_url, wait_until="networkidle", timeout=60000)

                # Trigger lazy loading
                await page.evaluate("window.scrollTo(0, 800)")
                await asyncio.sleep(4) 
                
                # Check for the Rupee symbol (the sign of real data)
                try:
                    await page.wait_for_selector("text=₹", timeout=8000)
                    data_loaded = True
                    print("✅ Real data detected!")
                    break 
                except:
                    print("❌ Skeleton detected, retrying...")
                    continue 

            # --- CLEANUP & CAPTURE ---
            await page.evaluate("""() => {
                const badOnes = ['.nb-search-along-metro-popover', '.modal', '.chat-widget-container', '.tooltip', '.nb-tp-container'];
                badOnes.forEach(s => document.querySelectorAll(s).forEach(el => el.remove()));
                document.body.style.overflow = 'auto';
            }""")

            await asyncio.sleep(1)
            screenshot_bytes = await page.screenshot(full_page=False)
            
            await browser.close()
            return Response(content=screenshot_bytes, media_type="image/png")

        except Exception as e:
            if browser: await browser.close()
            return {"error": str(e)}
