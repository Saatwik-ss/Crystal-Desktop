import sys
import os
import asyncio
import logging
import threading
from typing import Optional, Callable, Set, List
from collections import deque

logger = logging.getLogger(__name__)

class PTYSession:
    """
    Stateful interactive pseudoterminal session.
    Uses winpty on Windows, ptyprocess on Unix/Linux/macOS,
    with an asyncio subprocess fallback.
    """

    def __init__(
        self,
        session_id: str,
        cwd: Optional[str] = None,
        shell: Optional[str] = None,
        rows: int = 24,
        cols: int = 80,
    ):
        self.session_id = session_id
        self.cwd = cwd or os.getcwd()
        self.rows = rows
        self.cols = cols
        self.listeners: Set[Callable[[str], None]] = set()
        self.output_buffer: deque = deque(maxlen=200000)  # Character ring buffer
        self.process = None
        self._is_winpty = False
        self._is_ptyprocess = False
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()

        self._spawn(shell=shell)

    def _spawn(self, shell: Optional[str] = None):
        """Spawn the PTY process according to platform."""
        target_shell = shell
        if not target_shell:
            if sys.platform == "win32":
                target_shell = os.environ.get("COMSPEC", "powershell.exe")
            else:
                target_shell = os.environ.get("SHELL", "/bin/bash")

        # 1. Try Windows WinPTY
        if sys.platform == "win32":
            try:
                import winpty
                self.process = winpty.PtyProcess.spawn(
                    target_shell,
                    cwd=self.cwd,
                    dimensions=(self.rows, self.cols),
                )
                self._is_winpty = True
                self._running = True
                self._thread = threading.Thread(target=self._read_loop_winpty, daemon=True)
                self._thread.start()
                logger.info(f"[PTY] Spawned WinPTY session {self.session_id} running {target_shell}")
                return
            except Exception as e:
                logger.warning(f"[PTY] winpty spawn failed ({e}), falling back to standard process")

        # 2. Try Unix ptyprocess
        if sys.platform != "win32":
            try:
                import ptyprocess
                self.process = ptyprocess.PtyProcessUnicode.spawn(
                    [target_shell],
                    cwd=self.cwd,
                    dimensions=(self.rows, self.cols),
                )
                self._is_ptyprocess = True
                self._running = True
                self._thread = threading.Thread(target=self._read_loop_unix, daemon=True)
                self._thread.start()
                logger.info(f"[PTY] Spawned Unix pty session {self.session_id} running {target_shell}")
                return
            except Exception as e:
                logger.warning(f"[PTY] ptyprocess spawn failed ({e}), falling back")

        # 3. Fallback: Subprocess pipes
        import subprocess
        self.process = subprocess.Popen(
            target_shell,
            cwd=self.cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            shell=False,
        )
        self._running = True
        self._thread = threading.Thread(target=self._read_loop_pipe, daemon=True)
        self._thread.start()
        logger.info(f"[PTY] Spawned pipe fallback session {self.session_id} running {target_shell}")

    def _read_loop_winpty(self):
        """Continuous background reader for WinPTY."""
        while self._running and self.process and self.process.isalive():
            try:
                data = self.process.read()
                if data:
                    self._broadcast(data)
            except EOFError:
                break
            except Exception:
                break
        self._running = False
        self._broadcast("\r\n[Process terminated]\r\n")

    def _read_loop_unix(self):
        """Continuous background reader for Unix ptyprocess."""
        while self._running and self.process and self.process.isalive():
            try:
                data = self.process.read()
                if data:
                    self._broadcast(data)
            except EOFError:
                break
            except Exception:
                break
        self._running = False
        self._broadcast("\r\n[Process terminated]\r\n")

    def _read_loop_pipe(self):
        """Continuous background reader for standard pipe fallback."""
        try:
            while self._running and self.process and self.process.poll() is None:
                char = self.process.stdout.read(1)
                if not char:
                    break
                self._broadcast(char)
        except Exception:
            pass
        self._running = False
        self._broadcast("\r\n[Process terminated]\r\n")

    def _broadcast(self, text: str):
        """Store chunk in ring buffer and notify all active listeners."""
        with self._lock:
            for ch in text:
                self.output_buffer.append(ch)
            active_listeners = list(self.listeners)

        for listener in active_listeners:
            try:
                listener(text)
            except Exception as e:
                logger.debug(f"[PTY] Listener notification error: {e}")

    def add_listener(self, callback: Callable[[str], None]):
        """Subscribe to output stream."""
        with self._lock:
            self.listeners.add(callback)

    def remove_listener(self, callback: Callable[[str], None]):
        """Unsubscribe from output stream."""
        with self._lock:
            self.listeners.discard(callback)

    def get_history(self) -> str:
        """Retrieve full backlog history for client initialization."""
        with self._lock:
            return "".join(self.output_buffer)

    def write(self, data: str):
        """Send input keystrokes or commands to process."""
        if not self.is_alive():
            return
        try:
            if self._is_winpty or self._is_ptyprocess:
                self.process.write(data)
            elif self.process and self.process.stdin:
                self.process.stdin.write(data)
                self.process.stdin.flush()
        except Exception as e:
            logger.error(f"[PTY] Write failed for session {self.session_id}: {e}")

    def resize(self, rows: int, cols: int):
        """Resize pseudoterminal dimensions."""
        self.rows = max(1, rows)
        self.cols = max(1, cols)
        if self._is_winpty and self.process:
            try:
                self.process.set_size(self.cols, self.rows)
            except Exception:
                pass
        elif self._is_ptyprocess and self.process:
            try:
                self.process.setwinsize(self.rows, self.cols)
            except Exception:
                pass

    def send_signal(self, sig: str):
        """Send signal (Ctrl+C, SIGTERM, etc.)."""
        if sig in ("SIGINT", "ctrl_c", "\x03"):
            self.write("\x03")
        elif sig in ("EOF", "ctrl_d", "\x04"):
            self.write("\x04")
        elif sig == "SIGTERM":
            self.kill()

    def kill(self):
        """Terminate the terminal process."""
        self._running = False
        try:
            if self.process:
                if hasattr(self.process, "terminate"):
                    self.process.terminate()
                elif hasattr(self.process, "kill"):
                    self.process.kill()
        except Exception:
            pass

    def is_alive(self) -> bool:
        """Check if session process is active."""
        if not self._running:
            return False
        if self._is_winpty or self._is_ptyprocess:
            return bool(self.process and self.process.isalive())
        if self.process:
            return self.process.poll() is None
        return False
