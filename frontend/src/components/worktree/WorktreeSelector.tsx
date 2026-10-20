import { useState, useEffect } from 'react';
import { useAppStore } from '../../store';
import { GitBranch, Plus, ChevronDown, Check, Layers, GitCompare } from 'lucide-react';
import clsx from 'clsx';
import { apiClient } from '../../api/client';
import type { WorktreeInfo } from '../../types';

export default function WorktreeSelector() {
  const {
    currentRepository,
    worktrees,
    activeWorktree,
    loadWorktrees,
    createWorktree,
    selectWorktree,
  } = useAppStore();

  const [isOpen, setIsOpen] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [newWorktreeName, setNewWorktreeName] = useState('');
  const [loadingDiff, setLoadingDiff] = useState(false);
  const openDiffTab = useAppStore((s) => s.openDiffTab);

  const handleOpenDiff = async () => {
    if (!currentRepository?.id || !activeWorktree?.name) return;
    setLoadingDiff(true);
    try {
      const diffData = await apiClient.getWorktreeDiff(currentRepository.id, activeWorktree.name);
      if (diffData.files_changed && diffData.files_changed.length > 0) {
        for (const f of diffData.files_changed) {
          try {
            const modified = await apiClient.readFile(currentRepository.id, f.file_path);
            openDiffTab(f.file_path, '', modified, `Diff: ${f.file_path}`);
          } catch {
            openDiffTab(f.file_path, '', diffData.diff_patch, `Diff: ${f.file_path}`);
          }
        }
      } else if (diffData.diff_patch) {
        openDiffTab('changes.diff', '', diffData.diff_patch, `Diff: ${currentLabel}`);
      } else {
        alert('No unstaged or uncommitted changes found in active worktree.');
      }
    } catch (e: any) {
      alert('Diff error: ' + (e?.message || e));
    } finally {
      setLoadingDiff(false);
    }
  };

  useEffect(() => {
    if (currentRepository?.id) {
      loadWorktrees(currentRepository.id);
    }
  }, [currentRepository?.id, loadWorktrees]);

  const handleCreate = async () => {
    if (!newWorktreeName.trim() || !currentRepository?.id) return;
    await createWorktree(currentRepository.id, newWorktreeName.trim());
    setNewWorktreeName('');
    setShowCreate(false);
    setIsOpen(false);
  };

  const handleSelect = (wt: WorktreeInfo) => {
    selectWorktree(wt);
    setIsOpen(false);
  };

  const currentLabel = activeWorktree?.branch || 'main';
  const isCustomWorktree = activeWorktree && !activeWorktree.is_main;

  return (
    <div className="flex items-center gap-1.5">
      <div className="relative inline-block text-xs">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={clsx(
          'flex items-center gap-1.5 px-2.5 py-1 rounded font-mono border transition-colors',
          isCustomWorktree
            ? 'bg-indigo-950/80 border-indigo-700 text-indigo-200 hover:bg-indigo-900/80'
            : 'bg-gray-800 border-gray-700 text-gray-300 hover:bg-gray-700 hover:text-white'
        )}
        title="Active Git Worktree sandbox"
      >
        <GitBranch size={13} className={isCustomWorktree ? 'text-indigo-400' : 'text-gray-400'} />
        <span className="truncate max-w-[140px] font-medium">{currentLabel}</span>
        {isCustomWorktree && (
          <span className="text-[10px] bg-indigo-900 px-1 py-0.2 rounded text-indigo-300 uppercase">
            Worktree
          </span>
        )}
        <ChevronDown size={12} className="text-gray-400 ml-0.5" />
      </button>

      {isOpen && (
        <div className="absolute left-0 mt-1 w-64 bg-gray-800 border border-gray-700 rounded-md shadow-xl z-50 p-1.5 space-y-1">
          <div className="flex items-center justify-between px-2 py-1 text-[11px] font-semibold uppercase text-gray-400 border-b border-gray-700/60">
            <span className="flex items-center gap-1">
              <Layers size={12} />
              Git Worktrees
            </span>
            <button
              onClick={() => setShowCreate(!showCreate)}
              className="text-indigo-400 hover:text-indigo-300 flex items-center gap-0.5 text-[11px]"
            >
              <Plus size={11} />
              <span>New</span>
            </button>
          </div>

          {showCreate && (
            <div className="p-1.5 bg-gray-900/80 rounded border border-gray-700 space-y-1.5">
              <input
                type="text"
                value={newWorktreeName}
                onChange={(e) => setNewWorktreeName(e.target.value)}
                placeholder="Sandbox name (e.g. tkt-142)"
                className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1 text-white text-[11px] focus:outline-none focus:border-indigo-500"
              />
              <div className="flex justify-end gap-1">
                <button
                  onClick={() => setShowCreate(false)}
                  className="px-2 py-0.5 bg-gray-700 text-gray-300 rounded text-[10px]"
                >
                  Cancel
                </button>
                <button
                  onClick={handleCreate}
                  disabled={!newWorktreeName.trim()}
                  className="px-2 py-0.5 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded text-[10px]"
                >
                  Create
                </button>
              </div>
            </div>
          )}

          <div className="max-h-48 overflow-y-auto space-y-0.5">
            {worktrees.map((wt) => {
              const isSelected = activeWorktree?.path === wt.path;

              return (
                <div
                  key={wt.path}
                  onClick={() => handleSelect(wt)}
                  className={clsx(
                    'flex items-center justify-between px-2 py-1.5 rounded cursor-pointer transition-colors',
                    isSelected
                      ? 'bg-gray-700 text-white font-medium'
                      : 'text-gray-300 hover:bg-gray-700/50 hover:text-white'
                  )}
                >
                  <div className="flex items-center gap-1.5 min-w-0">
                    <GitBranch size={12} className={wt.is_main ? 'text-gray-400' : 'text-indigo-400'} />
                    <span className="truncate text-xs">{wt.branch}</span>
                    {wt.is_main && (
                      <span className="text-[10px] text-gray-500 italic">(main)</span>
                    )}
                  </div>
                  {isSelected && <Check size={12} className="text-emerald-400 shrink-0" />}
                </div>
              );
            })}
          </div>
        </div>
      )}
      </div>
      {isCustomWorktree && (
        <button
          type="button"
          onClick={handleOpenDiff}
          disabled={loadingDiff}
          className="flex items-center gap-1 px-2 py-1 rounded bg-amber-950/70 hover:bg-amber-900/80 border border-amber-600/50 text-amber-200 text-xs transition-colors cursor-pointer"
          title="Open worktree diff tabs in editor"
        >
          <GitCompare size={12} className="text-amber-400" />
          <span>{loadingDiff ? 'Diff…' : 'Diff'}</span>
        </button>
      )}
    </div>
  );
}
