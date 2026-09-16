import { useCallback, useEffect, useRef, useState } from "react";
import { api, RequestFailed } from "./lib/api";
import { Composer } from "./components/Composer";
import { EmptyState } from "./components/EmptyState";
import { Panel, type PanelTab } from "./components/Panel";
import { SessionRail } from "./components/SessionRail";
import { Turn } from "./components/Turn";
import type {
  Artifact,
  Message,
  ProviderConfig,
  Session,
  Skill,
} from "./lib/types";

type Health = "ok" | "degraded" | "down" | "unknown";

const USER_ID = "local-evaluator";

/**
 * Application shell.
 *
 * State deliberately lives in one place rather than in a store. The app has one
 * real workflow — pick a session, send a turn, inspect what came back — and a
 * reviewer reading this file should be able to follow that workflow end to end
 * without chasing reducers across the tree.
 *
 * Two behaviours are worth calling out:
 *
 * 1. The user's turn is appended optimistically so the thread never feels like
 *    it swallowed the message, but the assistant's turn is only ever rendered
 *    from the server response. Nothing is invented client-side.
 * 2. Failures are shown as a notice attached to the thread, carrying the
 *    backend's `hint` and trace id. A 500 with a trace id an evaluator can grep
 *    is worth more than a polite apology.
 */
export default function App() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [artifact, setArtifact] = useState<Artifact | null>(null);
  const [traceMessage, setTraceMessage] = useState<Message | null>(null);

  const [config, setConfig] = useState<ProviderConfig | null>(null);
  const [health, setHealth] = useState<Health>("unknown");

  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [panelOpen, setPanelOpen] = useState(false);
  const [panelTab, setPanelTab] = useState<PanelTab>("artifact");
  const [railOpen, setRailOpen] = useState(false);

  const threadRef = useRef<HTMLDivElement>(null);

  /* ------------------------------------------------------------- bootstrap */

  useEffect(() => {
    api.config().then(setConfig).catch(() => setConfig(null));
    api.listSessions(USER_ID).then(setSessions).catch(() => setSessions([]));
  }, []);

  // The badge in the rail is only honest if it is refreshed. Ollama going down
  // mid-session is exactly the case the badge exists for.
  useEffect(() => {
    let cancelled = false;
    const probe = async () => {
      try {
        const result = await api.health();
        if (!cancelled) setHealth((result.status as Health) ?? "ok");
      } catch {
        if (!cancelled) setHealth("down");
      }
    };
    probe();
    const timer = window.setInterval(probe, 20_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  // Keep the newest turn in view, but do not fight the user if they scrolled up.
  useEffect(() => {
    const node = threadRef.current;
    if (!node) return;
    const nearBottom =
      node.scrollHeight - node.scrollTop - node.clientHeight < 240;
    if (nearBottom || busy) node.scrollTop = node.scrollHeight;
  }, [messages, busy]);

  /* --------------------------------------------------------------- actions */

  const openSession = useCallback(async (id: string) => {
    setActiveId(id);
    setRailOpen(false);
    setError(null);
    setTraceMessage(null);
    try {
      const [history, artifacts] = await Promise.all([
        api.messages(id),
        api.artifacts(id),
      ]);
      setMessages(history);
      setArtifact(artifacts.length ? artifacts[artifacts.length - 1] : null);
    } catch (err) {
      setMessages([]);
      setArtifact(null);
      setError(describe(err));
    }
  }, []);

  const newSession = useCallback(() => {
    setActiveId(null);
    setMessages([]);
    setArtifact(null);
    setTraceMessage(null);
    setError(null);
    setDraft("");
    setRailOpen(false);
  }, []);

  const send = useCallback(
    async (text: string, skill: Skill | null) => {
      setBusy(true);
      setError(null);
      setDraft("");

      const optimistic: Message = {
        id: `local-${Date.now()}`,
        session_id: activeId ?? "pending",
        role: "user",
        content: text,
        citations: [],
        trace: {},
        token_usage: {},
        created_at: new Date().toISOString(),
      };
      setMessages((current) => [...current, optimistic]);

      try {
        const response = await api.send({
          message: text,
          session_id: activeId,
          force_skill: skill,
        });

        const assistant: Message = {
          ...response.message,
          notices: response.notices,
          essay_report: response.essay_report,
        };
        setMessages((current) => [...current, assistant]);
        setActiveId(response.session_id);

        if (response.artifact) {
          setArtifact(response.artifact);
          setPanelTab("artifact");
          setPanelOpen(true);
        }
        if (response.essay_report) {
          setTraceMessage(assistant);
        }

        // Refresh the rail so the generated title and ordering are the
        // server's, not a guess.
        api.listSessions(USER_ID).then(setSessions).catch(() => undefined);
      } catch (err) {
        setError(describe(err));
        setDraft(text); // give the message back rather than losing it
        setMessages((current) => current.filter((m) => m.id !== optimistic.id));
      } finally {
        setBusy(false);
      }
    },
    [activeId]
  );

  const openTrace = useCallback((message: Message) => {
    setTraceMessage(message);
    setPanelTab("inspector");
    setPanelOpen(true);
  }, []);

  /* ---------------------------------------------------------------- render */

  const activeSession = sessions.find((s) => s.id === activeId) ?? null;

  return (
    <div
      className="shell"
      data-panel={panelOpen ? "open" : "closed"}
      data-rail={railOpen ? "open" : "closed"}
    >
      <a className="skip-link" href="#thread">
        Skip to the conversation
      </a>

      <SessionRail
        sessions={sessions}
        activeId={activeId}
        config={config}
        health={health}
        onSelect={openSession}
        onNew={newSession}
      />

      {railOpen && (
        <button
          className="scrim"
          aria-label="Close the chat list"
          onClick={() => setRailOpen(false)}
        />
      )}

      <main className="convo">
        <header className="convo__head">
          <button
            className="ghost-btn rail-toggle"
            onClick={() => setRailOpen((open) => !open)}
            aria-label="Show the chat list"
          >
            ☰
          </button>
          <h2 className="convo__title">
            {activeSession ? activeSession.title : "New chat"}
          </h2>
          <span className="convo__spacer" />
          {!panelOpen && (
            <button className="ghost-btn" onClick={() => setPanelOpen(true)}>
              Open panel
            </button>
          )}
        </header>

        <div className="thread" id="thread" ref={threadRef}>
          <div className="thread__inner">
            {messages.length === 0 && !busy ? (
              <EmptyState onPick={(text) => send(text, null)} />
            ) : (
              messages.map((message) => (
                <Turn key={message.id} message={message} onOpenTrace={openTrace} />
              ))
            )}

            {busy && (
              <p className="thinking">
                <span className="thinking__lamp" aria-hidden="true" />
                Searching the transcripts…
              </p>
            )}

            {error && (
              <p className="notice notice--error" role="alert">
                {error}
              </p>
            )}
          </div>
        </div>

        <Composer value={draft} busy={busy} onChange={setDraft} onSend={send} />
      </main>

      {panelOpen && (
        <Panel
          tab={panelTab}
          artifact={artifact}
          traceMessage={traceMessage}
          onTab={setPanelTab}
          onClose={() => setPanelOpen(false)}
        />
      )}
    </div>
  );
}

/** Turn a thrown error into something an evaluator can act on. */
function describe(err: unknown): string {
  if (err instanceof RequestFailed) {
    const parts = [err.message];
    if (err.hint) parts.push(err.hint);
    if (err.traceId) parts.push(`trace ${err.traceId}`);
    return parts.join(" — ");
  }
  return "Something went wrong. Check the backend logs.";
}
