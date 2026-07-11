import { describe, expect, test, vi } from "vitest";
import { handleSsePayload } from "./sse";

describe("handleSsePayload", () => {
  test("run.started resets the workflow", () => {
    const resetRun = vi.fn();
    const patchStep = vi.fn();
    handleSsePayload(
      { type: "run.started", workflow_id: "wf1" },
      { resetRun, patchStep },
    );
    expect(resetRun).toHaveBeenCalledWith("wf1");
    expect(patchStep).not.toHaveBeenCalled();
  });

  test("run.step marks step succeeded", () => {
    const resetRun = vi.fn();
    const patchStep = vi.fn();
    handleSsePayload(
      { type: "run.step", workflow_id: "wf1", step: "fetch_traces" },
      { resetRun, patchStep },
    );
    expect(patchStep).toHaveBeenCalledWith("wf1", "fetch_traces", "succeeded");
  });

  test("run.step.started marks step running", () => {
    const resetRun = vi.fn();
    const patchStep = vi.fn();
    handleSsePayload(
      { type: "run.step.started", workflow_id: "wf1", step: "write_traces" },
      { resetRun, patchStep },
    );
    expect(patchStep).toHaveBeenCalledWith("wf1", "write_traces", "running");
  });

  test("run.failed patches step when present", () => {
    const resetRun = vi.fn();
    const patchStep = vi.fn();
    handleSsePayload(
      { type: "run.failed", workflow_id: "wf1", step: "fetch_traces" },
      { resetRun, patchStep },
    );
    expect(patchStep).toHaveBeenCalledWith("wf1", "fetch_traces", "failed");
  });
});
