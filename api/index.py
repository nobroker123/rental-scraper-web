from fastapi import FastAPI, Response
from playwright.async_api import async_playwright
import os
import asyncio
from PIL import Image
import io

app = FastAPI()

async def cleanup_overlays(page):
    """Aggressively removes popups and backdrops."""
    await page.evaluate("""() => {
        const selectors = [
            '.nb-search-along-metro-popover', '.modal', '.chat-widget-container', 
            '.tooltip', '.nb-tp-container', '#common-login', '.joyride-step__container',
            '.modal-backdrop', '.p-4.text-center', '.close', '.nearby-locality-container'
        ];
        selectors.forEach(s => document.querySelectorAll(s).forEach(el => el.remove()));
        document.body.style.overflow = 'auto';
    }""")

async def scrape_site(context, config, prop, city):
    page = await context.new_page()
    try:
        await page.goto(config["url"], wait_until="domcontentloaded", timeout=30000)
        await cleanup_overlays(page)

        if config["name"] == "NoBroker":
            await page.click("text=Rent")
        
        # 1. Type the property name
        await page.fill(config["input"], prop)
        
        # 2. SELECT THE RIGHT SOCIETY FROM DROPDOWN
        # This waits for the suggestions list to appear
        suggestion_selector = config.get("suggestion_list", ".suggestion-item")
        try:
            await page.wait_for_selector(suggestion_selector, timeout=5000)
            # Find all suggestions and click the one that matches our property
            suggestions = await page.query_selector_all(suggestion_selector)
            clicked = False
            for s in suggestions:
                text = await s.inner_text()
                if prop.lower() in text.lower():
                    await s.click()
                    clicked = True
                    break
            
            if not clicked: # Fallback if no perfect match found
                await page.keyboard.press("ArrowDown")
                await page.keyboard.press("Enter")
        except:
            await page.keyboard.press("Enter")

        # 3. CLICK SEARCH & WAIT FOR DATA
        if "btn" in config:
            try: await page.click(config["btn"], timeout=3000)
            except: pass

        # Wait for the actual listings (Rupee symbol is the best indicator)
        try:
            await page.wait_for_selector("text=₹", timeout=10000)
        except:
            await asyncio.sleep(5) 

        await cleanup_overlays(page)
        await page.evaluate("window.scrollTo(0, 0)")
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
            context = await browser.new_context(viewport={'width': 1280, 'height': 800})

            # Configuration for the sites
            configs = [
                {
                    "name": "NoBroker", 
                    "url": "https://www.nobroker.in/", 
                    "input": "input#listPageSearchLocality", 
                    "btn": "button.prop-search-button",
                    "suggestion_list": ".autocomplete-dropdown .suggestion" 
                },
                {
                    "name": "MagicBricks", 
                    "url": "https://www.magicbricks.com/", 
                    "input": "input#keyword", 
                    "suggestion_list": ".mb-search__auto-suggest__item"
                }
            ]

            tasks = [scrape_site(context, cfg, prop, city) for cfg in configs]
            screenshots = await asyncio.gather(*tasks)
            
            valid_images = [Image.open(io.BytesIO(s)) for s in screenshots if s is not None]
            if not valid_images:
                return {"error": "No data found for this society."}

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
