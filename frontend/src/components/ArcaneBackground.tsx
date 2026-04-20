import { MOTION_CLASSES } from "~/lib/motion";

/**
 * Fixed-position background layer for the Arcane Command Bridge theme
 * (ENG-172 / REVAMP M1).
 *
 * Paints three layers onto a pointer-events-none, ``z-index: -1`` surface:
 *
 *  1. **Radial wash** — cyan top-left, violet bottom-right, falling off
 *     into obsidian. Heritage of the design's ``.bg-arcane`` rule.
 *  2. **Ley-line grid** — faint 64 px × 64 px rune-line grid, masked via a
 *     radial gradient so it fades at the canvas edges. Gives the surface a
 *     summoning-table feel without dominating the composition.
 *  3. **Starfield dust** — layered 1 px ``radial-gradient`` dots, animated
 *     via ``starfield-drift`` when the user hasn't opted into reduced
 *     motion. The CSS keyframe block disables the animation on
 *     ``prefers-reduced-motion: reduce``, so we don't need to re-check
 *     the flag here.
 *
 * Mounted from ``__root.tsx`` so every route inherits the canvas. The
 * actual route content sits above this layer at ``z-index >= 0``.
 */
export function ArcaneBackground() {
  return (
    <div
      aria-hidden="true"
      data-arcane-background
      className="pointer-events-none fixed inset-0 -z-10 overflow-hidden"
      style={{
        background:
          "radial-gradient(900px 600px at 15% -10%, rgba(54, 224, 208, 0.08), transparent 60%)," +
          "radial-gradient(1100px 700px at 85% 110%, rgba(157, 123, 255, 0.10), transparent 55%)," +
          "radial-gradient(700px 500px at 50% 50%, rgba(54, 224, 208, 0.03), transparent 70%)," +
          "var(--color-obsidian)",
      }}
    >
      {/* Ley-line grid — rendered via ::before-style CSS would need a
          dedicated class; keeping the gradient inline is clearer and
          survives Tailwind purging. */}
      <div
        aria-hidden="true"
        className="absolute inset-0 opacity-50"
        style={{
          backgroundImage:
            "linear-gradient(var(--color-rune-line) 1px, transparent 1px)," +
            "linear-gradient(90deg, var(--color-rune-line) 1px, transparent 1px)",
          backgroundSize: "64px 64px",
          maskImage: "radial-gradient(ellipse at center, black 30%, transparent 80%)",
          WebkitMaskImage: "radial-gradient(ellipse at center, black 30%, transparent 80%)",
        }}
      />

      {/* Starfield dust — drift animation auto-freezes under reduced motion. */}
      <div
        aria-hidden="true"
        className={`absolute inset-0 ${MOTION_CLASSES.starfieldDrift}`}
        style={{
          backgroundImage:
            "radial-gradient(1px 1px at 14% 22%, #a8c7ff 50%, transparent 50%)," +
            "radial-gradient(1px 1px at 67% 71%, #7beee4 50%, transparent 50%)," +
            "radial-gradient(1px 1px at 83% 14%, #c0a3ff 50%, transparent 50%)," +
            "radial-gradient(1px 1px at 32% 88%, #eef2ff 50%, transparent 50%)," +
            "radial-gradient(1px 1px at 52% 41%, #7beee4 50%, transparent 50%)," +
            "radial-gradient(1px 1px at 91% 53%, #a8c7ff 50%, transparent 50%)," +
            "radial-gradient(1px 1px at 24% 64%, #eef2ff 50%, transparent 50%)," +
            "radial-gradient(1px 1px at 77% 28%, #c0a3ff 50%, transparent 50%)",
          backgroundSize: "480px 480px",
        }}
      />
    </div>
  );
}
