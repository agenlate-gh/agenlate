export type Agent = {
  id: string
  name: string
  role: string
  color: string
  initials: string
  model: string
}

export const llmModels = [
  { value: 'deepseek-v3', label: 'DeepSeek-V3', tier: 'Cost-efficient reasoning' },
  { value: 'gpt-4o', label: 'GPT-4o', tier: 'Balanced multimodal' },
  { value: 'claude-3.7-sonnet', label: 'Claude 3.7 Sonnet', tier: 'High-accuracy coding' },
  { value: 'gemini-2.0-flash', label: 'Gemini 2.0 Flash', tier: 'Ultra-fast throughput' },
  { value: 'llama-3.3-70b', label: 'Llama 3.3 70B', tier: 'Open-weight workhorse' },
  { value: 'o3-mini', label: 'o3-mini', tier: 'Deliberate reasoning' },
]

export const builderModels = [
  { value: 'gpt-4o-mini', label: 'GPT-4o Mini', tier: 'Fast & lightweight' },
  { value: 'claude-3.5-haiku', label: 'Claude 3.5 Haiku', tier: 'Speed-optimized coding' },
  { value: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash', tier: 'Ultra-fast throughput' },
]

export type BuilderTurn = {
  id: string
  from: 'human' | 'builder'
  text: string
}

export const builderLog: BuilderTurn[] = [
  {
    id: 'b1',
    from: 'human',
    text: 'I need an agent that watches Helm charts and manages canary traffic during rollouts.',
  },
  {
    id: 'b2',
    from: 'builder',
    text: 'Got it. Should it auto-rollback on failed health checks, or only alert the Orquestador?',
  },
  {
    id: 'b3',
    from: 'human',
    text: 'Auto-rollback if error rate crosses 2% over a 60s window.',
  },
  {
    id: 'b4',
    from: 'builder',
    text: 'Drafted instructions with a 2%/60s rollback threshold and a hand-off note to the Orquestador. Refine below or deploy.',
  },
]

export type ChatItem =
  | {
      kind: 'system'
      id: string
      from: string
      action: string
      cedeTo: string
    }
  | {
      kind: 'message'
      id: string
      agentId: string
      cost: string
      time: string
      body: string
    }

export const agents: Agent[] = [
  {
    id: 'supervisor',
    name: 'Orquestador',
    role: 'Orchestration Lead',
    color: '#fff41f',
    initials: 'OR',
    model: 'claude-3.7-sonnet',
  },
  {
    id: 'code-auditor',
    name: 'Code Auditor',
    role: 'Static Analysis',
    color: '#34d399',
    initials: 'CA',
    model: 'deepseek-v3',
  },
  {
    id: 'security-analyst',
    name: 'Security Analyst',
    role: 'Threat Modeling',
    color: '#f472b6',
    initials: 'SA',
    model: 'gpt-4o',
  },
  {
    id: 'infra-engineer',
    name: 'Infra Engineer',
    role: 'Deployment Ops',
    color: '#60a5fa',
    initials: 'IE',
    model: 'gemini-2.0-flash',
  },
]

export const blankTemplateAgents: Agent[] = [
  {
    id: 'supervisor',
    name: 'Orquestador',
    role: 'Orchestration Lead',
    color: '#fff41f',
    initials: 'OR',
    model: 'claude-3.7-sonnet',
  },
  {
    id: 'agent-1',
    name: 'Agente 1',
    role: 'Custom Agent',
    color: '#34d399',
    initials: 'A1',
    model: 'deepseek-v3',
  },
]

export const emptyConversation: ChatItem[] = []

export const rooms = [
  { id: '1', name: 'Production Deployment Analyzer', active: true, cost: '$4.271' },
  { id: '2', name: 'Smart Contract Auditor', active: false, cost: '$12.04' },
  { id: '3', name: 'Data Pipeline Monitor', active: false, cost: '$0.982' },
  { id: '4', name: 'Frontend Regression Sweep', active: false, cost: '$2.115' },
]

export const conversation: ChatItem[] = [
  {
    kind: 'message',
    id: 'm1',
    agentId: 'supervisor',
    cost: '$0.008 USD',
    time: '14:02',
    body: 'Received deployment manifest for release candidate rc-2.14.0. I will route the workspace through static analysis first, then threat modeling. Context loaded: 3 services, 41 changed files.',
  },
  {
    kind: 'system',
    id: 's1',
    from: 'Orquestador Orchestrating...',
    action: 'Analyzing workspace context',
    cedeTo: 'Code Auditor',
  },
  {
    kind: 'message',
    id: 'm2',
    agentId: 'code-auditor',
    cost: '$0.042 USD',
    time: '14:03',
    body: 'Completed static pass across the diff. Found 2 blocking issues: an unhandled promise rejection in payments/webhook.ts:88 and a missing null guard in auth/session.ts:212. Cyclomatic complexity is within budget elsewhere. Recommending a fix before the security review proceeds.',
  },
  {
    kind: 'system',
    id: 's2',
    from: 'Orquestador Orchestrating...',
    action: 'Merging audit findings into shared memory',
    cedeTo: 'Security Analyst',
  },
  {
    kind: 'message',
    id: 'm3',
    agentId: 'security-analyst',
    cost: '$0.061 USD',
    time: '14:05',
    body: 'Threat model updated. The webhook handler flagged by the Code Auditor also lacks signature verification — this is exploitable. Classifying as HIGH severity. No secrets detected in the changed environment files. Awaiting the infra readiness check before sign-off.',
  },
  {
    kind: 'system',
    id: 's3',
    from: 'Orquestador Orchestrating...',
    action: 'Escalating HIGH severity finding',
    cedeTo: 'Infra Engineer',
  },
]

export const streamingMessage = {
  agentId: 'infra-engineer',
  cost: '$0.037 USD',
  time: '14:06',
  fullText:
    'Rollout gate held. Blue/green slots are provisioned and healthy, but I am blocking promotion until the HIGH severity webhook signature issue is resolved. Canary traffic is capped at 0%. Once the patch lands I can resume the staged rollout in under 90 seconds.',
}
