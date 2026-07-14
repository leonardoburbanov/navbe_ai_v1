import { useEffect, useRef } from "react";

type SseOpts = {
  onError?: () => void;
  onOpen?: () => void;
};

/** Subscribe to an SSE endpoint; closes on unmount or url change. */
export function useSSE(
  url: string,
  onEvent: (e: MessageEvent) => void,
  opts?: SseOpts,
): void {
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;
  const optsRef = useRef(opts);
  optsRef.current = opts;

  useEffect(() => {
    const es = new EventSource(url);
    es.onmessage = (e) => onEventRef.current(e);
    es.onerror = () => optsRef.current?.onError?.();
    es.onopen = () => optsRef.current?.onOpen?.();
    return () => es.close();
  }, [url]);
}

export type SseEvent = {
  type?: string;
  workflow_id?: string;
  run_id?: string;
  process_slug?: string;
  slug?: string;
  step?: string;
  status?: string;
  live_url?: string;
};

type DagActions = {
  resetRun: (scopeId: string) => void;
  patchStep: (
    scopeId: string,
    step: string,
    status: "idle" | "running" | "succeeded" | "failed" | "skipped",
  ) => void;
};

type LiveActions = {
  upsert: (partial: {
    runId: string;
    workflowId: string;
    processSlug?: string | null;
    status?: "running" | "completed" | "failed" | "paused" | "cancelled";
    step?: string | null;
  }) => void;
  setStep: (runId: string, step: string) => void;
  complete: (runId: string) => void;
  fail: (runId: string) => void;
  pause?: (runId: string) => void;
  cancel?: (runId: string) => void;
};

type ProcessActions = {
  patchStatus: (workflowId: string, status: string) => void;
};

/** Prefer run_id for DAG overlays so each run has its own node colors. */
function dagScope(event: SseEvent): string | undefined {
  return event.run_id || event.workflow_id;
}

/** Map a hub SSE payload to dag + live + process store actions. Pure — unit-tested. */
export function handleSsePayload(
  event: SseEvent,
  dag: DagActions,
  live?: LiveActions,
  process?: ProcessActions,
): void {
  const wf = event.workflow_id;
  if (!wf || !event.type) return;

  const scope = dagScope(event) ?? wf;
  const runId = event.run_id;
  const slug = event.slug ?? event.process_slug ?? null;

  if (event.type === "run.started" || event.type === "run.preview.started") {
    dag.resetRun(scope);
    process?.patchStatus(wf, "running");
    if (runId && live) {
      live.upsert({
        runId,
        workflowId: wf,
        processSlug: slug,
        status: "running",
        step: null,
      });
    }
    return;
  }
  if (event.type === "run.step.started" && event.step) {
    dag.patchStep(scope, event.step, "running");
    if (runId && live) {
      live.upsert({
        runId,
        workflowId: wf,
        processSlug: slug,
        status: "running",
        step: event.step,
      });
      live.setStep(runId, event.step);
    }
    return;
  }
  if (event.type === "run.step" && event.step) {
    dag.patchStep(scope, event.step, "succeeded");
    return;
  }
  if (event.type === "run.paused") {
    process?.patchStatus(wf, "paused");
    if (runId && live) live.pause?.(runId);
    return;
  }
  if (event.type === "run.cancelled") {
    process?.patchStatus(wf, "cancelled");
    if (runId && live) live.cancel?.(runId);
    return;
  }
  if (
    event.type === "run.succeeded" ||
    event.type === "run.preview.completed"
  ) {
    process?.patchStatus(wf, "completed");
    if (runId && live) live.complete(runId);
    return;
  }
  if (event.type === "run.failed") {
    process?.patchStatus(wf, "failed");
    if (event.step) dag.patchStep(scope, event.step, "failed");
    if (runId && live) live.fail(runId);
  }
}
