import type { ProviderConfig } from "../lib/types";

/**
 * Which model answered, always visible.
 *
 * The assignment asks for the selected provider to be visible in the UI. It is
 * also the first thing anyone asks when an answer looks wrong, so it sits in
 * the rail permanently rather than behind a settings menu.
 */
export function ModelBadge({
  config,
  status,
}: {
  config: ProviderConfig | null;
  status: "ok" | "degraded" | "down" | "unknown";
}) {
  if (!config) {
    return (
      <p className="badge">
        <span className="badge__lamp" data-state="down" aria-hidden="true" />
        <span className="badge__where">Connecting to the API</span>
      </p>
    );
  }

  const lamp = status === "down" ? "down" : config.chat.is_local ? "local" : "cloud";
  const where = config.chat.is_local
    ? "running locally via Ollama"
    : `${config.chat.provider} API`;

  return (
    <p className="badge" title={`Embeddings: ${config.embedding.model} (${config.embedding.provider})`}>
      <span className="badge__lamp" data-state={lamp} aria-hidden="true" />
      <span>
        <span className="badge__model">{config.chat.model}</span>
        <br />
        <span className="badge__where">
          {where}
          {status === "degraded" ? " — degraded" : ""}
          {config.fallback ? ` · falls back to ${config.fallback.provider}` : ""}
        </span>
      </span>
    </p>
  );
}
