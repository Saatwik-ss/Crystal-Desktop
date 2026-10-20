import logging
from typing import Dict, Any, List
from collections import deque
from datetime import datetime

logger = logging.getLogger(__name__)

class BrowserTelemetry:
    """
    Captures console errors, page exceptions, and HTTP 4xx/5xx network failures
    to feed diagnostic telemetry directly into the agent's context.
    """

    def __init__(self):
        self.console_errors: deque = deque(maxlen=100)
        self.console_logs: deque = deque(maxlen=200)
        self.network_failures: deque = deque(maxlen=100)

    def attach(self, page):
        """Register listeners on a Playwright Page."""
        page.on("console", self._handle_console)
        page.on("pageerror", self._handle_page_error)
        page.on("response", self._handle_response)

    def _handle_console(self, msg):
        entry = {
            "type": msg.type,
            "text": msg.text,
            "time": datetime.now().strftime("%H:%M:%S"),
        }
        if msg.type in ("error", "warning"):
            self.console_errors.append(entry)
        else:
            self.console_logs.append(entry)

    def _handle_page_error(self, error):
        entry = {
            "type": "uncaught_exception",
            "text": str(error),
            "time": datetime.now().strftime("%H:%M:%S"),
        }
        self.console_errors.append(entry)

    def _handle_response(self, response):
        if response.status >= 400:
            entry = {
                "url": response.url,
                "status": response.status,
                "status_text": response.status_text,
                "time": datetime.now().strftime("%H:%M:%S"),
            }
            self.network_failures.append(entry)

    def get_summary(self) -> Dict[str, Any]:
        """Summarize active errors and failures for agent observation."""
        return {
            "has_errors": bool(self.console_errors or self.network_failures),
            "console_errors": list(self.console_errors)[-10:],
            "network_failures": list(self.network_failures)[-10:],
        }

    def clear(self):
        self.console_errors.clear()
        self.console_logs.clear()
        self.network_failures.clear()
