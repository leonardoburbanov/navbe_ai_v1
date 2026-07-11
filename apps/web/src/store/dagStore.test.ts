import { beforeEach, describe, expect, test } from "vitest";
import { useDagStore } from "./dagStore";

describe("dagStore", () => {
  beforeEach(() => {
    useDagStore.setState({ nodeStatus: {} });
  });

  test("patchStep sets status for a step", () => {
    useDagStore.getState().patchStep("wf1", "fetch_traces", "running");
    expect(useDagStore.getState().nodeStatus.wf1?.fetch_traces).toBe("running");
  });

  test("resetRun clears all step statuses for workflow", () => {
    useDagStore.getState().patchStep("wf1", "fetch_traces", "succeeded");
    useDagStore.getState().resetRun("wf1");
    expect(useDagStore.getState().nodeStatus.wf1).toEqual({});
  });
});
