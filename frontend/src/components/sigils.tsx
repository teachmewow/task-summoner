/**
 * Sigils — reusable magical SVG primitives used across the Monitor and
 * issue-detail surfaces. Extracted from the Claude Design bundle's
 * ``sigils.jsx`` so every component reaches for one canonical summoning
 * circle / phase ring / glyph instead of hand-rolling its own.
 *
 * Motion is always gated on ``useReducedMotion`` from ``~/lib/motion`` —
 * callers that respect the hook (they all do) pass ``active={false}``
 * when the user opted into reduced motion, and the SVG freezes.
 */

import type { Phase } from "~/lib/phases";
import { PHASE_COLOR_VAR } from "~/lib/phases";

/* ------------------------------------------------------------------ */
/* Summoning circle — three ornate concentric rings + core            */
/* ------------------------------------------------------------------ */

interface SummoningCircleProps {
  size?: number;
  color?: string;
  speed?: number;
  active?: boolean;
}

/**
 * Three concentric ornate rings counter-rotating + a pulsing core. Used
 * full-size (240 px) as the hero decoration on ``OrchestratorStatusBlock``
 * and at 88 px inline in a handful of smaller surfaces.
 */
export function SummoningCircle({
  size = 64,
  color = "var(--color-arcane)",
  speed = 1,
  active = true,
}: SummoningCircleProps) {
  const s = size;
  const r1 = s * 0.46;
  const r2 = s * 0.36;
  const r3 = s * 0.26;
  const gradientId = `sc-glow-${s}`;
  return (
    <svg
      width={s}
      height={s}
      viewBox={`0 0 ${s} ${s}`}
      aria-hidden="true"
      style={{ overflow: "visible" }}
    >
      <defs>
        <radialGradient id={gradientId}>
          <stop offset="0%" stopColor={color} stopOpacity="0.4" />
          <stop offset="70%" stopColor={color} stopOpacity="0" />
        </radialGradient>
      </defs>
      <circle cx={s / 2} cy={s / 2} r={s * 0.48} fill={`url(#${gradientId})`} />

      {/* Outer ring — dashed, with 6 rune dots */}
      <g
        style={{
          transformOrigin: "center",
          animation: active ? `phase-ring-spin ${14 / speed}s linear infinite` : "none",
        }}
      >
        <circle
          cx={s / 2}
          cy={s / 2}
          r={r1}
          fill="none"
          stroke={color}
          strokeWidth={1}
          strokeOpacity={0.9}
          strokeDasharray="2 4"
        />
        {[0, 60, 120, 180, 240, 300].map((a) => (
          <g key={a} transform={`rotate(${a} ${s / 2} ${s / 2})`}>
            <circle cx={s / 2} cy={s / 2 - r1} r={1.5} fill={color} />
          </g>
        ))}
      </g>

      {/* Middle ring — triangle glyph, counter-rotating */}
      <g
        style={{
          transformOrigin: "center",
          animation: active ? `rotate-ccw ${10 / speed}s linear infinite` : "none",
        }}
      >
        <circle
          cx={s / 2}
          cy={s / 2}
          r={r2}
          fill="none"
          stroke={color}
          strokeWidth={0.8}
          strokeOpacity={0.5}
        />
        <polygon
          points={`${s / 2},${s / 2 - r2} ${s / 2 + r2 * 0.866},${s / 2 + r2 * 0.5} ${
            s / 2 - r2 * 0.866
          },${s / 2 + r2 * 0.5}`}
          fill="none"
          stroke={color}
          strokeWidth={0.8}
          strokeOpacity={0.55}
        />
      </g>

      {/* Inner ring — fine dashes */}
      <g
        style={{
          transformOrigin: "center",
          animation: active ? `phase-ring-spin ${6 / speed}s linear infinite` : "none",
        }}
      >
        <circle
          cx={s / 2}
          cy={s / 2}
          r={r3}
          fill="none"
          stroke={color}
          strokeWidth={0.8}
          strokeDasharray="1 3"
          strokeOpacity={0.7}
        />
      </g>

      {/* Core — breathing dot */}
      <circle
        cx={s / 2}
        cy={s / 2}
        r={2}
        fill={color}
        style={{ filter: `drop-shadow(0 0 6px ${color})` }}
      >
        {active ? (
          <animate attributeName="r" values="1.6;2.4;1.6" dur="2.2s" repeatCount="indefinite" />
        ) : null}
      </circle>
    </svg>
  );
}

/* ------------------------------------------------------------------ */
/* Phase ring — 4 quarter arcs (doc / plan / implement / done)        */
/* ------------------------------------------------------------------ */

interface PhaseRingProps {
  size?: number;
  phase: Phase | null;
  progress?: number;
  active?: boolean;
}

const RING_PHASES: readonly { key: Phase; color: string }[] = [
  { key: "doc", color: "var(--color-phase-doc)" },
  { key: "plan", color: "var(--color-phase-plan)" },
  { key: "implement", color: "var(--color-phase-code)" },
  { key: "merged", color: "var(--color-phase-done)" },
] as const;

/**
 * Circular phase-progress indicator made of four quarter-arcs. Past
 * phases fill their arc solid; the current phase fills proportional to
 * ``progress`` (0–1); future phases sit at 22% opacity. A breathing ring
 * pulses inside the current phase when ``active`` is true.
 *
 * Exported from the design bundle — the previous implementation used a
 * single dashed ring which lost the per-phase read.
 */
