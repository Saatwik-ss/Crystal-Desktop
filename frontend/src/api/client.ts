/// <reference types="vite/client" />
import axios, { AxiosInstance } from 'axios';
import type {
  Repository,
  IndexingStatus,
  RepositoryFile,
  SearchResult,
  Project,
  ChatSession,
  ChatMessage,
  UserSettings,
  WorktreeInfo,
  WorktreeDiff,
  ChangeLedgerEvent,
  ProjectLedgerStats,
  Ticket,
  TicketAcceptanceCriteria,
} from '../types';
import { llmPayload, type LlmSettings } from '../utils/llmSettings';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || `${window.location.origin}/api`;
const WS_BASE_URL = import.meta.env.VITE_WS_URL || `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}`;


/** Session id used when no repository is uploaded */
export const LOCAL_SESSION_ID = 'local';

function sessionId(repoId?: string | null): string {
  return repoId && repoId !== LOCAL_SESSION_ID ? repoId : LOCAL_SESSION_ID;
}

class APIClient {
  private client: AxiosInstance;
  private wsConnections: Map<string, WebSocket> = new Map();
  private pendingCompletion: {
    resolve: (text: string) => void;
    reject: (error: Error) => void;
    buffer: string;
  } | null = null;
  private closingKeys = new Set<string>();
  private chatFirstChunkWatchdog: number | null = null;
  private chatOnMessage: ((message: any) => void) | null = null;

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
    });
  }

  // Repository endpoints
  async uploadRepository(
    files: File[],
    options?: { repoId?: string | null; finalize?: boolean }
  ): Promise<Repository> {
    const formData = new FormData();
    files.forEach((file) => {
      // Preserve a selected folder's relative path for the backend file tree.
      const relativePath = (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
      formData.append('files', file, relativePath);
    });

    const params: Record<string, string | boolean> = {};
    if (options?.repoId) {
      params.repo_id = options.repoId;
    }
    if (options?.finalize === false) {
      params.finalize = false;
    }

    const response = await this.client.post('/upload-repository', formData, {
      timeout: 600000,
      params,
    });

    const responseData = response.data as any;
    const repository = responseData.repository ?? responseData;

    return {
      ...repository,
      id: repository.id ?? repository.repository_id,
    } as Repository;
  }

  async openLocalRepository(path: string): Promise<Repository> {
    const response = await this.client.post('/open-local-repository', { path });
    const repository = response.data;
    return {
      ...repository,
      id: repository.id ?? repository.repository_id,
    } as Repository;
  }

  async getRepositoryStatus(repoId: string): Promise<IndexingStatus> {
    const response = await this.client.get(
      `/repositories/${repoId}/status`
    );
    return response.data;
  }

  async listRepositoryFiles(repoId: string): Promise<RepositoryFile[]> {
    const response = await this.client.get(
      `/repositories/${repoId}/files`
    );
    return response.data.files;
  }

  async deleteRepository(repoId: string): Promise<{
    repositories: number;
    files: number;
    indexing_status: number;
    snapshots: number;
    repo_ids: string[];
  }> {
    const response = await this.client.delete(`/repositories/${repoId}`);
    return response.data;
  }

  async cleanupAllRepositories(): Promise<{
    repositories: number;
    files: number;
    indexing_status: number;
    snapshots: number;
    repo_ids: string[];
  }> {
    const response = await this.client.delete('/repositories');
    return response.data;
  }

  async readFile(repoId: string, filePath: string): Promise<string> {
    const normalizedPath = filePath.replace(/\\/g, '/');
    const response = await this.client.get(
      `/repositories/${repoId}/file/${normalizedPath}`
    );
    return response.data.content;
  }

  async writeFile(
    repoId: string,
    filePath: string,
    content: string
  ): Promise<{ status: string }> {
    const normalizedPath = filePath.replace(/\\/g, '/');
    const response = await this.client.post(
      `/repositories/${repoId}/file/${normalizedPath}`,
      { content }
    );
    return response.data;
  }

  async applyEdits(
    repoId: string,
    payload: {
      request_id: string;
      edits: Array<{ file_path: string; proposed: string }>;
    }
  ): Promise<{ applied: Array<{ file_path: string; status: string }>; request_id: string }> {
    const response = await this.client.post(
      `/repositories/${repoId}/edits/apply`,
      payload
    );
    return response.data;
  }

  async undoEdits(
    repoId: string,
    requestId: string
  ): Promise<{ undone: Array<{ file_path: string; status: string }>; request_id: string }> {
    const response = await this.client.post(
      `/repositories/${repoId}/edits/undo`,
      { request_id: requestId }
    );
    return response.data;
  }

  // Chat WebSocket
  connectChat(
    repoId: string | null | undefined,
    onMessage: (message: any) => void,
    onError: (error: any) => void
  ): void {
    const id = sessionId(repoId);
    const key = `chat_${id}`;
    this.closeConnection(key);

    const wsUrl = `${WS_BASE_URL}/ws/chat/${id}`;
    const ws = new WebSocket(wsUrl);
    this.chatOnMessage = onMessage;

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        const isBootstrap =
          message?.type === 'planning' &&
          typeof message.content === 'string' &&
          message.content.startsWith('Loading repository');
        if (!isBootstrap && this.chatFirstChunkWatchdog != null) {
          window.clearTimeout(this.chatFirstChunkWatchdog);
          this.chatFirstChunkWatchdog = null;
        }
        onMessage(message);
      } catch (error) {
        console.error('Failed to parse chat message:', error);
      }
    };

    ws.onerror = (event) => {
      console.error('Chat WebSocket error:', event);
      onError(event);
    };

    ws.onclose = () => {
      if (this.chatFirstChunkWatchdog != null) {
        window.clearTimeout(this.chatFirstChunkWatchdog);
        this.chatFirstChunkWatchdog = null;
      }
      const intentional = this.closingKeys.has(key);
      this.closingKeys.delete(key);
      if (this.wsConnections.get(key) === ws) {
        this.wsConnections.delete(key);
      }
      if (!intentional) {
        onMessage({
          type: 'error',
          error: 'Chat connection closed unexpectedly',
        });
      }
    };

    this.wsConnections.set(key, ws);
  }

  async sendChatMessage(
    repoId: string | null | undefined,
    message: string,
    selectedFile?: string,
    selectedCode?: string,
    settings?: LlmSettings,
    enablePlanning: boolean = false,
    chatSessionId?: string | null,
    worktreePath?: string | null,
    ticketId?: string | null
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
      session_id: chatSessionId,
      message,
      selected_file: selectedFile,
      selected_code: selectedCode,
      enable_planning: enablePlanning,
      worktree_path: worktreePath,
      ticket_id: ticketId,
      ...(settings ? llmPayload(settings) : {}),
    }));

    if (this.chatFirstChunkWatchdog != null) {
      window.clearTimeout(this.chatFirstChunkWatchdog);
    }
    this.chatFirstChunkWatchdog = window.setTimeout(() => {
      this.chatFirstChunkWatchdog = null;
      const live = this.wsConnections.get(`chat_${id}`);
      if (live === ws) {
        this.chatOnMessage?.({
          type: 'error',
          error: 'Chat timed out waiting for a response',
        });
      }
    }, 45000);
  }

  // Completion WebSocket
  connectCompletion(
    repoId: string | null | undefined,
    onMessage: (message: any) => void,
    onError: (error: any) => void
  ): void {
    const id = sessionId(repoId);
    const key = `completion_${id}`;
    this.closeConnection(key);

    const wsUrl = `${WS_BASE_URL}/ws/completion/${id}`;
    const ws = new WebSocket(wsUrl);

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        if (this.pendingCompletion) {
          if (message.type === 'completion' && message.text) {
            this.pendingCompletion.buffer += message.text;
          } else if (message.type === 'completion_final' && typeof message.text === 'string') {
            this.pendingCompletion.buffer = message.text;
          } else if (message.type === 'end') {
            const text = this.pendingCompletion.buffer;
            const { resolve } = this.pendingCompletion;
            this.pendingCompletion = null;
            resolve(text);
          } else if (message.type === 'error') {
            const { reject } = this.pendingCompletion;
            this.pendingCompletion = null;
            reject(new Error(message.error || 'Completion failed'));
          }
        }
        onMessage(message);
      } catch (error) {
        console.error('Failed to parse completion message:', error);
      }
    };

    ws.onerror = (event) => {
      console.error('Completion WebSocket error:', event);
      onError(event);
    };

    ws.onclose = () => {
      if (this.wsConnections.get(key) === ws) {
        this.wsConnections.delete(key);
      }
      if (this.pendingCompletion) {
        const { reject } = this.pendingCompletion;
        this.pendingCompletion = null;
        reject(new Error('Completion connection closed'));
      }
    };

    this.wsConnections.set(key, ws);
  }

  async requestCompletion(
    repoId: string | null | undefined,
    prompt: string,
    filePath?: string,
    language?: string,
    settings?: LlmSettings,
    suffix?: string
  ): Promise<string> {
    const id = sessionId(repoId);
    let ws = this.wsConnections.get(`completion_${id}`);
    if (!ws) {
      this.connectCompletion(id, () => undefined, () => undefined);
      ws = this.wsConnections.get(`completion_${id}`);
    }
    if (!ws) throw new Error('Unable to create a completion connection');

    if (ws.readyState === WebSocket.CONNECTING) {
      await new Promise<void>((resolve, reject) => {
        const timeout = window.setTimeout(() => reject(new Error('Completion connection timed out')), 8000);
        ws!.addEventListener('open', () => { window.clearTimeout(timeout); resolve(); }, { once: true });
        ws!.addEventListener('error', () => { window.clearTimeout(timeout); reject(new Error('Completion connection failed')); }, { once: true });
      });
    }
    if (ws.readyState !== WebSocket.OPEN) {
      throw new Error('Completion connection is closed');
    }

    // Newer typing supersedes any in-flight completion
    if (this.pendingCompletion) {
      const stale = this.pendingCompletion;
      this.pendingCompletion = null;
      stale.resolve(stale.buffer || '');
    }

    return new Promise<string>((resolve, reject) => {
      const timeout = window.setTimeout(() => {
        if (this.pendingCompletion) {
          const partial = this.pendingCompletion.buffer;
          this.pendingCompletion = null;
          if (partial) {
            resolve(partial);
          } else {
            reject(new Error('Completion timed out'));
          }
        }
      }, 10000);

      this.pendingCompletion = {
        buffer: '',
        resolve: (text) => {
          window.clearTimeout(timeout);
          resolve(text);
        },
        reject: (error) => {
          window.clearTimeout(timeout);
          reject(error);
        },
      };

      ws!.send(
        JSON.stringify({
          prompt,
          suffix: suffix || '',
          file_path: filePath,
          language: language || 'javascript',
          ...(settings ? llmPayload(settings) : {}),
        })
      );
    });
  }

  // Search

  async fetchOllamaModels(url?: string): Promise<{
    models: Array<{ id: string; name: string; size?: number; details?: any; modified_at?: string }>;
    url: string;
    connected: boolean;
    error?: string;
  }> {
    try {
      const response = await this.client.post('/ollama/models', {
        url: url || 'http://localhost:11434',
      });
      return response.data;
    } catch (err: any) {
      return {
        models: [],
        url: url || 'http://localhost:11434',
        connected: false,
        error: err.response?.data?.error || err.message || 'Failed to connect to Ollama',
      };
    }
  }

  async fetchModels(apiKey: string): Promise<string[]> {
    const response = await fetch(`${API_BASE_URL}/models`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: apiKey }),
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Failed to fetch models');
    }
    const data = await response.json();
    return data.data.map((m: any) => m.id);
  }

  async search(

    repoId: string,
    query: string,
    searchType: 'semantic' | 'keyword' | 'hybrid' = 'semantic',
    topK: number = 5
  ): Promise<SearchResult[]> {
    const response = await this.client.get(
      `/search/${repoId}`,
      {
        params: {
          query,
          search_type: searchType,
          top_k: topK,
        },
      }
    );
    return response.data.results;
  }

  // Cleanup
  closeConnections(): void {
    this.wsConnections.forEach((_ws, key) => {
      this.closingKeys.add(key);
    });
    this.wsConnections.forEach((ws) => {
      if (
        ws.readyState === WebSocket.OPEN ||
        ws.readyState === WebSocket.CONNECTING
      ) {
        try {
          ws.close();
        } catch {
          // ignore close errors during cleanup
        }
      }
    });
    this.wsConnections.clear();
  }

  closeConnection(key: string): void {
    this.closingKeys.add(key);
    const ws = this.wsConnections.get(key);
    if (
      ws &&
      (ws.readyState === WebSocket.OPEN ||
        ws.readyState === WebSocket.CONNECTING)
    ) {
      try {
        ws.close();
      } catch {
        // ignore close errors during cleanup
      }
    }
    this.wsConnections.delete(key);
  }

  // Projects & Sessions API
  async listProjects(): Promise<Project[]> {
    const res = await this.client.get('/projects');
    return res.data;
  }

  async deleteProject(projectId: string): Promise<any> {
    const res = await this.client.delete(`/projects/${projectId}`);
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

  // Worktree Endpoints
  async listWorktrees(repoId: string): Promise<WorktreeInfo[]> {
    const res = await this.client.get(`/repositories/${repoId}/worktrees`);
    return res.data;
  }

  async createWorktree(
    repoId: string,
    name: string,
    branch?: string,
    baseCommit: string = 'HEAD'
  ): Promise<WorktreeInfo> {
    const res = await this.client.post(`/repositories/${repoId}/worktrees`, {
      name,
      branch,
      base_commit: baseCommit,
    });
    return res.data;
  }

  async removeWorktree(repoId: string, name: string, deleteBranch: boolean = false): Promise<void> {
    await this.client.delete(`/repositories/${repoId}/worktrees/${name}`, {
      params: { delete_branch: deleteBranch },
    });
  }

  async getWorktreeDiff(repoId: string, name: string, baseRef?: string): Promise<WorktreeDiff> {
    const res = await this.client.get(`/repositories/${repoId}/worktrees/${name}/diff`, {
      params: { base_ref: baseRef },
    });
    return res.data;
  }

  async commitWorktree(
    repoId: string,
    name: string,
    message: string,
    authorName: string = 'Crystal Agent',
    authorEmail: string = 'agent@crystal.local'
  ): Promise<{ success: boolean; commit_hash: string; message: string }> {
    const res = await this.client.post(`/repositories/${repoId}/worktrees/${name}/commit`, {
      message,
      author_name: authorName,
      author_email: authorEmail,
    });
    return res.data;
  }

  // Change Ledger Endpoints
  async listLedgerEvents(
    projectId: string,
    filters?: {
      ticket_id?: string;
      event_type?: string;
      verification_status?: string;
      limit?: number;
      offset?: number;
    }
  ): Promise<ChangeLedgerEvent[]> {
    const res = await this.client.get(`/projects/${projectId}/ledger`, {
      params: filters,
    });
    return res.data;
  }

  async getLedgerStats(projectId: string): Promise<ProjectLedgerStats> {
    const res = await this.client.get(`/projects/${projectId}/ledger/stats`);
    return res.data;
  }

  async recordLedgerEvent(projectId: string, eventData: Partial<ChangeLedgerEvent>): Promise<ChangeLedgerEvent> {
    const res = await this.client.post(`/projects/${projectId}/ledger`, eventData);
    return res.data;
  }

  // Ticket Endpoints
  async listTickets(projectId: string, status?: string): Promise<Ticket[]> {
    const res = await this.client.get(`/projects/${projectId}/tickets`, {
      params: { status },
    });
    return res.data;
  }

  async createTicket(
    projectId: string,
    ticketData: {
      title: string;
      description?: string;
      priority?: string;
      assignee_type?: string;
      assignee_id?: string;
      criteria?: Array<{ description: string; criterion_type?: string; verification_command?: string }>;
    }
  ): Promise<Ticket> {
    const res = await this.client.post(`/projects/${projectId}/tickets`, ticketData);
    return res.data;
  }

  async getTicket(ticketId: string): Promise<Ticket> {
    const res = await this.client.get(`/tickets/${ticketId}`);
    return res.data;
  }

  async updateTicket(ticketId: string, updates: Partial<Ticket>): Promise<Ticket> {
    const res = await this.client.patch(`/tickets/${ticketId}`, updates);
    return res.data;
  }

  async activateTicketWorktree(ticketId: string): Promise<{ ticket_id: string; worktree: WorktreeInfo }> {
    const res = await this.client.post(`/tickets/${ticketId}/worktree`);
    return res.data;
  }

  async addCriterion(
    ticketId: string,
    criterion: { description: string; criterion_type?: string; verification_command?: string }
  ): Promise<TicketAcceptanceCriteria> {
    const res = await this.client.post(`/tickets/${ticketId}/criteria`, criterion);
    return res.data;
  }

  async updateCriterion(criterionId: string, isSatisfied: boolean, evidenceEventId?: string): Promise<void> {
    await this.client.patch(`/criteria/${criterionId}`, {
      is_satisfied: isSatisfied,
      evidence_event_id: evidenceEventId,
    });
  }

}

export const apiClient = new APIClient();
