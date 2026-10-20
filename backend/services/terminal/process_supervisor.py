import subprocess
import threading
import uuid
import logging
from typing import Dict, Any, List, Optional
from collections import deque
from datetime import datetime

logger = logging.getLogger(__name__)

class SupervisedProcess:
    """Represents a supervised background daemon process."""

    def __init__(self, task_id: str, name: str, command: str, cwd: str):
        self.task_id = task_id
        self.name = name
        self.command = command
        self.cwd = cwd
        self.created_at = datetime.now().isoformat()
        self.process: Optional[subprocess.Popen] = None
        self.log_buffer: deque = deque(maxlen=2000)  # last 2,000 lines
        self.returncode: Optional[int] = None
        self._thread: Optional[threading.Thread] = None

    def start(self):
        try:
            self.process = subprocess.Popen(
                self.command,
                cwd=self.cwd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            self._thread = threading.Thread(target=self._reader, daemon=True)
            self._thread.start()
        except Exception as e:
            self.returncode = -1
            self.log_buffer.append(f"Failed to start: {e}\n")

    def _reader(self):
        try:
            if self.process and self.process.stdout:
                for line in iter(self.process.stdout.readline, ""):
                    self.log_buffer.append(line)
        except Exception:
            pass
        finally:
            if self.process:
                self.returncode = self.process.poll()
                self.log_buffer.append(f"\n[Process exited with returncode {self.returncode}]\n")

    def is_alive(self) -> bool:
        if self.process:
            return self.process.poll() is None
        return False

    def terminate(self):
        if self.process and self.is_alive():
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.returncode = self.process.poll()

    def get_logs(self, tail_lines: int = 100) -> str:
        lines = list(self.log_buffer)
        if tail_lines > 0:
            lines = lines[-tail_lines:]
        return "".join(lines)


class ProcessSupervisor:
    """
    Supervises background daemon processes for the agent and developer.
    """

    def __init__(self):
        self.processes: Dict[str, SupervisedProcess] = {}

    def spawn(self, command: str, cwd: str, name: Optional[str] = None) -> str:
        task_id = str(uuid.uuid4())[:8]
        process_name = name or (command[:30] + ("..." if len(command) > 30 else ""))
        proc = SupervisedProcess(task_id, process_name, command, cwd)
        proc.start()
        self.processes[task_id] = proc
        logger.info(f"[Supervisor] Spawned background task {task_id}: {command}")
        return task_id

    def get_logs(self, task_id: str, tail_lines: int = 100) -> str:
        proc = self.processes.get(task_id)
        if not proc:
            return f"Error: Task {task_id} not found."
        return proc.get_logs(tail_lines)

    def list_processes(self) -> List[Dict[str, Any]]:
        return [
            {
                "task_id": p.task_id,
                "name": p.name,
                "command": p.command,
                "cwd": p.cwd,
                "created_at": p.created_at,
                "is_alive": p.is_alive(),
                "returncode": p.returncode,
            }
            for p in self.processes.values()
        ]

    def terminate(self, task_id: str) -> bool:
        proc = self.processes.get(task_id)
        if proc:
            proc.terminate()
            return True
        return False

    def terminate_all(self):
        for proc in self.processes.values():
            proc.terminate()
        self.processes.clear()
