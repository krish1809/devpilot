export interface User {
  id: number;
  email: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Project {
  id: number;
  owner_id: number;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface Token {
  access_token: string;
  token_type: string;
}

export interface AuditLog {
  id: number;
  user_id: number | null;
  action: string;
  detail: string | null;
  ip_address: string | null;
  created_at: string;
}

export interface ProjectCreateInput {
  name: string;
  description?: string | null;
}

export interface ProjectUpdateInput {
  name?: string;
  description?: string | null;
}

// --- Agent (walking skeleton) ---
export interface Task {
  id: number;
  owner_id: number;
  repo_url: string;
  base_commit: string | null;
  base_branch: string | null;
  repo_full_name: string | null;
  issue_number: number | null;
  issue_title: string | null;
  issue_url: string | null;
  test_command: string;
  target_path: string | null;
  description: string | null;
  created_at: string;
}

export interface TaskCreateInput {
  repo_url: string;
  base_commit?: string | null;
  base_branch?: string | null;
  test_command: string;
  target_path?: string | null;
  description?: string | null;
}

export interface RunEvent {
  id: number;
  seq: number;
  stage: string;
  message: string;
  created_at: string;
}

export interface PullRequest {
  id: number;
  url: string;
  number: number | null;
  status: string;
  created_at: string;
}

export type RunStatus =
  | "running"
  | "validated"
  | "test_failed"
  | "error"
  | "approved"
  | "rejected"
  | "published"
  | "publish_failed"
  | "review_failed"
  | "cancelled";

export interface AgentRun {
  id: number;
  task_id: number;
  status: RunStatus;
  model: string;
  base_commit: string | null;
  plan: string | null;
  attempts: number;
  llm_calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  cancel_requested: boolean;
  use_rag: boolean;
  target_path: string | null;
  retrieval: RunRetrieval | null;
  diff: string | null;
  test_passed: boolean | null;
  sandbox_output: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
  events: RunEvent[];
  pull_request: PullRequest | null;
}

export interface RetrievedChunk {
  path: string;
  start_line: number;
  end_line: number;
  score: number;
}

export interface RunRetrieval {
  index: { id: number; files: number; chunks: number; built_now: boolean; model: string };
  boosted_paths: string[];
  candidates: string[];
  context: RetrievedChunk[];
}

export interface RunSummary {
  id: number;
  task_id: number;
  status: RunStatus;
  model: string;
  test_passed: boolean | null;
  attempts: number;
  created_at: string;
  updated_at: string;
}

export interface RunCheckpoint {
  checkpoint_id: string;
  step: number;
  next: string[];
  created_at: string | null;
  attempts: number;
  test_passed: boolean | null;
  llm_calls: number;
  waiting_for_approval: boolean;
}

// --- GitHub (Phase 4) ---
export interface GitHubRepo {
  full_name: string;
  private: boolean;
  default_branch: string;
  description: string | null;
  html_url: string;
  open_issues_count: number;
  can_push: boolean;
}

export interface GitHubIssue {
  number: number;
  title: string;
  state: string;
  html_url: string;
  labels: string[];
  created_at: string;
}

export interface GitHubTree {
  repo_full_name: string;
  ref: string;
  commit_sha: string;
  files: string[];
}

export interface TaskFromIssueInput {
  repo_full_name: string;
  issue_number: number;
  base_branch?: string | null;
  test_command: string;
  target_path?: string | null;
}

// --- Benchmarks (Phase 7) ---
export interface EvalConfigSummary {
  config: string;
  generated: number;
  scored: number;
  resolved: number;
  resolve_rate: number | null;
  ci95: [number, number] | null;
  infra_failures: string[];
  with_patch: number;
  localized: number;
  avg_tokens: number;
  avg_llm_calls: number;
  avg_seconds: number;
}

export interface EvalResult {
  instance_id: string;
  repo: string;
  config: string;
  agent_run_id: number | null;
  status: string;
  target_path: string | null;
  gold_path: string | null;
  localized: boolean | null;
  resolved: boolean | null;
  score_detail: Record<string, unknown> | null;
  error: string | null;
  llm_calls: number;
  prompt_tokens: number;
  completion_tokens: number;
  seconds: number;
  patch: string | null;
}

export interface EvalRunSummary {
  id: number;
  name: string;
  dataset: string;
  model: string;
  instance_count: number;
  configs: string[];
  settings: Record<string, unknown>;
  created_at: string;
  summary: EvalConfigSummary[];
}

export interface EvalRunDetail extends EvalRunSummary {
  instance_ids: string[];
  results: EvalResult[];
}
