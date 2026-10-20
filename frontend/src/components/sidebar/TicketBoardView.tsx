import { useState, useEffect } from 'react';
import { useAppStore } from '../../store';
import {
  ListTodo,
  Plus,
  GitBranch,
  Play,
  CheckCircle,
  Circle,
  RefreshCw,
} from 'lucide-react';
import clsx from 'clsx';

export default function TicketBoardView() {
  const {
    currentRepository,
    tickets,
    loadTickets,
    createTicket,
    activateTicketWorktree,
    activeWorktree,
  } = useAppStore();

  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [newPriority, setNewPriority] = useState('medium');
  const [newCriterion, setNewCriterion] = useState('');

  useEffect(() => {
    if (currentRepository?.id) {
      loadTickets(currentRepository.id);
    }
  }, [currentRepository?.id, loadTickets]);

  const handleCreate = async () => {
    if (!newTitle.trim() || !currentRepository?.id) return;
    const criteria = newCriterion.trim()
      ? [{ description: newCriterion.trim(), criterion_type: 'automated_test' }]
      : [];

    await createTicket(currentRepository.id, {
      title: newTitle.trim(),
      description: newDesc.trim(),
      priority: newPriority,
      assignee_type: 'agent',
      assignee_id: 'Crystal Agent',
      criteria,
    });

    setNewTitle('');
    setNewDesc('');
    setNewCriterion('');
    setShowCreateModal(false);
  };

  const filteredTickets = tickets.filter((t) => {
    if (filterStatus === 'all') return true;
    return t.status === filterStatus;
  });

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-gray-900 select-none text-gray-200">
      {/* Header Bar */}
      <div className="p-3 border-b border-gray-800 flex items-center justify-between bg-gray-950/40">
        <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-gray-400">
          <ListTodo size={14} className="text-indigo-400" />
          <span>Tickets & Tasks</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => currentRepository?.id && loadTickets(currentRepository.id)}
            className="p-1 text-gray-400 hover:text-white rounded hover:bg-gray-800 transition-colors"
            title="Refresh Tickets"
          >
            <RefreshCw size={12} />
          </button>
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-1 px-2 py-1 text-xs bg-indigo-600 hover:bg-indigo-500 text-white rounded transition-colors"
            title="Create New Ticket"
          >
            <Plus size={12} />
            <span>New Ticket</span>
          </button>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="px-3 py-1.5 border-b border-gray-800 flex items-center gap-1.5 text-xs bg-gray-900/60">
        {['all', 'todo', 'in_progress', 'done'].map((st) => (
          <button
            key={st}
            onClick={() => setFilterStatus(st)}
            className={clsx(
              'px-2 py-0.5 rounded text-[11px] font-medium transition-colors',
              filterStatus === st
                ? 'bg-gray-800 text-white border border-gray-700'
                : 'text-gray-400 hover:text-gray-200'
            )}
          >
            {st === 'in_progress' ? 'In Progress' : st.charAt(0).toUpperCase() + st.slice(1)}
          </button>
        ))}
      </div>

      {/* Tickets List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-2">
        {filteredTickets.length === 0 ? (
          <div className="p-4 text-center text-xs text-gray-500">
            <p>No tickets in this project yet.</p>
            <p className="mt-1">Click "New Ticket" to create a task with acceptance criteria.</p>
          </div>
        ) : (
          filteredTickets.map((ticket) => {
            const isWorktreeActive = activeWorktree?.branch === ticket.active_branch;

            return (
              <div
                key={ticket.id}
                className={clsx(
                  'p-3 rounded border text-xs transition-all',
                  isWorktreeActive
                    ? 'bg-gray-800/90 border-indigo-500 shadow-md'
                    : 'bg-gray-800/60 border-gray-800 hover:border-gray-700'
                )}
              >
                {/* Header Row */}
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-1.5">
                    <span className="font-mono text-[10px] text-gray-400 bg-gray-900 px-1 py-0.5 rounded border border-gray-700">
                      {ticket.id}
                    </span>
                    <span
                      className={clsx(
                        'text-[10px] font-medium px-1.5 py-0.2 rounded uppercase',
                        ticket.priority === 'critical'
                          ? 'bg-red-950 text-red-300 border border-red-800'
                          : ticket.priority === 'high'
                          ? 'bg-orange-950 text-orange-300 border border-orange-800'
                          : 'bg-gray-800 text-gray-300 border border-gray-700'
                      )}
                    >
                      {ticket.priority}
                    </span>
                  </div>

                  {/* Status Badge */}
                  <span
                    className={clsx(
                      'text-[10px] font-medium px-1.5 py-0.5 rounded uppercase',
                      ticket.status === 'done'
                        ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                        : ticket.status === 'in_progress'
                        ? 'bg-blue-950 text-blue-300 border border-blue-800'
                        : 'bg-gray-900 text-gray-400 border border-gray-800'
                    )}
                  >
                    {ticket.status.replace('_', ' ')}
                  </span>
                </div>

                {/* Title */}
                <div className="font-semibold text-white my-1 text-xs">
                  {ticket.title}
                </div>

                {ticket.description && (
                  <p className="text-[11px] text-gray-400 line-clamp-2 mb-2">
                    {ticket.description}
                  </p>
                )}

                {/* Acceptance Criteria Checklist */}
                {ticket.criteria && ticket.criteria.length > 0 && (
                  <div className="my-2 p-1.5 bg-gray-950/60 rounded border border-gray-800 space-y-1">
                    <div className="text-[10px] uppercase font-semibold text-gray-400">
                      Acceptance Criteria:
                    </div>
                    {ticket.criteria.map((c) => (
                      <div key={c.id} className="flex items-center gap-1.5 text-[11px]">
                        {c.is_satisfied ? (
                          <CheckCircle size={12} className="text-emerald-400 shrink-0" />
                        ) : (
                          <Circle size={12} className="text-gray-500 shrink-0" />
                        )}
                        <span className={c.is_satisfied ? 'text-gray-300 line-through' : 'text-gray-300'}>
                          {c.description}
                        </span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Action Bar */}
                <div className="flex items-center justify-between pt-1.5 mt-1 border-t border-gray-800/80">
                  <div className="flex items-center gap-1 text-[10px] text-gray-400">
                    <GitBranch size={11} className="text-indigo-400" />
                    <span className="truncate max-w-[130px]">
                      {ticket.active_branch || `mesh/${ticket.id}`}
                    </span>
                  </div>

                  <button
                    onClick={() => activateTicketWorktree(ticket.id)}
                    className={clsx(
                      'flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-medium transition-colors',
                      isWorktreeActive
                        ? 'bg-emerald-900/60 text-emerald-200 border border-emerald-700/60'
                        : 'bg-gray-700 hover:bg-gray-600 text-gray-200'
                    )}
                    title="Spawn/switch to isolated Git worktree for this ticket"
                  >
                    <Play size={10} />
                    <span>{isWorktreeActive ? 'Active Sandbox' : 'Activate Worktree'}</span>
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* New Ticket Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4">
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-4 w-full max-w-sm text-xs space-y-3">
            <h3 className="font-semibold text-white text-sm">Create Engineering Ticket</h3>
            <div>
              <label className="text-gray-400 block mb-1">Title *</label>
              <input
                type="text"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                placeholder="e.g. Fix intermittent API failures"
                className="w-full bg-gray-900 border border-gray-700 rounded px-2.5 py-1.5 text-white focus:outline-none focus:border-indigo-500"
              />
            </div>
            <div>
              <label className="text-gray-400 block mb-1">Description</label>
              <textarea
                value={newDesc}
                onChange={(e) => setNewDesc(e.target.value)}
                placeholder="Root cause, repro steps, and expectations"
                rows={2}
                className="w-full bg-gray-900 border border-gray-700 rounded px-2.5 py-1.5 text-white focus:outline-none focus:border-indigo-500"
              />
            </div>
            <div>
              <label className="text-gray-400 block mb-1">Priority</label>
              <select
                value={newPriority}
                onChange={(e) => setNewPriority(e.target.value)}
                className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1.5 text-white focus:outline-none"
              >
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="critical">Critical</option>
              </select>
            </div>
            <div>
              <label className="text-gray-400 block mb-1">Acceptance Criterion</label>
              <input
                type="text"
                value={newCriterion}
                onChange={(e) => setNewCriterion(e.target.value)}
                placeholder="e.g. Pass regression tests in tests/test_auth.py"
                className="w-full bg-gray-900 border border-gray-700 rounded px-2.5 py-1.5 text-white focus:outline-none focus:border-indigo-500"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setShowCreateModal(false)}
                className="px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-gray-300 rounded"
              >
                Cancel
              </button>
              <button
                onClick={handleCreate}
                disabled={!newTitle.trim()}
                className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded font-medium"
              >
                Create Ticket
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
