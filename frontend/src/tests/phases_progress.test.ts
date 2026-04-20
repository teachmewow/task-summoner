import { afterEach, describe, expect, it, vi } from "vitest";
import { PHASES, phaseFromOrchestratorState } from "~/lib/phases";
import { MAX_PROGRESS, advanceProgress, initialProgress, isProgressActive } from "~/lib/progress";

/**
 * Small, boring unit suite for the two helper modules that M2 / M3 both
 * depend on. No rendering, no DOM — just pure data.
 */

describe("phaseFromOrchestratorState", () => {
  it("maps every doc-lifecycle state to 'doc'", () => {
    for (const s of [
      "QUEUED",
      "CHECKING_DOC",
      "CREATING_DOC",
      "WAITING_DOC_REVIEW",
      "IMPROVING_DOC",
    ]) {
      expect(phaseFromOrchestratorState(s)).toBe("doc");
    }
  });

  it("maps planning states to 'plan'", () => {
    expect(phaseFromOrchestratorState("PLANNING")).toBe("plan");
    expect(phaseFromOrchestratorState("WAITING_PLAN_REVIEW")).toBe("plan");
  });

  it("maps implementation + review + fix states to 'implement'", () => {
    for (const s of ["IMPLEMENTING", "WAITING_MR_REVIEW", "FIXING_MR"]) {
      expect(phaseFromOrchestratorState(s)).toBe("implement");
    }
  });

  it("maps DONE to 'merged'", () => {
    expect(phaseFromOrchestratorState("DONE")).toBe("merged");
  });

  it("returns null for FAILED and unknown states (UI decides the marker)", () => {
    expect(phaseFromOrchestratorState("FAILED")).toBe(null);
    expect(phaseFromOrchestratorState("GIBBERISH")).toBe(null);
    expect(phaseFromOrchestratorState(null)).toBe(null);
    expect(phaseFromOrchestratorState(undefined)).toBe(null);
  });

  it("PHASES lists each phase exactly once in strip order", () => {
    expect(PHASES).toEqual(["doc", "plan", "implement", "merged"]);
  });
});

describe("initialProgress", () => {
  it("pins terminal states to 1", () => {
    expect(initialProgress("DONE")).toBe(1);
    expect(initialProgress("FAILED")).toBe(1);
  });

  it("pins QUEUED and unknown to 0", () => {
    expect(initialProgress("QUEUED")).toBe(0);
    expect(initialProgress(null)).toBe(0);
    expect(initialProgress(undefined)).toBe(0);
  });

  it("parks WAITING_* review states near the cap", () => {
    expect(initialProgress("WAITING_DOC_REVIEW")).toBe(0.95);
    expect(initialProgress("WAITING_PLAN_REVIEW")).toBe(0.95);
    expect(initialProgress("WAITING_MR_REVIEW")).toBe(0.95);
  });

  it("seeds in-flight agent states at ~10%", () => {
    for (const s of [
      "CHECKING_DOC",
      "CREATING_DOC",
      "PLANNING",
      "IMPLEMENTING",
      "IMPROVING_DOC",
      "FIXING_MR",
    ]) {
      expect(initialProgress(s)).toBe(0.1);
    }
  });
});

describe("advanceProgress", () => {
  afterEach(() => vi.restoreAllMocks());

  it("nudges forward by a bounded positive delta", () => {
    vi.spyOn(Math, "random").mockReturnValue(0.5);
    expect(advanceProgress(0.1)).toBeCloseTo(0.105, 4);
  });

  it("never exceeds MAX_PROGRESS even with Math.random = 1", () => {
    vi.spyOn(Math, "random").mockReturnValue(0.999);
    const result = advanceProgress(0.975);
    expect(result).toBeLessThanOrEqual(MAX_PROGRESS);
  });

  it("returns MAX_PROGRESS unchanged when already at the cap", () => {
    expect(advanceProgress(MAX_PROGRESS)).toBe(MAX_PROGRESS);
  });
});

describe("isProgressActive", () => {
  it("is true only for mid-agent-run states", () => {
    expect(isProgressActive("CREATING_DOC")).toBe(true);
    expect(isProgressActive("PLANNING")).toBe(true);
    expect(isProgressActive("IMPLEMENTING")).toBe(true);
  });

  it("is false for queued, waiting, terminal, and unknown", () => {
    expect(isProgressActive("QUEUED")).toBe(false);
    expect(isProgressActive("WAITING_DOC_REVIEW")).toBe(false);
    expect(isProgressActive("DONE")).toBe(false);
    expect(isProgressActive("FAILED")).toBe(false);
    expect(isProgressActive(null)).toBe(false);
  });
});
