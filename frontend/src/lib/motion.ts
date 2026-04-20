import { useEffect, useState } from "react";

/**
 * Motion primitives for the Arcane Command Bridge theme (ENG-171 / REVAMP M1).
 *
 * Two surfaces:
 *
 *  - ``useReducedMotion()`` — subscribes to the OS ``prefers-reduced-motion``
 *    media query. Returns ``true`` when the user opted into reduced motion;
 *    components use the flag to skip animation branches, freeze progress
 *    tickers, etc.
 *  - ``MOTION_CLASSES`` — the registry of CSS animation class names defined
 *    in ``styles.css``. Using the constants keeps the code honest about
 *    which keyframes exist; adding a new animation means registering it
 *    in both places so future reducers know what to disable.
 *
 * The CSS itself already contains a ``@media (prefers-reduced-motion: reduce)``
 * block that kills every registered animation — the hook exists for cases
 * where we need to skip JS-side intervals (the Monitor telemetry ticker),
 * not just CSS keyframes.
 */

const QUERY = "(prefers-reduced-motion: reduce)";

export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState<boolean>(() => {
    if (typeof window === "undefined" || !window.matchMedia) return false;
    return window.matchMedia(QUERY).matches;
  });

  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mql = window.matchMedia(QUERY);
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches);
    // ``addEventListener`` is the current spec; older Safari only has
    // ``addListener``. Feature-detect to keep tests + older browsers happy.
    if (mql.addEventListener) {
      mql.addEventListener("change", onChange);
      return () => mql.removeEventListener("change", onChange);
    }
    mql.addListener(onChange);
    return () => mql.removeListener(onChange);
  }, []);

  return reduced;
}

/**
 * Canonical list of animation classes defined in ``styles.css``. Import
 * from this file so a TypeScript rename or ripgrep surfaces every usage.
 */
export const MOTION_CLASSES = {
  /** Entrance animation — opacity + tiny rise, used on card mount. */
  runeIn: "anim-rune-in",
  /** Slow rotation for SVG rings on in-flight agents. */
  phaseRing: "anim-phase-ring",
  /** Background starfield drift. */
  starfieldDrift: "anim-starfield-drift",
  /** Soft pulse for tiny decorative accents. */
  particleSpark: "anim-particle-spark",
} as const;

export type MotionClass = (typeof MOTION_CLASSES)[keyof typeof MOTION_CLASSES];
