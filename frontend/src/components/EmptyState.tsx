const STARTERS = [
  {
    kind: "Grounded answer",
    text: "How do guests describe knowing you've hit product-market fit?",
  },
  {
    kind: "Grounded answer",
    text: "What actually moves activation during onboarding?",
  },
  {
    kind: "Ship 30 essay",
    text: "Write a Ship 30 essay on why most onboarding flows fail.",
  },
  {
    kind: "Rendered artifact",
    text: "Build an HTML one-pager comparing the growth loops guests describe.",
  },
  {
    kind: "Tests the grounding gate",
    text: "Summarise the episode where Genghis Khan discussed B2B pricing.",
  },
];

export function EmptyState({ onPick }: { onPick: (text: string) => void }) {
  return (
    <div className="empty">
      <p className="empty__lead">
        Every answer here comes from a transcript, and shows you which one.
      </p>
      <p className="empty__body">
        Ask a product or growth question and you get the answer plus the episodes
        behind it. Ask for an essay or a document and you get a draft you can
        take away. When the archive cannot answer, it says so rather than
        guessing.
      </p>

      <div className="starters">
        {STARTERS.map((s) => (
          <button key={s.text} className="starter" onClick={() => onPick(s.text)}>
            <span className="starter__kind">{s.kind}</span>
            {s.text}
          </button>
        ))}
      </div>
    </div>
  );
}
