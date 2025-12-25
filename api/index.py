from fastapi import FastAPI, Response
from playwright.async_api import async_playwright
import os
import asyncio

app = FastAPI()

async def cleanup_page(page):
    await page.evaluate("""() => {
        const selectors = [
            '.nb-search-along-metro-popover', '.modal-backdrop', '.modal', 
            '#common-login', '.chat-widget-container', '.tooltip', 
            '[id*="popover"]', '.active-tp', '#onBoardingStep1', 
            '.joyride-step__container', '.nb-tp-container'
        ];
        selectors.forEach(s => {
            document.querySelectorAll(s).forEach(el => {
                el.style.display = 'none';
                el.remove();
            });
        });
        document.body.classList.remove('modal-open');
        document.body.style.overflow = 'auto';
    }""")

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

            # 1. GENERATE URL
            formatted_prop = prop.replace(" ", "-").lower()
            formatted_city = city.lower()
            target_url = f"https://www.nobroker.in/property/rent/{formatted_city}/{formatted_prop}"
            
            # Go to page
            await page.goto(target_url, wait_until="networkidle", timeout=60000)

            # 2. WAIT FOR SKELETON TO DISAPPEAR
            # This is the most important part. We wait until the gray box class is GONE.
            try:
                # Wait for the property title to appear (meaning data is loaded)
                await page.wait_for_selector("h2.heading-6", timeout=15000)
            except:
                # Fallback: wait for the loading shimmer to disappear from the DOM
                await page.wait_for_function('() => !document.querySelector(".shimmer-container")', timeout=10000)

            # 3. INTERACT TO TRIGGER RENDER
            # We scroll a little and wait
            await page.mouse.wheel(0, 400)
            await asyncio.sleep(3) 

            # 4. RUN CLEANUP
            await cleanup_page(page)
            
            # 5. FINAL SETTLE FOR IMAGES
            await asyncio.sleep(2)

            # 6. CAPTURE
            screenshot_bytes = await page.screenshot(full_page=False)
            
            await browser.close()
            return Response(content=screenshot_bytes, media_type="image/png")

        except Exception as e:
            if browser: await browser.close()
            return {"error": str(e)}
