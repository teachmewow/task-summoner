import { useReducedMotion } from "~/lib/motion";
import { SummoningCircle } from "./sigils";

/**
 * Monitor hero — full-bleed status block matching the Claude Design
 * bundle's ``OrchestratorStatus``.
 *
 * Layout:
 *
 *   ┌───────────────────────────────────────────────────────────┐
 *   │ ◉  ORCHESTRATOR · RUNNING          ◉◉ 03   ⚠ 01   ·· 02  │
 *   │    The **shadow army** is listening.                     │
 *   │    board: linear · agent: claude_code · poll: 10s · ✓    │
 *   │                                                  ⟳  ⟳    │
 *   └───────────────────────────────────────────────────────────┘
 *
 * The 240 px summoning circle sits absolute top-right at 0.8 opacity so
 * the stats + hero still dominate the reading order. Decorative — hidden
 * from screen readers.
 */
interface Props {
  running: number;
  waiting: number;
  queued: number;
}

export function OrchestratorStatusBlock({ running, waiting, queued }: Props) {
  const reducedMotion = useReducedMotion();
  return (
    <section data-orchestrator-status className="surface-raised relative overflow-hidden p-6">
      {/* Summoning-circle decoration sits absolute in the top-right
          corner, partially clipped. Opacity drops under reduced motion
          because the core + rings freeze but the tint still reads. */}
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -right-8 -top-8"
        style={{ opacity: reducedMotion ? 0.3 : 0.8 }}
      >
        <SummoningCircle
          size={240}
          color="var(--color-arcane)"
          speed={0.6}
          active={!reducedMotion}
        />
      </div>

      <div className="relative z-[1] flex flex-wrap items-center justify-between gap-6">
        <div className="flex items-center gap-4">
          {/* Pulsing phase-done dot signaling "orchestrator is alive". */}
          <span className="relative inline-flex">
            <span
              aria-hidden="true"
              className="absolute inline-flex h-2.5 w-2.5 rounded-full bg-phase-done opacity-75 anim-pulse-glow"
              style={{ boxShadow: "0 0 16px var(--color-phase-done)" }}
            />
            <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-phase-done" />
          </span>
          <div>
            <p className="eyebrow" style={{ color: "var(--color-phase-done)" }}>
              Orchestrator · running
            </p>
            <h1 className="mt-0.5 text-[22px] font-semibold tracking-tight text-ghost">
              The{" "}
              <span className="text-arcane" style={{ textShadow: "0 0 16px var(--arcane-glow)" }}>
                shadow army
              </span>{" "}
              is listening.
            </h1>
            <p className="mt-1 font-mono text-[12.5px] text-ghost-dim">
              board: <span className="text-ghost">linear</span> · agent:{" "}
              <span className="text-ghost">claude_code</span> · poll: 10s · docs_repo ✓
            </p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <Stat label="Active" value={running} accent="arcane" />
          <Stat label="At gate" value={waiting} accent="ember" />
          <Stat label="Queued" value={queued} accent="idle" />
        </div>
      </div>
    </section>
  );
}

interface StatProps {
  label: string;
  value: number;
  accent: "arcane" | "ember" | "idle";
}

function Stat({ label, value, accent }: StatProps) {
  const color =
    accent === "arcane"
      ? "var(--color-arcane)"
      : accent === "ember"
        ? "var(--color-ember)"
        : "var(--color-ghost-dimmer)";
  return (
    <div className="min-w-[60px] text-center">
      <div
        className="font-mono text-[30px] font-semibold leading-none"
        style={{ color, textShadow: `0 0 20px ${color}` }}
      >
        {String(value).padStart(2, "0")}
      </div>
      <div className="mt-1 text-[10px] uppercase tracking-[0.2em] text-ghost-dim">{label}</div>
    </div>
  );
}
