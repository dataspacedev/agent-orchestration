import type { Agent } from '../types/agent';

const API_BASE = import.meta.env.VITE_API_URL ?? '';

export async function fetchAgents(): Promise<Agent[]> {
  const res = await fetch(`${API_BASE}/api/v1/agents`);
  if (!res.ok) throw new Error(`Failed to fetch agents: ${res.statusText}`);
  return res.json();
}
