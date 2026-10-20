import pathlib

p = pathlib.Path(r"C:\Users\saatw\Downloads\Crystal-Desktop\frontend\src\store\index.ts")
text = p.read_text(encoding="utf-8")

# 1. Update imports from ../types
old_types = """import type {
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
} from '../types';"""

new_types = """import type {
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
} from '../types';"""

text = text.replace(old_types.replace("\r\n", "\n"), new_types)

# 2. Add interface properties
old_interface = """interface AppStore {
  // Repository state
  currentRepository: Repository | null;"""

new_interface = """interface AppStore {
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
  renameSession: (sessionId: string, newTitle: string) => Promise<void>;
  updateModel: (model: string) => Promise<void>;

  // Repository state
  currentRepository: Repository | null;"""

text = text.replace(old_interface.replace("\r\n", "\n"), new_interface)

# 3. Add initial state and implementations to create<AppStore>
old_create = """export const useAppStore = create<AppStore>((set, get) => ({
  // Repository state
  currentRepository: null,"""

new_create = """export const useAppStore = create<AppStore>((set, get) => ({
  // Projects & Sessions state
  projects: [],
  projectSessions: {},
  activeSessionId: null,
  activeSessionTitle: null,
  activeSessionModel: null,

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
        const match = projectsList.find((p) => p.id === targetProjId);
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
      set({ chatLoading: true, activeSessionId: sessionId });
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
      set({ chatLoading: false });
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
        streamingContent: '',
        isStreaming: false,
      };
    });

    apiClient.saveSettings({
      active_project_id: pid,
      active_session_id: newSession.id,
    }).catch(() => undefined);

    return newSession;
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
  currentRepository: null,"""

text = text.replace(old_create.replace("\r\n", "\n"), new_create)

# 4. Handle session_updated in handleChatWsMessage
old_ws_handle = """      if (message.type === 'content') {"""
new_ws_handle = """      if (message.type === 'session_updated') {
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

      if (message.type === 'content') {"""

text = text.replace(old_ws_handle.replace("\r\n", "\n"), new_ws_handle)

p.write_text(text, encoding="utf-8")
print("store/index.ts updated with full project & session state.")
