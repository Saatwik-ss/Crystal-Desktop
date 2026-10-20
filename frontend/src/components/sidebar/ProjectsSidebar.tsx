import { useState, useEffect } from 'react';
import { useAppStore } from '../../store';
import {
  Folder,
  FolderOpen,
  Plus,
  Trash2,
  ChevronRight,
  ChevronDown,
  FolderPlus,
} from 'lucide-react';
import clsx from 'clsx';
import type { Project } from '../../types';

export function formatRelativeTime(dateString?: string): string {
  if (!dateString) return '';
  const now = new Date();
  const past = new Date(dateString);
  const diffMs = now.getTime() - past.getTime();
  if (isNaN(diffMs) || diffMs < 0) return 'now';

  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHours = Math.floor(diffMin / 60);
  const diffDays = Math.floor(diffHours / 24);
  const diffMonths = Math.floor(diffDays / 30);
  const diffYears = Math.floor(diffDays / 365);

  if (diffMin < 1) return 'now';
  if (diffMin < 60) return `${diffMin}m`;
  if (diffHours < 24) return `${diffHours}h`;
  if (diffDays < 30) return `${diffDays}d`;
  if (diffMonths < 12) return `${diffMonths}mo`;
  return `${diffYears}y`;
}

interface ProjectsSidebarProps {
  onOpenFolder?: () => void;
}

