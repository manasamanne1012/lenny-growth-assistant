/**
 * API client.
 *
 * One place where every network call lives, and one place where the backend's
 * structured error envelope is turned into something the UI can show. The
 * server always returns a `hint`; losing it in a generic "something went wrong"
 * would throw away the most useful part of the response.
 */
import type {
  Artifact,
  ApiError,
  ChatResponse,
  Message,
  ProviderConfig,
  Session,
  Skill,
} from "./types";

const BASE = "/api";

export class RequestFailed extends Error {
  code: string;
  hint: string | null;
  traceId: string | null;

  constructor(error: ApiError) {
    super(error.message);
    this.code = error.code;
    this.hint = error.hint;
    this.traceId = error.trace_id;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new RequestFailed({
      code: "network_unreachable",
      message: "Could not reach the assistant API.",
      hint: "Check that the backend is running: docker compose ps, then open /api/health/deep.",
      trace_id: null,
    });
  }

  if (response.status === 204) return undefined as T;

  if (!response.ok) {
    let body: { error?: ApiError } = {};
    try {
      body = await response.json();
    } catch {
      /* the body was not JSON; fall through to the generic envelope below */
    }
    throw new RequestFailed(
      body.error ?? {
        code: `http_${response.status}`,
        message: `The API returned ${response.status}.`,
        hint: "See the backend logs for the matching trace id.",
        trace_id: response.headers.get("X-Trace-Id"),
      }
    );
  }

  return (await response.json()) as T;
}

export const api = {
  config: () => request<ProviderConfig>("/config"),

  health: () => request<{ status: string; checks: Record<string, unknown> }>(
    "/health/deep"
  ),

  listSessions: (userId = "local-evaluator") =>
    request<Session[]>(`/sessions?user_id=${encodeURIComponent(userId)}`),

  messages: (sessionId: string) =>
    request<Message[]>(`/sessions/${sessionId}/messages`),

  artifacts: (sessionId: string) =>
    request<Artifact[]>(`/sessions/${sessionId}/artifacts`),

  archiveSession: (sessionId: string) =>
    request<void>(`/sessions/${sessionId}`, { method: "DELETE" }),

  send: (body: { message: string; session_id?: string | null; force_skill?: Skill | null }) =>
    request<ChatResponse>("/chat", {
      method: "POST",
      body: JSON.stringify({
        message: body.message,
        session_id: body.session_id ?? null,
        force_skill: body.force_skill ?? null,
      }),
    }),
};
