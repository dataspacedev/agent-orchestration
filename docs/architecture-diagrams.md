# Agent Orchestration Architecture Diagrams

This document captures the high-level system view and the main dynamic flows described in the planning docs for the agent orchestration platform.

## High-Level Architecture

```mermaid
flowchart TB
  subgraph UL [User Layer]
    user["Domain UI, MCP Client, A2A Caller"]
  end

  subgraph DL [Agent Stack and Domain Layer]
    stack["Domain Stack Resources: AgentStack, AgentPolicy, AgentRubric"]
    orchestrator["Domain Orchestrator Agent"]
    domain_agents["Domain Specialist Agents"]
  end

  subgraph FL [Platform Feature Layer]
    sdk["core-tools-lib"]
    resolver["skill-resolver sidecar"]
    announcer["registry-announcer sidecar"]
    directory["AgentDirectory CRD"]
    platform_agents["Platform Agents"]
    task_store["task-store service"]
    mcp["MCP Aggregator"]
  end

  subgraph AL [Platform Administration Layer]
    controller["agent-controller"]
    cluster_policy["ClusterAgentPolicy"]
    access_policy["AgentAccessPolicy"]
    inventory["inventory-api"]
    governance["RBAC, Promotion, Drift Detection, SLOs"]
  end

  user --> orchestrator
  user --> mcp

  stack --> orchestrator
  stack --> domain_agents
  orchestrator --> sdk
  domain_agents --> sdk

  orchestrator --> resolver
  resolver --> directory
  announcer --> directory
  announcer --> inventory

  orchestrator --> platform_agents
  domain_agents --> task_store
  orchestrator --> task_store
  platform_agents --> task_store
  mcp --> directory
  mcp --> platform_agents
  mcp --> domain_agents

  controller --> stack
  controller --> orchestrator
  controller --> domain_agents
  controller --> resolver
  controller --> announcer
  controller --> platform_agents

  cluster_policy --> controller
  cluster_policy --> sdk
  access_policy --> resolver
  governance --> controller
```

### Reading the diagram

- The user layer talks to domain surfaces, not cluster primitives.
- Domain stacks own business workflow and call shared platform capabilities through platform-managed runtime components.
- Platform features carry runtime traffic.
- Platform administration governs policy, lifecycle, and compliance, but should stay out of runtime hot paths where possible.

## Sequence: Agent Deployment and Registration

This sequence shows how a domain agent becomes a running workload and how it is published into both the runtime and management planes.

```mermaid
sequenceDiagram
  autonumber
  actor DomainTeam
  participant K8s as Kubernetes API
  participant Controller as agent-controller
  participant ClusterPolicy as ClusterAgentPolicy
  participant Pod as Agent Pod
  participant Agent as agent container
  participant Announcer as registry-announcer
  participant Directory as AgentDirectory
  participant Inventory as inventory-api

  DomainTeam->>K8s: Apply Agent / AgentStack / AgentPolicy manifests
  K8s-->>Controller: Watch create or update events
  Controller->>ClusterPolicy: Read cluster defaults
  Controller->>K8s: Reconcile Deployment, Service, SA, ConfigMap, HPA
  Note over Controller,K8s: Controller injects sidecars and env defaults
  K8s-->>Pod: Schedule pod
  Pod->>Agent: Start main agent container
  Pod->>Announcer: Start registry-announcer sidecar
  Announcer->>Agent: Read capability card and readiness
  Announcer->>Directory: Patch runtime entry
  Announcer->>Inventory: Best-effort management registration
  Note over Announcer,Directory: AgentDirectory write is the primary runtime publication path
  Directory-->>Controller: Updated runtime state visible via watch
  Pod-->>DomainTeam: Pod becomes Ready
```

### Deployment intent

- The controller owns lifecycle and sidecar injection.
- `registry-announcer` bridges the running pod into both the runtime plane and the management plane.
- `AgentDirectory` is the authoritative runtime publication path.

## Sequence: Runtime Cross-Stack A2A Flow

This is the core request path for a domain orchestrator calling a shared platform capability.

```mermaid
sequenceDiagram
  autonumber
  actor User
  participant Orchestrator as Domain Orchestrator
  participant Resolver as skill-resolver
  participant Directory as AgentDirectory
  participant Access as AgentAccessPolicy
  participant PlatformAgent as Platform Agent
  participant JWKS as OIDC JWKS / token cache
  participant TaskStore as task-store

  User->>Orchestrator: Start domain workflow
  Orchestrator->>Resolver: GET /resolve?skill=parse_document&minVersion=1.0&stackId=legal-stack
  Resolver->>Directory: Find Ready endpoint for requested skill
  Resolver->>Access: Verify stack may call the skill
  alt Access granted and skill available
    Resolver-->>Orchestrator: Return URL and runtime headers
    Orchestrator->>PlatformAgent: A2A request with Bearer SA token, X-Stack-Id, optional X-Agent-Rubric
    PlatformAgent->>JWKS: Validate token and audience
    Note over PlatformAgent: StackIsolationMiddleware enforces stack identity, rate limits, and audit logging
    PlatformAgent->>TaskStore: Read or persist task state
    PlatformAgent-->>Orchestrator: Capability result
    Orchestrator-->>User: Domain response
  else Access denied
    Resolver-->>Orchestrator: 403 forbidden
    Orchestrator-->>User: Domain workflow handles denial
  else Skill unavailable
    Resolver-->>Orchestrator: 503 unavailable with retry guidance
    Orchestrator-->>User: Domain workflow degrades gracefully
  end
```

### Runtime intent

- Skill resolution and access control happen before the network call to the platform agent.
- Authentication and multi-tenant enforcement happen again at the platform agent boundary.
- Task state is centralized in `task-store`, not in individual agent pods.

## Sequence: MCP Aggregator Refresh and Tool Invocation

This sequence shows how the aggregated MCP surface stays current while routing user tool calls to live agents.

```mermaid
sequenceDiagram
  autonumber
  actor Client as MCP Client
  participant Directory as AgentDirectory
  participant Aggregator as MCP Aggregator
  participant Agent as Backing Agent

  Directory-->>Aggregator: Watch add or update event
  Aggregator->>Aggregator: Rebuild versioned tool registry
  Note over Aggregator: New requests use the new registry generation while in-flight calls finish on the old generation
  Client->>Aggregator: tools/list
  Aggregator-->>Client: Versioned tool set
  Client->>Aggregator: tools/call agent_v1__tool
  Aggregator->>Agent: Proxy tool call to live backing agent
  Agent-->>Aggregator: Tool result
  Aggregator-->>Client: Tool result
```

### MCP intent

- The MCP surface is derived from live runtime state, not static config.
- Versioned tool names reduce schema ambiguity during agent upgrades.
- Registry swaps are generation-based so updates do not interrupt in-flight tool calls.

## Source Basis

- `.planning/PROJECT.md`
- `.planning/REQUIREMENTS.md`
- `.planning/ROADMAP.md`
- `.planning/research/ARCHITECTURE.md`
- `.planning/research/FEATURES.md`
- `.planning/research/SUMMARY.md`
- `docs/federated-agent-stack.md`