export function PhaseRing({ size = 56, phase, progress = 0, active = true }: PhaseRingProps) {
  const s = size;
  const r = s * 0.4;
  const circumference = 2 * Math.PI * r;
  const segLen = circumference / 4;
  const gap = 4;

  const phaseIdx = phase ? RING_PHASES.findIndex((p) => p.key === phase) : -1;

  return (
    <svg width={s} height={s} viewBox={`0 0 ${s} ${s}`} aria-hidden="true">
      {RING_PHASES.map((p, i) => {
        const isPast = phaseIdx > i;
        const isCurrent = phaseIdx === i;
        const isFuture = phaseIdx < i;
        const fillLen = isCurrent ? segLen * progress : isPast ? segLen - gap : 0;
        return (
          <g key={p.key}>
            {/* Track — dim version of the phase color (or faint white
                for future phases that haven't been reached). */}
            <circle
              cx={s / 2}
              cy={s / 2}
              r={r}
              fill="none"
              stroke={isFuture ? "rgba(255,255,255,0.08)" : p.color}
              strokeOpacity={isFuture ? 1 : 0.22}
              strokeWidth={3}
              strokeDasharray={`${segLen - gap} ${circumference - (segLen - gap)}`}
              strokeDashoffset={-(i * segLen)}
              transform={`rotate(-90 ${s / 2} ${s / 2})`}
            />
            {/* Fill — solid, glowing arc */}
            {isPast || isCurrent ? (
              <circle
                cx={s / 2}
                cy={s / 2}
                r={r}
                fill="none"
                stroke={p.color}
                strokeWidth={3}
                strokeLinecap="round"
                strokeDasharray={`${fillLen} ${circumference - fillLen}`}
                strokeDashoffset={-(i * segLen)}
                transform={`rotate(-90 ${s / 2} ${s / 2})`}
                style={{
                  filter: `drop-shadow(0 0 6px ${p.color})`,
                  transition: "stroke-dasharray 0.8s cubic-bezier(.2,.7,.2,1)",
                }}
              />
            ) : null}
          </g>
        );
      })}
      {/* Breathing inner ring inside the current phase. */}
      {active && phaseIdx >= 0 && phaseIdx < 3 ? (
        <circle
          cx={s / 2}
          cy={s / 2}
          r={r * 0.5}
          fill="none"
          stroke={PHASE_COLOR_VAR[RING_PHASES[phaseIdx]?.key ?? "doc"]}
          strokeWidth={0.5}
          strokeOpacity={0.4}
          className="anim-pulse-glow"
        />
      ) : null}
    </svg>
  );
}

/* ------------------------------------------------------------------ */
/* StreamPulse — 5 pulsing bars indicating a live stream               */
/* ------------------------------------------------------------------ */

export function StreamPulse({ color = "var(--color-arcane)" }: { color?: string }) {
  return (
    <span
      aria-hidden="true"
      style={{ display: "inline-flex", alignItems: "center", gap: 2, height: 14 }}
    >
      {[0, 1, 2, 3, 4].map((i) => (
        <span
          key={i}
          style={{
            display: "inline-block",
            width: 2,
            height: "100%",
            borderRadius: 1,
            background: color,
            boxShadow: `0 0 4px ${color}`,
            opacity: 0.8,
            animation: `pulse-glow ${0.8 + i * 0.12}s ease-in-out ${i * 0.08}s infinite`,
            transformOrigin: "center",
          }}
        />
      ))}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/* Sigil glyph — decorative inline rune/triangle/etc.                 */
/* ------------------------------------------------------------------ */

type GlyphKind = "sigil" | "rune" | "star";

export function Glyph({
  kind = "sigil",
  size = 14,
  color = "currentColor",
}: { kind?: GlyphKind; size?: number; color?: string }) {
  const content = {
    sigil: (
      <g>
        <circle
          cx="12"
          cy="12"
          r="9"
          fill="none"
          stroke={color}
          strokeWidth="1"
          strokeDasharray="2 3"
        />
        <polygon points="12,5 19,16 5,16" fill="none" stroke={color} strokeWidth="1" />
        <circle cx="12" cy="12" r="1.5" fill={color} />
      </g>
    ),
    rune: (
      <g stroke={color} strokeWidth="1.3" fill="none" strokeLinecap="round" strokeLinejoin="round">
        <path d="M12 4 L12 20" />
        <path d="M7 9 L12 6 L17 9" />
        <path d="M7 15 L12 18 L17 15" />
        <circle cx="12" cy="12" r="2" />
      </g>
    ),
    star: (
      <g stroke={color} fill="none" strokeWidth="1">
        {[0, 1, 2, 3, 4].map((i) => {
          const a1 = (i / 5) * Math.PI * 2 - Math.PI / 2;
          const a2 = ((i + 2) / 5) * Math.PI * 2 - Math.PI / 2;
          return (
            <line
              key={i}
              x1={12 + Math.cos(a1) * 8}
              y1={12 + Math.sin(a1) * 8}
              x2={12 + Math.cos(a2) * 8}
              y2={12 + Math.sin(a2) * 8}
            />
          );
        })}
      </g>
    ),
  } as const;
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
      {content[kind]}
    </svg>
  );
}
