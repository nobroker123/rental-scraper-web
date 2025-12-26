from fastapi import FastAPI, Response
from playwright.async_api import async_playwright
import os
import asyncio

app = FastAPI()

async def cleanup_overlays(page):
    """Aggressively removes popups and backdrops that block the view."""
    try:
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
    except: pass

@app.get("/scrape")
async def scrape(prop: str, city: str):
    browser = None
    async with async_playwright() as p:
        try:
            # 1. CONNECT & SETUP
            raw_url = os.getenv("BROWSER_URL")
            stealth_url = raw_url.replace("/chromium", "/chromium/stealth") if "/chromium" in raw_url else raw_url
            browser = await p.chromium.connect_over_cdp(stealth_url)
            
            # Set a high default timeout for the whole session (60 seconds)
            context = await browser.new_context(viewport={'width': 1280, 'height': 900})
            context.set_default_timeout(60000) 
            page = await context.new_page()

            # 2. NAVIGATE (Wait only for basic HTML to save time)
            await page.goto("https://www.nobroker.in/", wait_until="domcontentloaded", timeout=60000)
            await cleanup_overlays(page)

            # 3. PERFORM SEARCH
            await page.click("text=Rent")
            search_input = "input#listPageSearchLocality"
            await page.fill(search_input, f"{prop} {city}")
            
            # Wait for dropdown and select
            try:
                await page.wait_for_selector(".suggestion-item", timeout=10000)
                await page.keyboard.press("ArrowDown")
                await page.keyboard.press("Enter")
            except:
                await page.keyboard.press("Enter")

            # 4. TRIGGER SEARCH & WAIT FOR REDIRECT
            # We wait for the URL to change or the 'networkidle' state
            await asyncio.gather(
                page.click("button.prop-search-button"),
                page.wait_for_load_state("networkidle", timeout=45000)
            )

            # 5. VERIFY LISTINGS LOADED (The Rupee Test)
            # We look for the currency symbol '₹' which confirms property cards are present
            print("Verifying listings...")
            try:
                await page.wait_for_selector("text=₹", timeout=30000)
                # Scroll to trigger 'Lazy Loading' of listing images
                await page.evaluate("window.scrollTo(0, 600)")
                await asyncio.sleep(2)
                await page.evaluate("window.scrollTo(0, 0)")
            except Exception as e:
                print(f"Verification failed: {e}")

            # 6. FINAL CAPTURE
            await cleanup_overlays(page)
            screenshot_bytes = await page.screenshot(full_page=False, type='jpeg', quality=70)
            
            return Response(content=screenshot_bytes, media_type="image/jpeg")

        except Exception as e:
            return {"error": f"Scrape Failed: {str(e)}"}
        finally:
            if browser: await browser.close()
