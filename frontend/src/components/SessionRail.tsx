import type { ProviderConfig, Session } from "../lib/types";
import { ModelBadge } from "./ModelBadge";

function group(sessions: Session[]) {
  const now = Date.now();
  const buckets: Record<string, Session[]> = { Today: [], "Past week": [], Earlier: [] };
  for (const s of sessions) {
    const age = now - new Date(s.updated_at).getTime();
    const key = age < 864e5 ? "Today" : age < 6048e5 ? "Past week" : "Earlier";
    buckets[key].push(s);
  }
  return Object.entries(buckets).filter(([, list]) => list.length > 0);
}

export function SessionRail({
  sessions,
  activeId,
  config,
  health,
  onSelect,
  onNew,
}: {
  sessions: Session[];
  activeId: string | null;
  config: ProviderConfig | null;
  health: "ok" | "degraded" | "down" | "unknown";
  onSelect: (id: string) => void;
  onNew: () => void;
}) {
  return (
    <nav className="rail" aria-label="Your chats">
      <div className="rail__head">
        <h1 className="wordmark">
          The Lenny <span>Growth</span> Assistant
        </h1>
        <p className="rail__sub">Answers from the podcast archive</p>
      </div>

      <button className="new-chat" onClick={onNew}>
        Start a new chat
      </button>

      <div className="rail__list">
        {sessions.length === 0 ? (
          <p className="rail__groupLabel">
            No chats yet. Ask something to begin.
          </p>
        ) : (
          group(sessions).map(([label, list]) => (
            <div key={label}>
              <p className="rail__groupLabel">{label}</p>
              {list.map((s) => (
                <button
                  key={s.id}
                  className="session"
                  aria-current={s.id === activeId}
                  onClick={() => onSelect(s.id)}
                >
                  <span className="session__title">{s.title}</span>
                  <span className="session__meta">
                    {s.message_count} message{s.message_count === 1 ? "" : "s"}
                    {s.model ? ` · ${s.model}` : ""}
                  </span>
                </button>
              ))}
            </div>
          ))
        )}
      </div>

      <div className="rail__foot">
        <ModelBadge config={config} status={health} />
      </div>
    </nav>
  );
}
