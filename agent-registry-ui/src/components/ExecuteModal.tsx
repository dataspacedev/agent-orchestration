import { useState, useEffect, useRef } from 'react';
import type { Agent } from '../types/agent';

interface Props {
  agent: Agent;
  onClose: () => void;
}

interface SearchResult {
  query: string;
  html: string;
  elapsed_ms: number;
}

function ExternalLinkIcon() {
  return (
    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
        d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
    </svg>
  );
}

export function ExecuteModal({ agent, onClose }: Props) {
  const defaultUrl = agent.spec.config?.AGENT_URL ?? '';
  const [agentUrl, setAgentUrl] = useState(defaultUrl);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SearchResult | null>(null);
  const [tab, setTab] = useState<'rendered' | 'source'>('rendered');
  const queryRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    queryRef.current?.focus();
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  async function handleSearch() {
    const q = query.trim();
    const url = agentUrl.trim().replace(/\/$/, '');
    if (!q || !url) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const res = await fetch(`${url}/api/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: q }),
      });
      const data = await res.json();
      if (!res.ok || data.error) throw new Error(data.error ?? res.statusText);
      setResult(data as SearchResult);
      setTab('rendered');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }

  const standaloneUrl = agentUrl.trim() ? `${agentUrl.trim().replace(/\/$/, '')}/ui` : null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

      <div className="relative bg-white rounded-xl shadow-2xl w-full max-w-4xl flex flex-col max-h-[90vh]">
        {/* header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 shrink-0">
          <div>
            <h2 className="text-base font-semibold text-gray-900">Execute Agent</h2>
            <p className="text-xs text-gray-400 mt-0.5 font-mono">{agent.name} · v{agent.version}</p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-600 transition-colors p-1 rounded-lg hover:bg-gray-100">
            <CloseIcon />
          </button>
        </div>

        {/* body */}
        <div className="px-6 py-5 space-y-4 overflow-y-auto flex-1">
          {/* agent URL */}
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1.5">Agent URL</label>
            <div className="flex gap-2">
              <input
                type="url"
                value={agentUrl}
                onChange={(e) => setAgentUrl(e.target.value)}
                placeholder="http://localhost:18081"
                className="flex-1 text-sm font-mono bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              />
              {standaloneUrl && (
                <a
                  href={standaloneUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium text-indigo-600 border border-indigo-200 bg-indigo-50 rounded-lg hover:bg-indigo-100 transition-colors whitespace-nowrap"
                >
                  Open UI <ExternalLinkIcon />
                </a>
              )}
            </div>
            {!agentUrl && (
              <p className="mt-1.5 text-xs text-amber-600">
                Port-forward the agent first:{' '}
                <code className="font-mono bg-amber-50 px-1 py-0.5 rounded">make port-forward</code>
                {' '}in <code className="font-mono bg-amber-50 px-1 py-0.5 rounded">serp-agent/</code>,
                then use <code className="font-mono bg-amber-50 px-1 py-0.5 rounded">http://localhost:18081</code>.
              </p>
            )}
            {agentUrl && agentUrl.includes('.svc.cluster.local') && (
              <p className="mt-1.5 text-xs text-amber-600">
                This is an in-cluster URL. Replace with your port-forwarded address (e.g.,{' '}
                <code className="font-mono bg-amber-50 px-1 py-0.5 rounded">http://localhost:18081</code>)
                to reach the agent from your browser.
              </p>
            )}
          </div>

          {/* query */}
          <div>
            <label className="block text-xs font-medium text-gray-500 mb-1.5">Search Query</label>
            <div className="flex gap-2">
              <input
                ref={queryRef}
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleSearch(); }}
                placeholder="python asyncio tutorial"
                className="flex-1 text-sm bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent"
              />
              <button
                onClick={handleSearch}
                disabled={loading || !query.trim() || !agentUrl.trim()}
                className="px-4 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:bg-gray-300 disabled:cursor-not-allowed rounded-lg transition-colors whitespace-nowrap"
              >
                {loading ? 'Searching…' : 'Search'}
              </button>
            </div>
          </div>

          {/* loading */}
          {loading && (
            <div className="flex items-center gap-2.5 text-sm text-slate-500 py-1">
              <svg className="w-4 h-4 animate-spin text-indigo-500 shrink-0" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              Scraping… expect 10–20 seconds
            </div>
          )}

          {/* error */}
          {error && (
            <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}

          {/* results */}
          {result && (
            <div>
              <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
                <div className="flex items-center gap-1.5 text-xs text-gray-500">
                  <span className="bg-gray-100 border border-gray-200 rounded px-2 py-0.5 font-mono">
                    &ldquo;{result.query}&rdquo;
                  </span>
                  <span className="bg-gray-100 border border-gray-200 rounded px-2 py-0.5 font-mono">
                    {(result.elapsed_ms / 1000).toFixed(1)}s
                  </span>
                </div>
                <div className="flex border border-gray-200 rounded-lg overflow-hidden text-xs">
                  <button
                    onClick={() => setTab('rendered')}
                    className={`px-3 py-1 transition-colors ${tab === 'rendered' ? 'bg-gray-100 font-medium text-gray-700' : 'text-gray-500 hover:bg-gray-50'}`}
                  >
                    Rendered
                  </button>
                  <button
                    onClick={() => setTab('source')}
                    className={`px-3 py-1 transition-colors border-l border-gray-200 ${tab === 'source' ? 'bg-gray-100 font-medium text-gray-700' : 'text-gray-500 hover:bg-gray-50'}`}
                  >
                    Source
                  </button>
                </div>
              </div>

              {tab === 'rendered' ? (
                <iframe
                  srcDoc={result.html}
                  sandbox="allow-same-origin allow-scripts allow-forms"
                  title="Search results"
                  className="w-full h-96 border border-gray-200 rounded-lg bg-white"
                />
              ) : (
                <pre className="w-full h-96 overflow-auto border border-gray-200 rounded-lg bg-gray-50 p-4 text-xs font-mono text-gray-700 whitespace-pre-wrap break-all">
                  {result.html}
                </pre>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
