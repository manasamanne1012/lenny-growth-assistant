export type Grounding =
  | "grounded"
  | "partial"
  | "ungrounded"
  | "abstained"
  | "n/a";

export interface Citation {
  marker: string;
  chunk_id: string;
  source_id: string;
  title: string;
  guest: string | null;
  episode_url: string | null;
  timestamp: string | null;
  heading: string | null;
  score: number;
  retrieved_by: string;
  excerpt: string;
}

export interface Artifact {
  id?: string | null;
  kind: "markdown" | "html";
  title: string;
  content: string;
  sanitizer_report: SanitizerReport;
  created_at?: string | null;
}

export interface SanitizerReport {
  kind?: string;
  clean?: boolean;
  removed_elements?: string[];
  removed_attributes?: string[];
  blocked_urls?: string[];
  inline_scripts_kept?: number;
  truncated?: boolean;
  notes?: string[];
}

export interface TraceSpan {
  name: string;
  duration_ms: number | null;
  status: string;
  detail: Record<string, unknown>;
}

export interface Trace {
  trace_id?: string;
  total_ms?: number;
  spans?: TraceSpan[];
  facts?: Record<string, unknown>;
}

export interface Message {
  id: string;
  session_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  skill?: string | null;
  grounding?: Grounding | null;
  citations: Citation[];
  trace: Trace;
  provider?: string | null;
  model?: string | null;
  latency_ms?: number | null;
  token_usage: Record<string, number>;
  created_at: string;
  /** Client-only: notices and rubric report attached to the turn that produced it. */
  notices?: string[];
  essay_report?: EssayReport | null;
  artifact_id?: string | null;
}

export interface EssayReport {
  passed: boolean;
  word_count: number;
  hook_words: number;
  h2_count: number;
  bullet_blocks: number;
  bold_phrases: number;
  avg_sentence_words: number;
  citation_coverage: number;
  distinct_citations: number;
  has_takeaway: boolean;
  failures: string[];
}

export interface Session {
  id: string;
  title: string;
  user_id: string;
  provider?: string | null;
  model?: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
}

export interface ChatResponse {
  session_id: string;
  session_title: string;
  message: Message;
  artifact: Artifact | null;
  essay_report: EssayReport | null;
  route: Record<string, unknown>;
  notices: string[];
  trace_id: string;
}

export interface ProviderConfig {
  chat: { provider: string; model: string; is_local: boolean };
  fallback: { provider: string; model: string } | null;
  embedding: { provider: string; model: string; dim: number };
  agent_runtime: string;
}

export interface ApiError {
  code: string;
  message: string;
  hint: string | null;
  trace_id: string | null;
}

export type Skill = "grounded_qa" | "ship30_essay" | "artifact";
