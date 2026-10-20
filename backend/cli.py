"""
Crystal AI Coding Assistant - Windows & Cross-Platform CLI
Command-line interface to launch the Crystal desktop harness, open local codebases,
run terminal-based chat with agent planner, index repositories, and manage configuration.
"""

import sys
import os
import json
import argparse
import asyncio
import subprocess
import time
from pathlib import Path
from typing import Optional, Dict, Any

# Ensure backend directory is in sys.path
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

# Default configuration paths
if sys.platform == "win32":
    DEFAULT_CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home())) / "Crystal"
else:
    DEFAULT_CONFIG_DIR = Path.home() / ".crystal"

CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.json"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


def get_config() -> Dict[str, Any]:
    """Load configuration from config.json"""
    DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_config(config: Dict[str, Any]) -> None:
    """Save configuration to config.json"""
    DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2), encoding="utf-8")


def is_server_running(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> bool:
    """Check if Crystal backend server is actively listening and healthy"""
    import urllib.request
    try:
        url = f"http://{host}:{port}/health"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def start_server_background(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> subprocess.Popen:
    """Start Crystal backend server in background"""
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    
    # Pass user config keys to environment if not already set
    cfg = get_config()
    if cfg.get("groq_api_key") and "GROQ_API_KEY" not in env:
        env["GROQ_API_KEY"] = cfg["groq_api_key"]
    if cfg.get("gemini_api_key") and "GEMINI_API_KEY" not in env:
        env["GEMINI_API_KEY"] = cfg["gemini_api_key"]

    cmd = [sys.executable, "-m", "uvicorn", "main:app", f"--host={host}", f"--port={port}"]
    
    # On Windows, use creation flags to detach if needed
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

    proc = subprocess.Popen(
        cmd,
        cwd=str(CURRENT_DIR),
        env=env,
        creationflags=creationflags,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    return proc


def wait_for_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, timeout_sec: int = 45) -> bool:
    """Poll health check until server responds or times out"""
    start = time.time()
    while time.time() - start < timeout_sec:
        if is_server_running(host, port):
            return True
        time.sleep(0.5)
    return False


def cmd_serve(args: argparse.Namespace) -> None:
    """Run the Crystal backend server in foreground"""
    import uvicorn
    host = args.host or DEFAULT_HOST
    port = args.port or DEFAULT_PORT

    print(f"\033[96m[Crystal]\033[0m Starting server on http://{host}:{port}")
    if args.open:
        import webbrowser
        def open_browser():
            if wait_for_server(host, port):
                webbrowser.open(f"http://{host}:{port}")
        import threading
        threading.Thread(target=open_browser, daemon=True).start()

    uvicorn.run("main:app", host=host, port=port, reload=args.reload, app_dir=str(CURRENT_DIR))



def cmd_stop(args: argparse.Namespace) -> None:
    """Stop any running Crystal backend server"""
    port = getattr(args, "port", DEFAULT_PORT)
    killed = False
    if sys.platform == "win32":
        try:
            out = subprocess.check_output(f"netstat -ano | findstr :{port} | findstr LISTENING", shell=True, text=True)
            for line in out.strip().splitlines():
                parts = line.split()
                if len(parts) >= 5:
                    pid = parts[-1]
                    if pid.isdigit() and int(pid) > 0:
                        subprocess.run(f"taskkill /F /T /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        print(f"\033[92m? Stopped Crystal server (PID {pid}) on port {port}.\033[0m")
                        killed = True
        except Exception:
            pass
    else:
        try:
            out = subprocess.check_output(f"lsof -ti:{port}", shell=True, text=True)
            for pid in out.strip().split():
                if pid.isdigit():
                    subprocess.run(["kill", "-9", pid])
                    print(f"\033[92m? Stopped Crystal server (PID {pid}) on port {port}.\033[0m")
                    killed = True
        except Exception:
            pass

    if not killed:
        print(f"No active Crystal server found on port {port}.")

def cmd_status(args: argparse.Namespace) -> None:
    """Report status of backend server and local configuration"""
    host = args.host or DEFAULT_HOST
    port = args.port or DEFAULT_PORT
    running = is_server_running(host, port)
    cfg = get_config()

    print("\n\033[1m=== Crystal AI Assistant Status ===\033[0m")
    if running:
        print(f"Backend Server:   \033[92mONLINE\033[0m (http://{host}:{port})")
    else:
        print(f"Backend Server:   \033[91mOFFLINE\033[0m (http://{host}:{port})")

    groq_key = cfg.get("groq_api_key") or os.environ.get("GROQ_API_KEY")
    gemini_key = cfg.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY")

    if groq_key:
        masked_groq = groq_key[:6] + "..." + groq_key[-4:] if len(groq_key) > 10 else "***"
        print(f"Groq API Key:     \033[92mCONFIGURED\033[0m ({masked_groq})")
    else:
        print("Groq API Key:     \033[93mNOT SET\033[0m")

    if gemini_key:
        masked_gemini = gemini_key[:6] + "..." + gemini_key[-4:] if len(gemini_key) > 10 else "***"
        print(f"Gemini API Key:   \033[92mCONFIGURED\033[0m ({masked_gemini})")
    else:
        print("Gemini API Key:   \033[93mNOT SET\033[0m")

    print(f"Default Model:    {cfg.get('default_model', 'llama-3.3-70b-versatile')}")
    print(f"Data Directory:   {DEFAULT_CONFIG_DIR}")
    print(f"Config File:      {CONFIG_FILE}\n")


def cmd_config(args: argparse.Namespace) -> None:
    """Manage Crystal configuration"""
    cfg = get_config()
    changed = False

    if args.set_groq_key:
        cfg["groq_api_key"] = args.set_groq_key.strip()
        print("\033[92m✔ Groq API Key updated.\033[0m")
        changed = True

    if args.set_gemini_key:
        cfg["gemini_api_key"] = args.set_gemini_key.strip()
        print("\033[92m✔ Gemini API Key updated.\033[0m")
        changed = True

    if args.set_model:
        cfg["default_model"] = args.set_model.strip()
        print(f"\033[92m✔ Default model set to: {args.set_model.strip()}\033[0m")
        changed = True

    if changed:
        save_config(cfg)
        return

    # If no flags passed or --list, display config
    print("\n\033[1m=== Crystal Configuration ===\033[0m")
    for k, v in cfg.items():
        if "key" in k and isinstance(v, str) and len(v) > 8:
            v_masked = v[:4] + "..." + v[-4:]
            print(f"  {k}: {v_masked}")
        else:
            print(f"  {k}: {v}")
    if not cfg:
        print("  (No custom configuration saved yet. Use --set-groq-key or --set-gemini-key)")
    print()


def cmd_open(args: argparse.Namespace) -> None:
    """Open a folder in Crystal desktop harness or browser"""
    folder_path = Path(args.path or ".").resolve()
    if not folder_path.exists():
        print(f"\033[91mError: Path does not exist: {folder_path}\033[0m")
        sys.exit(1)

    host = getattr(args, "host", DEFAULT_HOST)
    port = getattr(args, "port", DEFAULT_PORT)

    use_web = getattr(args, "web", False)

    # If desktop app is desired, check for packaged executable first
    if not use_web:
        local_app_data = Path(os.environ.get("LOCALAPPDATA", ""))
        user_profile = Path(os.environ.get("USERPROFILE", ""))
        exe_candidates = [
            CURRENT_DIR.parent / "dist-desktop" / "win-unpacked" / "Crystal.exe",
            CURRENT_DIR.parent / "app" / "Crystal.exe",
            local_app_data / "Programs" / "Crystal" / "app" / "Crystal.exe",
            user_profile / "Downloads" / "Crystal-Desktop" / "dist-desktop" / "win-unpacked" / "Crystal.exe"
        ]

        for exe in exe_candidates:
            if exe.exists():
                try:
                    subprocess.Popen([str(exe), str(folder_path)])
                    print(f"\033[92m✔ Launched Crystal Desktop Application ({exe.name}).\033[0m")
                    return
                except Exception as ex:
                    print(f"\033[93m[Warning] Could not launch {exe}: {ex}\033[0m")

    # Otherwise ensure backend server is running for browser / local electron
    if not is_server_running(host, port):
        print(f"\033[96m[Crystal]\033[0m Starting background server...")
        start_server_background(host, port)
        if not wait_for_server(host, port):
            print("\033[91mFailed to start backend server.\033[0m")
            sys.exit(1)

    # Call open-local-repository endpoint
    import urllib.request
    try:
        req_data = json.dumps({"path": str(folder_path)}).encode("utf-8")
        req = urllib.request.Request(
            f"http://{host}:{port}/api/open-local-repository",
            data=req_data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            repo_id = data.get("id")
            print(f"\033[92m✔ Opened workspace: {folder_path.name} (ID: {repo_id})\033[0m")
    except Exception as e:
        print(f"\033[93m[Warning] Could not mount local repository directly: {e}\033[0m")
        repo_id = "local"

    electron_launched = False
    if not use_web:
        desktop_dir = CURRENT_DIR.parent / "desktop"
        if not desktop_dir.exists():
            alt_desktop = Path(os.environ.get("USERPROFILE", "")) / "Downloads" / "Crystal-Desktop" / "desktop"
            if alt_desktop.exists():
                desktop_dir = alt_desktop

        local_electron = desktop_dir / "node_modules" / ".bin" / "electron.cmd"
        if local_electron.exists():
            try:
                subprocess.Popen([str(local_electron), ".", str(folder_path)], cwd=str(desktop_dir), shell=True)
                electron_launched = True
                print("\033[92m✔ Launched Crystal Desktop Harness via local Electron.\033[0m")
            except Exception as ex:
                print(f"\033[93m[Warning] Could not launch Electron: {ex}\033[0m")

    if not electron_launched or use_web:
        import webbrowser
        target_url = f"http://{host}:{port}/?repo={repo_id}"
        print(f"\033[96mOpening in browser: {target_url}\033[0m")
        webbrowser.open(target_url)


def cmd_index(args: argparse.Namespace) -> None:
    """Scan and index a repository directly from the command line"""
    target_path = Path(args.path or ".").resolve()
    if not target_path.exists():
        print(f"\033[91mPath does not exist: {target_path}\033[0m")
        sys.exit(1)

    print(f"\033[96m[Crystal Indexer]\033[0m Scanning repository at: {target_path}")

    from services.repository_manager import RepositoryManager
    from services.ast_service import ASTService

    repo_mgr = RepositoryManager()
    ast_svc = ASTService()

    async def _run_index():
        files = await repo_mgr._traverse_repository(target_path)
        print(f"Found \033[1m{len(files)}\033[0m files eligible for indexing.")
        lang_counts: Dict[str, int] = {}
        parsed_ast = 0

        for f in files:
            ext = f.suffix.lower()
            lang = repo_mgr._get_language(ext)
            lang_counts[lang] = lang_counts.get(lang, 0) + 1
            if lang in ["python", "javascript", "typescript"] and f.stat().st_size < 300 * 1024:
                try:
                    content = f.read_text(encoding="utf-8", errors="ignore")
                    if ast_svc.parse_file(content, lang):
                        parsed_ast += 1
                except Exception:
                    pass

        print("\n\033[1mLanguage Breakdown:\033[0m")
        for lang, count in sorted(lang_counts.items(), key=lambda x: -x[1]):
            print(f"  • {lang.capitalize():15}: {count} files")
        print(f"\nAST parsed symbols: \033[92m{parsed_ast}\033[0m files analyzed successfully.")
        print("\033[92m✔ Repository scan complete.\033[0m\n")

    asyncio.run(_run_index())


def cmd_chat(args: argparse.Namespace) -> None:
    """Terminal chat interface with Crystal agent planner"""
    target_path = Path(args.repo or ".").resolve()
    cfg = get_config()

    groq_key = cfg.get("groq_api_key") or os.environ.get("GROQ_API_KEY")
    gemini_key = cfg.get("gemini_api_key") or os.environ.get("GEMINI_API_KEY")
    api_key = args.key or groq_key or gemini_key

    model = args.model or cfg.get("default_model") or "llama-3.3-70b-versatile"

    if not api_key:
        print("\033[93mNotice: No API key detected. Set one using: crystal config --set-groq-key <KEY> or --set-gemini-key <KEY>\033[0m")

    from services.agent_planner import AgentPlanner
    from services.chat_service import ChatService
    from services.tool_executor import ToolExecutor
    from services.repository_manager import RepositoryManager
    from services.ast_service import ASTService
    from services.search_service import SearchService
    from services.embedding_service import EmbeddingService
    from services.edit_history import EditHistory

    emb_svc = EmbeddingService()
    repo_mgr = RepositoryManager(embedding_service=emb_svc)
    ast_svc = ASTService()
    search_svc = SearchService(emb_svc)
    edit_hist = EditHistory()
    tool_exec = ToolExecutor(repo_mgr, ast_svc, search_svc, edit_history=edit_hist)
    chat_svc = ChatService()
    agent = AgentPlanner(tool_exec, chat_svc)

    async def _send_query(prompt: str, repo_ctx: Dict[str, Any]):
        print(f"\n\033[1mCrystal ({model}):\033[0m\n")
        async for chunk in agent.process_user_request(
            message=prompt,
            repo_id="local",
            context=repo_ctx,
            api_key=api_key,
            model=model,
            enable_planning=True,
        ):
            chunk_type = chunk.get("type")
            content = chunk.get("content", "")
            
            if chunk_type == "content":
                sys.stdout.write(content)
                sys.stdout.flush()
            elif chunk_type == "tool_start":
                tool_name = chunk.get("tool", "")
                args_str = json.dumps(chunk.get("args", {}))[:80]
                sys.stdout.write(f"\n\033[93m[Tool: {tool_name}({args_str}...)]\033[0m\n")
                sys.stdout.flush()
            elif chunk_type == "planning":
                sys.stdout.write(f"\033[90m{content}\033[0m\n")
                sys.stdout.flush()
        print("\n")

    async def _interactive():
        repo_ctx = {"files": [], "total_files": 0, "languages": []}
        if args.prompt:
            await _send_query(args.prompt, repo_ctx)
            return

        print("\n\033[1;96m=== Crystal AI Agent Terminal ===\033[0m")
        print(f"Target: {target_path} | Model: {model}")
        print("Type your message below. Type \033[1mexit\033[0m or \033[1mquit\033[0m to leave.\n")

        while True:
            try:
                user_msg = input("\033[1;32mcrystal > \033[0m").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nGoodbye!")
                break

            if not user_msg:
                continue
            if user_msg.lower() in ("exit", "quit"):
                print("Goodbye!")
                break
            if user_msg == "/clear":
                os.system("cls" if sys.platform == "win32" else "clear")
                continue

            await _send_query(user_msg, repo_ctx)

    asyncio.run(_interactive())


def main():
    parser = argparse.ArgumentParser(
        prog="crystal",
        description="Crystal AI Coding Assistant - Windows & Terminal Harness"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # open / default
    open_p = subparsers.add_parser("open", help="Open a repository folder in Crystal")
    open_p.add_argument("path", nargs="?", default=".", help="Path to project directory")
    open_p.add_argument("--web", action="store_true", help="Force opening in browser instead of desktop app")
    open_p.add_argument("--port", type=int, default=DEFAULT_PORT, help="Server port")

    # serve
    serve_p = subparsers.add_parser("serve", help="Start the backend server in foreground")
    serve_p.add_argument("--host", default=DEFAULT_HOST, help="Host to bind")
    serve_p.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to bind")
    serve_p.add_argument("--reload", action="store_true", help="Enable hot reload")
    serve_p.add_argument("--open", action="store_true", help="Open browser on start")

    # chat
    chat_p = subparsers.add_parser("chat", help="Chat with AI coding agent in terminal")
    chat_p.add_argument("prompt", nargs="?", help="Initial question or prompt")
    chat_p.add_argument("-r", "--repo", default=".", help="Target repository directory")
    chat_p.add_argument("-m", "--model", help="LLM model override")
    chat_p.add_argument("-k", "--key", help="API key override")

    # index
    index_p = subparsers.add_parser("index", help="Index repository symbols and files from CLI")
    index_p.add_argument("path", nargs="?", default=".", help="Directory to index")

    # config
    config_p = subparsers.add_parser("config", help="View or modify Crystal configuration")
    config_p.add_argument("--set-groq-key", help="Set Groq API key")
    config_p.add_argument("--set-gemini-key", help="Set Gemini API key")
    config_p.add_argument("--set-model", help="Set default LLM model")
    config_p.add_argument("--list", action="store_true", help="List current configuration")

    # status
    status_p = subparsers.add_parser("status", help="Show system and server health status")
    status_p.add_argument("--host", default=DEFAULT_HOST)
    status_p.add_argument("--port", type=int, default=DEFAULT_PORT)

    # stop
    stop_p = subparsers.add_parser("stop", help="Stop running Crystal backend server")
    stop_p.add_argument("--port", type=int, default=DEFAULT_PORT)
    # Preprocess sys.argv so `crystal .` or `crystal path/to/dir` routes to `crystal open <path>`
    valid_commands = {"open", "serve", "stop", "chat", "index", "config", "status", "-h", "--help", "-v", "--version"}
    if len(sys.argv) > 1 and sys.argv[1] not in valid_commands:
        sys.argv.insert(1, "open")
    elif len(sys.argv) == 1:
        sys.argv.extend(["open", "."])

    args, unknown = parser.parse_known_args()

    # If no subcommand provided
    if not args.command:
        args.path = "."
        args.web = False
        args.port = DEFAULT_PORT
        cmd_open(args)
        return

    commands = {
        "open": cmd_open,
        "serve": cmd_serve,
        "chat": cmd_chat,
        "index": cmd_index,
        "config": cmd_config,
        "status": cmd_status,
        "stop": cmd_stop,
    }

    cmd_fn = commands.get(args.command)
    if cmd_fn:
        cmd_fn(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
