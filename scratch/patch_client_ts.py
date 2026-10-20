import pathlib

p = pathlib.Path(r"C:\Users\saatw\Downloads\Crystal-Desktop\frontend\src\api\client.ts")
text = p.read_text(encoding="utf-8")

# Update imports
old_imp = "import type {\n  Repository,\n  IndexingStatus,\n  RepositoryFile,\n  SearchResult,\n} from '../types';"
new_imp = """import type {
  Repository,
  IndexingStatus,
  RepositoryFile,
  SearchResult,
  Project,
  ChatSession,
  ChatMessage,
  UserSettings,
} from '../types';"""
text = text.replace(old_imp.replace("\r\n", "\n"), new_imp)

# Update sendChatMessage to include sessionId
old_send = """  async sendChatMessage(
    repoId: string | null | undefined,
    message: string,
    selectedFile?: string,
    selectedCode?: string,
    settings?: LlmSettings,
    enablePlanning: boolean = false
  ): Promise<void> {
    const id = sessionId(repoId);
    let ws = this.wsConnections.get(`chat_${id}`);
    if (!ws) {
      this.connectChat(id, () => undefined, () => undefined);
      ws = this.wsConnections.get(`chat_${id}`);
    }
    if (!ws) throw new Error('Unable to create a chat connection');

    if (ws.readyState === WebSocket.CONNECTING) {
      await new Promise<void>((resolve, reject) => {
        const timeout = window.setTimeout(() => reject(new Error('Chat connection timed out')), 8000);
        ws!.addEventListener('open', () => { window.clearTimeout(timeout); resolve(); }, { once: true });
        ws!.addEventListener('error', () => { window.clearTimeout(timeout); reject(new Error('Chat connection failed')); }, { once: true });
      });
    }
    if (ws.readyState !== WebSocket.OPEN) throw new Error('Chat connection is closed');
    ws.send(JSON.stringify({
      message,
      selected_file: selectedFile,
      selected_code: selectedCode,
      enable_planning: enablePlanning,
      ...(settings ? llmPayload(settings) : {}),
    }));"""

new_send = """  async sendChatMessage(
    repoId: string | null | undefined,
    message: string,
    selectedFile?: string,
    selectedCode?: string,
    settings?: LlmSettings,
    enablePlanning: boolean = false,
    sessionId?: string | null
  ): Promise<void> {
    const id = sessionId(repoId);
    let ws = this.wsConnections.get(`chat_${id}`);
    if (!ws) {
      this.connectChat(id, () => undefined, () => undefined);
      ws = this.wsConnections.get(`chat_${id}`);
    }
    if (!ws) throw new Error('Unable to create a chat connection');

    if (ws.readyState === WebSocket.CONNECTING) {
      await new Promise<void>((resolve, reject) => {
        const timeout = window.setTimeout(() => reject(new Error('Chat connection timed out')), 8000);
        ws!.addEventListener('open', () => { window.clearTimeout(timeout); resolve(); }, { once: true });
        ws!.addEventListener('error', () => { window.clearTimeout(timeout); reject(new Error('Chat connection failed')); }, { once: true });
      });
    }
    if (ws.readyState !== WebSocket.OPEN) throw new Error('Chat connection is closed');
    ws.send(JSON.stringify({
      session_id: sessionId,
      message,
      selected_file: selectedFile,
      selected_code: selectedCode,
      enable_planning: enablePlanning,
      ...(settings ? llmPayload(settings) : {}),
    }));"""

text = text.replace(old_send.replace("\r\n", "\n"), new_send)

# Add Project and Session API methods
new_methods = """
  // Projects & Sessions API
  async listProjects(): Promise<Project[]> {
    const res = await this.client.get('/projects');
    return res.data;
  }

  async listProjectSessions(projectId: string): Promise<ChatSession[]> {
    const res = await this.client.get(`/projects/${projectId}/sessions`);
    return res.data;
  }

  async createSession(projectId: string, title: string = 'New Chat', model?: string): Promise<ChatSession> {
    const res = await this.client.post(`/projects/${projectId}/sessions`, { title, model });
    return res.data;
  }

  async getSessionMessages(sessionId: string): Promise<{ session: ChatSession; messages: ChatMessage[] }> {
    const res = await this.client.get(`/sessions/${sessionId}/messages`);
    return res.data;
  }

  async updateSession(sessionId: string, data: { title?: string; model?: string }): Promise<void> {
    await this.client.patch(`/sessions/${sessionId}`, data);
  }

  async deleteSession(sessionId: string): Promise<void> {
    await this.client.delete(`/sessions/${sessionId}`);
  }

  async getSettings(): Promise<UserSettings> {
    const res = await this.client.get('/settings');
    return res.data;
  }

  async saveSettings(settings: Partial<UserSettings>): Promise<void> {
    await this.client.post('/settings', settings);
  }
"""

if "async listProjects():" not in text:
    # insert before close of APIClient class (before the last closing brace)
    idx = text.rfind("}")
    text = text[:idx] + new_methods + "\n}\n"

p.write_text(text, encoding="utf-8")
print("frontend api/client.ts updated.")
