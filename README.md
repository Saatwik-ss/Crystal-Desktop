# Crystal AI Coding Assistant

Crystal is a full-stack, state-of-the-art AI coding assistant and agentic pair programming harness with deep repository understanding, Monaco code editor, live code completion, AST parsing, neural embeddings, and multi-provider LLM support (Groq and Google Gemini).

Crystal runs as a native **Windows Desktop Application Harness**, a versatile **Terminal CLI tool (`crystal`)**, and a **Web Server**.

---

## Features

- **Windows Desktop Harness (Electron)**: Native desktop application window (`Crystal.exe`) that automatically supervises the Python FastAPI backend, provides tray controls, and manages process lifecycles.
- **First-Class CLI (`crystal`)**: Launch the desktop app, open local folders, index codebases, manage API keys, or chat with the agent directly in PowerShell / CMD.
- **Direct Local Workspace Mounting**: Open any folder on your machine (`crystal .` or "Open Local Folder") without slow HTTP multipart uploads, indexing projects in-place.
- **Intelligent Agent Planner**: Autonomous tool execution (`read_file`, `write_file`, `propose_edit`, `apply_patch`, `search_repository`, `semantic_search`, `execute_terminal`, `ast_lookup`, `build_dependency_graph`).
- **Multi-Provider LLM Routing**:
  - **Groq**: Lightning-fast inference with `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`, `openai/gpt-oss-120b`, `qwen/qwen3-32b`.
  - **Google Gemini**: Deep multimodal reasoning with `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-2.0-flash`.
- **Monaco Code Editor**: Professional syntax highlighting, inline diff viewer, and real-time streaming code completions.
- **Isolated User Storage**: Data (`ai_assistant.db`, `chroma_db`, logs) is safely stored in `%APPDATA%\Crystal` on Windows (`~/.crystal` on Linux/macOS).

---

## Windows Installation & Quick Setup

### Option 1: Automated Windows Installer (Recommended)

1. Double-click **`scripts/install-windows.bat`** (or run PowerShell):
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts/install-windows.ps1
   ```
2. The installer will:
   - Verify Python 3.10+ (or assist with installation).
   - Set up an isolated Python virtual environment at `%LOCALAPPDATA%\Programs\Crystal\venv`.
   - Build and bundle the latest frontend assets.
   - Register the `crystal` CLI into your persistent Windows user `PATH`.
   - Create Desktop and Start Menu shortcuts.
3. Open any terminal and run `crystal status` to verify!

### Option 2: Build the NSIS Windows Installer (`Crystal-Setup.exe`)

To package a standalone Windows installer wizard:
```powershell
powershell -ExecutionPolicy Bypass -File scripts/build-windows.ps1
```
The installer executable and portable `.zip` will be generated in `dist-desktop/`.

---

## CLI Usage (`crystal`)

The `crystal` CLI command is accessible from any PowerShell, Windows Terminal, or CMD prompt:

```powershell
# Open current folder in Crystal Desktop Harness
crystal .

# Open a specific project directory
crystal open C:\Users\YourName\Documents\MyProject

# Ask the AI agent a question directly in your terminal
crystal chat "Explain the architecture of this repository"

# Start an interactive multi-turn terminal chat session
crystal chat

# Index a codebase directly from terminal and view AST stats
crystal index .

# Configure API keys and default models
crystal config --set-groq-key "gsk_..."
crystal config --set-gemini-key "AIzaSy..."
crystal config --set-model "llama-3.3-70b-versatile"
crystal config --list

# Check backend server health, port, and configuration
crystal status

# Run the backend server standalone
crystal serve --port 8000 --open
```

---

## Desktop Harness Architecture

```
User CLI / Desktop App
       │
       ▼
Electron Process Supervisor (desktop/main.js)
  ├── Manages background Python FastAPI backend
  ├── Single-instance lock (crystal . brings window to front)
  ├── Native Windows Folder Dialog (dialog:openFolder)
  └── Graceful shutdown (terminates backend on exit)
       │
       ▼
FastAPI Backend (http://127.0.0.1:8000)
  ├── Serves prebuilt SPA (frontend/dist)
  ├── In-place Local Repository Mount (/api/open-local-repository)
  ├── Streaming Chat WebSocket (/ws/chat/{repo_id})
  ├── Streaming Completion WebSocket (/ws/completion/{repo_id})
  └── Persistent Data in %APPDATA%\Crystal
```

---

## License

MIT License. See [LICENSE](LICENSE) for details.