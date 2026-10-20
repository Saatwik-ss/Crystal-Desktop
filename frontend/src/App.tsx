import { useState, useEffect } from 'react';
import { useAppStore } from './store';
import { apiClient, LOCAL_SESSION_ID } from './api/client';
import { useRepositoryIndexing } from './hooks/useRepositoryIndexing';
import Upload from './components/Upload';
import Editor from './components/Editor';
import Explorer from './components/Explorer';
import ChatSidebar from './components/ChatSidebar';
import IndexingStatus from './components/IndexingStatus';
import NewFileDialog from './components/NewFileDialog';
import { Menu, FolderPlus, FilePlus, Settings, MessageSquare, FolderTree } from 'lucide-react';
import clsx from 'clsx';
import ProjectsSidebar from './components/sidebar/ProjectsSidebar';
import ActivityLedgerView from './components/sidebar/ActivityLedgerView';
import TicketBoardView from './components/sidebar/TicketBoardView';
import WorktreeSelector from './components/worktree/WorktreeSelector';
import { Activity, ListTodo } from 'lucide-react';
import SettingsDialog from './components/SettingsDialog';
import BottomDock from './components/dock/BottomDock';
import ApprovalModal from './components/safety/ApprovalModal';

export default function App() {
  const currentRepository = useAppStore((s) => s.currentRepository);
  const handleChatWsMessage = useAppStore((s) => s.handleChatWsMessage);
  const sidebarOpen = useAppStore((s) => s.sidebarOpen);
  const toggleSidebar = useAppStore((s) => s.toggleSidebar);
  const settingsOpen = useAppStore((s) => s.settingsOpen);
  const setSettingsOpen = useAppStore((s) => s.setSettingsOpen);
  const pendingApproval = useAppStore((s) => s.pendingApproval);
  const setPendingApproval = useAppStore((s) => s.setPendingApproval);
  const [dockOpen, setDockOpen] = useState(true);
  const [showUpload, setShowUpload] = useState(false);
  const [showNewFile, setShowNewFile] = useState(false);
  const [activeLeftTab, setActiveLeftTab] = useState<'projects' | 'tickets' | 'ledger' | 'files'>('projects');
  const loadProjects = useAppStore((s) => s.loadProjects);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  
  const [leftWidth, setLeftWidth] = useState(256);
  const [rightWidth, setRightWidth] = useState(384);
  const [isDraggingLeft, setIsDraggingLeft] = useState(false);
  const [isDraggingRight, setIsDraggingRight] = useState(false);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (isDraggingLeft) {
        setLeftWidth(Math.max(150, Math.min(e.clientX, 600)));
      }
      if (isDraggingRight) {
        setRightWidth(Math.max(250, Math.min(window.innerWidth - e.clientX, 800)));
      }
    };
    const handleMouseUp = () => { document.body.style.userSelect = '';
      setIsDraggingLeft(false);
      setIsDraggingRight(false);
    };

    if (isDraggingLeft || isDraggingRight) { document.body.style.userSelect = 'none';
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
    }
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDraggingLeft, isDraggingRight]);

  useRepositoryIndexing();

  useEffect(() => {
    if (currentRepository) {
      setShowUpload(false);
    }
  }, [currentRepository]);

  // Always keep chat + completion sockets open (local session if no repo)
  useEffect(() => {
    const sessionId = currentRepository?.id || LOCAL_SESSION_ID;

    apiClient.connectChat(
      sessionId,
      handleChatWsMessage,
      (error: any) => {
        console.error('Chat error:', error);
      }
    );

    apiClient.connectCompletion(
      sessionId,
      () => undefined,
      (error: any) => {
        console.error('Completion error:', error);
      }
    );

    return () => {
      apiClient.closeConnections();
    };
  }, [currentRepository, handleChatWsMessage]);

  return (
    <div className="flex h-screen bg-gray-900 text-gray-100">
      {/* Left Sidebar (Projects & Explorer) */}
      <div className="bg-gray-800 border-r border-gray-700 flex flex-col overflow-hidden relative shrink-0" style={{ width: leftWidth }}>
        {/* Tab Switcher */}
        <div className="flex items-center border-b border-gray-700 bg-gray-900/60 text-xs shrink-0">
          <button
            onClick={() => setActiveLeftTab('projects')}
            className={clsx(
              'flex-1 py-2 px-1.5 flex items-center justify-center gap-1 font-medium transition-colors border-b-2 text-[11px]',
              activeLeftTab === 'projects'
                ? 'border-indigo-500 text-white bg-gray-800/80'
                : 'border-transparent text-gray-400 hover:text-gray-200 hover:bg-gray-800/40'
            )}
            title="Projects & Chats"
          >
            <MessageSquare size={12} className={activeLeftTab === 'projects' ? 'text-indigo-400' : ''} />
            <span>Chats</span>
          </button>
          <button
            onClick={() => setActiveLeftTab('tickets')}
            className={clsx(
              'flex-1 py-2 px-1.5 flex items-center justify-center gap-1 font-medium transition-colors border-b-2 text-[11px]',
              activeLeftTab === 'tickets'
                ? 'border-indigo-500 text-white bg-gray-800/80'
                : 'border-transparent text-gray-400 hover:text-gray-200 hover:bg-gray-800/40'
            )}
            title="Tickets & Tasks"
          >
            <ListTodo size={12} className={activeLeftTab === 'tickets' ? 'text-indigo-400' : ''} />
            <span>Tasks</span>
          </button>
          <button
            onClick={() => setActiveLeftTab('ledger')}
            className={clsx(
              'flex-1 py-2 px-1.5 flex items-center justify-center gap-1 font-medium transition-colors border-b-2 text-[11px]',
              activeLeftTab === 'ledger'
                ? 'border-emerald-500 text-white bg-gray-800/80'
                : 'border-transparent text-gray-400 hover:text-gray-200 hover:bg-gray-800/40'
            )}
            title="Engineering Change Ledger"
          >
            <Activity size={12} className={activeLeftTab === 'ledger' ? 'text-emerald-400' : ''} />
            <span>Ledger</span>
          </button>
          <button
            onClick={() => setActiveLeftTab('files')}
            className={clsx(
              'flex-1 py-2 px-1.5 flex items-center justify-center gap-1 font-medium transition-colors border-b-2 text-[11px]',
              activeLeftTab === 'files'
                ? 'border-blue-500 text-white bg-gray-800/80'
                : 'border-transparent text-gray-400 hover:text-gray-200 hover:bg-gray-800/40'
            )}
            title="File Explorer"
          >
            <FolderTree size={12} className={activeLeftTab === 'files' ? 'text-blue-400' : ''} />
            <span>Files</span>
          </button>
        </div>

        {/* Tab Content */}
        {activeLeftTab === 'projects' && (
          <ProjectsSidebar onOpenFolder={() => setShowUpload(true)} />
        )}
        {activeLeftTab === 'tickets' && (
          <TicketBoardView />
        )}
        {activeLeftTab === 'ledger' && (
          <ActivityLedgerView />
        )}
        {activeLeftTab === 'files' && (
          <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
            <div className="p-3 border-b border-gray-700/80 flex items-center justify-between shrink-0">
              <h2 className="font-semibold text-xs uppercase tracking-wider text-gray-400">Files</h2>
              <div className="flex gap-1">
                <button
                  onClick={() => setShowNewFile(true)}
                  className="p-1 text-gray-300 hover:bg-gray-700 rounded"
                  title="New file"
                >
                  <FilePlus size={15} />
                </button>
                <button
                  onClick={() => setShowUpload(true)}
                  className="p-1 text-gray-300 hover:bg-gray-700 rounded"
                  title="Add repository files or folders"
                >
                  <FolderPlus size={15} />
                </button>
              </div>
            </div>
            <Explorer />
          </div>
        )}

        <div
          className="absolute right-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-blue-500 z-10"
          onMouseDown={() => setIsDraggingLeft(true)}
        />
      </div>

      {/* Editor Area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="bg-gray-800 border-b border-gray-700 px-4 py-2 flex items-center justify-between text-xs">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1.5">
              <span className="text-gray-400">Workspace:</span>
              <span className="font-mono font-medium text-white">
                {currentRepository?.name || 'Local (no repository)'}
              </span>
            </div>
            {currentRepository && <WorktreeSelector />}
          </div>
          <div className="flex items-center gap-2">
            <IndexingStatus />
            <button
              onClick={() => setSettingsOpen(true)}
              className="p-1 text-gray-300 hover:bg-gray-700 rounded"
              title="API key and system prompt"
            >
              <Settings size={16} />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-hidden">
          <Editor onRequestNewFile={() => setShowNewFile(true)} />
        </div>
        <BottomDock isOpen={dockOpen} onToggle={() => setDockOpen(!dockOpen)} />
      </div>

      {sidebarOpen && (
        <div className="bg-gray-800 border-l border-gray-700 flex flex-col overflow-hidden relative shrink-0" style={{ width: rightWidth }}>
          <div
            className="absolute left-0 top-0 bottom-0 w-1 cursor-col-resize hover:bg-blue-500 z-10"
            onMouseDown={() => setIsDraggingRight(true)}
          />
          <ChatSidebar />
        </div>
      )}

      {!sidebarOpen && (
        <button
          onClick={toggleSidebar}
          className="fixed bottom-6 right-6 p-2 bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors"
          title="Open AI Chat"
        >
          <Menu size={20} />
        </button>
      )}

      {showUpload && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-gray-800 rounded-lg p-6 max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold">Add repository context</h2>
              <button
                onClick={() => setShowUpload(false)}
                className="text-gray-400 hover:text-white text-sm"
              >
                Close
              </button>
            </div>
            <Upload
              compact
              onUploadComplete={() => {
                setShowUpload(false);
              }}
            />
          </div>
        </div>
      )}

      {showNewFile && <NewFileDialog onClose={() => setShowNewFile(false)} />}
      {settingsOpen && <SettingsDialog onClose={() => setSettingsOpen(false)} />}
      {pendingApproval && (
        <ApprovalModal
          approval={pendingApproval}
          onResolved={() => setPendingApproval(null)}
        />
      )}
    </div>
  );
}
