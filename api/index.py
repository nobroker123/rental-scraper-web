from fastapi import FastAPI, Response
from playwright.async_api import async_playwright
import os
import asyncio
from PIL import Image
import io

app = FastAPI()

async def cleanup_overlays(page):
    """Removes popups so they don't block the listing data."""
    await page.evaluate("""() => {
        const selectors = ['.nb-search-along-metro-popover', '.modal', '.chat-widget-container', '.tooltip', '.nb-tp-container', '#common-login'];
        selectors.forEach(s => document.querySelectorAll(s).forEach(el => el.remove()));
        document.body.style.overflow = 'auto';
    }""")

async def scrape_site(context, site_config, prop, city):
    """Individual task to scrape a specific site."""
    page = await context.new_page()
    try:
        await page.goto(site_config["url"], wait_until="commit", timeout=15000)
        await cleanup_overlays(page)
        
        # Site-specific search logic
        search_input = site_config["input"]
        await page.fill(search_input, f"{prop} {city}")
        await asyncio.sleep(1)
        await page.keyboard.press("Enter")
        
        # Wait for the listing to actually appear
        await asyncio.sleep(4) 
        await cleanup_overlays(page)
        await page.evaluate("window.scrollTo(0, 0)")
        
        return await page.screenshot(full_page=False)
    except Exception as e:
        print(f"Error on {site_config['name']}: {e}")
        return None
    finally:
        await page.close()

@app.get("/scrape")
async def scrape(prop: str, city: str):
    browser = None
    async with async_playwright() as p:
        try:
            raw_url = os.getenv("BROWSER_URL")
            stealth_url = raw_url.replace("/chromium", "/chromium/stealth") if "/chromium" in raw_url else raw_url
            browser = await p.chromium.connect_over_cdp(stealth_url)
            context = await browser.new_context(viewport={'width': 1280, 'height': 800})

            # Configuration for the first two sites to stay under the 10s limit
            configs = [
                {"name": "NoBroker", "url": "https://www.nobroker.in/", "input": "input#listPageSearchLocality"},
                {"name": "MagicBricks", "url": "https://www.magicbricks.com/", "input": "input#keyword"}
            ]

            # Run both scrapers at the same time
            tasks = [scrape_site(context, cfg, prop, city) for cfg in configs]
            screenshots = await asyncio.gather(*tasks)
            
            # Filter out failed attempts
            valid_shots = [Image.open(io.BytesIO(s)) for s in screenshots if s is not None]

            if not valid_shots:
                return {"error": "All sites timed out or failed to load data."}

            # Stitch images vertically
            total_height = sum(img.height for img in valid_shots)
            combined = Image.new('RGB', (1280, total_height))
            y_offset = 0
            for img in valid_shots:
                combined.paste(img, (0, y_offset))
                y_offset += img.height

            output = io.BytesIO()
            combined.save(output, format='PNG')
            return Response(content=output.getvalue(), media_type="image/png")

        except Exception as e:
            return {"error": str(e)}
        finally:
            if browser: await browser.close()
