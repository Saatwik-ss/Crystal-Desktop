import { useEffect, useState, useRef } from 'react';
import { useAppStore } from '../store';
import { apiClient } from '../api/client';
import {
  DEFAULT_LLM_SETTINGS,
  CHAT_MODEL_OPTIONS,
  type LlmSettings,
} from '../utils/llmSettings';

interface SettingsDialogProps {
  onClose: () => void;
}

export default function SettingsDialog({ onClose }: SettingsDialogProps) {
  const llmSettings = useAppStore((s) => s.llmSettings);
  const setLlmSettings = useAppStore((s) => s.setLlmSettings);
  const [draft, setDraft] = useState<LlmSettings>(llmSettings);
  const [saved, setSaved] = useState(false);

  const isPresetModel = (model: string) =>
    (CHAT_MODEL_OPTIONS as readonly string[]).includes(model);

  const initialIsCustom = Boolean(
    llmSettings.model && !isPresetModel(llmSettings.model)
  );

  // Persistent custom mode flag so deleting input characters doesn't unmount the box
  const [isCustomMode, setIsCustomMode] = useState<boolean>(initialIsCustom);
  const [customModelText, setCustomModelText] = useState<string>(
    initialIsCustom ? llmSettings.model : ''
  );
  const customInputRef = useRef<HTMLInputElement>(null);

  const [availableModels, setAvailableModels] = useState<string[]>(() => {
    const list: string[] = [...CHAT_MODEL_OPTIONS];
    return list;
  });

  useEffect(() => {
    async function fetchModels() {
      if (!draft.apiKey.trim()) return;
      try {
        const models = await apiClient.fetchModels(draft.apiKey.trim());
        if (Array.isArray(models) && models.length > 0) {
          setAvailableModels((prev) => {
            const combined = Array.from(new Set([...models, ...prev]));
            return combined;
          });
        }
      } catch (e: any) {
        console.error('Failed to fetch models for API key:', e);
      }
    }
    const timeout = setTimeout(fetchModels, 1000);
    return () => clearTimeout(timeout);
  }, [draft.apiKey]);

  useEffect(() => {
    setDraft(llmSettings);
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
    setLlmSettings({
      apiKey: draft.apiKey.trim(),
      model: finalModel,
      systemPrompt: draft.systemPrompt.trim(),
    });
    setDraft((s) => ({ ...s, model: finalModel }));
    setSaved(true);
    window.setTimeout(() => setSaved(false), 1200);
  };

  const handleReset = () => {
    setDraft({ ...DEFAULT_LLM_SETTINGS });
    setIsCustomMode(false);
    setCustomModelText('');
  };

  const currentEffectiveModel = isCustomMode ? customModelText.trim() : draft.model.trim();
  const usingDefaults =
    !draft.apiKey.trim() && !currentEffectiveModel && !draft.systemPrompt.trim();

  // If in custom mode, select value remains '__custom__' even if all characters are erased
  const selectValue = isCustomMode ? '__custom__' : (draft.model || '');

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-800 rounded-lg p-6 w-full max-w-lg mx-4 border border-gray-700 shadow-xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white">Assistant settings</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white text-sm"
          >
            Close
          </button>
        </div>

        <p className="text-xs text-gray-400 mb-4">
          Leave fields empty to use the server defaults. Your values are stored only in this browser.
        </p>

        <label className="block text-xs text-gray-400 mb-1">API key (Groq or Gemini)</label>
        <input
          type="password"
          autoComplete="off"
          value={draft.apiKey}
          onChange={(e) => setDraft((s) => ({ ...s, apiKey: e.target.value }))}
          placeholder="Leave blank to use the default key"
          className="w-full bg-gray-700 text-white placeholder-gray-500 px-3 py-2 rounded border border-gray-600 focus:border-blue-500 focus:outline-none mb-4"
        />

        <label className="block text-xs text-gray-400 mb-1">Chat model</label>
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
          className="w-full bg-gray-700 text-white px-3 py-2 rounded border border-gray-600 focus:border-blue-500 focus:outline-none mb-2"
        >
          <option value="">Server default</option>
          {availableModels.map((id) => (
            <option key={id} value={id}>
              {id}
            </option>
          ))}
          <option value="__custom__">Custom model id…</option>
        </select>

        {/* Custom model box: stays open and visible even if all letters are deleted */}
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
              placeholder="e.g. llama-3.3-70b-versatile or gemini-2.5-flash"
              className="w-full bg-gray-800 text-white placeholder-gray-500 px-3 py-2 rounded border border-gray-600 focus:border-blue-500 focus:outline-none text-sm font-mono mb-1.5"
            />
            <p className="text-[11px] text-gray-400">
              Enter the exact name of the model present with your API key.
            </p>
          </div>
        )}

        <p className="text-xs text-gray-500 mb-4">
          Use a function-calling chat model (e.g. llama-3.3-70b-versatile,
          gemini-2.5-flash, or openai/gpt-oss-120b). Whisper, TTS, prompt-guard, and
          groq/compound are not supported for Crystal&apos;s local agent tools.
        </p>

        <label className="block text-xs text-gray-400 mb-1">Personal system prompt</label>
        <textarea
          value={draft.systemPrompt}
          onChange={(e) => setDraft((s) => ({ ...s, systemPrompt: e.target.value }))}
          placeholder="Optional instructions added on top of the default assistant prompt"
          rows={6}
          className="w-full bg-gray-700 text-white placeholder-gray-500 px-3 py-2 rounded border border-gray-600 focus:border-blue-500 focus:outline-none mb-3 resize-y"
        />

        <p className="text-xs text-gray-500 mb-4">
          {usingDefaults
            ? 'Using default API key, model, and system prompt.'
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
