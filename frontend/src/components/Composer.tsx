import { useEffect, useRef, useState } from "react";
import type { Skill } from "../lib/types";

const SKILLS: { id: Skill; label: string; hint: string }[] = [
  { id: "grounded_qa", label: "Answer", hint: "Answer from the transcripts with sources." },
  { id: "ship30_essay", label: "Essay", hint: "Write a ~1,250-word Ship 30 style essay." },
  { id: "artifact", label: "Document", hint: "Build a Markdown or HTML artifact." },
];

export function Composer({
  value,
  busy,
  onChange,
  onSend,
}: {
  value: string;
  busy: boolean;
  onChange: (text: string) => void;
  onSend: (text: string, skill: Skill | null) => void;
}) {
  const [skill, setSkill] = useState<Skill | null>(null);
  const ref = useRef<HTMLTextAreaElement>(null);

  // Grow with the content rather than scrolling inside a fixed box.
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }, [value]);

  const submit = () => {
    const text = value.trim();
    if (!text || busy) return;
    onSend(text, skill);
  };

  const active = SKILLS.find((s) => s.id === skill);

  return (
    <div className="composer">
      <div className="composer__inner">
        <div className="composer__skills" role="group" aria-label="Choose what to produce">
          {SKILLS.map((s) => (
            <button
              key={s.id}
              className="chip"
              aria-pressed={skill === s.id}
              onClick={() => setSkill(skill === s.id ? null : s.id)}
            >
              {s.label}
            </button>
          ))}
        </div>

        <div className="composer__field">
          <label htmlFor="composer-input" className="skip-link">
            Your message
          </label>
          <textarea
            id="composer-input"
            ref={ref}
            rows={1}
            value={value}
            disabled={busy}
            placeholder="Ask about product, growth, pricing, hiring — anything the show covers"
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
          />
          <button className="send" onClick={submit} disabled={busy || !value.trim()}>
            {busy ? "Working" : "Send"}
          </button>
        </div>

        <p className="composer__hint">
          {active
            ? active.hint
            : "Enter to send, Shift+Enter for a new line. Pick a mode above to skip the router."}
        </p>
      </div>
    </div>
  );
}
