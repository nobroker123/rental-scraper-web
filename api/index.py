from fastapi import FastAPI, Response
from playwright.async_api import async_playwright
import os
import asyncio

app = FastAPI()

# Site configurations with their specific selectors
SITES = {
    "nobroker": {
        "url": "https://www.nobroker.in/",
        "search": "input#listPageSearchLocality",
        "verify": "xpath=//*[contains(text(), '₹')]"
    },
    "housing": {
        "url": "https://housing.com/",
        "search": ".search-box input", 
        "verify": "text=Rent"
    },
    "magicbricks": {
        "url": "https://www.magicbricks.com/",
        "search": "#keyword",
        "verify": ".mb-srp__card"
    },
    "makaan": {
        "url": "https://www.makaan.com/",
        "search": ".typeahead",
        "verify": ".listing-card"
    },
    "99acres": {
        "url": "https://www.99acres.com/",
        "search": "#keyword",
        "verify": ".pageComponent"
    }
}

async def clean_page(page):
    """Universal popup killer for all real estate sites."""
    await page.evaluate("""() => {
        const popups = [
            '.modal', '.nb-search-along-metro-popover', '.chat-widget-container', 
            '.tooltip', '.nb-tp-container', '#common-login', '.joyride-step__container',
            '.cross-icon', '.close-btn', '.p-4.text-center'
        ];
        popups.forEach(s => document.querySelectorAll(s).forEach(el => el.remove()));
        document.body.style.overflow = 'auto';
    }""")

@app.get("/scrape")
async def scrape_all(prop: str, city: str):
    browser = None
    results = {}
    
    async with async_playwright() as p:
        try:
            raw_url = os.getenv("BROWSER_URL")
            stealth_url = raw_url.replace("/chromium", "/chromium/stealth") if "/chromium" in raw_url else raw_url
            browser = await p.chromium.connect_over_cdp(stealth_url)
            context = await browser.new_context(viewport={'width': 1280, 'height': 900})

            # We loop through each site automatically
            for name, config in SITES.items():
                print(f"Searching {name} for {prop}...")
                page = await context.new_page()
                
                try:
                    # 1. Load Home
                    await page.goto(config["url"], wait_until="networkidle", timeout=45000)
                    await clean_page(page)

                    # 2. Perform Search
                    await page.wait_for_selector(config["search"], timeout=10000)
                    await page.fill(config["search"], f"{prop} {city}")
                    await asyncio.sleep(2)
                    await page.keyboard.press("ArrowDown")
                    await page.keyboard.press("Enter")
                    
                    # 3. Handle specific site search buttons if Enter isn't enough
                    if name == "nobroker":
                        await page.click("button.prop-search-button")

                    # 4. Wait for real data
                    try:
                        await page.wait_for_selector(config["verify"], timeout=15000)
                    except:
                        pass
                    
                    # 5. Cleanup and Scroll
                    await clean_page(page)
                    await page.evaluate("window.scrollTo(0, 0)")
                    
                    # 6. Save screenshot (Only NoBroker returned to browser, others logged)
                    shot = await page.screenshot(full_page=False)
                    results[name] = shot
                    print(f"✅ {name} captured successfully.")
                    
                except Exception as site_error:
                    print(f"❌ Failed to scrape {name}: {str(site_error)}")
                
                await page.close()

            # For now, we return the NoBroker shot as the primary response
            if "nobroker" in results:
                return Response(content=results["nobroker"], media_type="image/png")
            
            return {"status": "All sites processed", "sites_captured": list(results.keys())}

        except Exception as e:
            if browser: await browser.close()
            return {"error": str(e)}
