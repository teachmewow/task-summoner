import { MOTION_CLASSES } from "~/lib/motion";

/**
 * Top-of-Monitor hero block (REVAMP M2, ENG-174).
 *
 * Communicates two things at a glance:
 *  - the orchestrator is alive (breathing pulse next to "summoning
 *    circle live"),
 *  - N tickets are in flight right now (derived from the caller).
 *
 * The summoning circle is an SVG with three concentric rune rings
 * rotating at slightly different speeds. The anim class from the
 * motion registry auto-freezes under ``prefers-reduced-motion``.
 *
 * Pure presentation — no hooks, no mutations. Parent owns the
 * ``running`` count.
 */
interface Props {
  /** Non-terminal ticket count surfaced to the user. */
  running: number;
  /** Total tickets the orchestrator currently tracks. */
  total: number;
}

export function OrchestratorStatusBlock({ running, total }: Props) {
  return (
    <section
      data-orchestrator-status
      className="relative flex items-center gap-6 overflow-hidden rounded-2xl border border-rune-line-strong bg-obsidian-raised p-6"
    >
      <SummoningCircle />
      <div className="flex flex-col gap-1">
        <p className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-wider text-ghost-dim">
          <span className="relative inline-flex">
            <span
              className={`absolute inline-flex h-2 w-2 rounded-full bg-phase-done opacity-75 ${MOTION_CLASSES.particleSpark}`}
            />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-phase-done" />
          </span>
          summoning circle live
        </p>
        <h1 className="text-2xl font-semibold text-ghost">Agents Monitoring</h1>
        <p className="text-sm text-ghost-dim">
          {running > 0 ? (
            <>
              <span className="text-arcane">{running}</span>
              <span> in flight · {total} tracked total</span>
            </>
          ) : (
            <>{total} tickets tracked · none running right now</>
          )}
        </p>
      </div>
    </section>
  );
}

/**
 * Three concentric rune rings rotating at different speeds. Kept as a
 * local helper so the visual lives alongside the only consumer —
 * ``OrchestratorStatusBlock``. If a second screen ever wants this motif
 * it can move to ``~/components/sigils/`` then.
 */
function SummoningCircle() {
  // Static size; Monitor hero is always 96 px of room for it.
  const size = 88;
  const half = size / 2;
  const runes = Array.from({ length: 12 }, (_, i) => (i / 12) * 360);

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      aria-hidden="true"
      className="shrink-0"
    >
      {/* Outer ring — slow counter-rotation */}
      <g
        className={MOTION_CLASSES.phaseRing}
        style={{
          animationDirection: "reverse",
          animationDuration: "32s",
          transformOrigin: "center",
        }}
      >
        <circle
          cx={half}
          cy={half}
          r={half - 4}
          fill="none"
          stroke="var(--color-rune-line-strong)"
          strokeWidth={1}
        />
        {runes.map((deg) => (
          <line
            key={`outer-${deg}`}
            x1={half}
            y1={6}
            x2={half}
            y2={10}
            stroke="var(--color-arcane)"
            strokeWidth={1}
            transform={`rotate(${deg} ${half} ${half})`}
            opacity={0.6}
          />
        ))}
      </g>

      {/* Middle ring — forward, medium speed */}
      <g
        className={MOTION_CLASSES.phaseRing}
        style={{ animationDuration: "18s", transformOrigin: "center" }}
      >
        <circle
          cx={half}
          cy={half}
          r={half - 14}
          fill="none"
          stroke="var(--color-arcane)"
          strokeWidth={1}
          strokeDasharray="4 6"
          opacity={0.7}
        />
      </g>

      {/* Inner pentagram + core */}
      <g style={{ transformOrigin: "center" }}>
        <Pentagram cx={half} cy={half} r={half - 24} />
        <circle cx={half} cy={half} r={3} fill="var(--color-arcane)" />
        <circle
          cx={half}
          cy={half}
          r={6}
          fill="none"
          stroke="var(--color-arcane)"
          strokeWidth={1}
          opacity={0.5}
        />
      </g>
    </svg>
  );
}

function Pentagram({ cx, cy, r }: { cx: number; cy: number; r: number }) {
  const points: string[] = [];
  for (let i = 0; i < 5; i++) {
    const angle = -Math.PI / 2 + (i * 2 * Math.PI) / 5;
    const x = cx + r * Math.cos(angle);
    const y = cy + r * Math.sin(angle);
    points.push(`${x},${y}`);
  }
  // Star polyline: 0 → 2 → 4 → 1 → 3 → 0
  const order = [0, 2, 4, 1, 3, 0];
  const d = order.map((i) => points[i]).join(" ");
  return (
    <polyline points={d} fill="none" stroke="var(--color-rune)" strokeWidth={1} opacity={0.5} />
  );
}
