from fastapi import FastAPI, Response
from playwright.async_api import async_playwright
import os

app = FastAPI()

@app.get("/")
async def home():
    return {"status": "online", "instructions": "Visit /scrape?prop=Society&city=City"}

@app.get("/scrape")
async def scrape(prop: str, city: str):
    async with async_playwright() as p:
        # We connect to a remote browser because Vercel is too small to hold Chrome
        browser_url = os.getenv("BROWSER_URL")
        browser = await p.chromium.connect_over_cdp(browser_url)
        context = await browser.new_context()
        page = await context.new_page()
        
        # Simplified Search Logic
        search_query = f"site:nobroker.in {prop} {city} rent"
        await page.goto(f"https://duckduckgo.com/?q={search_query}")
        await page.wait_for_timeout(3000)
        
        # Take screenshot of the search results or first link
        screenshot_bytes = await page.screenshot(full_page=False)
        
        await browser.close()
        return Response(content=screenshot_bytes, media_type="image/png")
