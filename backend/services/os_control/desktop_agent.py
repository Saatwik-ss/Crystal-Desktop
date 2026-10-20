import io
import base64
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class DesktopAgent:
    """
    Provides OS-level GUI automation primitives for desktop control via PyAutoGUI and mss.
    """

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._setup_pyautogui()

    def _setup_pyautogui(self):
        try:
            import pyautogui
            pyautogui.FAILSAFE = True  # Moving mouse to any screen corner triggers fail-safe
            pyautogui.PAUSE = 0.1
        except Exception as e:
            logger.warning(f"[DesktopAgent] PyAutoGUI initialization note: {e}")

    def screenshot(self) -> Dict[str, Any]:
        """Capture screen via mss or pyautogui."""
        if not self.enabled:
            return {"status": "error", "error": "Desktop OS control is disabled"}

        try:
            import mss
            from PIL import Image

            try:
                with mss.MSS() as sct:
                    monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                    sct_img = sct.grab(monitor)
                    img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
            except Exception:
                import pyautogui
                img = pyautogui.screenshot()

            # Resize to standard FHD max to conserve token budget
            img.thumbnail((1920, 1080))
            buffered = io.BytesIO()
            img.save(buffered, format="JPEG", quality=80)
            b64 = base64.b64encode(buffered.getvalue()).decode("utf-8")

            return {
                "status": "success",
                "width": img.width,
                "height": img.height,
                "mime_type": "image/jpeg",
                "base64": b64,
            }
        except Exception as e:
            logger.warning(f"[DesktopAgent] Screenshot unavailable in this environment: {e}")
            return {"status": "unavailable", "message": f"Screen capture not supported in non-GUI session: {e}"}

    def mouse_click(self, x: int, y: int, button: str = "left", double: bool = False) -> Dict[str, Any]:
        if not self.enabled:
            return {"status": "error", "error": "Desktop OS control is disabled"}

        try:
            import pyautogui
            if double:
                pyautogui.doubleClick(x=x, y=y, button=button)
            else:
                pyautogui.click(x=x, y=y, button=button)
            return {"status": "success", "action": f"clicked ({x}, {y}) with {button}"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def type_text(self, text: str) -> Dict[str, Any]:
        if not self.enabled:
            return {"status": "error", "error": "Desktop OS control is disabled"}

        try:
            import pyautogui
            pyautogui.write(text, interval=0.01)
            return {"status": "success", "action": f"typed text (len {len(text)})"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def key_combo(self, keys: List[str]) -> Dict[str, Any]:
        if not self.enabled:
            return {"status": "error", "error": "Desktop OS control is disabled"}

        try:
            import pyautogui
            pyautogui.hotkey(*keys)
            return {"status": "success", "action": f"pressed key combination: {'+'.join(keys)}"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def mouse_scroll(self, clicks: int) -> Dict[str, Any]:
        if not self.enabled:
            return {"status": "error", "error": "Desktop OS control is disabled"}

        try:
            import pyautogui
            pyautogui.scroll(clicks)
            return {"status": "success", "action": f"scrolled {clicks} clicks"}
        except Exception as e:
            return {"status": "error", "error": str(e)}
