from fastapi import FastAPI, Response
from playwright.async_api import async_playwright
import os
import asyncio

app = FastAPI()

async def cleanup_overlays(page):
    """Aggressively removes popups and backdrops that block the view."""
    await page.evaluate("""() => {
        const selectors = [
            '.nb-search-along-metro-popover', '.modal', '.chat-widget-container', 
            '.tooltip', '.nb-tp-container', '#common-login', '.joyride-step__container',
            '.modal-backdrop', '.p-4.text-center', '.close', '.nearby-locality-container'
        ];
        selectors.forEach(s => {
            document.querySelectorAll(s).forEach(el => el.remove());
        });
        document.body.classList.remove('modal-open');
        document.body.style.overflow = 'auto';
    }""")

@app.get("/scrape")
async def scrape(prop: str, city: str):
    browser = None
    async with async_playwright() as p:
        try:
            raw_url = os.getenv("BROWSER_URL")
            # Using stealth to avoid 'bot' detection
            stealth_url = raw_url.replace("/chromium", "/chromium/stealth") if "/chromium" in raw_url else raw_url
            browser = await p.chromium.connect_over_cdp(stealth_url)
            
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 800}
            )
            page = await context.new_page()

            # 1. Navigate to NoBroker
            await page.goto("https://www.nobroker.in/", wait_until="domcontentloaded", timeout=60000)
            await cleanup_overlays(page)

            # 2. Select Rent Tab
            await page.click("text=Rent")

            # 3. Type Society Name and Wait for Dropdown
            search_input = "input#listPageSearchLocality"
            await page.fill(search_input, f"{prop} {city}")
            
            # CRITICAL: Wait for the suggestion list to actually appear
            # NoBroker uses '.autocomplete-dropdown' or similar
            try:
                await page.wait_for_selector(".suggestion-item, .autocomplete-dropdown", timeout=5000)
                await page.keyboard.press("ArrowDown")
                await page.keyboard.press("Enter")
            except:
                # Fallback if dropdown doesn't show: just hit Enter
                await page.keyboard.press("Enter")

            # 4. Click Search and WAIT FOR NAVIGATION OR CONTENT
            # We use a Promise to wait for the network to go quiet after the click
            await asyncio.gather(
                page.click("button.prop-search-button"),
                page.wait_for_load_state("networkidle")
            )

            # 5. VERIFY LISTINGS ARE PRESENT
            # We look for the Rupee symbol (₹) which only appears in listing cards
            try:
                await page.wait_for_selector("text=₹", timeout=15000)
                # Scroll a bit to trigger 'Lazy Loading' of images
                await page.evaluate("window.scrollTo(0, 500)")
                await asyncio.sleep(1)
                await page.evaluate("window.scrollTo(0, 0)")
            except:
                print("Results did not load in time.")

            # 6. Final cleanup of any 'Login' popups that triggered on search
            await cleanup_overlays(page)
            
            # Take screenshot of the result area
            screenshot_bytes = await page.screenshot(full_page=False)
            
            return Response(content=screenshot_bytes, media_type="image/png")

        except Exception as e:
            return {"error": str(e)}
        finally:
            if browser: await browser.close()
