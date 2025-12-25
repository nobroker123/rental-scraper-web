from fastapi import FastAPI, Response
from playwright.async_api import async_playwright
import os
import asyncio
import io
from PIL import Image

app = FastAPI()

# Clean up function to save memory and clear view
async def cleanup(page):
    try:
        await page.evaluate("""() => {
            const boxes = ['.modal', '.nb-tp-container', '.chat-widget-container', '.tooltip', '#common-login'];
            boxes.forEach(s => document.querySelectorAll(s).forEach(el => el.remove()));
        }""")
    except: pass

async def get_screenshot(context, site, prop, city):
    page = await context.new_page()
    try:
        # 1. Faster Navigation
        await page.goto(site["url"], wait_until="commit", timeout=20000)
        await cleanup(page)
        
        # 2. Search Logic
        await page.fill(site["input"], f"{prop} {city}")
        await page.keyboard.press("Enter")
        
        # 3. Wait for data - reduced time to prevent Vercel crash
        await asyncio.sleep(6) 
        await cleanup(page)
        await page.evaluate("window.scrollTo(0, 0)")
        
        # 4. Take Screenshot
        img_bytes = await page.screenshot(type='jpeg', quality=50) # JPEG is lighter than PNG
        return Image.open(io.BytesIO(img_bytes))
    except Exception as e:
        print(f"Error on {site['url']}: {e}")
        return None
    finally:
        await page.close()

@app.get("/scrape")
async def scrape(prop: str, city: str):
    browser = None
    async with async_playwright() as p:
        try:
            raw_url = os.getenv("BROWSER_URL")
            # Connect to external browser to save Vercel memory
            browser = await p.chromium.connect_over_cdp(raw_url)
            context = await browser.new_context(viewport={'width': 1000, 'height': 800})

            targets = [
                {"url": "https://www.nobroker.in/", "input": "input#listPageSearchLocality"},
                {"url": "https://www.magicbricks.com/", "input": "input#keyword"}
            ]

            # Run tasks one by one to avoid memory spikes on Vercel Free
            images = []
            for target in targets:
                img = await get_screenshot(context, target, prop, city)
                if img:
                    images.append(img)

            if not images:
                return {"error": "All sites failed to load. Check logs."}

            # Stitch Images
            widths, heights = zip(*(i.size for i in images))
            total_height = sum(heights)
            max_width = max(widths)

            combined = Image.new('RGB', (max_width, total_height))
            y_offset = 0
            for im in images:
                combined.paste(im, (0, y_offset))
                y_offset += im.height

            # Export
            buf = io.BytesIO()
            combined.save(buf, format='JPEG', quality=60)
            return Response(content=buf.getvalue(), media_type="image/jpeg")

        except Exception as e:
            return {"error": str(e)}
        finally:
            if browser: await browser.close()
