import { useState, useEffect } from 'react';
import { useAppStore } from '../../store';
import {
  Activity,
  CheckCircle2,
  XCircle,
  Clock,
  FileCode,
  Filter,
  RefreshCw,
  GitBranch,
} from 'lucide-react';
import clsx from 'clsx';
import type { ChangeLedgerEvent } from '../../types';

export default function ActivityLedgerView() {
  const {
    currentRepository,
    ledgerEvents,
    ledgerStats,
    loadLedgerEvents,
    loadLedgerStats,
  } = useAppStore();

  const [selectedEvent, setSelectedEvent] = useState<ChangeLedgerEvent | null>(null);
  const [filterStatus, setFilterStatus] = useState<string>('all');
  const [filterType, setFilterType] = useState<string>('all');

  useEffect(() => {
    if (currentRepository?.id) {
      loadLedgerEvents(currentRepository.id);
      loadLedgerStats(currentRepository.id);
    }
  }, [currentRepository?.id, loadLedgerEvents, loadLedgerStats]);

  const handleRefresh = () => {
    if (currentRepository?.id) {
      loadLedgerEvents(currentRepository.id, {
        verification_status: filterStatus !== 'all' ? filterStatus : undefined,
        event_type: filterType !== 'all' ? filterType : undefined,
      });
      loadLedgerStats(currentRepository.id);
    }
  };

  const filteredEvents = ledgerEvents.filter((e) => {
    if (filterStatus !== 'all' && e.verification_status !== filterStatus) return false;
    if (filterType !== 'all' && e.event_type !== filterType) return false;
    return true;
  });

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-gray-900 select-none text-gray-200">
      {/* Metrics Banner */}
      <div className="p-3 border-b border-gray-800 bg-gray-950/40">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-gray-400">
            <Activity size={14} className="text-emerald-400" />
            <span>Engineering Ledger</span>
          </div>
          <button
            onClick={handleRefresh}
            className="p-1 text-gray-400 hover:text-white rounded hover:bg-gray-800 transition-colors"
            title="Refresh Ledger"
          >
            <RefreshCw size={12} />
          </button>
        </div>

        <div className="grid grid-cols-3 gap-2">
          <div className="bg-gray-800/80 border border-gray-700/60 rounded p-2 text-center">
            <div className="text-[10px] text-gray-400 uppercase font-medium">Changes</div>
            <div className="text-base font-bold text-white mt-0.5">
              {ledgerStats?.total_changes ?? ledgerEvents.length}
            </div>
          </div>
          <div className="bg-gray-800/80 border border-emerald-900/40 rounded p-2 text-center">
            <div className="text-[10px] text-emerald-400 uppercase font-medium">Verified</div>
            <div className="text-base font-bold text-emerald-300 mt-0.5">
              {ledgerStats?.verified_changes ?? ledgerEvents.filter(e => e.verification_status === 'passed').length}
            </div>
          </div>
          <div className="bg-gray-800/80 border border-indigo-900/40 rounded p-2 text-center">
            <div className="text-[10px] text-indigo-400 uppercase font-medium">Open Tasks</div>
            <div className="text-base font-bold text-indigo-300 mt-0.5">
              {ledgerStats?.open_tickets ?? 0}
            </div>
          </div>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="px-3 py-2 border-b border-gray-800 flex items-center gap-2 text-xs bg-gray-900/60">
        <Filter size={12} className="text-gray-400" />
        <select
          value={filterStatus}
          onChange={(e) => setFilterStatus(e.target.value)}
          className="bg-gray-800 border border-gray-700 text-gray-200 text-[11px] rounded px-1.5 py-0.5 focus:outline-none"
        >
          <option value="all">All Verification</option>
          <option value="passed">Verified (Passed)</option>
          <option value="failed">Failed Tests</option>
          <option value="not_run">Not Run</option>
        </select>
        <select
          value={filterType}
          onChange={(e) => setFilterType(e.target.value)}
          className="bg-gray-800 border border-gray-700 text-gray-200 text-[11px] rounded px-1.5 py-0.5 focus:outline-none"
        >
          <option value="all">All Types</option>
          <option value="edit">Edits</option>
          <option value="commit">Commits</option>
          <option value="test_run">Test Runs</option>
        </select>
      </div>

      {/* Event Records List */}
      <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
        {filteredEvents.length === 0 ? (
          <div className="p-4 text-center text-xs text-gray-500">
            <p>No engineering events recorded yet.</p>
            <p className="mt-1">Changes made by developers and AI agents will appear here.</p>
          </div>
        ) : (
          filteredEvents.map((event) => {
            const isVerified = event.verification_status === 'passed';
            const isFailed = event.verification_status === 'failed';
            const isPending = event.verification_status === 'pending';

            return (
              <div
                key={event.id}
                onClick={() => setSelectedEvent(selectedEvent?.id === event.id ? null : event)}
                className={clsx(
                  'p-2.5 rounded border text-xs cursor-pointer transition-all',
                  selectedEvent?.id === event.id
                    ? 'bg-gray-800 border-indigo-500/80 shadow-md'
                    : 'bg-gray-800/60 border-gray-800 hover:border-gray-700 hover:bg-gray-800/90'
                )}
              >
                {/* Row 1: Badges & Status */}
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-1.5">
                    <span className="font-mono text-[10px] text-gray-400 bg-gray-900 px-1 py-0.5 rounded border border-gray-700">
                      {event.id.slice(0, 8)}
                    </span>
                    {event.ticket_id && (
                      <span className="font-medium text-[10px] text-indigo-300 bg-indigo-950/60 px-1.5 py-0.5 rounded border border-indigo-800">
                        {event.ticket_id}
                      </span>
                    )}
                    <span
                      className={clsx(
                        'text-[10px] font-medium px-1.5 py-0.2 rounded',
                        event.actor_type === 'agent'
                          ? 'bg-blue-900/50 text-blue-200 border border-blue-700/50'
                          : 'bg-purple-900/50 text-purple-200 border border-purple-700/50'
                      )}
                    >
                      {event.actor_id}
                    </span>
                  </div>

                  {/* Verification Pill */}
                  <div className="flex items-center gap-1">
                    {isVerified && (
                      <span className="flex items-center gap-1 text-[10px] text-emerald-400 font-medium bg-emerald-950/60 px-1.5 py-0.5 rounded border border-emerald-800/80">
                        <CheckCircle2 size={10} />
                        Verified
                      </span>
                    )}
                    {isFailed && (
                      <span className="flex items-center gap-1 text-[10px] text-red-400 font-medium bg-red-950/60 px-1.5 py-0.5 rounded border border-red-800/80">
                        <XCircle size={10} />
                        Failed
                      </span>
                    )}
                    {isPending && (
                      <span className="flex items-center gap-1 text-[10px] text-yellow-400 font-medium bg-yellow-950/60 px-1.5 py-0.5 rounded border border-yellow-800/80">
                        <Clock size={10} />
                        Pending
                      </span>
                    )}
                  </div>
                </div>

                {/* Row 2: Event Summary */}
                <div className="font-medium text-gray-200 line-clamp-2 my-1">
                  {event.summary}
                </div>

                {/* Row 3: Meta & Diff Stats */}
                <div className="flex items-center justify-between text-[11px] text-gray-400 mt-1.5 pt-1 border-t border-gray-800/60">
                  <div className="flex items-center gap-2">
                    {event.branch && (
                      <span className="flex items-center gap-1 text-[10px] text-gray-400">
                        <GitBranch size={10} />
                        {event.branch}
                      </span>
                    )}
                    {event.files_changed && event.files_changed.length > 0 && (
                      <span className="flex items-center gap-1 text-[10px] text-gray-400">
                        <FileCode size={10} />
                        {event.files_changed.length} file{event.files_changed.length > 1 ? 's' : ''}
                      </span>
                    )}
                  </div>

                  {/* Diff Stats Pill */}
                  {event.diff_stats && (event.diff_stats.additions !== undefined || event.diff_stats.deletions !== undefined) && (
                    <div className="font-mono text-[10px] flex items-center gap-1">
                      <span className="text-emerald-400">+{event.diff_stats.additions || 0}</span>
                      <span className="text-red-400">-{event.diff_stats.deletions || 0}</span>
                    </div>
                  )}
                </div>

                {/* Expanded Details */}
                {selectedEvent?.id === event.id && (
                  <div className="mt-2.5 pt-2 border-t border-gray-700/80 space-y-1.5 text-[11px]">
                    {event.diff_patch && (
                      <div>
                        <div className="text-[10px] text-gray-400 uppercase font-semibold mb-1">
                          Unified Patch:
                        </div>
                        <pre className="bg-gray-950 text-gray-300 p-2 rounded text-[10px] font-mono overflow-x-auto max-h-36">
                          {event.diff_patch}
                        </pre>
                      </div>
                    )}
                    {event.verification_details && Object.keys(event.verification_details).length > 0 && (
                      <div>
                        <div className="text-[10px] text-gray-400 uppercase font-semibold mb-0.5">
                          Verification Output:
                        </div>
                        <pre className="bg-gray-950 text-emerald-400 p-2 rounded text-[10px] font-mono overflow-x-auto max-h-24">
                          {JSON.stringify(event.verification_details, null, 2)}
                        </pre>
                      </div>
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
