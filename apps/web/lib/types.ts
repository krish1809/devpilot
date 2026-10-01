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
  target_path: string;
  description: string | null;
  created_at: string;
}

export interface TaskCreateInput {
  repo_url: string;
  base_commit?: string | null;
  base_branch?: string | null;
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
  base_commit: string | null;
  diff: string | null;
  test_passed: boolean | null;
  sandbox_output: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
  events: RunEvent[];
  pull_request: PullRequest | null;
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
  target_path: string;
}
