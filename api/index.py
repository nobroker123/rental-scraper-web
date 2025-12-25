from fastapi import FastAPI, Response
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async
import os, asyncio, io
from PIL import Image

app = FastAPI()

async def cleanup_overlays(page):
    await page.evaluate("""() => {
        const selectors = ['.modal', '.nb-tp-container', '.chat-widget-container', '.tooltip', '.p-4.text-center', '#common-login'];
        selectors.forEach(s => document.querySelectorAll(s).forEach(el => el.remove()));
        document.body.style.overflow = 'auto';
    }""")

async def scrape_site(context, config, prop, city):
    page = await context.new_page()
    # Apply Stealth to bypass MagicBricks/Housing blocks
    await stealth_async(page) 
    
    try:
        # Step 1: Rapid Load
        await page.goto(config["url"], wait_until="commit", timeout=10000)
        await cleanup_overlays(page)
        
        # Step 2: Search (Speed is key for Vercel)
        await page.fill(config["input"], f"{prop} {city}")
        await page.keyboard.press("Enter")
        
        # Step 3: Wait specifically for results or a short grace period
        try:
            # Wait for a price symbol or property card
            await page.wait_for_selector(config["wait_for"], timeout=6000)
        except:
            await asyncio.sleep(2) # Minimum wait if selector fails
            
        await cleanup_overlays(page)
        return await page.screenshot(full_page=False)
    except Exception as e:
        print(f"Skipping {config['name']} due to error or timeout.")
        return None
    finally:
        await page.close()

@app.get("/scrape")
async def scrape(prop: str, city: str):
    async with async_playwright() as p:
        browser = None
        try:
            raw_url = os.getenv("BROWSER_URL")
            browser = await p.chromium.connect_over_cdp(raw_url)
            context = await browser.new_context(viewport={'width': 1280, 'height': 800})

            configs = [
                {"name": "NoBroker", "url": "https://www.nobroker.in/", "input": "input#listPageSearchLocality", "wait_for": "text=₹"},
                {"name": "MagicBricks", "url": "https://www.magicbricks.com/", "input": "input#keyword", "wait_for": ".mb-srp__card"}
            ]

            # Run in parallel but with a strict timeout for the whole group
            tasks = [scrape_site(context, cfg, prop, city) for cfg in configs]
            screenshots = await asyncio.gather(*tasks)
            
            valid_images = [Image.open(io.BytesIO(s)) for s in screenshots if s is not None]
            
            if not valid_images:
                return {"error": "All sites blocked the request or timed out."}

            # Vertical Stitching
            total_height = sum(img.height for img in valid_images)
            combined = Image.new('RGB', (1280, total_height))
            y = 0
            for img in valid_images:
                combined.paste(img, (0, y))
                y += img.height

            output = io.BytesIO()
            combined.save(output, format='PNG')
            return Response(content=output.getvalue(), media_type="image/png")
        finally:
            if browser: await browser.close()
