import { ArtifactViewer } from "./ArtifactViewer";
import { Inspector } from "./Inspector";
import type { Artifact, Message } from "../lib/types";

export type PanelTab = "artifact" | "inspector";

/**
 * The right-hand panel.
 *
 * Artifacts and traces compete for the same space on purpose. Both are
 * "evidence about this answer", both are read after the answer rather than
 * during it, and giving each its own permanent column would leave one of them
 * empty most of the time. Tabs keep the reading column at a comfortable width.
 */
export function Panel({
  tab,
  artifact,
  traceMessage,
  onTab,
  onClose,
}: {
  tab: PanelTab;
  artifact: Artifact | null;
  traceMessage: Message | null;
  onTab: (tab: PanelTab) => void;
  onClose: () => void;
}) {
  return (
    <aside className="panel" aria-label="Artifact and trace panel">
      <div className="panel__tabs" role="tablist">
        <button
          className="tab"
          role="tab"
          aria-selected={tab === "artifact"}
          onClick={() => onTab("artifact")}
        >
          Artifact
        </button>
        <button
          className="tab"
          role="tab"
          aria-selected={tab === "inspector"}
          onClick={() => onTab("inspector")}
        >
          Inspector
        </button>
        <button
          className="tab panel__close"
          onClick={onClose}
          aria-label="Close panel"
          title="Close panel"
        >
          ✕
        </button>
      </div>

      {tab === "artifact" ? (
        artifact ? (
          <ArtifactViewer artifact={artifact} />
        ) : (
          <div className="panel__body">
            <p className="panel__heading">No artifact yet</p>
            <p className="panel__sub">
              Ask for a document — a launch checklist, a one-pager, an interactive
              summary — and it will render here, sandboxed, with a report of what
              the viewer stripped out.
            </p>
          </div>
        )
      ) : (
        <Inspector message={traceMessage} />
      )}
    </aside>
  );
}
