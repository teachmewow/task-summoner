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
        className="w-full max-w-lg rounded-lg border border-shadow-purple/60 bg-void-900 p-5 shadow-[0_0_20px_rgba(168,85,247,0.2)]"
      >
        <header className="flex items-center justify-between pb-3">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-arise-violet-bright">
            Request changes
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="text-soul-cyan/70 hover:text-ghost-white"
            aria-label="Close"
          >
            <X size={16} strokeWidth={2} />
          </button>
        </header>

        <p className="pb-3 text-sm text-soul-cyan/80">
          Posts <code className="text-ghost-white/90">gh pr review --request-changes</code> with
          your feedback
          {skillName ? (
            <>
              {" "}
              and re-summons <code className="text-ghost-white/90">{skillName}</code>.
            </>
          ) : (
            "."
          )}
        </p>

        <textarea
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
          placeholder="What needs to change? This text becomes the PR review body."
          className="h-40 w-full resize-y rounded-md border border-shadow-purple/60 bg-void-800/70 p-3 font-mono text-xs text-ghost-white focus:border-arise-violet focus:outline-none focus:ring-2 focus:ring-arise-violet/40"
        />

        {error ? (
          <div className="mt-2 flex items-start gap-2 rounded-md border border-ember-red/40 bg-ember-red/10 px-3 py-2 text-xs text-ember-red">
            <AlertTriangle size={12} strokeWidth={2} className="mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
        ) : null}

        <footer className="mt-4 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-shadow-purple/60 bg-void-800/70 px-3 py-1.5 text-xs text-soul-cyan hover:text-ghost-white"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!canSubmit}
            className="inline-flex items-center gap-1.5 rounded-md border border-amber-flame/60 bg-amber-flame/20 px-3 py-1.5 text-xs font-medium text-amber-flame transition hover:bg-amber-flame/30 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isPending ? <Loader2 size={12} strokeWidth={2} className="animate-spin" /> : null}
            Send feedback
          </button>
        </footer>
      </form>
    </div>
  );
}
