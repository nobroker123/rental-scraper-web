from fastapi import FastAPI, Response
from playwright.async_api import async_playwright
import os
import asyncio
from PIL import Image
import io

app = FastAPI()

async def cleanup_overlays(page):
    """Aggressively removes popups that block visibility."""
    await page.evaluate("""() => {
        const selectors = [
            '.nb-search-along-metro-popover', '.modal', '.chat-widget-container', 
            '.tooltip', '.nb-tp-container', '#common-login', '.joyride-step__container',
            '.modal-backdrop', '.p-4.text-center'
        ];
        selectors.forEach(s => {
            document.querySelectorAll(s).forEach(el => el.remove());
        });
        document.body.style.overflow = 'auto';
    }""")

async def scrape_single_site(context, name, url, selector, prop, city):
    """Helper to process each site individually within the same context."""
    page = await context.new_page()
    try:
        # Load the page quickly
        await page.goto(url, wait_until="domcontentloaded", timeout=20000)
        await cleanup_overlays(page)
        
        # Site-specific Search Logic
        if name == "NoBroker":
            await page.click("text=Rent")
        
        # Type and Force Enter immediately
        await page.fill(selector, f"{prop} {city}")
        await page.keyboard.press("Enter")
        
        # Wait for the results to start appearing
        await asyncio.sleep(5) 
        await cleanup_overlays(page)
        await page.evaluate("window.scrollTo(0, 0)")
        
        return await page.screenshot(full_page=False)
    except Exception as e:
        print(f"Error scraping {name}: {e}")
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

            # Define 3 sites to try simultaneously to stay under the limit
            configs = [
                {"name": "NoBroker", "url": "https://www.nobroker.in/", "selector": "input#listPageSearchLocality"},
                {"name": "Housing", "url": "https://housing.com/", "selector": "input.search-box"},
                {"name": "MagicBricks", "url": "https://www.magicbricks.com/", "selector": "input#keyword"}
            ]

            # Run all searches at once
            tasks = [scrape_single_site(context, c['name'], c['url'], c['selector'], prop, city) for c in configs]
            screenshots = await asyncio.gather(*tasks)
            
            # Combine successful screenshots
            valid_images = [Image.open(io.BytesIO(s)) for s in screenshots if s is not None]
            
            if not valid_images:
                return {"error": "Could not capture listings from any site. They may be blocking the bot."}

            # Stitch images vertically
            total_height = sum(img.height for img in valid_images)
            combined = Image.new('RGB', (1280, total_height))
            current_y = 0
            for img in valid_images:
                combined.paste(img, (0, current_y))
                current_y += img.height

            output = io.BytesIO()
            combined.save(output, format='PNG')
            return Response(content=output.getvalue(), media_type="image/png")

        except Exception as e:
            return {"error": str(e)}
        finally:
            if browser: await browser.close()
