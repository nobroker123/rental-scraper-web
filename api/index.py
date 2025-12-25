from fastapi import FastAPI, Response
from playwright.async_api import async_playwright
import os
import asyncio
from PIL import Image
import io

app = FastAPI()

async def cleanup_overlays(page):
    """Removes popups so they don't block the listing results."""
    await page.evaluate("""() => {
        const selectors = [
            '.nb-search-along-metro-popover', '.modal', '.chat-widget-container', 
            '.tooltip', '.nb-tp-container', '#common-login', '.joyride-step__container',
            '.modal-backdrop', '.p-4.text-center', '.close'
        ];
        selectors.forEach(s => document.querySelectorAll(s).forEach(el => el.remove()));
        document.body.style.overflow = 'auto';
    }""")

async def scrape_site(context, config, prop, city):
    """Individual task to search and wait for actual listings."""
    page = await context.new_page()
    try:
        # 1. GO TO SITE
        await page.goto(config["url"], wait_until="domcontentloaded", timeout=15000)
        await cleanup_overlays(page)
        
        # 2. PERFORM SEARCH
        await page.fill(config["input"], f"{prop} {city}")
        await asyncio.sleep(1.5) # Time for dropdown to appear
        
        # Press ArrowDown and Enter to select the first suggestion
        await page.keyboard.press("ArrowDown")
        await page.keyboard.press("Enter")
        
        # Some sites need an extra click on the search button
        if "btn" in config:
            try:
                await page.click(config["btn"], timeout=3000)
            except:
                pass

        # 3. THE CRITICAL WAIT: Look for the 'Rupee' symbol or listing card
        # This ensures we are on the results page, not the home page
        try:
            await page.wait_for_selector(config["wait_for"], timeout=10000)
        except:
            # Fallback: wait a few seconds if the selector is hidden/different
            await asyncio.sleep(4)

        # 4. FINAL CLEANUP
        await cleanup_overlays(page)
        await page.evaluate("window.scrollTo(0, 0)") # Reset to top
        
        return await page.screenshot(full_page=False)
    except Exception as e:
        print(f"Error on {config['name']}: {e}")
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
            context = await browser.new_context(viewport={'width': 1280, 'height': 900})

            # Configuration for the sites
            site_configs = [
                {
                    "name": "NoBroker", 
                    "url": "https://www.nobroker.in/", 
                    "input": "input#listPageSearchLocality", 
                    "btn": "button.prop-search-button",
                    "wait_for": "xpath=//*[contains(text(), '₹')]"
                },
                {
                    "name": "MagicBricks", 
                    "url": "https://www.magicbricks.com/", 
                    "input": "input#keyword", 
                    "wait_for": ".mb-srp__card"
                }
            ]

            # Run sites in parallel 
            tasks = [scrape_site(context, cfg, prop, city) for cfg in site_configs]
            results = await asyncio.gather(*tasks)
            
            # Filter and Stitch
            valid_shots = [Image.open(io.BytesIO(s)) for s in results if s is not None]
            if not valid_shots:
                return {"error": "Failed to load listings from any site within the time limit."}

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
