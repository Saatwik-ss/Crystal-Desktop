import { useState, useEffect } from 'react';
import axios from 'axios';
import { Cpu, Square, FileText, RefreshCw } from 'lucide-react';

interface ProcessItem {
  task_id: string;
  name: string;
  command: string;
  cwd: string;
  created_at: string;
  is_alive: boolean;
  returncode: number | null;
}

export default function ProcessMonitor() {
  const [processes, setProcesses] = useState<ProcessItem[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [logs, setLogs] = useState<string>('');
  const [loading, setLoading] = useState(false);

  const fetchProcesses = async () => {
    try {
      const res = await axios.get('/api/processes');
      setProcesses(res.data.processes || []);
    } catch (e) {
      // ignore
    }
  };

  const fetchLogs = async (taskId: string) => {
    setSelectedTaskId(taskId);
    setLoading(true);
    try {
      const res = await axios.get(`/api/processes/${taskId}/logs?tail=200`);
      setLogs(res.data.logs || 'No logs recorded.');
    } catch (e: any) {
      setLogs(`Error reading logs: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  const terminateProcess = async (taskId: string) => {
    if (!confirm('Are you sure you want to terminate this process?')) return;
    try {
      await axios.delete(`/api/processes/${taskId}`);
      fetchProcesses();
      if (selectedTaskId === taskId) {
        fetchLogs(taskId);
      }
    } catch (e: any) {
      alert(`Failed to terminate: ${e.message}`);
    }
  };

  useEffect(() => {
    fetchProcesses();
    const interval = setInterval(fetchProcesses, 4000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex flex-col h-full bg-[#181825] text-gray-200">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-800 bg-[#11111b] px-3 py-1.5 text-xs">
        <div className="flex items-center gap-2">
          <Cpu size={14} className="text-green-400" />
          <span className="font-semibold text-gray-200">Background Processes & Daemons</span>
          <span className="text-gray-500 font-mono">({processes.length})</span>
        </div>
        <button
          onClick={fetchProcesses}
          className="p-1 text-gray-400 hover:text-gray-200 hover:bg-[#1e1e2e] rounded"
          title="Refresh process list"
        >
          <RefreshCw size={13} />
        </button>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Left: Process List */}
        <div className="w-1/2 border-r border-gray-800 overflow-y-auto p-2 space-y-1 text-xs">
          {processes.length === 0 ? (
            <div className="text-center text-gray-500 py-8">
              <Cpu size={28} className="mx-auto text-gray-600 mb-2" />
              <p>No active background daemons running.</p>
              <p className="text-[11px] text-gray-600">
                Spanned dev servers, docker tasks, or watchers will appear here.
              </p>
            </div>
          ) : (
            processes.map((proc) => (
              <div
                key={proc.task_id}
                onClick={() => fetchLogs(proc.task_id)}
                className={`p-2.5 rounded border transition-colors cursor-pointer ${
                  selectedTaskId === proc.task_id
                    ? 'bg-[#1e1e2e] border-blue-500'
                    : 'bg-[#11111b] border-gray-800 hover:border-gray-700'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2 font-mono">
                    <span
                      className={`inline-block w-2 h-2 rounded-full ${
                        proc.is_alive ? 'bg-green-400 animate-pulse' : 'bg-gray-500'
                      }`}
                    />
                    <span className="font-semibold text-gray-100">{proc.name}</span>
                  </div>
                  <span
                    className={`px-1.5 py-0.5 rounded text-[10px] uppercase font-bold ${
                      proc.is_alive
                        ? 'bg-green-950 text-green-300 border border-green-800'
                        : 'bg-gray-800 text-gray-400'
                    }`}
                  >
                    {proc.is_alive ? 'Running' : `Exited (${proc.returncode ?? 0})`}
                  </span>
                </div>

                <p className="text-gray-400 font-mono text-[11px] truncate mb-2">
                  $ {proc.command}
                </p>

                <div className="flex items-center justify-between text-[11px] text-gray-500">
                  <span>ID: {proc.task_id}</span>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        fetchLogs(proc.task_id);
                      }}
                      className="flex items-center gap-1 text-blue-400 hover:text-blue-300"
                    >
                      <FileText size={11} /> Logs
                    </button>
                    {proc.is_alive && (
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          terminateProcess(proc.task_id);
                        }}
                        className="flex items-center gap-1 text-red-400 hover:text-red-300"
                      >
                        <Square size={11} /> Terminate
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Right: Log Viewer */}
        <div className="w-1/2 flex flex-col bg-[#11111b]">
          <div className="px-3 py-1.5 border-b border-gray-800 text-xs font-semibold text-gray-400 flex items-center justify-between">
            <span>Process Console Output</span>
            {selectedTaskId && (
              <button
                onClick={() => fetchLogs(selectedTaskId)}
                className="text-blue-400 hover:text-blue-300 flex items-center gap-1"
              >
                <RefreshCw size={11} className={loading ? 'animate-spin' : ''} /> Refresh
              </button>
            )}
          </div>
          <pre className="flex-1 p-3 text-xs font-mono text-gray-300 overflow-auto whitespace-pre-wrap leading-relaxed select-text">
            {logs || (selectedTaskId ? 'Loading logs...' : 'Select a process on the left to inspect logs.')}
          </pre>
        </div>
      </div>
    </div>
  );
}
