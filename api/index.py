from fastapi import FastAPI, Response
from playwright.async_api import async_playwright
import os
import asyncio
from PIL import Image
import io

app = FastAPI()

async def cleanup_overlays(page):
    """Removes popups and overlays that block the data."""
    await page.evaluate("""() => {
        const selectors = [
            '.nb-search-along-metro-popover', '.modal', '.chat-widget-container', 
            '.tooltip', '.nb-tp-container', '#common-login', '.joyride-step__container',
            '.modal-backdrop', '.p-4.text-center', '.close', '.nearby-locality-container'
        ];
        selectors.forEach(s => document.querySelectorAll(s).forEach(el => el.remove()));
        document.body.style.overflow = 'auto';
    }""")

@app.get("/scrape")
async def scrape_all(prop: str, city: str):
    browser = None
    all_screenshots = []
    
    async with async_playwright() as p:
        try:
            raw_url = os.getenv("BROWSER_URL")
            stealth_url = raw_url.replace("/chromium", "/chromium/stealth") if "/chromium" in raw_url else raw_url
            browser = await p.chromium.connect_over_cdp(stealth_url)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 900}
            )

            # Define the sites and their specific search bar IDs
            targets = [
                {"name": "NoBroker", "url": "https://www.nobroker.in/", "input": "input#listPageSearchLocality", "btn": "button.prop-search-button"},
                {"name": "Housing", "url": "https://housing.com/", "input": "input.search-box", "btn": "button.search-btn"},
                {"name": "MagicBricks", "url": "https://www.magicbricks.com/", "input": "input#keyword", "btn": "button.search-button"}
            ]

            for site in targets:
                try:
                    page = await context.new_page()
                    # 1. SEARCH PROCESS
                    await page.goto(site["url"], wait_until="networkidle", timeout=45000)
                    await cleanup_overlays(page)
                    
                    if site["name"] == "NoBroker":
                        await page.click("text=Rent")
                    
                    await page.fill(site["input"], f"{prop} {city}")
                    await asyncio.sleep(2)
                    await page.keyboard.press("ArrowDown")
                    await page.keyboard.press("Enter")
                    
                    try:
                        await page.click(site["btn"], timeout=5000)
                    except:
                        pass

                    # 2. WAIT FOR RESULTS (Looking for Rupee symbol or price indicators)
                    await asyncio.sleep(5) 
                    await cleanup_overlays(page)
                    await page.evaluate("window.scrollTo(0, 0)")
                    
                    # 3. CAPTURE
                    shot = await page.screenshot(full_page=False)
                    all_screenshots.append(Image.open(io.BytesIO(shot)))
                    await page.close()
                except Exception as e:
                    print(f"Skipping {site['name']} due to error: {e}")

            await browser.close()

            # STITCH IMAGES TOGETHER
            if not all_screenshots:
                return {"error": "No screenshots captured"}
            
            total_height = sum(img.height for img in all_screenshots)
            max_width = max(img.width for img in all_screenshots)
            combined_image = Image.new('RGB', (max_width, total_height))
            
            y_offset = 0
            for img in all_screenshots:
                combined_image.paste(img, (0, y_offset))
                y_offset += img.height

            img_byte_arr = io.BytesIO()
            combined_image.save(img_byte_arr, format='PNG')
            return Response(content=img_byte_arr.getvalue(), media_type="image/png")

        except Exception as e:
            if browser: await browser.close()
            return {"error": str(e)}
