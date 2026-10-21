import { create } from 'zustand';
import type {
  Repository,
  RepositoryFile,
  FileContent,
  ChatMessage,
  IndexingStatus,
  ProposedEdit,
  AppliedEditSnapshot,
  AgentPlan,
  AgentTodo,
  TerminalLog,
  PendingApproval,
  Project,
  ChatSession,
  WorktreeInfo,
  ChangeLedgerEvent,
  ProjectLedgerStats,
  Ticket,
} from '../types';
import { apiClient, LOCAL_SESSION_ID } from '../api/client';
import { getMonacoLanguage } from '../utils/language';
import {
  loadLlmSettings,
  saveLlmSettings,
  type LlmSettings,
} from '../utils/llmSettings';

interface AppStore {
  // Projects & Sessions state
  projects: Project[];
  projectSessions: Record<string, ChatSession[]>;
  activeSessionId: string | null;
  activeSessionTitle: string | null;
  activeSessionModel: string | null;

  loadProjects: () => Promise<void>;
  loadProjectSessions: (projectId: string) => Promise<ChatSession[]>;
  selectSession: (sessionId: string, projectId?: string) => Promise<void>;
  createSession: (projectId?: string, title?: string) => Promise<ChatSession>;
  deleteSession: (sessionId: string) => Promise<void>;
  deleteProject: (projectId: string) => Promise<void>;
  renameSession: (sessionId: string, newTitle: string) => Promise<void>;
  updateModel: (model: string) => Promise<void>;

  // Worktree state
  worktrees: WorktreeInfo[];
  activeWorktree: WorktreeInfo | null;
  loadWorktrees: (repoId: string) => Promise<WorktreeInfo[]>;
  createWorktree: (repoId: string, name: string, branch?: string) => Promise<WorktreeInfo>;
  selectWorktree: (worktree: WorktreeInfo | null) => void;
  removeWorktree: (repoId: string, name: string) => Promise<void>;

  // Change Ledger state
  ledgerEvents: ChangeLedgerEvent[];
  ledgerStats: ProjectLedgerStats | null;
  loadLedgerEvents: (projectId: string, filters?: any) => Promise<void>;
  loadLedgerStats: (projectId: string) => Promise<void>;

  // Ticket state
  tickets: Ticket[];
  activeTicketId: string | null;
  loadTickets: (projectId: string, status?: string) => Promise<void>;
  createTicket: (projectId: string, data: any) => Promise<Ticket>;
  selectTicket: (ticketId: string | null) => void;
  activateTicketWorktree: (ticketId: string) => Promise<void>;

  // Repository state
  currentRepository: Repository | null;
  repositoryFiles: RepositoryFile[];
  indexingStatus: IndexingStatus | null;
  setCurrentRepository: (repo: Repository) => void;
  setRepositoryFiles: (files: RepositoryFile[]) => void;
  setIndexingStatus: (status: IndexingStatus) => void;

  // Editor state
  openFiles: Map<string, FileContent>;
  activeFile: string | null;
  selectedCode: string | null;
  selectedCodeRange?: { start: number; end: number };

  openFile: (file: FileContent) => void;
  openDiffTab: (filePath: string, original: string, proposed: string, diffTitle?: string) => void;
  closeFile: (path: string) => void;
  setActiveFile: (path: string) => void;
  updateFileContent: (path: string, content: string) => void;
  setSelectedCode: (code: string | null) => void;
  createLocalFile: (file: FileContent) => void;
  localFiles: FileContent[];
  removeLocalFile: (path: string) => void;

  // Chat state
  chatMessages: ChatMessage[];
  chatLoading: boolean;
  chatError: string | null;
  streamingContent: string;
  streamingThought: string;
  isStreaming: boolean;
  statusLine: string | null;
  agentPlan: AgentPlan | null;
  terminalLogs: TerminalLog[];
  pendingApproval: PendingApproval | null;
  setPendingApproval: (approval: PendingApproval | null) => void;
  agentStep: string | null;
  enablePlanning: boolean;
  setEnablePlanning: (enabled: boolean) => void;

