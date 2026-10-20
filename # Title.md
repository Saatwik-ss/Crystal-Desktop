Below is a **deep‑dive** into every major piece of the **Crystal** code‑base, how the pieces talk to each other, and why they are organized the way they are. I’ll walk through the **backend**, **frontend**, **CLI**, **testing**, **safety**, and **Git worktree** subsystems, pointing out the most important files and the data‑flow between them.

---

## 1. High‑level picture (re‑stated for context)

```
┌─────────────────────┐          ┌─────────────────────┐          ┌─────────────────────┐
│   Desktop UI (Electron) │ ◀─────► │   FastAPI Backend (Python) │ ◀─────► │   LLM Provider APIs   │
└─────────────────────┘          └─────────────────────┘          └─────────────────────┘
        ▲   ▲   ▲                         ▲   ▲   ▲
        │   │   │                         │   │   │
        │   │   │                         │   │   │
        │   │   │                         │   │   │
        │   │   │                         │   │   │
        │   │   │                         │   │   │
        │   │   │                         │   │   │
        │   │   │                         │   │   │
        │   │   │                         │   │   │
        │   │   │                         │   │   │
        │   │   │                         │   │   │
        ▼   ▼   ▼                         ▼   ▼   ▼
   Terminal, Git, Browser          Chat, Completion,
   Automation, File‑system          Policy Engine,
   UI‑tests, etc.                   Tool Executor,
                                    Repository Manager
```

*The UI runs inside Electron (a Chromium‑based desktop shell). It talks to the backend over a local HTTP API (FastAPI). The backend is the “brain”: it talks to LLMs, runs safety checks, spawns tools, and manages a Git‑based workspace.*

---

## 2. Backend (Python)

All backend code lives under `backend/`. The entry point is `backend/main.py` (started by the CLI or by the Electron preload script). The backend is a **FastAPI** server exposing a small set of JSON‑RPC‑style endpoints that the UI consumes.

### 2.1 Core services

| Service | File | Responsibility | Key functions / classes |
|---------|------|----------------|--------------------------|
| **Chat Service** | `chat_service.py` | Maintains a conversation state, forwards user messages to the LLM, streams responses back to the UI. | `ChatSession`, `handle_user_message`, `stream_llm_response` |
| **Code Completion Service** | `code_completion_service.py` | Takes a file + cursor position, builds a prompt, calls the LLM, returns a snippet or full file diff. | `CompletionEngine`, `generate_completion` |
| **Repository Manager** | `repository_manager.py` | Wraps Git operations (worktree creation, diff, commit, rollback). Guarantees that every LLM‑driven edit happens inside an isolated worktree. | `GitWorktree`, `create_worktree`, `apply_patch`, `commit`, `rollback`

