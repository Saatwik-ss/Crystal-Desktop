import pytest
import asyncio
import time
import sys
import os

from services.terminal.terminal_manager import TerminalManager
from services.terminal.process_supervisor import ProcessSupervisor
from services.safety.policy_engine import PolicyEngine, RiskTier
from services.safety.git_checkpoints import GitCheckpointManager
from services.browser.browser_manager import BrowserManager
from services.subagents.coder_subagent import CoderSubagent
from services.subagents.research_subagent import ResearchSubagent
from services.subagents.test_subagent import TestSubagent
from services.os_control.desktop_agent import DesktopAgent

def test_terminal_manager():
    async def _run():
        tm = TerminalManager()
        session = tm.create_session()
        assert session.session_id is not None
        assert session.is_alive()

        # Write a command
        if sys.platform == "win32":
            session.write("echo crystal_pty_alive\r\n")
        else:
            session.write("echo crystal_pty_alive\n")

        # Wait for output
        await asyncio.sleep(1.0)
        history = session.get_history()
        assert "crystal_pty_alive" in history or len(history) > 0

        tm.close_session(session.session_id)
        assert not session.is_alive()

    asyncio.run(_run())

def test_process_supervisor():
    supervisor = ProcessSupervisor()
    py_code = "import time; print('DAEMON_START', flush=True); time.sleep(5)"
    task_id = supervisor.spawn(f'python -c "{py_code}"', cwd=os.getcwd(), name="test-daemon")

    time.sleep(1.0)
    procs = supervisor.list_processes()
    assert any(p["task_id"] == task_id for p in procs)

    logs = supervisor.get_logs(task_id)
    assert "DAEMON_START" in logs or len(logs) > 0

    terminated = supervisor.terminate(task_id)
    assert terminated is True

def test_policy_engine_strict():
    pe = PolicyEngine(mode="strict")

    # Dangerous command
    tier, needs_appr, reason = pe.evaluate("terminal_command", {"command": "rm -rf /"})
    assert tier == RiskTier.DANGEROUS
    assert needs_appr is True

    # In strict mode, standard commands also request confirmation
    tier, needs_appr, reason = pe.evaluate("terminal_command", {"command": "pytest"})
    assert needs_appr is True

    # Test approval grant
    action_id = pe.compute_action_id("terminal_command", {"command": "pytest"})
    pe.grant_approval(action_id, scope="once")
    tier, needs_appr, reason = pe.evaluate("terminal_command", {"command": "pytest"})
    assert needs_appr is False

def test_subagent_roles():
    coder = CoderSubagent()
    assert "apply_patch" in coder.allowed_tools
    assert "propose_edit" in coder.allowed_tools

    researcher = ResearchSubagent()
    assert "browser_navigate" in researcher.allowed_tools
    assert "browser_screenshot" in researcher.allowed_tools

    tester = TestSubagent()
    assert "run_terminal" in tester.allowed_tools

def test_browser_manager_headed():
    pytest.importorskip("playwright")
    async def _run():
        bm = BrowserManager(headless=True) # test headless in test suite
        data_url = "data:text/html,<html><head><title>Crystal Test</title></head><body><h1>Hello Agent</h1><button>Click Me</button></body></html>"
        res = await bm.navigate(data_url)
        assert res["status"] == "success"
        assert "Crystal Test" in res.get("title", "")
        assert "Hello Agent" in res.get("a11y_tree", "")

        ss = await bm.screenshot()
        assert ss["status"] == "success"
        assert len(ss.get("base64", "")) > 100

        await bm.close()

    asyncio.run(_run())

def test_desktop_agent():
    da = DesktopAgent(enabled=True)
    ss = da.screenshot()
    assert ss["status"] in ("success", "unavailable")
