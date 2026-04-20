import { AlertTriangle, Loader2, X } from "lucide-react";
import { useEffect, useState } from "react";

interface Props {
  open: boolean;
  skillName: string | null;
  onClose: () => void;
  onSubmit: (feedback: string) => void;
  isPending: boolean;
  error: string | null;
}

export function RequestChangesModal({
  open,
  skillName,
  onClose,
  onSubmit,
  isPending,
  error,
}: Props) {
  const [feedback, setFeedback] = useState("");

  // Reset the textarea whenever the modal opens so stale copy doesn't leak
  // between gates on the same page.
  useEffect(() => {
    if (open) setFeedback("");
  }, [open]);

  if (!open) return null;

  const canSubmit = feedback.trim().length >= 3 && !isPending;

  return (
    <div
      className="fixed inset-0 z-40 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      data-modal="request-changes"
      aria-modal="true"
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (canSubmit) onSubmit(feedback);
        }}
        className="w-full max-w-lg rounded-2xl border border-rune-line-strong bg-obsidian-raised p-5 glow-arcane-soft"
      >
        <header className="flex items-center justify-between pb-3">
          <h2 className="font-mono text-[10px] font-semibold uppercase tracking-wider text-arcane">
            Request changes
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="text-ghost-dim hover:text-arcane"
            aria-label="Close"
          >
            <X size={16} strokeWidth={2} />
          </button>
        </header>

        <p className="pb-3 text-sm text-ghost/80">
          Posts <code className="text-ghost/90">gh pr review --request-changes</code> with your
          feedback
          {skillName ? (
            <>
              {" "}
              and re-summons <code className="text-ghost/90">{skillName}</code>.
            </>
          ) : (
            "."
          )}
        </p>

        <textarea
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
          placeholder="What needs to change? This text becomes the PR review body."
          className="h-40 w-full resize-y rounded-md border border-rune-line-strong bg-vault-soft p-3 font-mono text-xs text-ghost focus:border-arcane focus:outline-none focus:ring-2 focus:ring-arcane/40"
        />

        {error ? (
          <div className="mt-2 flex items-start gap-2 rounded-md border border-blood/40 bg-blood/10 px-3 py-2 text-xs text-blood">
            <AlertTriangle size={12} strokeWidth={2} className="mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        ) : null}

        <footer className="mt-4 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-rune-line-strong bg-vault-soft px-3 py-1.5 text-xs text-ghost-dim transition hover:border-arcane/40 hover:text-arcane"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!canSubmit}
            className="inline-flex items-center gap-1.5 rounded-md border border-ember/60 bg-ember/20 px-3 py-1.5 text-xs font-medium text-ember transition hover:bg-ember/30 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isPending ? <Loader2 size={12} strokeWidth={2} className="animate-spin" /> : null}
            Send feedback
          </button>
        </footer>
      </form>
    </div>
  );
}
