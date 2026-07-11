import { create } from "zustand";
import type { ProcessRow } from "../api/client";

interface ProcessStore {
  processes: ProcessRow[];
  setProcesses: (rows: ProcessRow[]) => void;
  patchStatus: (workflowId: string, status: string) => void;
}

export const useProcessStore = create<ProcessStore>((set) => ({
  processes: [],
  setProcesses: (rows) => set({ processes: rows }),
  patchStatus: (workflowId, status) =>
    set((s) => ({
      processes: s.processes.map((p) =>
        p.workflow_id === workflowId ? { ...p, status } : p,
      ),
    })),
}));
