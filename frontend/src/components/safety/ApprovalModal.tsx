import { useState } from 'react';
import axios from 'axios';
import { Check, X, Terminal, FileCode, Monitor } from 'lucide-react';

export interface PendingApproval {
  action_id: string;
  tool_name: string;
  action_category: string;
  details: Record<string, any>;
  reason: string;
  tier: 'safe' | 'caution' | 'dangerous';
}

interface ApprovalModalProps {
  approval: PendingApproval;
  onResolved: () => void;
}

export default function ApprovalModal({ approval, onResolved }: ApprovalModalProps) {
  const [feedback, setFeedback] = useState('');
  const [loading, setLoading] = useState(false);

  const handleApprove = async (scope: 'once' | 'session' = 'once') => {
    setLoading(true);
    try {
      await axios.post('/api/safety/approve', {
        action_id: approval.action_id,
        scope,
      });
      onResolved();
    } catch (e: any) {
      alert(`Approval failed: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  const handleReject = async () => {
    setLoading(true);
    try {
      await axios.post('/api/safety/reject', {
        action_id: approval.action_id,
        feedback,
      });
      onResolved();
    } catch (e: any) {
      alert(`Rejection failed: ${e.message}`);
    } finally {
      setLoading(false);
    }
  };

  const getIcon = () => {
    if (approval.action_category === 'terminal_command') return <Terminal size={20} className="text-yellow-400" />;
    if (approval.action_category.startsWith('browser_')) return <Monitor size={20} className="text-blue-400" />;
    return <FileCode size={20} className="text-purple-400" />;
  };

  const isDangerous = approval.tier === 'dangerous';

  return (
    <div className="fixed inset-0 bg-black/75 backdrop-blur-sm flex items-center justify-center z-50 p-4">
      <div className="bg-[#181825] border border-gray-700 rounded-xl max-w-lg w-full shadow-2xl overflow-hidden flex flex-col">
        {/* Header */}
        <div className={`p-4 border-b flex items-center gap-3 ${
          isDangerous ? 'bg-red-950/40 border-red-800/60' : 'bg-yellow-950/40 border-yellow-800/60'
        }`}>
          <div className="p-2 rounded-lg bg-[#11111b] border border-gray-700">
            {getIcon()}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-semibold text-sm text-gray-100">Action Approval Required</h3>
              <span className={`px-2 py-0.5 rounded text-[10px] uppercase font-bold ${
                isDangerous ? 'bg-red-900/60 text-red-300 border border-red-700' : 'bg-yellow-900/60 text-yellow-300 border border-yellow-700'
              }`}>
                {approval.tier}
              </span>
            </div>
            <p className="text-xs text-gray-400 mt-0.5">
              The AI agent is attempting an action that requires your explicit confirmation.
            </p>
          </div>
        </div>

        {/* Body */}
        <div className="p-4 space-y-3 text-xs">
          <div>
            <label className="text-gray-400 font-semibold block mb-1">Reason / Guardrail Rule:</label>
            <p className="text-gray-200 bg-[#11111b] p-2.5 rounded border border-gray-800 leading-relaxed">
              {approval.reason}
            </p>
          </div>

          <div>
            <label className="text-gray-400 font-semibold block mb-1">Action Details:</label>
            <div className="bg-[#11111b] p-2.5 rounded border border-gray-800 font-mono text-[11px] text-gray-300 max-h-40 overflow-y-auto whitespace-pre-wrap">
              {approval.details.command && (
                <div>
                  <span className="text-gray-500">$ </span>
                  <span className="text-yellow-300">{approval.details.command}</span>
                </div>
              )}
              {approval.details.file_path && (
                <div>
                  <span className="text-gray-500">Target File: </span>
                  <span className="text-blue-300">{approval.details.file_path}</span>
                </div>
              )}
              {approval.details.rationale && (
                <div className="mt-1 text-gray-400 italic">
                  Rationale: {approval.details.rationale}
                </div>
              )}
              {!approval.details.command && !approval.details.file_path && (
                JSON.stringify(approval.details, null, 2)
              )}
            </div>
          </div>

          <div>
            <label className="text-gray-400 font-semibold block mb-1">Feedback to Agent (if rejecting):</label>
            <input
              type="text"
              value={feedback}
              onChange={(e) => setFeedback(e.target.value)}
              placeholder="e.g. Do not delete that file; use git stash instead..."
              className="w-full bg-[#11111b] border border-gray-700 rounded px-2.5 py-1.5 text-gray-200 placeholder-gray-500 focus:outline-none focus:border-blue-500"
            />
          </div>
        </div>

        {/* Footer actions */}
        <div className="p-4 border-t border-gray-800 bg-[#11111b] flex items-center justify-between gap-2">
          <button
            onClick={handleReject}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 hover:text-white rounded text-xs font-medium disabled:opacity-50"
          >
            <X size={13} />
            <span>Reject</span>
          </button>

          <div className="flex items-center gap-2">
            <button
              onClick={() => handleApprove('session')}
              disabled={loading}
              className="px-3 py-1.5 bg-blue-900/40 hover:bg-blue-800/60 text-blue-300 border border-blue-700/60 rounded text-xs font-medium disabled:opacity-50"
              title="Allow all similar actions for the rest of this session"
            >
              Approve for Session
            </button>
            <button
              onClick={() => handleApprove('once')}
              disabled={loading}
              className="flex items-center gap-1.5 px-3.5 py-1.5 bg-green-600 hover:bg-green-700 text-white rounded text-xs font-semibold disabled:opacity-50"
            >
              <Check size={13} />
              <span>Approve Once</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
