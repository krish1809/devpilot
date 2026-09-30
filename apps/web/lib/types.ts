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
  test_command: string;
  target_path: string;
  description: string | null;
  created_at: string;
}

export interface TaskCreateInput {
  repo_url: string;
  base_commit?: string | null;
  test_command: string;
  target_path: string;
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
  | "publish_failed";

export interface AgentRun {
  id: number;
  task_id: number;
  status: RunStatus;
  model: string;
  diff: string | null;
  test_passed: boolean | null;
  sandbox_output: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
  events: RunEvent[];
  pull_request: PullRequest | null;
}
