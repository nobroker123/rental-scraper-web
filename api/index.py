from fastapi import FastAPI, Response
from playwright.async_api import async_playwright
import os
import asyncio
from PIL import Image
import io

app = FastAPI()

async def cleanup_overlays(page):
    """Kills popups that block the listing data."""
    await page.evaluate("""() => {
        const selectors = [
            '.nb-search-along-metro-popover', '.modal', '.chat-widget-container', 
            '.tooltip', '.nb-tp-container', '#common-login', '.joyride-step__container',
            '.modal-backdrop', '.p-4.text-center'
        ];
        selectors.forEach(s => document.querySelectorAll(s).forEach(el => el.remove()));
        document.body.style.overflow = 'auto';
    }""")

async def scrape_site(context, config, prop, city):
    page = await context.new_page()
    try:
        # 1. LOAD PAGE
        await page.goto(config["url"], wait_until="domcontentloaded", timeout=30000)
        await cleanup_overlays(page)

        # 2. PERFORM SEARCH
        if config["name"] == "NoBroker":
            await page.click("text=Rent")
        
        await page.fill(config["input"], f"{prop} {city}")
        await asyncio.sleep(3) # Wait for dropdown to settle
        
        # Select first suggestion and hit Enter
        await page.keyboard.press("ArrowDown")
        await page.keyboard.press("Enter")
        
        # 3. VERIFY NAVIGATION
        # We wait for the URL to change from the base home page URL
        try:
            # Force the search button click as a backup
            if "btn" in config:
                await page.click(config["btn"], timeout=5000)
        except:
            pass

        # 4. WAIT FOR DATA (The 'Rupee' test)
        # We wait for the actual listing card to appear
        print(f"Waiting for results on {config['name']}...")
        try:
            await page.wait_for_selector(config["wait_for"], timeout=15000)
        except:
            # If the specific selector fails, wait for any text containing 'BHK' or 'Price'
            await page.wait_for_selector("text=/BHK|Rent|₹/", timeout=5000)

        # 5. STABILIZE & CAPTURE
        await cleanup_overlays(page)
        # Scroll down and back up to trigger lazy-loaded listings
        await page.evaluate("window.scrollTo(0, 400)")
        await asyncio.sleep(2)
        await page.evaluate("window.scrollTo(0, 0)")
        
        return await page.screenshot(full_page=False)

    except Exception as e:
        print(f"❌ {config['name']} Error: {e}")
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
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 900}
            )

            # Define the targets
            site_configs = [
                {
                    "name": "NoBroker", 
                    "url": "https://www.nobroker.in/", 
                    "input": "input#listPageSearchLocality", 
                    "btn": "button.prop-search-button",
                    "wait_for": ".nb-srp-listing__card, text=₹"
                },
                {
                    "name": "MagicBricks", 
                    "url": "https://www.magicbricks.com/", 
                    "input": "input#keyword", 
                    "btn": "button.search-button",
                    "wait_for": ".mb-srp__card, .mb-srp__list"
                }
            ]

            # Execute tasks
            tasks = [scrape_site(context, cfg, prop, city) for cfg in site_configs]
            screenshots = await asyncio.gather(*tasks)
            
            # Combine successful results
            valid_shots = [Image.open(io.BytesIO(s)) for s in screenshots if s is not None]
            
            if not valid_shots:
                return {"error": "All sites failed to load listings. Check if the property name is correct."}

            # Stitch images
            total_height = sum(img.height for img in valid_shots)
            combined = Image.new('RGB', (1280, total_height))
            y = 0
            for img in valid_shots:
                combined.paste(img, (0, y))
                y += img.height

            output = io.BytesIO()
            combined.save(output, format='PNG')
            return Response(content=output.getvalue(), media_type="image/png")

        except Exception as e:
            return {"error": str(e)}
        finally:
            if browser: await browser.close()
