import { useState, useEffect } from 'react';
import axios from 'axios';
import { Globe, RefreshCw, Camera, AlertTriangle, Layers, ExternalLink } from 'lucide-react';

interface BrowserState {
  url?: string;
  title?: string;
  a11y_tree?: string;
  telemetry?: {
    has_errors: boolean;
    console_errors: Array<{ type: string; text: string; time: string }>;
    network_failures: Array<{ url: string; status: number; status_text: string; time: string }>;
  };
}

export default function BrowserView() {
  const [url, setUrl] = useState('http://localhost:5173');
  const [browserState, setBrowserState] = useState<BrowserState | null>(null);
  const [screenshotData, setScreenshotData] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<'preview' | 'a11y' | 'errors'>('preview');
  const [loading, setLoading] = useState(false);

  const fetchState = async () => {
    try {
      const res = await axios.get('/api/browser/state');
      setBrowserState(res.data);
      if (res.data.url) setUrl(res.data.url);
    } catch (e) {
      // ignore if server starting
    }
  };

  const handleNavigate = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!url) return;
    setLoading(true);
    try {
      const res = await axios.post('/api/browser/navigate', { url });
      setBrowserState(res.data);
      await takeScreenshot();
    } catch (err: any) {
      alert(`Navigation failed: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const takeScreenshot = async () => {
    try {
      const res = await axios.get('/api/browser/screenshot');
      if (res.data.base64) {
        setScreenshotData(`data:${res.data.mime_type};base64,${res.data.base64}`);
      }
    } catch (e) {
      // ignore
    }
  };

  useEffect(() => {
    fetchState();
  }, []);

  const errorCount =
    (browserState?.telemetry?.console_errors?.length || 0) +
    (browserState?.telemetry?.network_failures?.length || 0);

  return (
    <div className="flex flex-col h-full bg-[#181825] text-gray-200">
      {/* Navigation bar */}
      <form
        onSubmit={handleNavigate}
        className="flex items-center gap-2 border-b border-gray-800 bg-[#11111b] px-3 py-1.5 text-xs"
      >
        <Globe size={14} className="text-blue-400 shrink-0" />
        <input
          type="text"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="http://localhost:5173"
          className="flex-1 bg-[#181825] border border-gray-700 rounded px-2.5 py-1 text-gray-100 placeholder-gray-500 font-mono text-xs focus:outline-none focus:border-blue-500"
        />
        <button
          type="submit"
          disabled={loading}
          className="px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white rounded font-medium disabled:opacity-50"
        >
          {loading ? 'Loading...' : 'Go'}
        </button>
        <button
          type="button"
          onClick={takeScreenshot}
          className="p-1.5 text-gray-400 hover:text-gray-100 hover:bg-[#1e1e2e] rounded"
          title="Capture Viewport Screenshot"
        >
          <Camera size={14} />
        </button>
        <button
          type="button"
          onClick={handleNavigate}
          className="p-1.5 text-gray-400 hover:text-gray-100 hover:bg-[#1e1e2e] rounded"
          title="Refresh"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
        </button>
        {browserState?.url && (
          <a
            href={browserState.url}
            target="_blank"
            rel="noreferrer"
            className="p-1.5 text-gray-400 hover:text-gray-100 hover:bg-[#1e1e2e] rounded"
            title="Open in system browser"
          >
            <ExternalLink size={14} />
          </a>
        )}
      </form>

      {/* Sub-tabs header */}
      <div className="flex items-center justify-between border-b border-gray-800 bg-[#181825] px-3 py-1 text-xs">
        <div className="flex items-center gap-3">
          <button
            onClick={() => setActiveTab('preview')}
            className={`flex items-center gap-1.5 py-1 font-medium ${
              activeTab === 'preview' ? 'text-blue-400 border-b-2 border-blue-500' : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            <Camera size={13} />
            <span>Visual Viewport</span>
          </button>
          <button
            onClick={() => setActiveTab('a11y')}
            className={`flex items-center gap-1.5 py-1 font-medium ${
              activeTab === 'a11y' ? 'text-blue-400 border-b-2 border-blue-500' : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            <Layers size={13} />
            <span>Accessibility Tree (A11y)</span>
          </button>
          <button
            onClick={() => setActiveTab('errors')}
            className={`flex items-center gap-1.5 py-1 font-medium ${
              activeTab === 'errors' ? 'text-blue-400 border-b-2 border-blue-500' : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            <AlertTriangle size={13} className={errorCount > 0 ? 'text-red-400' : ''} />
            <span>Telemetry & Errors</span>
            {errorCount > 0 && (
              <span className="px-1.5 py-0.2 rounded-full bg-red-900/60 text-red-300 text-[10px] font-bold">
                {errorCount}
              </span>
            )}
          </button>
        </div>

        {browserState?.title && (
          <span className="text-gray-500 text-[11px] truncate max-w-sm">
            {browserState.title}
          </span>
        )}
      </div>

      {/* Tab body */}
      <div className="flex-1 overflow-auto p-3">
        {activeTab === 'preview' && (
          <div className="flex flex-col items-center justify-center min-h-full">
            {screenshotData ? (
              <img
                src={screenshotData}
                alt="Browser Viewport"
                className="max-h-full max-w-full rounded border border-gray-700 shadow-lg object-contain"
              />
            ) : (
              <div className="text-center text-gray-500 space-y-2">
                <Globe size={36} className="mx-auto text-gray-600" />
                <p>No browser session active or screenshot taken.</p>
                <button
                  onClick={() => handleNavigate()}
                  className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded text-xs"
                >
                  Launch Headed Browser
                </button>
              </div>
            )}
          </div>
        )}

        {activeTab === 'a11y' && (
          <pre className="text-xs font-mono text-gray-300 bg-[#11111b] p-3 rounded border border-gray-800 whitespace-pre-wrap leading-relaxed">
            {browserState?.a11y_tree || 'No page tree extracted yet. Navigate to a URL above.'}
          </pre>
        )}

        {activeTab === 'errors' && (
          <div className="space-y-4 text-xs font-mono">
            <div>
              <h4 className="text-gray-400 font-semibold mb-2 flex items-center gap-1">
                <span>Console Errors & Exceptions</span>
                <span className="text-gray-500">
                  ({browserState?.telemetry?.console_errors?.length || 0})
                </span>
              </h4>
              {browserState?.telemetry?.console_errors?.length ? (
                <div className="space-y-1">
                  {browserState.telemetry.console_errors.map((err, i) => (
                    <div key={i} className="p-2 bg-red-950/40 border border-red-800/60 rounded text-red-200">
                      <span className="text-gray-500 text-[10px] mr-2">[{err.time}]</span>
                      <span>{err.text}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-gray-500">No console errors logged.</p>
              )}
            </div>

            <div>
              <h4 className="text-gray-400 font-semibold mb-2 flex items-center gap-1">
                <span>Network 4xx/5xx Failures</span>
                <span className="text-gray-500">
                  ({browserState?.telemetry?.network_failures?.length || 0})
                </span>
              </h4>
              {browserState?.telemetry?.network_failures?.length ? (
                <div className="space-y-1">
                  {browserState.telemetry.network_failures.map((fail, i) => (
                    <div key={i} className="p-2 bg-yellow-950/40 border border-yellow-800/60 rounded text-yellow-200">
                      <span className="text-gray-500 text-[10px] mr-2">[{fail.time}]</span>
                      <span className="font-bold mr-2">{fail.status} {fail.status_text}</span>
                      <span className="text-gray-300">{fail.url}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-gray-500">No failed network requests.</p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