  addChatMessage: (message: ChatMessage) => void;
  clearChatMessages: () => void;
  setChatLoading: (loading: boolean) => void;
  setChatError: (error: string | null) => void;
  startChatStream: () => void;
  handleChatWsMessage: (message: {
    type?: string;
    content?: string;
    error?: string;
    tool?: string;
    args?: Record<string, unknown>;
    request_id?: string;
    edits?: ProposedEdit[];
    applied?: boolean;
    goal?: string;
    todos?: AgentTodo[];
    id?: string;
    status?: string;
    note?: string;
    plan?: AgentPlan;
    command?: string;
    returncode?: number | null;
    stdout?: string;
    stderr?: string;
    step?: number;
    max_steps?: number;
  }) => void;

  // Edit proposals
  pendingEdits: ProposedEdit[] | null;
  activeRequestId: string | null;
  lastAppliedRequest: AppliedEditSnapshot | null;
  editApplying: boolean;
  applyPendingEdits: () => Promise<void>;
  rejectPendingEdits: () => void;
  undoLastApply: () => Promise<void>;

  // UI state
  sidebarOpen: boolean;
  explorerExpanded: Map<string, boolean>;

  toggleSidebar: () => void;
  toggleExplorerNode: (path: string) => void;

  llmSettings: LlmSettings;
  setLlmSettings: (settings: LlmSettings) => void;
  settingsOpen: boolean;
  setSettingsOpen: (open: boolean) => void;

  // File explorer state
  expandedFolders: Set<string>;
  toggleFolder: (path: string) => void;
}

function overviewMessage(
  verb: string,
  edits: ProposedEdit[],
): ChatMessage {
  const lines = edits.map((e) => {
    const name = e.file_path.split('/').pop() || e.file_path;
    const note = e.rationale?.trim() || (e.is_new_file ? 'new file' : 'updated');
    return `• ${name}: ${note}`;
  });
  return {
    role: 'assistant',
    content: `${verb}\n${lines.join('\n')}`,
    type: 'message',
    timestamp: new Date().toISOString(),
  };
}

function applyEditsToOpenTabs(
  state: {
    openFiles: Map<string, FileContent>;
    localFiles: FileContent[];
    activeFile: string | null;
  },
  edits: ProposedEdit[],
  useProposed: boolean,
): Partial<AppStore> {
  const newOpenFiles = new Map(state.openFiles);
  let localFiles = [...state.localFiles];
  let activeFile = state.activeFile;

  for (const edit of edits) {
    const path = edit.file_path.replace(/\\/g, '/');
    const content = useProposed ? edit.proposed : edit.original;
    const existing = newOpenFiles.get(path);
    const language = existing?.language || getMonacoLanguage(path);
    const file: FileContent = { path, content, language };
    newOpenFiles.set(path, file);

    const localIdx = localFiles.findIndex((f) => f.path === path);
    if (localIdx >= 0) {
      localFiles[localIdx] = file;
    } else if (!useProposed && edit.is_new_file) {
      // Undoing a new file: remove from local list if it was created
      localFiles = localFiles.filter((f) => f.path !== path);
      newOpenFiles.delete(path);
      if (activeFile === path) {
        const remaining = Array.from(newOpenFiles.keys());
        activeFile = remaining.length ? remaining[remaining.length - 1] : null;
      }
      continue;
    } else if (useProposed && !existing) {
      localFiles = [...localFiles, file];
    }
  }

  return { openFiles: newOpenFiles, localFiles, activeFile };
}