export default function ProjectsSidebar({ onOpenFolder }: ProjectsSidebarProps) {
  const {
    projects,
    currentRepository,
    setCurrentRepository,
    projectSessions,
    loadProjects,
    loadProjectSessions,
    activeSessionId,
    selectSession,
    createSession,
    deleteSession,
    deleteProject,
  } = useAppStore();

  const [expandedProjects, setExpandedProjects] = useState<Set<string>>(new Set());

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  // Auto-expand current project and load its sessions
  useEffect(() => {
    if (currentRepository?.id) {
      setExpandedProjects((prev) => new Set(prev).add(currentRepository.id));
      loadProjectSessions(currentRepository.id);
    }
  }, [currentRepository?.id, loadProjectSessions]);

  const toggleProjectExpand = async (projectId: string, e?: React.MouseEvent) => {
    e?.stopPropagation();
    const next = new Set(expandedProjects);
    if (next.has(projectId)) {
      next.delete(projectId);
    } else {
      next.add(projectId);
      if (!projectSessions[projectId]) {
        await loadProjectSessions(projectId);
      }
    }
    setExpandedProjects(next);
  };

  const handleSelectProject = async (project: Project) => {
    if (currentRepository?.id === project.id) return;
    setCurrentRepository({
      id: project.id,
      name: project.name,
      path: project.path,
      created_at: project.created_at,
    });
    setExpandedProjects((prev) => new Set(prev).add(project.id));
    const sessions = await loadProjectSessions(project.id);
    if (sessions.length > 0) {
      await selectSession(sessions[0].id, project.id);
    } else {
      await createSession(project.id, 'New Chat');
    }
  };

  const handleCreateNewChat = async (projectId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    const proj = projects.find((p) => p.id === projectId);
    if (proj && currentRepository?.id !== projectId) {
      setCurrentRepository({
        id: proj.id,
        name: proj.name,
        path: proj.path,
        created_at: proj.created_at,
      });
    }
    setExpandedProjects((prev) => new Set(prev).add(projectId));
    await createSession(projectId, 'New Chat');
  };

  const handleDeleteProject = async (projectId: string, projectName: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (window.confirm(`Delete indexed data and remove project "${projectName}" from application history?`)) {
      try {
        await deleteProject(projectId);
      } catch (err) {
        alert('Failed to delete project. Please check backend logs.');
      }
    }
  };

  const handleDeleteSession = async (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (window.confirm('Delete this chat session?')) {
      await deleteSession(sessionId);
    }
  };

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-gray-900 select-none text-gray-200">
      {/* Top Action Bar */}
      <div className="p-3 border-b border-gray-800 flex items-center justify-between">
        <span className="text-xs font-semibold uppercase tracking-wider text-gray-400">
          Projects & Chats
        </span>
        <button
          onClick={onOpenFolder}
          className="flex items-center gap-1.5 px-2 py-1 text-xs bg-gray-800 hover:bg-gray-700 text-gray-200 rounded border border-gray-700 transition-colors"
          title="Open local folder or repository"
        >
          <FolderPlus size={14} className="text-indigo-400" />
          <span>Open Folder</span>
        </button>
      </div>

      {/* Projects Tree List */}
      <div className="flex-1 overflow-y-auto px-2 py-2 space-y-1">
        {projects.length === 0 ? (
          <div className="p-4 text-center text-xs text-gray-500">
            <p>No projects open yet.</p>
            <p className="mt-1">Click "Open Folder" to open a local repository.</p>
          </div>
        ) : (
          projects.map((proj) => {
            const isExpanded = expandedProjects.has(proj.id);
            const isCurrent = currentRepository?.id === proj.id;
            const sessions = projectSessions[proj.id] || [];

            return (
              <div key={proj.id} className="group/proj">
                {/* Project Header Row */}
                <div
                  onClick={() => handleSelectProject(proj)}
                  className={clsx(
                    'flex items-center justify-between px-2 py-1.5 rounded text-xs cursor-pointer transition-colors',
                    isCurrent
                      ? 'text-white font-medium bg-gray-800/80'
                      : 'text-gray-300 hover:bg-gray-800/50 hover:text-white'
                  )}
                >
                  <div className="flex items-center gap-1.5 min-w-0">
                    <button
                      onClick={(e) => toggleProjectExpand(proj.id, e)}
                      className="text-gray-400 hover:text-gray-200 p-0.5 rounded"
                    >
                      {isExpanded ? (
                        <ChevronDown size={14} className="text-gray-400" />
                      ) : (
                        <ChevronRight size={14} className="text-gray-400" />
                      )}
                    </button>
                    {isExpanded ? (
                      <FolderOpen size={16} className="text-indigo-400 shrink-0" />
                    ) : (
                      <Folder size={16} className="text-indigo-300 shrink-0" />
                    )}
                    <span className="truncate" title={proj.path || proj.name}>
                      {proj.name}
                    </span>
                  </div>

                  {/* Actions on hover */}
                  <div className="flex items-center gap-0.5 opacity-0 group-hover/proj:opacity-100 transition-opacity">
                    <button
                      onClick={(e) => handleCreateNewChat(proj.id, e)}
                      className="p-1 text-gray-400 hover:text-white hover:bg-gray-700 rounded transition-colors"
                      title="New Chat in this project"
                    >
                      <Plus size={14} />
                    </button>
                    <button
                      onClick={(e) => handleDeleteProject(proj.id, proj.name, e)}
                      className="p-1 text-gray-400 hover:text-red-400 hover:bg-gray-700 rounded transition-colors"
                      title="Delete indexed data and remove project from history"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                </div>

                {/* Sub-Sessions List (Indented) */}
                {isExpanded && (
                  <div className="pl-6 pr-1 py-0.5 space-y-0.5">
                    {sessions.length === 0 ? (
                      <div
                        onClick={(e) => handleCreateNewChat(proj.id, e)}
                        className="px-2 py-1 text-[11px] text-gray-500 hover:text-gray-300 cursor-pointer italic"
                      >
                        + Start first chat...
                      </div>
                    ) : (
                      sessions.map((sess) => {
                        const isActiveChat = activeSessionId === sess.id;
                        const relTime = formatRelativeTime(sess.updated_at || sess.created_at);

                        return (
                          <div
                            key={sess.id}
                            onClick={() => {
                              if (currentRepository?.id !== proj.id) {
                                setCurrentRepository({
                                  id: proj.id,
                                  name: proj.name,
                                  path: proj.path,
                                  created_at: proj.created_at,
                                });
                              }
                              selectSession(sess.id, proj.id);
                            }}
                            className={clsx(
                              'group/chat flex items-center justify-between px-2.5 py-1.5 rounded text-xs cursor-pointer transition-colors',
                              isActiveChat
                                ? 'bg-gray-700/80 text-white font-medium shadow-sm'
                                : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
                            )}
                          >
                            <span
                              className="truncate pr-2"
                              title={sess.title || 'Chat'}
                            >
                              {sess.title || 'New Chat'}
                            </span>

                            <div className="flex items-center gap-1.5 shrink-0">
                              {/* Relative Time Badge */}
                              {relTime && (
                                <span className="text-[10px] text-gray-500 group-hover/chat:hidden">
                                  {relTime}
                                </span>
                              )}
                              {/* Delete Chat Button on hover */}
                              <button
                                onClick={(e) => handleDeleteSession(sess.id, e)}
                                className="hidden group-hover/chat:block p-0.5 text-gray-400 hover:text-red-400 rounded transition-colors"
                                title="Delete chat"
                              >
                                <Trash2 size={12} />
                              </button>
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
