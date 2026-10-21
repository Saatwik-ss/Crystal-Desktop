import { useState, useRef, useEffect } from 'react';
import { useAppStore } from '../store';
import { apiClient, LOCAL_SESSION_ID } from '../api/client';
import EditProposalCard from './EditProposalCard';
import AgentProgressPanel from './AgentProgressPanel';
import { Send, Trash2, X, Settings, ListTodo, Plus, Brain, ChevronDown, ChevronUp, GitCompare, Square } from 'lucide-react';

function ThoughtCard({ thought }: { thought: string }) {
  const [open, setOpen] = useState(false);
  if (!thought || !thought.trim()) return null;

  return (
    <div className="mb-2 border border-purple-500/30 rounded-md bg-purple-950/20 overflow-hidden text-xs shadow-sm">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-2.5 py-1.5 text-purple-200 hover:text-white hover:bg-purple-900/30 transition-colors cursor-pointer"
      >
        <span className="flex items-center gap-1.5 font-medium text-[11px] text-purple-300">
          <Brain size={13} className="text-purple-400 shrink-0" />
          Thinking & Rationale
        </span>
        <span className="text-[10px] text-purple-400/80 flex items-center gap-1 font-sans">
          {open ? 'Hide' : 'Show details'}
          {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
        </span>
      </button>
      {open && (
        <div className="px-2.5 py-2 border-t border-purple-500/20 text-gray-200 text-[11px] leading-relaxed whitespace-pre-wrap max-h-56 overflow-y-auto bg-gray-900/80 font-mono">
          {thought}
        </div>
      )}
    </div>
  );
}
import { CHAT_MODEL_OPTIONS } from '../utils/llmSettings';
import clsx from 'clsx';

export default function ChatSidebar() {
  const {
    currentRepository,
    chatMessages,
    streamingContent,
    streamingThought,
    isStreaming,
    statusLine,
    openDiffTab,
    pendingEdits,
    addChatMessage,
    clearChatMessages,
    startChatStream,
    toggleSidebar,
    activeFile,
    selectedCode,
    openFiles,
    enablePlanning,
    setEnablePlanning,
    activeSessionTitle,
    llmSettings,
    updateModel,
    createSession,
  } = useAppStore();

  const [input, setInput] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [chatMessages, streamingContent, pendingEdits, statusLine]);

  const handleStopStreaming = () => {
    const currentContent = useAppStore.getState().streamingContent;
    const currentThought = useAppStore.getState().streamingThought;
    if (currentContent || currentThought) {
      addChatMessage({
        role: 'assistant',
        content: currentContent || '(Response stopped)',
        thought: currentThought || undefined,
        type: 'message',
        timestamp: new Date().toISOString(),
      });
    }
    useAppStore.setState({
      isStreaming: false,
      streamingContent: '',
      streamingThought: '',
      statusLine: null,
    });
  };

  const handleSendMessage = async () => {
    if (!input.trim()) return;

    if (isStreaming) {
      handleStopStreaming();
    }

    const userMessage = input.trim();
    setInput('');

    addChatMessage({
      role: 'user',
      content: userMessage,
      type: 'message',
      timestamp: new Date().toISOString(),
    });

    startChatStream();

    const activeContent = activeFile ? openFiles.get(activeFile)?.content : undefined;
    // Prefer full open file for edit proposals; cap size to stay under Groq TPM limits
    const CODE_CONTEXT_CAP = 5000;
    const codeContext =
      selectedCode ||
      (activeContent
        ? activeContent.length > CODE_CONTEXT_CAP
          ? activeContent.slice(0, CODE_CONTEXT_CAP)
          : activeContent
        : undefined);

    try {
      await apiClient.sendChatMessage(
        currentRepository?.id || LOCAL_SESSION_ID,
        userMessage,
        activeFile || undefined,
        codeContext,
        useAppStore.getState().llmSettings,
        useAppStore.getState().enablePlanning,
        useAppStore.getState().activeSessionId,
        useAppStore.getState().activeWorktree?.path,
        useAppStore.getState().activeTicketId
      );
    } catch (error) {
      console.error('Failed to send message:', error);
      addChatMessage({
        role: 'assistant',
        content: 'Failed to send message. Please try again.',
        type: 'error',
        timestamp: new Date().toISOString(),
      });
      useAppStore.setState({ isStreaming: false, streamingContent: '' });
    }
  };

  return (
    <div className="h-full flex flex-col min-h-0 overflow-hidden bg-gray-800">
      <div className="p-3 border-b border-gray-700 flex flex-col gap-2 bg-gray-800 shrink-0">
        <div className="flex items-center justify-between">
          <div className="min-w-0 flex-1 mr-2">
            <h3 className="font-semibold text-white text-sm truncate" title={activeSessionTitle || 'AI Assistant'}>
              {activeSessionTitle || 'AI Assistant'}
            </h3>
            <p className="text-[11px] text-gray-400 truncate">
              {currentRepository ? currentRepository.name : 'Local Workspace'}
            </p>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            <button
              onClick={() => createSession(currentRepository?.id, 'New Chat')}
              className="p-1 text-gray-400 hover:text-white hover:bg-gray-700 rounded transition-colors"
              title="New Chat"
            >
              <Plus size={16} />
            </button>
            <button
              onClick={() => useAppStore.getState().setSettingsOpen(true)}
              className="p-1 text-gray-400 hover:text-gray-200 transition-colors rounded hover:bg-gray-700"
              title="API key and settings"
            >
              <Settings size={16} />
            </button>
            <button
              onClick={clearChatMessages}
              className="p-1 text-gray-400 hover:text-gray-200 transition-colors rounded hover:bg-gray-700"
              title="Clear current chat messages"
            >
              <Trash2 size={16} />
            </button>
            <button
              onClick={() => toggleSidebar()}
              className="p-1 text-gray-400 hover:text-gray-200 transition-colors rounded hover:bg-gray-700"
              title="Close sidebar"
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {/* Model Selector Bar */}
        <div className="flex items-center justify-between text-xs bg-gray-900/60 rounded px-2 py-1 border border-gray-700/60">
          <span className="text-gray-400 text-[11px]">Model:</span>
          <select
            value={llmSettings.model || 'llama-3.3-70b-versatile'}
            onChange={(e) => updateModel(e.target.value)}
            className="bg-transparent text-gray-200 text-xs font-mono focus:outline-none cursor-pointer max-w-[200px] truncate"
          >
            {llmSettings.model && !CHAT_MODEL_OPTIONS.includes(llmSettings.model as any) && (
              <option value={llmSettings.model} className="bg-gray-800 text-gray-200">
                {llmSettings.model} (Custom)
              </option>
            )}
            {CHAT_MODEL_OPTIONS.map((m) => (
              <option key={m} value={m} className="bg-gray-800 text-gray-200">
                {m}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-4">
        {chatMessages.length === 0 && !isStreaming && !pendingEdits && (
          <div className="h-full flex items-center justify-center">
            <div className="text-center text-gray-400">
              <p className="text-sm">Ask anything about code</p>
              <p className="text-xs mt-2 text-gray-500">
                Upload a folder for codebase-aware answers.
              </p>
            </div>
          </div>
        )}

        {chatMessages.map((message, idx) => (
          <div
            key={idx}
            className={clsx(
              'flex flex-col gap-1',
              message.role === 'user' ? 'items-end' : 'items-start'
            )}
          >
            <div
              className={clsx(
                'max-w-[90%] px-3.5 py-2.5 rounded-lg text-sm shadow-sm',
                message.role === 'user'
                  ? 'bg-blue-600 text-white'
                  : message.type === 'error'
                  ? 'bg-red-900 text-red-100'
                  : 'bg-gray-700 text-gray-100'
              )}
            >
              {message.thought && <ThoughtCard thought={message.thought} />}
              {message.content && (
                <p className="whitespace-pre-wrap break-words">{message.content}</p>
              )}

              {message.proposed_edits && message.proposed_edits.length > 0 && (
                <div className="mt-2.5 pt-2 border-t border-gray-600/60 space-y-1.5">
                  <div className="text-[11px] font-medium text-gray-300 flex items-center gap-1">
                    <GitCompare size={12} className="text-amber-400" />
                    Changes ({message.proposed_edits.length}):
                  </div>
                  {message.proposed_edits.map((edit, eIdx) => (
                    <button
                      key={eIdx}
                      type="button"
                      onClick={() => openDiffTab(edit.file_path, edit.original, edit.proposed)}
                      className="w-full flex items-center justify-between gap-2 px-2.5 py-1.5 rounded bg-gray-800/90 hover:bg-gray-800 border border-blue-500/40 text-blue-200 text-xs transition-colors group cursor-pointer text-left"
                      title="Click to view full inline diff in editor tab"
                    >
                      <div className="flex items-center gap-1.5 truncate">
                        <GitCompare size={13} className="text-amber-400 shrink-0" />
                        <span className="font-mono text-[11px] text-blue-200 truncate">{edit.file_path}</span>
                        {edit.is_new_file && <span className="text-[10px] text-emerald-400 font-sans shrink-0">(new)</span>}
                      </div>
                      <span className="shrink-0 text-[10px] text-blue-300 bg-blue-900/60 border border-blue-500/30 px-1.5 py-0.5 rounded font-sans group-hover:bg-blue-800 transition-colors">
                        View Diff →
                      </span>
                    </button>
                  ))}
                </div>
              )}

              {message.timestamp && (
                <p className="text-[10px] opacity-40 mt-1.5 text-right">
                  {new Date(message.timestamp).toLocaleTimeString()}
                </p>
              )}
            </div>
          </div>
        ))}

        {isStreaming && (streamingContent || streamingThought) && (
          <div className="flex flex-col gap-1 items-start">
            <div className="max-w-[90%] px-3.5 py-2.5 rounded-lg text-sm bg-gray-700 text-gray-100 shadow-sm">
              {streamingThought && <ThoughtCard thought={streamingThought} />}
              {streamingContent && (
                <p className="whitespace-pre-wrap break-words">{streamingContent}</p>
              )}
              <div className="flex gap-1 mt-2">
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" />
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-100" />
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce delay-200" />
              </div>
            </div>
          </div>
        )}

        {isStreaming && !streamingContent && statusLine && (
          <p className="text-xs text-gray-500 px-1">{statusLine}</p>
        )}

        <div ref={messagesEndRef} />
      </div>

      <AgentProgressPanel />

      <EditProposalCard />

      <div className="p-4 border-t border-gray-700 shrink-0 bg-gray-800 z-10">
        <div className="flex items-center gap-2 mb-2">
          <button
            type="button"
            onClick={() => setEnablePlanning(!enablePlanning)}
            className={clsx(
              'flex items-center gap-1.5 px-2.5 py-1 rounded text-xs border transition-colors',
              enablePlanning
                ? 'bg-blue-600/30 border-blue-500 text-blue-100'
                : 'bg-gray-700/80 border-gray-600 text-gray-400 hover:text-gray-200'
            )}
            title="Off: chat + direct file edits (no plan checklist). On: multi-step agent with plan."
          >
            <ListTodo size={14} />
            Plan
          </button>
          {enablePlanning ? (
            <span className="text-[11px] text-blue-300/80">Agent + plan</span>
          ) : (
            <span className="text-[11px] text-gray-500">Chat + edits</span>
          )}
        </div>
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSendMessage();
              }
            }}
            placeholder={isStreaming ? "Please Wait" : "Ask about your code..."}
            rows={1}
            className="flex-1 bg-gray-700 text-white placeholder-gray-500 px-3 py-2 rounded border border-gray-600 focus:border-blue-500 focus:outline-none resize-y min-h-[40px] max-h-[50vh]"
          />
          {isStreaming ? (
            <button
              type="button"
              onClick={handleStopStreaming}
              className="bg-red-600 hover:bg-red-700 text-white px-3.5 py-2 rounded transition-colors flex items-center gap-1.5 shrink-0 text-xs font-medium"
              title="Stop AI response"
            >
              <Square size={13} className="fill-current" />
              <span>Stop</span>
            </button>
          ) : (
            <button
              type="button"
              onClick={handleSendMessage}
              disabled={!input.trim()}
              className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white px-4 py-2 rounded transition-colors flex items-center gap-2 shrink-0"
              title="Send message (Enter)"
            >
              <Send size={16} />
            </button>
          )}
        </div>

        {activeFile && (
          <p className="text-xs text-gray-400 mt-2">
            Current file: {activeFile.split('/').pop()}
          </p>
        )}

        {selectedCode && (
          <p className="text-xs text-gray-400 mt-1">
            Code selected: {selectedCode.split('\n').length} lines
          </p>
        )}
      </div>
    </div>
  );
}
