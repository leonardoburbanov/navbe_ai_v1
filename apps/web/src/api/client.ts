/** Typed fetch wrappers for Control UI → daemon REST. */

export type ProcessRow = {
  process_slug: string;
  workflow_id: string;
  name: string;
  status: string;
  scheduled_at: string | null;
  watermark: string | null;
  last_run: {
    run_id: string;
    status: string;
    started_at: string;
    completed_at: string | null;
  } | null;
};

export type RunRow = {
  run_id: string;
  status: string;
  started_at: string;
  completed_at: string | null;
  error?: string | null;
};

export type FlowNode = {
  id: string;
  type: string;
  data: { label: string; step: string; status: string };
  position: { x: number; y: number };
};

export type FlowEdge = {
  id: string;
  source: string;
  target: string;
  animated?: boolean;
};

export type CatalogResponse = {
  connectors: Array<{
    id: string;
    type: string;
    name: string;
    host: string;
    status: string;
  }>;
  destinations: Array<{
    id: string;
    type: string;
    name: string;
    schema_version: number | null;
    templates: Array<{ id: string; name: string; description: string }>;
  }>;
  connector_types: string[];
  destination_types: string[];
};

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${res.status} ${path}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export function fetchProcesses(): Promise<{ processes: ProcessRow[] }> {
  return getJson("/api/processes");
}

export function fetchRuns(
  workflowId: string,
  page = 1,
  pageSize = 20,
): Promise<{ runs: RunRow[]; page?: number; total?: number }> {
  return getJson(`/api/runs/${workflowId}?page=${page}&page_size=${pageSize}`);
}

export function fetchCatalog(): Promise<CatalogResponse> {
  return getJson("/api/catalog");
}

export function fetchGraph(
  workflowId: string,
): Promise<{ nodes: FlowNode[]; edges: FlowEdge[] }> {
  return getJson(`/api/workflows/${workflowId}/graph`);
}
