import { describe, expect, it } from "vitest";

import { pipelineStates } from "./RunParts";

describe("pipelineStates", () => {
  it("marks everything done for a published run", () => {
    const s = pipelineStates(
      ["start", "retrieve", "plan", "code", "test", "review", "publish"],
      "published",
    );
    expect(Object.values(s).every((v) => v === "done")).toBe(true);
  });

  it("waits at approval for a validated run", () => {
    const s = pipelineStates(
      ["prepare", "retrieve", "plan", "code", "test", "review"],
      "validated",
    );
    expect(s.review).toBe("done");
    expect(s.approve).toBe("waiting");
    expect(s.publish).toBe("pending");
  });

  it("shows the furthest step in progress while running", () => {
    const s = pipelineStates(["prepare", "retrieve", "plan"], "running");
    expect(s.plan).toBe("current");
    expect(s.code).toBe("pending");
  });

  it("marks retrieval skipped when the run went on without it", () => {
    const s = pipelineStates(["prepare", "plan", "code"], "running");
    expect(s.retrieve).toBe("skipped");
  });

  it("stops at the step a failed status names", () => {
    expect(pipelineStates(["prepare", "plan", "code", "test"], "test_failed").test).toBe("failed");
    expect(pipelineStates(["prepare", "plan", "code", "test", "review"], "rejected").approve).toBe(
      "failed",
    );
    expect(pipelineStates(["prepare", "plan"], "error").plan).toBe("failed");
  });
});
