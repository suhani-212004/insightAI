"""Dashboard -> PDF using a headless browser (Playwright).

The frontend has a print-friendly page at /print/dashboards/<id>. We give the
browser a 5-minute token in the URL, wait for the charts
to render, and save the page as an A4 landscape PDF.

Install the browser once:  playwright install --with-deps chromium
"""
import os

from app.core.config import settings
from app.core.security import create_token


def print_url(dashboard_id: int, org_id: int, user_id: int) -> str:
    token = create_token(user_id, minutes=5, scope="access", purpose="report")
    base = settings.PRINT_BASE_URL or settings.FRONTEND_URL
    return f"{base}/print/dashboards/{dashboard_id}?token={token}&org={org_id}"


async def render_pdf(url: str) -> bytes:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        # PLAYWRIGHT_CHROMIUM_PATH lets you point at an already-installed Chrome/Chromium.
        browser = await p.chromium.launch(executable_path=os.environ.get("PLAYWRIGHT_CHROMIUM_PATH") or None)
        try:
            page = await browser.new_page(viewport={"width": 1400, "height": 900})
            await page.goto(url, wait_until="networkidle", timeout=30_000)
            # The print page sets data-ready="true" on <body> once every widget has loaded.
            await page.wait_for_selector("body[data-ready='true']", timeout=30_000)
            return await page.pdf(format="A4", landscape=True, print_background=True,
                                  margin={"top": "12mm", "bottom": "12mm", "left": "10mm", "right": "10mm"})
        finally:
            await browser.close()
