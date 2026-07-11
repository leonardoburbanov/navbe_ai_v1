import { create } from "zustand";
import type { NodeStatus } from "../statusColors";

interface DagStore {
  nodeStatus: Record<string, Record<string, NodeStatus>>;
  patchStep: (workflowId: string, step: string, status: NodeStatus) => void;
  resetRun: (workflowId: string) => void;
}

export const useDagStore = create<DagStore>((set) => ({
  nodeStatus: {},
  patchStep: (wfId, step, status) =>
    set((s) => ({
      nodeStatus: {
        ...s.nodeStatus,
        [wfId]: { ...s.nodeStatus[wfId], [step]: status },
      },
    })),
  resetRun: (wfId) =>
    set((s) => ({
      nodeStatus: { ...s.nodeStatus, [wfId]: {} },
    })),
}));
