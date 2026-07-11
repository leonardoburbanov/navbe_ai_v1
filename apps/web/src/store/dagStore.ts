import { create } from "zustand";
import type { NodeStatus } from "../statusColors";

interface DagStore {
  /** Keyed by run_id when live; falls back to workflow_id for legacy. */
  nodeStatus: Record<string, Record<string, NodeStatus>>;
  patchStep: (scopeId: string, step: string, status: NodeStatus) => void;
  resetRun: (scopeId: string) => void;
  seedSteps: (
    scopeId: string,
    steps: Array<{ id: string; status: string }>,
  ) => void;
}

function asNodeStatus(status: string): NodeStatus {
  if (
    status === "running" ||
    status === "succeeded" ||
    status === "failed" ||
    status === "skipped" ||
    status === "idle"
  ) {
    return status;
  }
  if (status === "completed") return "succeeded";
  return "idle";
}

export const useDagStore = create<DagStore>((set) => ({
  nodeStatus: {},
  patchStep: (scopeId, step, status) =>
    set((s) => ({
      nodeStatus: {
        ...s.nodeStatus,
        [scopeId]: { ...s.nodeStatus[scopeId], [step]: status },
      },
    })),
  resetRun: (scopeId) =>
    set((s) => ({
      nodeStatus: { ...s.nodeStatus, [scopeId]: {} },
    })),
  seedSteps: (scopeId, steps) =>
    set((s) => {
      const next: Record<string, NodeStatus> = {};
      for (const step of steps) {
        next[step.id] = asNodeStatus(step.status);
      }
      return { nodeStatus: { ...s.nodeStatus, [scopeId]: next } };
    }),
}));
