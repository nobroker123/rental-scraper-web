from fastapi import FastAPI, Response
from playwright.async_api import async_playwright
import os
import asyncio
from PIL import Image
import io

app = FastAPI()

async def cleanup_overlays(page):
    """Aggressively removes popups and backdrops that block listings."""
    await page.evaluate("""() => {
        const selectors = [
            '.nb-search-along-metro-popover', '.modal', '.chat-widget-container', 
            '.tooltip', '.nb-tp-container', '#common-login', '.joyride-step__container',
            '.modal-backdrop', '.p-4.text-center', '.close', '.nearby-locality-container'
        ];
        selectors.forEach(s => document.querySelectorAll(s).forEach(el => el.remove()));
        document.body.classList.remove('modal-open');
        document.body.style.overflow = 'auto';
    }""")

async def scrape_site(context, config, prop, city):
    """Universal search handler with 'Wait-for-Listing' logic."""
    page = await context.new_page()
    try:
        # 1. Load the site
        await page.goto(config["url"], wait_until="domcontentloaded", timeout=30000)
        await cleanup_overlays(page)

        # 2. Site-specific Search Logic
        if config["name"] == "NoBroker":
            await page.click("text=Rent")
        
        # Type the property name
        await page.fill(config["input"], f"{prop} {city}")
        await asyncio.sleep(2) # Mandatory wait for dropdown suggestions to appear

        # Select the first suggestion and Search
        await page.keyboard.press("ArrowDown")
        await page.keyboard.press("Enter")
        
        # Click search button if Enter isn't enough (NoBroker specific)
        if "btn" in config:
            try:
                await page.click(config["btn"], timeout=3000)
            except:
                pass

        # 3. THE KEY FIX: Wait for Actual Data to Appear
        # We wait for a Rupee symbol or a listing card to prove we left the home page
        try:
            await page.wait_for_selector(config["wait_for"], timeout=15000)
        except:
            # Fallback for sites that hide the Rupee symbol in images
            await asyncio.sleep(5) 

        # 4. Final Cleanup & Capture
        await cleanup_overlays(page)
        await page.evaluate("window.scrollTo(0, 0)")
        return await page.screenshot(full_page=False)

    except Exception as e:
        print(f"Error on {config['name']}: {e}")
        return None
    finally:
        await page.close()

@app.get("/scrape")
async def scrape_all(prop: str, city: str):
    browser = None
    async with async_playwright() as p:
        try:
            raw_url = os.getenv("BROWSER_URL")
            stealth_url = raw_url.replace("/chromium", "/chromium/stealth") if "/chromium" in raw_url else raw_url
            browser = await p.chromium.connect_over_cdp(stealth_url)
            context = await browser.new_context(viewport={'width': 1280, 'height': 800})

            # Configuration for the target sites
            configs = [
                {
                    "name": "NoBroker", 
                    "url": "https://www.nobroker.in/", 
                    "input": "input#listPageSearchLocality", 
                    "btn": "button.prop-search-button",
                    "wait_for": "xpath=//*[contains(text(), '₹')]"
                },
                {
                    "name": "Housing", 
                    "url": "https://housing.com/", 
                    "input": ".search-box input", 
                    "wait_for": "text=Rent"
                },
                {
                    "name": "MagicBricks", 
                    "url": "https://www.magicbricks.com/", 
                    "input": "input#keyword", 
                    "wait_for": ".mb-srp__card"
                }
            ]

            # Run all searches simultaneously to save time
            tasks = [scrape_site(context, cfg, prop, city) for cfg in configs]
            screenshots = await asyncio.gather(*tasks)
            
            # Stitch the valid screenshots together
            valid_images = [Image.open(io.BytesIO(s)) for s in screenshots if s is not None]
            
            if not valid_images:
                return {"error": "All sites failed or timed out. Try a more specific property name."}

            # Combine images vertically
            total_height = sum(img.height for img in valid_images)
            combined = Image.new('RGB', (1280, total_height))
            y = 0
            for img in valid_images:
                combined.paste(img, (0, y))
                y += img.height

            img_bytes = io.BytesIO()
            combined.save(img_bytes, format='PNG')
            return Response(content=img_bytes.getvalue(), media_type="image/png")

        except Exception as e:
            return {"error": str(e)}
        finally:
            if browser and browser.is_connected():
                await browser.close()
