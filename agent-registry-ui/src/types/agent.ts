export type DeploymentState = 'running' | 'stopped' | 'deleted';

export interface ResourceSpec {
  cpu?: string;
  memory?: string;
}

export interface ResourceRequirements {
  requests?: ResourceSpec;
  limits?: ResourceSpec;
}

export interface ScalingConfig {
  min_replicas?: number;
  max_replicas?: number;
  target_cpu_utilization_percentage?: number;
}

export interface AgentSpec {
  image: string;
  port?: number;
  secret_name?: string;
  config?: Record<string, string>;
  resources?: ResourceRequirements;
  scaling?: ScalingConfig;
}

export interface Agent {
  id: string;
  name: string;
  version: string;
  description?: string;
  status: string;
  deployment_state: DeploymentState;
  spec: AgentSpec;
  created_at: string;
  updated_at: string;
}
