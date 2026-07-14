import { create } from "zustand";
import type { WorkflowRow } from "../api/client";

interface WorkflowStore {
  workflows: WorkflowRow[];
  setWorkflows: (rows: WorkflowRow[]) => void;
  patchStatus: (workflowId: string, status: string) => void;
}

export const useWorkflowStore = create<WorkflowStore>((set) => ({
  workflows: [],
  setWorkflows: (rows) => set({ workflows: rows }),
  patchStatus: (workflowId, status) =>
    set((s) => ({
      workflows: s.workflows.map((p) =>
        p.workflow_id === workflowId ? { ...p, status } : p,
      ),
    })),
}));

/** @deprecated use useWorkflowStore */
export const useProcessStore = useWorkflowStore;
