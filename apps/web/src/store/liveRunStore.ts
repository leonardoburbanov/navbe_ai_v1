import { create } from "zustand";

export type LiveRun = {
  runId: string;
  workflowId: string;
  processSlug: string | null;
  status: "running" | "completed" | "failed" | "paused" | "cancelled";
  step: string | null;
  startedAt: number;
  updatedAt: number;
};

interface LiveRunStore {
  runs: Record<string, LiveRun>;
  upsert: (partial: {
    runId: string;
    workflowId: string;
    processSlug?: string | null;
    status?: LiveRun["status"];
    step?: string | null;
  }) => void;
  setStep: (runId: string, step: string) => void;
  complete: (runId: string) => void;
  fail: (runId: string) => void;
  pause: (runId: string) => void;
  cancel: (runId: string) => void;
  dismiss: (runId: string) => void;
  hydrate: (rows: LiveRun[]) => void;
  isWorkflowLive: (workflowId: string) => boolean;
}

/** In-flight (and recently finished) runs for the Live strip. */
export const useLiveRunStore = create<LiveRunStore>((set, get) => ({
  runs: {},
  upsert: (partial) =>
    set((s) => {
      const prev = s.runs[partial.runId];
      const now = Date.now();
      return {
        runs: {
          ...s.runs,
          [partial.runId]: {
            runId: partial.runId,
            workflowId: partial.workflowId,
            processSlug: partial.processSlug ?? prev?.processSlug ?? null,
            status: partial.status ?? prev?.status ?? "running",
            step:
              partial.step !== undefined ? partial.step : (prev?.step ?? null),
            startedAt: prev?.startedAt ?? now,
            updatedAt: now,
          },
        },
      };
    }),
  setStep: (runId, step) =>
    set((s) => {
      const prev = s.runs[runId];
      if (!prev) return s;
      return {
        runs: {
          ...s.runs,
          [runId]: { ...prev, step, status: "running", updatedAt: Date.now() },
        },
      };
    }),
  complete: (runId) =>
    set((s) => {
      const prev = s.runs[runId];
      if (!prev) return s;
      return {
        runs: {
          ...s.runs,
          [runId]: { ...prev, status: "completed", updatedAt: Date.now() },
        },
      };
    }),
  fail: (runId) =>
    set((s) => {
      const prev = s.runs[runId];
      if (!prev) return s;
      return {
        runs: {
          ...s.runs,
          [runId]: { ...prev, status: "failed", updatedAt: Date.now() },
        },
      };
    }),
  pause: (runId) =>
    set((s) => {
      const prev = s.runs[runId];
      if (!prev) return s;
      return {
        runs: {
          ...s.runs,
          [runId]: { ...prev, status: "paused", updatedAt: Date.now() },
        },
      };
    }),
  cancel: (runId) =>
    set((s) => {
      const prev = s.runs[runId];
      if (!prev) return s;
      return {
        runs: {
          ...s.runs,
          [runId]: { ...prev, status: "cancelled", updatedAt: Date.now() },
        },
      };
    }),
  dismiss: (runId) =>
    set((s) => {
      const next = { ...s.runs };
      delete next[runId];
      return { runs: next };
    }),
  hydrate: (rows) =>
    set((s) => {
      const next = { ...s.runs };
      for (const r of rows) {
        next[r.runId] = r;
      }
      return { runs: next };
    }),
  isWorkflowLive: (workflowId) =>
    Object.values(get().runs).some(
      (r) =>
        r.workflowId === workflowId &&
        (r.status === "running" || r.status === "paused"),
    ),
}));
