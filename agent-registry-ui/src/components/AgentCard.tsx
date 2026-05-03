import { useState } from 'react';
import type { Agent, ResourceRequirements } from '../types/agent';
import { DeploymentBadge, StatusBadge } from './StatusBadge';

function formatDate(iso: string): string {
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', year: 'numeric' }).format(new Date(iso));
}

function ResourceChip({ label, resources }: { label: string; resources?: ResourceRequirements }) {
  const req = label === 'CPU' ? resources?.requests?.cpu : resources?.requests?.memory;
  const lim = label === 'CPU' ? resources?.limits?.cpu : resources?.limits?.memory;
  if (!req && !lim) return null;
  return (
    <div className="bg-gray-50 rounded-lg px-3 py-2">
      <p className="text-xs font-medium text-gray-500 mb-1">{label}</p>
      {req && <p className="text-xs text-gray-600 font-mono">req: {req}</p>}
      {lim && <p className="text-xs text-gray-600 font-mono">lim: {lim}</p>}
    </div>
  );
}

export function AgentCard({
  agent,
  onStop,
  onDeploy,
}: {
  agent: Agent;
  onStop?: () => Promise<void>;
  onDeploy?: () => Promise<void>;
}) {
  const [stopping, setStopping] = useState(false);
  const [deploying, setDeploying] = useState(false);
  const { name, version, description, status, deployment_state, spec, created_at, updated_at } = agent;

  async function handleStop() {
    if (!onStop) return;
    setStopping(true);
    try { await onStop(); } finally { setStopping(false); }
  }

  async function handleDeploy() {
    if (!onDeploy) return;
    setDeploying(true);
    try { await onDeploy(); } finally { setDeploying(false); }
  }
  const { image, port, resources, scaling } = spec;
  const hasResources = resources?.requests || resources?.limits;
  const hasScaling = scaling?.min_replicas !== undefined || scaling?.max_replicas !== undefined;
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm hover:shadow-md transition-shadow duration-200 flex flex-col overflow-hidden">
      <div className="px-5 pt-5 pb-4">
        <div className="flex items-start justify-between gap-2 mb-2">
          <h3 className="text-gray-900 font-semibold text-base leading-tight">{name}</h3>
          <span className="text-xs font-mono text-gray-400 bg-gray-50 border border-gray-200 rounded px-2 py-0.5 shrink-0">
            {version}
          </span>
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <DeploymentBadge state={deployment_state} />
          <StatusBadge status={status} />
        </div>
        {description && (
          <p className="mt-3 text-sm text-gray-500 leading-relaxed line-clamp-2">{description}</p>
        )}
      </div>

      <div className="border-t border-gray-100" />

      <div className="px-5 py-4 flex-1 space-y-4">
        <div className="space-y-2">
          <div className="flex items-start gap-2">
            <span className="text-xs text-gray-400 w-10 shrink-0 pt-0.5">Image</span>
            <span className="font-mono text-xs text-gray-700 break-all leading-relaxed">{image}</span>
          </div>
          {port !== undefined && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-400 w-10 shrink-0">Port</span>
              <span className="font-mono text-xs text-gray-700">{port}</span>
            </div>
          )}
          {spec.secret_name && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-400 w-10 shrink-0">Secret</span>
              <span className="font-mono text-xs text-gray-700">{spec.secret_name}</span>
            </div>
          )}
        </div>

        {hasResources && (
          <div>
            <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">Resources</p>
            <div className="grid grid-cols-2 gap-2">
              <ResourceChip label="CPU" resources={resources} />
              <ResourceChip label="Memory" resources={resources} />
            </div>
          </div>
        )}

        {hasScaling && (
          <div>
            <p className="text-xs font-medium text-gray-400 uppercase tracking-wide mb-2">Scaling</p>
            <div className="flex items-center gap-3 text-xs text-gray-600 flex-wrap">
              {scaling?.min_replicas !== undefined && scaling?.max_replicas !== undefined && (
                <span className="bg-gray-50 border border-gray-200 rounded px-2 py-1 font-mono">
                  {scaling.min_replicas}–{scaling.max_replicas} replicas
                </span>
              )}
              {scaling?.target_cpu_utilization_percentage !== undefined && (
                <span className="bg-gray-50 border border-gray-200 rounded px-2 py-1 font-mono">
                  {scaling.target_cpu_utilization_percentage}% CPU
                </span>
              )}
            </div>
          </div>
        )}
      </div>

      <div className="border-t border-gray-100 px-5 py-3 bg-gray-50">
        <div className="flex items-center justify-between text-xs text-gray-400">
          <span>Created {formatDate(created_at)}</span>
          <span>Updated {formatDate(updated_at)}</span>
        </div>
        {deployment_state === 'running' && onStop && (
          <div className="mt-3">
            <button
              onClick={handleStop}
              disabled={stopping}
              className="w-full inline-flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs font-medium text-red-600 bg-white hover:bg-red-50 border border-red-200 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {stopping ? (
                <>
                  <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Stopping…
                </>
              ) : (
                <>
                  <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                    <rect x="5" y="5" width="10" height="10" rx="1" />
                  </svg>
                  Stop agent
                </>
              )}
            </button>
          </div>
        )}
        {deployment_state === 'stopped' && onDeploy && (
          <div className="mt-3">
            <button
              onClick={handleDeploy}
              disabled={deploying}
              className="w-full inline-flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs font-medium text-emerald-700 bg-white hover:bg-emerald-50 border border-emerald-200 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {deploying ? (
                <>
                  <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Deploying…
                </>
              ) : (
                <>
                  <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                    <path d="M6.3 2.841A1.5 1.5 0 004 4.11v11.78a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z" />
                  </svg>
                  Deploy agent
                </>
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
