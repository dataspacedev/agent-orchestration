import type { DeploymentState } from '../types/agent';

const DEPLOYMENT_STYLES: Record<DeploymentState, string> = {
  running: 'bg-green-100 text-green-700 border-green-200',
  stopped: 'bg-amber-100 text-amber-700 border-amber-200',
  deleted: 'bg-red-100 text-red-700 border-red-200',
};

const DEPLOYMENT_DOT: Record<DeploymentState, string> = {
  running: 'bg-green-500',
  stopped: 'bg-amber-400',
  deleted: 'bg-red-400',
};

export function DeploymentBadge({ state }: { state: DeploymentState }) {
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border ${DEPLOYMENT_STYLES[state]}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${DEPLOYMENT_DOT[state]}`} />
      {state}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  const isActive = status === 'active';
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${isActive ? 'bg-emerald-50 text-emerald-700 border-emerald-200' : 'bg-gray-100 text-gray-500 border-gray-200'}`}>
      {status}
    </span>
  );
}
