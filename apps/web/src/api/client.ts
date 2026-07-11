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
  output?: Record<string, unknown> | null;
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

export type AnalysisTemplate = {
  id: string;
  name: string;
  description: string;
  query_example: string;
  min_schema_version?: number;
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
    config_summary?: Record<string, string | null>;
    templates: AnalysisTemplate[];
  }>;
  connector_types: string[];
  destination_types: string[];
};

export type QueryResult = {
  columns: string[];
  rows: unknown[][];
  page: number;
  page_size: number;
  total: number;
};

export type ReplayRow = {
  id: string;
  trace_id: string;
  api_url: string;
  status_code: number;
  latency_ms: number;
  original_output: unknown;
  response_body: unknown;
  compare: {
    identical?: boolean;
    diff_count?: number;
    diffs?: Array<{ path: string; expected: unknown; actual: unknown }>;
    experiment_messages?: Array<{
      index: number;
      expected?: string | null;
      actual?: string | null;
      match?: boolean;
    }>;
    messages_identical?: boolean;
  } | null;
  ts: string;
  destination_id?: string;
};

export type EmailStatus = {
  configured: boolean;
  provider: string | null;
  from_addr: string | null;
};

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${res.status} ${path}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${res.status} ${path}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

export function fetchHealth(): Promise<{ status: string }> {
  return getJson("/health");
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

export function fetchReplays(
  workflowId?: string,
): Promise<{ replays: ReplayRow[] }> {
  const q = workflowId ? `?workflow_id=${encodeURIComponent(workflowId)}` : "";
  return getJson(`/api/replays${q}`);
}

export type LiveRunApiRow = {
  run_id: string;
  workflow_id: string;
  process_slug: string | null;
  status: string;
  step: string | null;
  started_at: string;
};

/** In-flight runs for Live strip hydrate. */
export function fetchLiveRuns(): Promise<{ runs: LiveRunApiRow[] }> {
  return getJson("/api/runs/live");
}

/** Run a read-only SELECT against a workflow's destination (paginated). */
export function queryWorkflowDestination(
  workflowId: string,
  sql: string,
  page = 1,
  pageSize = 20,
): Promise<QueryResult> {
  return postJson(`/api/workflows/${workflowId}/query`, {
    sql,
    page,
    page_size: pageSize,
  });
}

export function fetchEmailStatus(): Promise<EmailStatus> {
  return getJson("/api/settings/email");
}

export function configureResendApi(
  apiKey: string,
  fromAddr = "onboarding@resend.dev",
): Promise<Record<string, unknown>> {
  return postJson("/api/settings/resend", {
    api_key: apiKey,
    from_addr: fromAddr,
  });
}

export function previewDailyReportApi(
  destinationId: string,
): Promise<Record<string, unknown>> {
  return postJson("/api/reports/preview", { destination_id: destinationId });
}

export function scheduleDailyReportApi(body: {
  destination_id: string;
  email_to: string;
  when?: string;
  name?: string;
}): Promise<Record<string, unknown>> {
  return postJson("/api/reports/schedule", body);
}

export function sendDailyReportApi(body: {
  workflow_id?: string;
  destination_id?: string;
  email_to?: string;
}): Promise<Record<string, unknown>> {
  return postJson("/api/reports/send", body);
}