export const useAppStore = create<AppStore>((set, get) => ({
  // Projects & Sessions state
  projects: [],
  projectSessions: {},
  activeSessionId: null,
  activeSessionTitle: null,
  activeSessionModel: null,

  worktrees: [],
  activeWorktree: null,
  ledgerEvents: [],
  ledgerStats: null,
  tickets: [],
  activeTicketId: null,

  loadWorktrees: async (repoId: string) => {
    try {
      const wts = await apiClient.listWorktrees(repoId);
      set({ worktrees: wts });
      if (!get().activeWorktree && wts.length > 0) {
        const mainWt = wts.find((w) => w.is_main) || wts[0];
        set({ activeWorktree: mainWt });
      }
      return wts;
    } catch (e) {
      console.error('Failed to load worktrees:', e);
      return [];
    }
  },

  createWorktree: async (repoId: string, name: string, branch?: string) => {
    const wt = await apiClient.createWorktree(repoId, name, branch);
    set((s) => ({
      worktrees: [...s.worktrees, wt],
      activeWorktree: wt,
    }));
    return wt;
  },

  selectWorktree: (worktree: WorktreeInfo | null) => {
    set({ activeWorktree: worktree });
  },

  removeWorktree: async (repoId: string, name: string) => {
    await apiClient.removeWorktree(repoId, name);
    const updated = await apiClient.listWorktrees(repoId);
    set({
      worktrees: updated,
      activeWorktree: get().activeWorktree?.name === name ? (updated[0] || null) : get().activeWorktree,
    });
  },

  loadLedgerEvents: async (projectId: string, filters?: any) => {
    try {
      const events = await apiClient.listLedgerEvents(projectId, filters);
      set({ ledgerEvents: events });
    } catch (e) {
      console.error('Failed to load ledger events:', e);
    }
  },

  loadLedgerStats: async (projectId: string) => {
    try {
      const stats = await apiClient.getLedgerStats(projectId);
      set({ ledgerStats: stats });
    } catch (e) {
      console.error('Failed to load ledger stats:', e);
    }
  },

  loadTickets: async (projectId: string, status?: string) => {
    try {
      const tkts = await apiClient.listTickets(projectId, status);
      set({ tickets: tkts });
    } catch (e) {
      console.error('Failed to load tickets:', e);
    }
  },

  createTicket: async (projectId: string, data: any) => {
    const tkt = await apiClient.createTicket(projectId, data);
    set((s) => ({ tickets: [tkt, ...s.tickets] }));
    get().loadLedgerStats(projectId);
    return tkt;
  },

  selectTicket: (ticketId: string | null) => {
    set({ activeTicketId: ticketId });
  },

  activateTicketWorktree: async (ticketId: string) => {
    try {
      const res = await apiClient.activateTicketWorktree(ticketId);
      const curRepo = get().currentRepository;
      if (curRepo) {
        await get().loadWorktrees(curRepo.id);
        await get().loadTickets(curRepo.id);
        await get().loadLedgerEvents(curRepo.id);
      }
      set({ activeWorktree: res.worktree });
    } catch (e) {
      console.error('Failed to activate ticket worktree:', e);
    }
  },

  loadProjects: async () => {
    try {
      const [projectsList, settings] = await Promise.all([
        apiClient.listProjects(),
        apiClient.getSettings().catch(() => null),
      ]);
      set({ projects: projectsList });

      // Restore saved model if present
      if (settings?.default_model) {
        const curSettings = get().llmSettings;
        if (curSettings.model !== settings.default_model) {
          const next = { ...curSettings, model: settings.default_model };
          saveLlmSettings(next);
          set({ llmSettings: next });
        }
      }

      // If there's an active project in settings or first project
      const targetProjId = settings?.active_project_id || (projectsList.length ? projectsList[0].id : null);
      if (targetProjId && !get().currentRepository) {
        const match = projectsList.find((p: Project) => p.id === targetProjId);
        if (match) {
          get().setCurrentRepository({
            id: match.id,
            name: match.name,
            path: match.path,
            created_at: match.created_at,
          });
          await get().loadProjectSessions(match.id);
        }
      }
    } catch (e) {
      console.error('Failed to load projects:', e);
    }
  },

  loadProjectSessions: async (projectId: string) => {
    try {
      const sessions = await apiClient.listProjectSessions(projectId);
      set((state) => ({
        projectSessions: {
          ...state.projectSessions,
          [projectId]: sessions,
        },
      }));

      // If no active session, auto-select first or create one
      if (!get().activeSessionId && sessions.length > 0) {
        await get().selectSession(sessions[0].id, projectId);
      }
      return sessions;
    } catch (e) {
      console.error(`Failed to load sessions for project ${projectId}:`, e);
      return [];
    }
  },

  selectSession: async (sessionId: string, projectId?: string) => {
    try {
      set({
        chatLoading: true,
        activeSessionId: sessionId,
        isStreaming: false,
        streamingContent: '',
        streamingThought: '',
        statusLine: null,
        pendingEdits: null,
        activeRequestId: null,
      });
      const data = await apiClient.getSessionMessages(sessionId);
      const title = data.session?.title || 'Chat';
      const model = data.session?.model || null;

      // Restore plan from messages if any
      let lastPlan: AgentPlan | null = null;
      for (const m of data.messages) {
        if (m.plan) lastPlan = m.plan;
      }

      set({
        chatMessages: data.messages,
        activeSessionId: sessionId,
        activeSessionTitle: title,
        activeSessionModel: model,
        agentPlan: lastPlan,
        streamingContent: '',
        isStreaming: false,
        chatLoading: false,
      });

      const pid = projectId || data.session?.project_id || get().currentRepository?.id;
      apiClient.saveSettings({
        active_project_id: pid || undefined,
        active_session_id: sessionId,
      }).catch(() => undefined);
    } catch (e) {
      console.error(`Failed to select session ${sessionId}:`, e);
      set({ chatLoading: false, isStreaming: false });
    }
  },

  createSession: async (projectId?: string, title: string = 'New Chat') => {
    const pid = projectId || get().currentRepository?.id || LOCAL_SESSION_ID;
    const model = get().llmSettings.model || undefined;
    const newSession = await apiClient.createSession(pid, title, model);

    set((state) => {
      const existing = state.projectSessions[pid] || [];
      return {
        projectSessions: {
          ...state.projectSessions,
          [pid]: [newSession, ...existing],
        },
        activeSessionId: newSession.id,
        activeSessionTitle: newSession.title,
        activeSessionModel: newSession.model,
        chatMessages: [],
        agentPlan: null,
        terminalLogs: [],
        pendingEdits: null,
        activeRequestId: null,
        agentStep: null,
        statusLine: null,
        streamingContent: '',
        streamingThought: '',
        isStreaming: false,
        chatLoading: false,
      };
    });

    apiClient.saveSettings({
      active_project_id: pid,
      active_session_id: newSession.id,
    }).catch(() => undefined);

    return newSession;
  },

  deleteProject: async (projectId: string) => {
    try {
      await apiClient.deleteProject(projectId);
      set((state) => {
        const nextProjects = state.projects.filter((p) => p.id !== projectId);
        const isCurrent = state.currentRepository?.id === projectId;
        const nextRepo = isCurrent ? (nextProjects.length > 0 ? nextProjects[0] : null) : state.currentRepository;
        const nextProjectSessions = { ...state.projectSessions };
        delete nextProjectSessions[projectId];
        return {
          projects: nextProjects,
          currentRepository: nextRepo,
          projectSessions: nextProjectSessions,
          ...(isCurrent
            ? {
                activeSessionId: null,
                activeSessionTitle: null,
                chatMessages: [],
                agentPlan: null,
                pendingEdits: null,
                worktrees: [],
                activeWorktree: null,
                tickets: [],
                activeTicket: null,
                ledgerEvents: [],
                ledgerStats: null,
              }
            : {}),
        };
      });
    } catch (e) {
      console.error(`Failed to delete project ${projectId}:`, e);
      throw e;
    }
  },

  deleteSession: async (sessionId: string) => {
    try {
      await apiClient.deleteSession(sessionId);
      set((state) => {
        const nextProjectSessions: Record<string, ChatSession[]> = {};
        for (const [pid, list] of Object.entries(state.projectSessions)) {
          nextProjectSessions[pid] = list.filter((s) => s.id !== sessionId);
        }
        const isCurrent = state.activeSessionId === sessionId;
        return {
          projectSessions: nextProjectSessions,
          ...(isCurrent
            ? {
                activeSessionId: null,
                activeSessionTitle: null,
                chatMessages: [],
                agentPlan: null,
              }
            : {}),
        };
      });
    } catch (e) {
      console.error(`Failed to delete session ${sessionId}:`, e);
    }
  },

  renameSession: async (sessionId: string, newTitle: string) => {
    try {
      await apiClient.updateSession(sessionId, { title: newTitle });
      set((state) => {
        const nextProjectSessions: Record<string, ChatSession[]> = {};
        for (const [pid, list] of Object.entries(state.projectSessions)) {
          nextProjectSessions[pid] = list.map((s) =>
            s.id === sessionId ? { ...s, title: newTitle } : s
          );
        }
        return {
          projectSessions: nextProjectSessions,
          activeSessionTitle:
            state.activeSessionId === sessionId ? newTitle : state.activeSessionTitle,
        };
      });
    } catch (e) {
      console.error(`Failed to rename session ${sessionId}:`, e);
    }
  },

  updateModel: async (model: string) => {
    const curSettings = get().llmSettings;
    const nextSettings = { ...curSettings, model };
    saveLlmSettings(nextSettings);
    set({ llmSettings: nextSettings });

    apiClient.saveSettings({ default_model: model }).catch(() => undefined);
    if (get().activeSessionId) {
      apiClient.updateSession(get().activeSessionId!, { model }).catch(() => undefined);
    }
  },

  // Repository state
  currentRepository: null,
  repositoryFiles: [],
  indexingStatus: null,
  setCurrentRepository: (repo) =>
    set({
      currentRepository: repo,
      indexingStatus: null,
      repositoryFiles: [],
      openFiles: new Map(),
      activeFile: null,
      selectedCode: null,
      pendingEdits: null,
      activeRequestId: null,
      lastAppliedRequest: null,
      agentPlan: null,
      terminalLogs: [],
      agentStep: null,
      statusLine: null,
      streamingContent: '',
      streamingThought: '',
      isStreaming: false,
      chatLoading: false,
    }),
  setRepositoryFiles: (files) =>
    set({
      repositoryFiles: files.map((file) => ({
        ...file,
        path: file.path.replace(/\\/g, '/'),
      })),
    }),
  setIndexingStatus: (status) => set({ indexingStatus: status }),

  // Editor state
  openFiles: new Map(),
  activeFile: null,
  selectedCode: null,
  localFiles: [],

  openFile: (file) =>
    set((state) => {
      const newOpenFiles = new Map(state.openFiles);
      newOpenFiles.set(file.path, file);
      return {
        openFiles: newOpenFiles,
        activeFile: file.path,
        selectedCode: null,
      };
    }),

  openDiffTab: (filePath, original, proposed, diffTitle) => {
    const cleanPath = filePath.replace(/\\/g, '/');
    const diffKey = `diff:${cleanPath}`;
    const file: FileContent = {
      path: diffKey,
      content: proposed || '',
      language: getMonacoLanguage(cleanPath),
      isDiff: true,
      originalContent: original || '',
      modifiedContent: proposed || '',
      diffTitle: diffTitle || `Diff: ${cleanPath.split('/').pop()}`,
    };
    get().openFile(file);
  },

  createLocalFile: (file) =>
    set((state) => {
      const newOpenFiles = new Map(state.openFiles);
      newOpenFiles.set(file.path, file);
      const exists = state.localFiles.some((f) => f.path === file.path);
      return {
        openFiles: newOpenFiles,
        activeFile: file.path,
        localFiles: exists
          ? state.localFiles.map((f) => (f.path === file.path ? file : f))
          : [...state.localFiles, file],
      };
    }),

  removeLocalFile: (path) =>
    set((state) => {
      const newOpenFiles = new Map(state.openFiles);
      newOpenFiles.delete(path);
      const remaining = Array.from(newOpenFiles.keys());
      return {
        localFiles: state.localFiles.filter((f) => f.path !== path),
        openFiles: newOpenFiles,
        activeFile:
          state.activeFile === path
            ? remaining.length > 0
              ? remaining[remaining.length - 1]
              : null
            : state.activeFile,
      };
    }),

  closeFile: (path) =>
    set((state) => {
      const newOpenFiles = new Map(state.openFiles);
      newOpenFiles.delete(path);
      const remaining = Array.from(newOpenFiles.keys());
      return {
        openFiles: newOpenFiles,
        activeFile: remaining.length > 0 ? remaining[remaining.length - 1] : null,
      };
    }),

  setActiveFile: (path) => set({ activeFile: path, selectedCode: null }),

  updateFileContent: (path, content) =>
    set((state) => {
      const newOpenFiles = new Map(state.openFiles);
      const file = newOpenFiles.get(path);
      if (file) {
        newOpenFiles.set(path, { ...file, content });
      }
      return {
        openFiles: newOpenFiles,
        localFiles: state.localFiles.map((f) =>
          f.path === path ? { ...f, content } : f
        ),
      };
    }),

  setSelectedCode: (code) => set({ selectedCode: code }),

  // Chat state
  chatMessages: [],
  chatLoading: false,
  chatError: null,
  streamingContent: '',
  streamingThought: '',
  isStreaming: false,
  statusLine: null,
  agentPlan: null,
  terminalLogs: [],
  pendingApproval: null,
  setPendingApproval: (approval) => set({ pendingApproval: approval }),
  agentStep: null,
  enablePlanning: false,
  setEnablePlanning: (enabled) => set({ enablePlanning: enabled }),

  addChatMessage: (message) =>
    set((state) => ({
      chatMessages: [...state.chatMessages, message],
    })),

  clearChatMessages: () =>
    set({
      chatMessages: [],
      streamingContent: '',
      isStreaming: false,
      statusLine: null,
      pendingEdits: null,
      activeRequestId: null,
      agentPlan: null,
      terminalLogs: [],
      agentStep: null,
    }),

  setChatLoading: (loading) => set({ chatLoading: loading }),

  setChatError: (error) => set({ chatError: error }),

  startChatStream: () =>
    set({
      streamingContent: '',
      streamingThought: '',
      isStreaming: true,
      statusLine: null,
      agentPlan: null,
      terminalLogs: [],
      agentStep: null,
    }),

  handleChatWsMessage: (message) =>
    set((state) => {
      const timestamp = new Date().toISOString();

      if (message.type === 'session_updated') {
        const sid = (message as any).session_id;
        const newTitle = (message as any).title;
        const currentRepoId = state.currentRepository?.id || LOCAL_SESSION_ID;
        const existingSessions = state.projectSessions[currentRepoId] || [];
        const updated = existingSessions.map((s) =>
          s.id === sid ? { ...s, title: newTitle } : s
        );
        return {
          activeSessionTitle: sid === state.activeSessionId ? newTitle : state.activeSessionTitle,
          projectSessions: {
            ...state.projectSessions,
            [currentRepoId]: updated,
          },
        };
      }

      if (message.type === 'content') {
        return {
          streamingContent: state.streamingContent + (message.content ?? ''),
          isStreaming: true,
          statusLine: null,
        };
      }

      if (message.type === 'response') {
        return { isStreaming: true, statusLine: null };
      }

      if (message.type === 'planning') {
        return {
          statusLine: message.content || 'Planning…',
          isStreaming: true,
        };
      }

      if (message.type === 'step') {
        const label =
          message.content ||
          (message.step != null
            ? `Step ${message.step}/${message.max_steps ?? '?'}`
            : 'Working…');
        return {
          agentStep: label,
          statusLine: label,
          isStreaming: true,
        };
      }

      if (message.type === 'plan') {
        const plan: AgentPlan = {
          goal: message.goal || '',
          todos: (message.todos || []).map((t) => ({
            id: t.id,
            title: t.title,
            status: t.status || 'pending',
            note: t.note,
          })),
        };
        return {
          agentPlan: plan,
          statusLine: plan.goal ? `Plan: ${plan.goal}` : 'Plan created',
          isStreaming: true,
        };
      }

      if (message.type === 'todo_update') {
        const incoming = message.plan;
        let plan = state.agentPlan;
        if (incoming?.todos) {
          plan = {
            goal: incoming.goal || plan?.goal || '',
            todos: incoming.todos,
          };
        } else if (plan && message.id) {
          plan = {
            ...plan,
            todos: plan.todos.map((t) =>
              t.id === message.id
                ? {
                    ...t,
                    status: message.status || t.status,
                    note: message.note ?? t.note,
                  }
                : t
            ),
          };
        }
        const active = plan?.todos.find((t) => t.status === 'in_progress');
        return {
          agentPlan: plan,
          statusLine: active
            ? `Working: ${active.title}`
            : message.status
              ? `Todo ${message.id}: ${message.status}`
              : state.statusLine,
          isStreaming: true,
        };
      }

      if (message.type === 'terminal') {
        const entry: TerminalLog = {
          command: message.command || '',
          returncode: message.returncode,
          stdout: message.stdout,
          stderr: message.stderr,
          status: message.status,
          error: message.error,
          timestamp,
        };
        const ok = message.returncode === 0;
        return {
          terminalLogs: [...state.terminalLogs.slice(-9), entry],
          statusLine: ok
            ? `✓ ${entry.command}`
            : `✗ ${entry.command} (exit ${message.returncode ?? '?'})`,
          isStreaming: true,
        };
      }

      if (message.type === 'approval_required') {
        return {
          pendingApproval: {
            action_id: (message as any).action_id || '',
            tool_name: (message as any).tool_name || '',
            action_category: (message as any).action_category || (message as any).tool_name || '',
            details: (message as any).details || {},
            reason: (message as any).reason || 'Confirmation required',
            tier: (message as any).tier || 'caution',
          },
          statusLine: `Action approval required for ${(message as any).tool_name || 'agent'}`,
          isStreaming: true,
        };
      }

      if (message.type === 'thought') {
        const thoughtChunk = message.content ?? '';
        return {
          streamingThought: (state.streamingThought ? state.streamingThought + '\n' : '') + thoughtChunk,
          isStreaming: true,
        };
      }

      if (message.type === 'tool_call') {
        const toolName = message.tool || 'tool';
        const rationale = (message as any).rationale || '';
        const statusText = rationale ? `${toolName}: ${rationale}` : `Running ${toolName}…`;
        return {
          statusLine: statusText,
          isStreaming: true,
        };
      }

      if (message.type === 'tool_result') {
        return {
          statusLine: message.tool ? `Finished ${message.tool}` : null,
          isStreaming: true,
        };
      }

      if (message.type === 'edit_proposal') {
        const edits = (message.edits ?? []).map((e) => ({
          ...e,
          file_path: (e.file_path || '').replace(/\\/g, '/'),
          validation: e.validation ?? { ok: true, errors: [] },
          // Keep full content for diff UI — may already be applied on disk
          original: e.original ?? '',
          proposed: e.proposed ?? '',
          diff: e.diff ?? '',
        }));
        const applied = Boolean(message.applied);
        const tabUpdates = applied
          ? applyEditsToOpenTabs(state, edits, true)
          : {};
        if (edits.length > 0 && edits[0].file_path) {
          const first = edits[0];
          setTimeout(() => {
            get().openDiffTab(first.file_path, first.original, first.proposed);
          }, 60);
        }

        return {
          ...tabUpdates,
          pendingEdits: edits,
          activeRequestId: message.request_id ?? null,
          lastAppliedRequest: applied
            ? { request_id: message.request_id ?? '', edits }
            : state.lastAppliedRequest,
          isStreaming: true,
          statusLine: edits.length
            ? applied
              ? `Applied ${edits.length} file${edits.length === 1 ? '' : 's'} — review / undo below`
              : `Proposed ${edits.length} edit${edits.length === 1 ? '' : 's'} — review below`
            : null,
        };
      }

      if (message.type === 'message') {
        const thought = state.streamingThought || undefined;
        return {
          streamingContent: '',
          streamingThought: '',
          isStreaming: false,
          statusLine: null,
          chatMessages: [
            ...state.chatMessages,
            {
              role: 'assistant',
              content: message.content ?? '',
              thought,
              proposed_edits: state.pendingEdits || undefined,
              type: 'message',
              timestamp,
            },
          ],
        };
      }

      if (message.type === 'end') {
        const thought = state.streamingThought || undefined;
        if (!state.streamingContent && !thought) {
          return { streamingContent: '', streamingThought: '', isStreaming: false, statusLine: null };
        }

        return {
          streamingContent: '',
          streamingThought: '',
          isStreaming: false,
          statusLine: null,
          chatMessages: [
            ...state.chatMessages,
            {
              role: 'assistant',
              content: state.streamingContent,
              thought,
              proposed_edits: state.pendingEdits || undefined,
              type: 'message',
              timestamp,
            },
          ],
        };
      }

      if (message.type === 'error') {
        if (!state.isStreaming && !state.streamingContent) {
          return state;
        }
        return {
          streamingContent: '',
          isStreaming: false,
          statusLine: null,
          chatMessages: [
            ...state.chatMessages,
            {
              role: 'assistant',
              content: `Error: ${message.error ?? 'Unknown error'}`,
              type: 'error',
              timestamp,
            },
          ],
        };
      }

      return state;
    }),

  // Edit proposals
  pendingEdits: null,
  activeRequestId: null,
  lastAppliedRequest: null,
  editApplying: false,

  applyPendingEdits: async () => {
    const state = get();
    const edits = state.pendingEdits;
    const requestId = state.activeRequestId;
    if (!edits?.length || !requestId || state.editApplying) return;

    const hasInvalid = edits.some((e) => e.validation && e.validation.ok === false);
    if (hasInvalid) return;

    set({ editApplying: true });
    const repoId = state.currentRepository?.id;
    const isLocal = !repoId || repoId === LOCAL_SESSION_ID;

    // Prefer live editor/disk originals for accurate undo (chat buffer may be truncated)
    const editsForUndo: ProposedEdit[] = edits.map((e) => {
      const path = e.file_path.replace(/\\/g, '/');
      const open = state.openFiles.get(path);
      const local = state.localFiles.find((f) => f.path === path);
      const liveOriginal = open?.content ?? local?.content;
      if (liveOriginal !== undefined) {
        return { ...e, original: liveOriginal, is_new_file: false };
      }
      return e;
    });

    try {
      if (!isLocal) {
        await apiClient.applyEdits(repoId, {
          request_id: requestId,
          edits: edits.map((e) => ({
            file_path: e.file_path,
            proposed: e.proposed,
          })),
        });
      }

      set((s) => {
        const tabUpdates = applyEditsToOpenTabs(s, editsForUndo, true);
        return {
          ...tabUpdates,
          pendingEdits: null,
          activeRequestId: null,
          lastAppliedRequest: { request_id: requestId, edits: editsForUndo },
          editApplying: false,
          chatMessages: [...s.chatMessages, overviewMessage('Applied changes:', editsForUndo)],
        };
      });
    } catch (error) {
      console.error('Failed to apply edits:', error);
      set((s) => ({
        editApplying: false,
        chatMessages: [
          ...s.chatMessages,
          {
            role: 'assistant',
            content: `Failed to apply edits: ${error instanceof Error ? error.message : 'Unknown error'}`,
            type: 'error',
            timestamp: new Date().toISOString(),
          },
        ],
      }));
    }
  },

  rejectPendingEdits: () => {
    const state = get();
    const edits = state.pendingEdits;
    if (!edits?.length) {
      set({ pendingEdits: null, activeRequestId: null });
      return;
    }
    set((s) => ({
      pendingEdits: null,
      activeRequestId: null,
      chatMessages: [...s.chatMessages, overviewMessage('Rejected proposed changes:', edits)],
    }));
  },

  undoLastApply: async () => {
    const state = get();
    const last = state.lastAppliedRequest;
    if (!last || state.editApplying) return;

    set({ editApplying: true });
    const repoId = state.currentRepository?.id;
    const isLocal = !repoId || repoId === LOCAL_SESSION_ID;

    try {
      if (!isLocal) {
        await apiClient.undoEdits(repoId, last.request_id);
      }

      set((s) => {
        const tabUpdates = applyEditsToOpenTabs(s, last.edits, false);
        return {
          ...tabUpdates,
          lastAppliedRequest: null,
          editApplying: false,
          chatMessages: [
            ...s.chatMessages,
            overviewMessage('Undid applied changes:', last.edits),
          ],
        };
      });
    } catch (error) {
      console.error('Failed to undo edits:', error);
      set((s) => ({
        editApplying: false,
        chatMessages: [
          ...s.chatMessages,
          {
            role: 'assistant',
            content: `Failed to undo: ${error instanceof Error ? error.message : 'Unknown error'}`,
            type: 'error',
            timestamp: new Date().toISOString(),
          },
        ],
      }));
    }
  },

  // UI state
  sidebarOpen: true,
  explorerExpanded: new Map(),

  toggleSidebar: () =>
    set((state) => ({
      sidebarOpen: !state.sidebarOpen,
    })),

  toggleExplorerNode: (path) =>
    set((state) => {
      const newExpanded = new Map(state.explorerExpanded);
      newExpanded.set(path, !(newExpanded.get(path) ?? false));
      return { explorerExpanded: newExpanded };
    }),

  llmSettings: loadLlmSettings(),
  setLlmSettings: (settings) => {
    saveLlmSettings(settings);
    set({ llmSettings: settings });
  },
  settingsOpen: false,
  setSettingsOpen: (open) => set({ settingsOpen: open }),

  // File explorer state
  expandedFolders: new Set(),
  toggleFolder: (path) =>
    set((state) => {
      const newExpanded = new Set(state.expandedFolders);
      if (newExpanded.has(path)) {
        newExpanded.delete(path);
      } else {
        newExpanded.add(path);
      }
      return { expandedFolders: newExpanded };
    }),
}));
