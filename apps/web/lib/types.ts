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
