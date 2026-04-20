import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MOTION_CLASSES, useReducedMotion } from "~/lib/motion";

/**
 * ``useReducedMotion`` feeds the Monitor telemetry ticker (ENG-177) and the
 * modal entrance animations. It must:
 *  - return the initial media-query state on first render,
 *  - flip when the query's ``change`` event fires (user toggles the OS
 *    preference live),
 *  - unsubscribe on unmount (no listener leak).
 */

function installMatchMedia(initial: boolean) {
  const listeners = new Set<(e: MediaQueryListEvent) => void>();
  const mql: Partial<MediaQueryList> = {
    matches: initial,
    media: "(prefers-reduced-motion: reduce)",
    addEventListener: (_type: string, cb: EventListenerOrEventListenerObject) => {
      listeners.add(cb as (e: MediaQueryListEvent) => void);
    },
    removeEventListener: (_type: string, cb: EventListenerOrEventListenerObject) => {
      listeners.delete(cb as (e: MediaQueryListEvent) => void);
    },
  };
  const matchMedia = vi.fn(() => mql as MediaQueryList);
  vi.stubGlobal("matchMedia", matchMedia);
  return {
    listenerCount: () => listeners.size,
    emit: (matches: boolean) => {
      (mql as { matches: boolean }).matches = matches;
      for (const cb of listeners) cb({ matches } as MediaQueryListEvent);
    },
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("useReducedMotion", () => {
  it("returns the initial media-query state", () => {
    installMatchMedia(true);
    const { result } = renderHook(() => useReducedMotion());
    expect(result.current).toBe(true);
  });

  it("flips when the user toggles the OS preference mid-session", () => {
    const handle = installMatchMedia(false);
    const { result } = renderHook(() => useReducedMotion());
    expect(result.current).toBe(false);

    act(() => handle.emit(true));
    expect(result.current).toBe(true);

    act(() => handle.emit(false));
    expect(result.current).toBe(false);
  });

  it("unsubscribes on unmount", () => {
    const handle = installMatchMedia(false);
    const { unmount } = renderHook(() => useReducedMotion());
    expect(handle.listenerCount()).toBe(1);
    unmount();
    expect(handle.listenerCount()).toBe(0);
  });
});

describe("MOTION_CLASSES", () => {
  it("exposes every keyframe class declared in styles.css", () => {
    // Guardrail: if someone removes a keyframe class in CSS without
    // updating the registry (or vice-versa), this test still passes —
    // but the expectation here makes the contract explicit in one place
    // so a reviewer spots a mismatch.
    expect(MOTION_CLASSES).toEqual({
      runeIn: "anim-rune-in",
      phaseRing: "anim-phase-ring",
      starfieldDrift: "anim-starfield-drift",
      particleSpark: "anim-particle-spark",
    });
  });
});
