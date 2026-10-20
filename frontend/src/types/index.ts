export interface Repository {
  id: string;
  name: string;
  path: string;
  created_at: string;
  indexing_status?: IndexingStatus;
}

export interface IndexingStatus {
  status: "initializing" | "indexing" | "completed" | "failed";
  files_processed: number;
  total_files: number;
  errors: string[];
}

export interface RepositoryFile {
  path: string;
  language: string;
  size: number;
  ast?: any;
}

export interface FileContent {
  path: string;
  content: string;
  language: string;
  isDiff?: boolean;
  originalContent?: string;
  modifiedContent?: string;
  diffTitle?: string;
}

export interface ChatMessage {
  id?: string;
  role: "user" | "assistant" | "system";
  content: string;
  type?: "message" | "planning" | "tool_call" | "tool_result" | "edit_proposal" | "error";
  thought?: string;
  plan?: AgentPlan;
  tool_calls?: any[];
  terminal_logs?: TerminalLog[];
  proposed_edits?: ProposedEdit[];
  timestamp?: string;
}

export interface CodeCompletion {
  text: string;
  imports?: string[];
}

export interface SearchResult {
  file_path: string;
  chunk_index: number;
  content: string;
  similarity: number;
}

export interface ToolCall {
  tool: string;
  args: Record<string, any>;
}

export interface ToolResult {
  status: "success" | "error";
  result?: any;
  error?: string;
}

export interface DiffLine {
  type: "add" | "remove" | "context";
  content: string;
  lineNumber?: number;
}

export interface Diff {
  file_path: string;
  original: string;
  modified: string;
  lines: DiffLine[];
}

export interface EditValidation {
  ok: boolean;
  errors: string[];
  language?: string;
  skipped?: boolean;
}

export interface ProposedEdit {
  file_path: string;
  original: string;
  proposed: string;
  diff: string;
  rationale?: string;
  validation: EditValidation;
  is_new_file?: boolean;
  applied?: boolean;
}

export interface EditProposal {
  request_id: string;
  edits: ProposedEdit[];
}

export interface AgentTodo {
  id: string;
  title: string;
  status: 'pending' | 'in_progress' | 'completed' | 'cancelled' | string;
  note?: string;
}

export interface AgentPlan {
  goal: string;
  todos: AgentTodo[];
}

export interface TerminalLog {
  command: string;
  returncode?: number | null;
  stdout?: string;
  stderr?: string;
  status?: string;
  error?: string;
  timestamp: string;
}

export interface AppliedEditSnapshot {
  request_id: string;
  edits: ProposedEdit[];
}

export interface ContextWindow {
  currentFile?: string;
  selectedCode?: string;
  repositoryContext?: RepositoryContext;
}

export interface RepositoryContext {
  files: RepositoryFile[];
  total_files: number;
  languages: string[];
  dependencies?: Record<string, string[]>;
}

export interface EditorState {
  openFiles: Map<string, FileContent>;
  activeFile?: string;
  cursorPosition?: { line: number; column: number };
}

export interface ElectronAPI {
  isDesktop: boolean;
  openFolderDialog: () => Promise<string | null>;
  openExternal: (url: string) => Promise<void>;
  restartBackend: () => Promise<boolean>;
  getBackendStatus: () => Promise<{ running: boolean; port: number }>;
  onOpenRepository: (callback: (path: string) => void) => void;
  onBackendStatusChange: (callback: (status: any) => void) => void;
}

declare global {
  interface Window {
    electronAPI?: ElectronAPI;
  }
}

export interface PendingApproval {
  action_id: string;
  tool_name: string;
  action_category: string;
  details: Record<string, any>;
  reason: string;
  tier: "safe" | "caution" | "dangerous";
}


export interface ChatSession {
  id: string;
  project_id?: string | null;
  title: string;
  model?: string | null;
  created_at: string;
  updated_at: string;
  last_message?: string;
}

export interface Project {
  id: string;
  name: string;
  path: string;
  exists?: boolean;
  file_count?: number;
  created_at: string;
  updated_at: string;
  metadata?: Record<string, any>;
  sessions?: ChatSession[];
}

export interface UserSettings {
  default_model: string;
  active_project_id?: string | null;
  active_session_id?: string | null;
}

export interface WorktreeInfo {
  name: string;
  path: string;
  branch: string;
  commit_hash?: string;
  is_main?: boolean;
  created_at?: string;
}

export interface WorktreeDiff {
  worktree_path: string;
  additions: number;
  deletions: number;
  files_count: number;
  files_changed: Array<{
    file_path: string;
    additions: number;
    deletions: number;
  }>;
  diff_patch: string;
}

export interface ChangeLedgerEvent {
  id: string;
  project_id: string;
  ticket_id?: string | null;
  actor_type: 'human' | 'agent' | 'system' | 'reviewer';
  actor_id: string;
  branch?: string | null;
  worktree_path?: string | null;
  event_type: 'edit' | 'commit' | 'test_run' | 'hypothesis_eval' | 'pr_opened' | 'review' | 'merged' | 'reverted';
  summary: string;
  files_changed?: string[];
  diff_stats?: {
    additions?: number;
    deletions?: number;
    files_count?: number;
  };
  diff_patch?: string | null;
  verification_status: 'not_run' | 'pending' | 'passed' | 'failed';
  verification_details?: Record<string, any>;
  causal_metadata?: Record<string, any>;
  github_references?: {
    commit_sha?: string;
    pr_number?: number;
    pr_url?: string;
    issue_number?: number;
  };
  cost_metrics?: {
    model?: string;
    prompt_tokens?: number;
    completion_tokens?: number;
    duration_ms?: number;
    estimated_cost_usd?: number;
  };
  created_at?: string;
}

export interface ProjectLedgerStats {
  total_changes: number;
  verified_changes: number;
  open_tickets: number;
}

export interface TicketAcceptanceCriteria {
  id: string;
  ticket_id?: string;
  description: string;
  criterion_type: 'automated_test' | 'manual_review' | 'repro_check';
  verification_command?: string | null;
  is_satisfied: boolean;
  evidence_event_id?: string | null;
}

export interface Ticket {
  id: string;
  project_id: string;
  title: string;
  description?: string;
  status: 'todo' | 'in_progress' | 'in_verification' | 'in_review' | 'done' | 'blocked';
  priority: 'low' | 'medium' | 'high' | 'critical';
  assignee_type: 'human' | 'agent' | 'unassigned';
  assignee_id?: string | null;
  reviewer_id?: string | null;
  active_branch?: string | null;
  active_worktree?: string | null;
  github_issue_number?: number | null;
  github_issue_url?: string | null;
  criteria?: TicketAcceptanceCriteria[];
  created_at?: string;
  updated_at?: string;
}
