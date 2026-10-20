import { useState, useEffect } from 'react';
import { Terminal as TerminalIcon, Globe, Cpu, ChevronDown, ChevronUp, Maximize2, Minimize2 } from 'lucide-react';
import TerminalView from './TerminalView';
import BrowserView from './BrowserView';
import ProcessMonitor from './ProcessMonitor';

interface BottomDockProps {
  isOpen: boolean;
  onToggle: () => void;
}

export default function BottomDock({ isOpen, onToggle }: BottomDockProps) {
  const [activeTab, setActiveTab] = useState<'terminal' | 'browser' | 'processes'>('terminal');
  const [height, setHeight] = useState<number>(280);
  const [isMaximized, setIsMaximized] = useState<boolean>(false);
  const [isDragging, setIsDragging] = useState<boolean>(false);

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isDragging) return;
      const newHeight = window.innerHeight - e.clientY;
      setHeight(Math.max(140, Math.min(newHeight, window.innerHeight - 150)));
    };

    const handleMouseUp = () => {
      setIsDragging(false);
      document.body.style.userSelect = '';
    };

    if (isDragging) {
      document.body.style.userSelect = 'none';
      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
    }

    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging]);

  if (!isOpen) {
    return (
      <div className="bg-[#11111b] border-t border-gray-800 px-3 py-1 flex items-center justify-between text-xs text-gray-400">
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              setActiveTab('terminal');
              onToggle();
            }}
            className="flex items-center gap-1.5 px-2 py-0.5 hover:text-gray-100 hover:bg-[#1e1e2e] rounded"
          >
            <TerminalIcon size={13} className="text-blue-400" />
            <span>Terminal</span>
          </button>
          <button
            onClick={() => {
              setActiveTab('browser');
              onToggle();
            }}
            className="flex items-center gap-1.5 px-2 py-0.5 hover:text-gray-100 hover:bg-[#1e1e2e] rounded"
          >
            <Globe size={13} className="text-green-400" />
            <span>Browser</span>
          </button>
          <button
            onClick={() => {
              setActiveTab('processes');
              onToggle();
            }}
            className="flex items-center gap-1.5 px-2 py-0.5 hover:text-gray-100 hover:bg-[#1e1e2e] rounded"
          >
            <Cpu size={13} className="text-purple-400" />
            <span>Processes</span>
          </button>
        </div>
        <button
          onClick={onToggle}
          className="p-1 text-gray-400 hover:text-gray-100 hover:bg-[#1e1e2e] rounded"
          title="Open dock panel"
        >
          <ChevronUp size={14} />
        </button>
      </div>
    );
  }

  const effectiveHeight = isMaximized ? window.innerHeight - 80 : height;

  return (
    <div
      className="bg-[#181825] border-t border-gray-800 flex flex-col relative z-20 shrink-0 shadow-2xl"
      style={{ height: effectiveHeight }}
    >
      {/* Top resize handle */}
      {!isMaximized && (
        <div
          className="absolute top-0 left-0 right-0 h-1.5 cursor-row-resize hover:bg-blue-500 transition-colors z-30"
          onMouseDown={() => setIsDragging(true)}
        />
      )}

      {/* Dock Header Tabs */}
      <div className="flex items-center justify-between border-b border-gray-800 bg-[#11111b] px-3 py-1 text-xs select-none">
        <div className="flex items-center gap-1">
          <button
            onClick={() => setActiveTab('terminal')}
            className={`flex items-center gap-1.5 px-3 py-1 rounded font-medium transition-colors ${
              activeTab === 'terminal'
                ? 'bg-[#181825] text-blue-400 border-b-2 border-blue-500'
                : 'text-gray-400 hover:text-gray-200 hover:bg-[#1e1e2e]'
            }`}
          >
            <TerminalIcon size={13} />
            <span>Terminal</span>
          </button>
          <button
            onClick={() => setActiveTab('browser')}
            className={`flex items-center gap-1.5 px-3 py-1 rounded font-medium transition-colors ${
              activeTab === 'browser'
                ? 'bg-[#181825] text-green-400 border-b-2 border-green-500'
                : 'text-gray-400 hover:text-gray-200 hover:bg-[#1e1e2e]'
            }`}
          >
            <Globe size={13} />
            <span>Browser View</span>
          </button>
          <button
            onClick={() => setActiveTab('processes')}
            className={`flex items-center gap-1.5 px-3 py-1 rounded font-medium transition-colors ${
              activeTab === 'processes'
                ? 'bg-[#181825] text-purple-400 border-b-2 border-purple-500'
                : 'text-gray-400 hover:text-gray-200 hover:bg-[#1e1e2e]'
            }`}
          >
            <Cpu size={13} />
            <span>Processes</span>
          </button>
        </div>

        <div className="flex items-center gap-1 text-gray-400">
          <button
            onClick={() => setIsMaximized(!isMaximized)}
            className="p-1 hover:text-gray-100 hover:bg-[#1e1e2e] rounded"
            title={isMaximized ? 'Restore' : 'Maximize'}
          >
            {isMaximized ? <Minimize2 size={13} /> : <Maximize2 size={13} />}
          </button>
          <button
            onClick={onToggle}
            className="p-1 hover:text-gray-100 hover:bg-[#1e1e2e] rounded"
            title="Minimize dock"
          >
            <ChevronDown size={14} />
          </button>
        </div>
      </div>

      {/* Dock Content Body */}
      <div className="flex-1 overflow-hidden">
        {activeTab === 'terminal' && <TerminalView />}
        {activeTab === 'browser' && <BrowserView />}
        {activeTab === 'processes' && <ProcessMonitor />}
      </div>
    </div>
  );
}
