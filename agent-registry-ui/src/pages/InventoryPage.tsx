import { useState, useEffect, useCallback } from 'react';
import type { Agent } from '../types/agent';
import { fetchAgents, stopAgent, deployAgent } from '../api/agents';
import { AgentCard } from '../components/AgentCard';
import { Nav } from '../components/Nav';
import type { Page } from '../components/Nav';

interface Props {
  page: Page;
  onNavigate: (page: Page) => void;
}

function RefreshIcon({ spinning }: { spinning: boolean }) {
  return (
    <svg
      className={`w-4 h-4 ${spinning ? 'animate-spin' : ''}`}
      fill="none"
      stroke="currentColor"
      viewBox="0 0 24 24"
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
        d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
      />
    </svg>
  );
}

export function InventoryPage({ page, onNavigate }: Props) {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadAgents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchAgents();
      setAgents(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadAgents(); }, [loadAgents]);

  const runningCount = agents.filter((a) => a.deployment_state === 'running').length;

  async function handleStop(agentId: string) {
    await stopAgent(agentId);
    await loadAgents();
  }

  async function handleDeploy(agentId: string) {
    await deployAgent(agentId);
    await loadAgents();
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-slate-900 border-b border-slate-800">
        <div className="max-w-7xl mx-auto px-6 py-5 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-white tracking-tight">Agent Registry</h1>
            <p className="text-sm text-slate-400 mt-0.5">
              {loading
                ? 'Loading\u2026'
                : `${agents.length} agent${agents.length !== 1 ? 's' : ''} registered${agents.length > 0 ? ` \u00b7 ${runningCount} running` : ''}`}
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Nav current={page} onNavigate={onNavigate} />
            <div className="w-px h-5 bg-slate-700" />
            <button
              onClick={loadAgents}
              disabled={loading}
              className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-slate-300 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <RefreshIcon spinning={loading} />
              Refresh
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8">
        {error ? (
          <div className="rounded-xl border border-red-200 bg-red-50 px-5 py-4 text-sm text-red-700">
            <strong>Error:</strong> {error}
          </div>
        ) : loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="bg-white rounded-xl border border-gray-200 h-64 animate-pulse" />
            ))}
          </div>
        ) : agents.length === 0 ? (
          <div className="text-center py-24">
            <p className="text-3xl mb-3">&#x1F916;</p>
            <p className="text-gray-600 font-medium">No agents registered</p>
            <p className="text-sm text-gray-400 mt-1">Create your first agent via the API to get started.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {agents.map((agent) => (
              <AgentCard
                key={agent.id}
                agent={agent}
                onStop={() => handleStop(agent.id)}
                onDeploy={() => handleDeploy(agent.id)}
              />
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
