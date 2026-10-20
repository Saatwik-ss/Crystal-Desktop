import React, { useEffect, useRef, useState } from 'react';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import { WebLinksAddon } from '@xterm/addon-web-links';
import '@xterm/xterm/css/xterm.css';
import { Plus, X, RefreshCw, Trash2 } from 'lucide-react';

interface TerminalTab {
  id: string;
  title: string;
}

export default function TerminalView() {
  const [tabs, setTabs] = useState<TerminalTab[]>([
    { id: 'default', title: 'Terminal 1' },
  ]);
  const [activeTabId, setActiveTabId] = useState<string>('default');
  const terminalRef = useRef<HTMLDivElement>(null);
  const xtermInstance = useRef<Terminal | null>(null);
  const fitAddonRef = useRef<FitAddon | null>(null);
  const socketRef = useRef<WebSocket | null>(null);

  const createTab = () => {
    const newId = `term-${Date.now().toString(36)}`;
    const newTab = { id: newId, title: `Terminal ${tabs.length + 1}` };
    setTabs([...tabs, newTab]);
    setActiveTabId(newId);
  };

  const closeTab = (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (tabs.length === 1) return;
    const remaining = tabs.filter((t) => t.id !== id);
    setTabs(remaining);
    if (activeTabId === id) {
      setActiveTabId(remaining[0].id);
    }
  };

  useEffect(() => {
    if (!terminalRef.current) return;

    // Dispose previous instance
    if (xtermInstance.current) {
      xtermInstance.current.dispose();
      xtermInstance.current = null;
    }
    if (socketRef.current) {
      socketRef.current.close();
      socketRef.current = null;
    }

    const term = new Terminal({
      cursorBlink: true,
      fontSize: 13,
      fontFamily: 'Consolas, "Fira Code", monospace',
      theme: {
        background: '#181825',
        foreground: '#cdd6f4',
        cursor: '#f5e0dc',
        selectionBackground: '#585b7066',
        black: '#45475a',
        red: '#f38ba8',
        green: '#a6e3a1',
        yellow: '#f9e2af',
        blue: '#89b4fa',
        magenta: '#f5c2e7',
        cyan: '#94e2d5',
        white: '#bac2de',
      },
      scrollback: 5000,
    });

    const fitAddon = new FitAddon();
    term.loadAddon(fitAddon);
    term.loadAddon(new WebLinksAddon());

    term.open(terminalRef.current);
    fitAddon.fit();

    xtermInstance.current = term;
    fitAddonRef.current = fitAddon;

    // WebSocket connection
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.hostname || 'localhost';
    const port = window.location.port === '5173' ? '8000' : window.location.port || '8000';
    const wsUrl = `${proto}//${host}:${port}/ws/terminal/${activeTabId}`;

    const ws = new WebSocket(wsUrl);
    socketRef.current = ws;

    ws.onopen = () => {
      term.write('\x1b[32m[Connected to Crystal Terminal Daemon]\x1b[0m\r\n');
      ws.send(JSON.stringify({ type: 'resize', rows: term.rows, cols: term.cols }));
    };

    ws.onmessage = (event) => {
      term.write(event.data);
    };

    ws.onclose = () => {
      term.write('\r\n\x1b[33m[Terminal disconnected]\x1b[0m\r\n');
    };

    term.onData((data) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'input', data }));
      }
    });

    const handleResize = () => {
      try {
        fitAddon.fit();
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'resize', rows: term.rows, cols: term.cols }));
        }
      } catch (err) {
        // ignore
      }
    };

    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      ws.close();
      term.dispose();
    };
  }, [activeTabId]);

  return (
    <div className="flex flex-col h-full bg-[#181825] text-gray-200">
      {/* Tab bar */}
      <div className="flex items-center justify-between border-b border-gray-800 bg-[#11111b] px-2 py-1 text-xs select-none">
        <div className="flex items-center gap-1 overflow-x-auto">
          {tabs.map((tab) => (
            <div
              key={tab.id}
              onClick={() => setActiveTabId(tab.id)}
              className={`flex items-center gap-2 px-3 py-1 rounded cursor-pointer transition-colors ${
                activeTabId === tab.id
                  ? 'bg-[#181825] text-blue-400 border-t-2 border-blue-500'
                  : 'text-gray-400 hover:bg-[#1e1e2e] hover:text-gray-200'
              }`}
            >
              <span>{tab.title}</span>
              {tabs.length > 1 && (
                <button
                  onClick={(e) => closeTab(tab.id, e)}
                  className="hover:text-red-400 rounded p-0.5"
                >
                  <X size={12} />
                </button>
              )}
            </div>
          ))}
          <button
            onClick={createTab}
            className="p-1 text-gray-400 hover:text-gray-100 hover:bg-[#1e1e2e] rounded"
            title="New Terminal"
          >
            <Plus size={14} />
          </button>
        </div>

        <div className="flex items-center gap-2 text-gray-400">
          <button
            onClick={() => xtermInstance.current?.clear()}
            className="p-1 hover:text-gray-100 hover:bg-[#1e1e2e] rounded"
            title="Clear terminal"
          >
            <Trash2 size={13} />
          </button>
          <button
            onClick={() => fitAddonRef.current?.fit()}
            className="p-1 hover:text-gray-100 hover:bg-[#1e1e2e] rounded"
            title="Refit layout"
          >
            <RefreshCw size={13} />
          </button>
        </div>
      </div>

      {/* Terminal Viewport */}
      <div className="flex-1 p-2 overflow-hidden" ref={terminalRef} />
    </div>
  );
}
