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

export function AgentCard({ agent }: { agent: Agent }) {
  const { name, version, description, status, deployment_state, spec, created_at, updated_at } = agent;
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
      </div>
    </div>
  );
}
