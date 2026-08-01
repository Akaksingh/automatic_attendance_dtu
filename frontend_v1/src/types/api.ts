export type Role = "admin" | "teacher" | "student";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  profile_image_url: string | null;
}

export interface Group {
  id: string;
  name: string;
  join_code: string;
  owner_id: string;
  archived_at: string | null;
  created_at: string;
}

export interface PageMeta { page: number; page_size: number; total: number; pages: number; }
export interface Page<T> { items: T[]; meta: PageMeta; }

export interface RosterStudent {
  student_id: string;
  user_id: string;
  roll_no: string;
  full_name: string;
  email: string;
  profile_image_url: string | null;
  joined_at: string;
}

export type SessionState = "created" | "processing" | "review" | "finalized" | "failed";
export type AttendanceStatus = "present" | "absent";

export interface AttendanceRecord { id: string; student_id: string; status: AttendanceStatus; marked_at: string; }
export interface ClassSession {
  id: string;
  group_id: string;
  created_by_id: string;
  state: SessionState;
  started_at: string;
  finalized_at: string | null;
  processing_total: number;
  processing_completed: number;
  processing_message: string | null;
  photos: Array<{ id: string; image_url: string; expires_at: string; processed_at: string | null; error: string | null; created_at: string }>;
  attendance: AttendanceRecord[];
}

export interface ImportJob {
  id: string;
  kind: string;
  status: string;
  total: number;
  processed: number;
  succeeded: number;
  failed: number;
  error: string | null;
  error_file_url: string | null;
  created_at: string;
  completed_at: string | null;
}
