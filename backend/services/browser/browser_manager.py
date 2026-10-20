import asyncio
import base64
import logging
from typing import Optional, Dict, Any
from services.browser.telemetry_capture import BrowserTelemetry
from services.browser.a11y_tree import extract_compact_a11y_tree

logger = logging.getLogger(__name__)

class BrowserManager:
    """
    Manages Playwright browser instance with headed execution by default,
    telemetry interceptors, compact DOM extraction, and visual screenshot capture.
    """

    def __init__(self, headless: bool = False):
        # User requested: 1-headed by default
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None
        self.telemetry = BrowserTelemetry()
        self._lock = asyncio.Lock()

    async def ensure_page(self):
        """Ensure Playwright browser and page are initialized."""
        if self.page and not self.page.is_closed():
            return self.page

        async with self._lock:
            if not self.playwright:
                from playwright.async_api import async_playwright
                self.playwright = await async_playwright().start()

            if not self.browser:
                logger.info(f"[Browser] Launching Chromium (headless={self.headless})")
                self.browser = await self.playwright.chromium.launch(
                    headless=self.headless,
                    args=["--disable-web-security"],
                )

            if not self.context:
                self.context = await self.browser.new_context(
                    viewport={"width": 1280, "height": 800},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Crystal/1.0",
                )

            if not self.page or self.page.is_closed():
                self.page = await self.context.new_page()
                self.telemetry.attach(self.page)

            return self.page

    async def navigate(self, url: str) -> Dict[str, Any]:
        """Navigate to a URL and capture tree + telemetry."""
        page = await self.ensure_page()
        try:
            if url.startswith(("http://", "https://", "data:", "file://", "about:")):
                target_url = url
            else:
                target_url = f"http://{url}"
            self.telemetry.clear()
            await page.goto(target_url, wait_until="load", timeout=30000)
            await asyncio.sleep(0.5)

            tree_text, _ = await extract_compact_a11y_tree(page)
            telemetry_summary = self.telemetry.get_summary()

            return {
                "status": "success",
                "url": page.url,
                "title": await page.title(),
                "a11y_tree": tree_text,
                "telemetry": telemetry_summary,
            }
        except Exception as e:
            logger.error(f"[Browser] Navigate failed: {e}")
            return {
                "status": "error",
                "error": str(e),
                "url": url,
            }

    async def click(self, ref_or_selector: str) -> Dict[str, Any]:
        """Click an element identified by [ref=ID] or CSS selector."""
        page = await self.ensure_page()
        try:
            # Check if integer ref
            if str(ref_or_selector).isdigit():
                selector = f"[data-crystal-ref='{ref_or_selector}']"
            elif ref_or_selector.startswith("ref="):
                selector = f"[data-crystal-ref='{ref_or_selector.split('=')[1]}']"
            else:
                selector = ref_or_selector

            await page.click(selector, timeout=5000)
            await asyncio.sleep(0.5)
            tree_text, _ = await extract_compact_a11y_tree(page)
            return {
                "status": "success",
                "action": f"clicked {ref_or_selector}",
                "url": page.url,
                "a11y_tree": tree_text,
                "telemetry": self.telemetry.get_summary(),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def type_text(self, ref_or_selector: str, text: str) -> Dict[str, Any]:
        """Fill or type text into an input element."""
        page = await self.ensure_page()
        try:
            if str(ref_or_selector).isdigit():
                selector = f"[data-crystal-ref='{ref_or_selector}']"
            elif ref_or_selector.startswith("ref="):
                selector = f"[data-crystal-ref='{ref_or_selector.split('=')[1]}']"
            else:
                selector = ref_or_selector

            await page.fill(selector, text, timeout=5000)
            return {
                "status": "success",
                "action": f"typed into {ref_or_selector}",
                "url": page.url,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def press_key(self, key: str) -> Dict[str, Any]:
        """Send a keyboard stroke (e.g. 'Enter', 'Escape', 'Tab')."""
        page = await self.ensure_page()
        try:
            await page.keyboard.press(key)
            await asyncio.sleep(0.3)
            return {"status": "success", "action": f"pressed key {key}"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def screenshot(self) -> Dict[str, Any]:
        """Capture viewport screenshot for multimodal LLM visual verification."""
        page = await self.ensure_page()
        try:
            jpeg_bytes = await page.screenshot(type="jpeg", quality=80)
            base64_data = base64.b64encode(jpeg_bytes).decode("utf-8")
            return {
                "status": "success",
                "mime_type": "image/jpeg",
                "base64": base64_data,
                "url": page.url,
                "title": await page.title(),
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def get_state(self) -> Dict[str, Any]:
        """Get current URL, title, A11y tree and error telemetry."""
        page = await self.ensure_page()
        tree_text, _ = await extract_compact_a11y_tree(page)
        return {
            "url": page.url,
            "title": await page.title(),
            "a11y_tree": tree_text,
            "telemetry": self.telemetry.get_summary(),
        }

    async def close(self):
        """Close browser resources."""
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
        except Exception as e:
            logger.debug(f"[Browser] Error closing: {e}")
        finally:
            self.page = None
            self.context = None
            self.browser = None
            self.playwright = None
