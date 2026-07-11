import { describe, expect, test, vi } from "vitest";
import { handleSsePayload } from "./sse";

describe("handleSsePayload", () => {
  test("run.started resets the workflow and upserts live run", () => {
    const resetRun = vi.fn();
    const patchStep = vi.fn();
    const upsert = vi.fn();
    const patchStatus = vi.fn();
    handleSsePayload(
      {
        type: "run.started",
        workflow_id: "wf1",
        run_id: "r1",
        process_slug: "langfuse_daily",
      },
      { resetRun, patchStep },
      { upsert, setStep: vi.fn(), complete: vi.fn(), fail: vi.fn() },
      { patchStatus },
    );
    expect(resetRun).toHaveBeenCalledWith("wf1");
    expect(upsert).toHaveBeenCalledWith({
      runId: "r1",
      workflowId: "wf1",
      processSlug: "langfuse_daily",
      status: "running",
      step: null,
    });
    expect(patchStatus).toHaveBeenCalledWith("wf1", "running");
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

  test("run.step.started marks step running and updates live strip", () => {
    const resetRun = vi.fn();
    const patchStep = vi.fn();
    const upsert = vi.fn();
    const setStep = vi.fn();
    handleSsePayload(
      {
        type: "run.step.started",
        workflow_id: "wf1",
        run_id: "r1",
        step: "write_traces",
      },
      { resetRun, patchStep },
      { upsert, setStep, complete: vi.fn(), fail: vi.fn() },
    );
    expect(patchStep).toHaveBeenCalledWith("wf1", "write_traces", "running");
    expect(setStep).toHaveBeenCalledWith("r1", "write_traces");
  });

  test("run.failed patches step when present and fails live run", () => {
    const resetRun = vi.fn();
    const patchStep = vi.fn();
    const fail = vi.fn();
    const patchStatus = vi.fn();
    handleSsePayload(
      {
        type: "run.failed",
        workflow_id: "wf1",
        run_id: "r1",
        step: "fetch_traces",
      },
      { resetRun, patchStep },
      { upsert: vi.fn(), setStep: vi.fn(), complete: vi.fn(), fail },
      { patchStatus },
    );
    expect(patchStep).toHaveBeenCalledWith("wf1", "fetch_traces", "failed");
    expect(fail).toHaveBeenCalledWith("r1");
    expect(patchStatus).toHaveBeenCalledWith("wf1", "failed");
  });

  test("run.succeeded completes live run", () => {
    const complete = vi.fn();
    const patchStatus = vi.fn();
    handleSsePayload(
      { type: "run.succeeded", workflow_id: "wf1", run_id: "r1" },
      { resetRun: vi.fn(), patchStep: vi.fn() },
      { upsert: vi.fn(), setStep: vi.fn(), complete, fail: vi.fn() },
      { patchStatus },
    );
    expect(complete).toHaveBeenCalledWith("r1");
    expect(patchStatus).toHaveBeenCalledWith("wf1", "completed");
  });
});
