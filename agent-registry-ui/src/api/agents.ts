import type { Agent, AgentCreatePayload } from '../types/agent';

const API_BASE = import.meta.env.VITE_API_URL ?? '';

export async function fetchAgents(): Promise<Agent[]> {
  const res = await fetch(`${API_BASE}/api/v1/agents`);
  if (!res.ok) throw new Error(`Failed to fetch agents: ${res.statusText}`);
  return res.json();
}

export async function deployAgent(agentId: string): Promise<Agent> {
  const res = await fetch(`${API_BASE}/api/v1/agents/${agentId}/deploy`, { method: 'POST' });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    const msg = detail?.detail ?? res.statusText;
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }
  return res.json();
}

export async function stopAgent(agentId: string): Promise<Agent> {
  const res = await fetch(`${API_BASE}/api/v1/agents/${agentId}/stop`, { method: 'POST' });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    const msg = detail?.detail ?? res.statusText;
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }
  return res.json();
}

export async function createAgent(payload: AgentCreatePayload): Promise<Agent> {
  const res = await fetch(`${API_BASE}/api/v1/agents`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    const msg = detail?.detail ?? res.statusText;
    throw new Error(typeof msg === 'string' ? msg : JSON.stringify(msg));
  }
  return res.json();
}
