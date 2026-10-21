import { useEffect, useState, useRef } from 'react';
import { useAppStore } from '../store';
import { apiClient } from '../api/client';
import {
  DEFAULT_LLM_SETTINGS,
  CHAT_MODEL_OPTIONS,
  OLLAMA_POPULAR_MODELS,
  type LlmSettings,
} from '../utils/llmSettings';
import { HardDrive, RefreshCw, CheckCircle2, AlertTriangle } from 'lucide-react';
import clsx from 'clsx';

interface SettingsDialogProps {
  onClose: () => void;
}

export default function SettingsDialog({ onClose }: SettingsDialogProps) {
  const llmSettings = useAppStore((s) => s.llmSettings);
  const setLlmSettings = useAppStore((s) => s.setLlmSettings);
  const [draft, setDraft] = useState<LlmSettings>(llmSettings);
  const [saved, setSaved] = useState(false);

  // Ollama local state
  const [ollamaUrl, setOllamaUrl] = useState<string>(
    draft.ollamaUrl || 'http://localhost:11434'
  );
  const [ollamaChecking, setOllamaChecking] = useState<boolean>(false);
  const [ollamaConnected, setOllamaConnected] = useState<boolean | null>(null);
  const [ollamaError, setOllamaError] = useState<string | null>(null);
  const [ollamaModels, setOllamaModels] = useState<string[]>([]);

  const isPresetModel = (model: string) =>
    (CHAT_MODEL_OPTIONS as readonly string[]).includes(model) ||
    ollamaModels.includes(model) ||
    (OLLAMA_POPULAR_MODELS as readonly string[]).includes(model);

  const initialIsCustom = Boolean(
    llmSettings.model && !isPresetModel(llmSettings.model)
  );

  const [isCustomMode, setIsCustomMode] = useState<boolean>(initialIsCustom);
  const [customModelText, setCustomModelText] = useState<string>(
    initialIsCustom ? llmSettings.model : ''
  );
  const customInputRef = useRef<HTMLInputElement>(null);

  const [availableCloudModels, setAvailableCloudModels] = useState<string[]>(() => [
    ...CHAT_MODEL_OPTIONS,
  ]);

  // Fetch Ollama models
  const handleCheckOllama = async (targetUrl?: string) => {
    const url = (targetUrl ?? ollamaUrl).trim() || 'http://localhost:11434';
    setOllamaChecking(true);
    setOllamaError(null);
    try {
      const res = await apiClient.fetchOllamaModels(url);
      if (res.connected && Array.isArray(res.models)) {
        const ids = res.models.map((m) => m.id);
        setOllamaConnected(true);
        setOllamaModels(ids);
      } else {
        setOllamaConnected(false);
        setOllamaError(res.error || `Could not connect to Ollama at ${url}`);
      }
    } catch (err: any) {
      setOllamaConnected(false);
      setOllamaError(err.message || `Could not reach Ollama at ${url}`);
    } finally {
      setOllamaChecking(false);
    }
  };

  // Check Ollama on initial open
  useEffect(() => {
    handleCheckOllama(draft.ollamaUrl);
  }, []);

  // Fetch Cloud models when API key is provided
  useEffect(() => {
    async function fetchCloudModels() {
      if (!draft.apiKey.trim()) return;
      try {
        const models = await apiClient.fetchModels(draft.apiKey.trim());
        if (Array.isArray(models) && models.length > 0) {
          setAvailableCloudModels((prev) => Array.from(new Set([...models, ...prev])));
        }
      } catch (e: any) {
        console.error('Failed to fetch models for API key:', e);
      }
    }
    const timeout = setTimeout(fetchCloudModels, 1000);
    return () => clearTimeout(timeout);
  }, [draft.apiKey]);

  useEffect(() => {
    setDraft(llmSettings);
    setOllamaUrl(llmSettings.ollamaUrl || 'http://localhost:11434');
    if (llmSettings.model && !isPresetModel(llmSettings.model)) {
      setIsCustomMode(true);
      setCustomModelText(llmSettings.model);
    }
  }, [llmSettings]);

  useEffect(() => {
    if (isCustomMode) {
      setTimeout(() => {
        customInputRef.current?.focus();
      }, 50);
    }
  }, [isCustomMode]);

  const handleSave = () => {
    const finalModel = isCustomMode ? customModelText.trim() : draft.model.trim();
    const finalOllamaUrl = ollamaUrl.trim() || 'http://localhost:11434';
    setLlmSettings({
      apiKey: draft.apiKey.trim(),
      model: finalModel,
      systemPrompt: draft.systemPrompt.trim(),
      ollamaUrl: finalOllamaUrl,
    });
    setDraft((s) => ({ ...s, model: finalModel, ollamaUrl: finalOllamaUrl }));
    setSaved(true);
    window.setTimeout(() => setSaved(false), 1200);
  };

  const handleReset = () => {
    setDraft({ ...DEFAULT_LLM_SETTINGS });
    setOllamaUrl('http://localhost:11434');
    setIsCustomMode(false);
    setCustomModelText('');
    setOllamaConnected(null);
    setOllamaError(null);
  };

  const selectOllamaModel = (modelId: string) => {
    setIsCustomMode(false);
    setDraft((s) => ({ ...s, model: modelId }));
    setCustomModelText('');
  };

  const currentEffectiveModel = isCustomMode ? customModelText.trim() : draft.model.trim();
  const usingDefaults =
    !draft.apiKey.trim() &&
    !currentEffectiveModel &&
    !draft.systemPrompt.trim() &&
    ollamaUrl === 'http://localhost:11434';

  const selectValue = isCustomMode ? '__custom__' : (draft.model || '');

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-800 rounded-lg p-6 w-full max-w-xl mx-4 border border-gray-700 shadow-xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <h2 className="text-lg font-semibold text-white">Assistant settings</h2>

          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white text-sm"
          >
            Close
          </button>
        </div>

        <p className="text-xs text-gray-400 mb-4">
          Configure cloud LLM providers (Groq, Gemini) or your local Ollama instance. Values are stored locally in this browser.
        </p>

        {/* Section: Local Models (Ollama) */}
        <div className="bg-gray-900/80 border border-orange-500/30 rounded-lg p-3.5 mb-5 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <HardDrive size={16} className="text-orange-400" />
              <span className="text-xs font-semibold text-gray-200">Local Models (Ollama)</span>
            </div>
            {ollamaConnected === true && (
              <span className="text-[11px] text-emerald-400 flex items-center gap-1 font-medium bg-emerald-950/60 border border-emerald-700/50 px-2 py-0.5 rounded">
                <CheckCircle2 size={12} />
                Connected ({ollamaModels.length} model{ollamaModels.length === 1 ? '' : 's'})
              </span>
            )}
            {ollamaConnected === false && (
              <span className="text-[11px] text-amber-400 flex items-center gap-1 font-medium bg-amber-950/60 border border-amber-700/50 px-2 py-0.5 rounded">
                <AlertTriangle size={12} />
                Offline
              </span>
            )}
          </div>

          <div className="flex gap-2">
            <input
              type="text"
              value={ollamaUrl}
              onChange={(e) => setOllamaUrl(e.target.value)}
              placeholder="http://localhost:11434"
              className="flex-1 bg-gray-800 text-white placeholder-gray-500 px-3 py-1.5 rounded border border-gray-700 focus:border-orange-500 focus:outline-none text-xs font-mono"
            />
            <button
              type="button"
              onClick={() => handleCheckOllama()}
              disabled={ollamaChecking}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-orange-600/80 hover:bg-orange-600 text-white text-xs font-medium rounded transition-colors disabled:opacity-50"
              title="Test connection and discover local Ollama models"
            >
              <RefreshCw size={13} className={clsx(ollamaChecking && 'animate-spin')} />
              <span>{ollamaChecking ? 'Checking…' : 'Fetch Models'}</span>
            </button>
          </div>

          {/* Installed Ollama models list */}
          {ollamaConnected === true && ollamaModels.length > 0 && (
            <div className="pt-2 border-t border-gray-800">
              <span className="text-[11px] text-gray-400 block mb-1.5">
                Installed local models:
              </span>
              <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto">
                {ollamaModels.map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => selectOllamaModel(m)}
                    className={clsx(
                      'px-2 py-1 rounded text-[11px] font-mono transition-colors border',
                      draft.model === m
                        ? 'bg-orange-600 text-white border-orange-400 font-medium'
                        : 'bg-gray-800 text-gray-300 border-gray-700 hover:bg-gray-750 hover:text-white'
                    )}
                  >
                    {m}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Quick presets for common local models */}
          <div className="pt-1">
            <span className="text-[11px] text-gray-400 block mb-1">
              Popular coding models:
            </span>
            <div className="flex flex-wrap gap-1">
              {OLLAMA_POPULAR_MODELS.map((pop) => (
                <button
                  key={pop}
                  type="button"
                  onClick={() => selectOllamaModel(pop)}
                  className={clsx(
                    'px-2 py-0.5 rounded text-[10px] font-mono border transition-colors',
                    draft.model === pop
                      ? 'bg-orange-600 text-white border-orange-400'
                      : 'bg-gray-800/80 text-gray-400 border-gray-700/60 hover:text-gray-200'
                  )}
                  title={`Select ${pop} as active model`}
                >
                  {pop}
                </button>
              ))}
            </div>
          </div>

          {ollamaError && (
            <p className="text-[11px] text-amber-300 bg-amber-950/40 p-2 rounded border border-amber-800/60">
              {ollamaError}
              <span className="block mt-0.5 text-gray-400">
                To start Ollama, run <code className="text-amber-200 font-mono">ollama serve</code> in your terminal.
              </span>
            </p>
          )}
        </div>

        {/* Section: Cloud API Key */}
        <label className="block text-xs text-gray-400 mb-1">
          Cloud API key (Groq or Gemini)
        </label>
        <input
          type="password"
          autoComplete="off"
          value={draft.apiKey}
          onChange={(e) => setDraft((s) => ({ ...s, apiKey: e.target.value }))}
          placeholder="Leave blank to use local Ollama or server default key"
          className="w-full bg-gray-700 text-white placeholder-gray-500 px-3 py-2 rounded border border-gray-600 focus:border-blue-500 focus:outline-none mb-4"
        />

        {/* Section: Chat Model Selection */}
        <label className="block text-xs text-gray-400 mb-1">Active chat model</label>
        <select
          value={selectValue}
          onChange={(e) => {
            const value = e.target.value;
            if (value === '__custom__') {
              setIsCustomMode(true);
              if (!customModelText && draft.model) {
                setCustomModelText(draft.model);
              }
            } else if (value === '') {
              setIsCustomMode(false);
              setDraft((s) => ({ ...s, model: '' }));
            } else {
              setIsCustomMode(false);
              setDraft((s) => ({ ...s, model: value }));
            }
          }}
          className="w-full bg-gray-700 text-white px-3 py-2 rounded border border-gray-600 focus:border-blue-500 focus:outline-none mb-2 font-mono text-xs"
        >
          <option value="">Server default (Groq: llama-3.3-70b-versatile)</option>

          {/* Ollama local models optgroup */}
          {ollamaModels.length > 0 && (
            <optgroup label="Local Models (Ollama)">
              {ollamaModels.map((id) => (
                <option key={`ollama-${id}`} value={id}>
                  {id} (Local Ollama)
                </option>
              ))}
            </optgroup>
          )}

          {/* Cloud models optgroup */}
          <optgroup label="Cloud Models (Groq / Gemini / OpenAI)">
            {availableCloudModels.map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </optgroup>

          <option value="__custom__">Custom model id…</option>
        </select>

        {/* Custom model input */}
        {isCustomMode && (
          <div className="bg-gray-900/90 border border-gray-600 rounded-lg p-3 mb-3">
            <div className="flex items-center justify-between mb-1">
              <label className="block text-xs font-medium text-gray-200">
                Custom model name / ID
              </label>
              <button
                type="button"
                onClick={() => {
                  setIsCustomMode(false);
                  setDraft((s) => ({ ...s, model: '' }));
                  setCustomModelText('');
                }}
                className="text-xs text-gray-400 hover:text-gray-200 transition-colors"
              >
                Reset to default
              </button>
            </div>
            <input
              ref={customInputRef}
              type="text"
              autoFocus
              value={customModelText}
              onChange={(e) => setCustomModelText(e.target.value)}
              placeholder="e.g. llama3.2, deepseek-r1, or gemini-2.5-flash"
              className="w-full bg-gray-800 text-white placeholder-gray-500 px-3 py-2 rounded border border-gray-600 focus:border-blue-500 focus:outline-none text-sm font-mono mb-1.5"
            />
            <p className="text-[11px] text-gray-400">
              Enter any local model from Ollama (e.g. <code className="text-orange-300">llama3.2</code>) or cloud model ID.
            </p>
          </div>
        )}

        <label className="block text-xs text-gray-400 mb-1">Personal system prompt</label>
        <textarea
          value={draft.systemPrompt}
          onChange={(e) => setDraft((s) => ({ ...s, systemPrompt: e.target.value }))}
          placeholder="Optional instructions added on top of the default assistant prompt"
          rows={4}
          className="w-full bg-gray-700 text-white placeholder-gray-500 px-3 py-2 rounded border border-gray-600 focus:border-blue-500 focus:outline-none mb-3 resize-y text-xs"
        />

        <p className="text-xs text-gray-500 mb-4">
          {usingDefaults
            ? 'Using default cloud key, model, and system prompt.'
            : 'Custom values will be sent with chat and completion requests.'}
        </p>

        <div className="flex justify-between gap-2">
          <button
            onClick={handleReset}
            className="px-4 py-2 rounded bg-gray-700 hover:bg-gray-600 text-white text-sm"
          >
            Clear to defaults
          </button>
          <button
            onClick={handleSave}
            className="px-4 py-2 rounded bg-blue-600 hover:bg-blue-700 text-white text-sm"
          >
            {saved ? 'Saved' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}
