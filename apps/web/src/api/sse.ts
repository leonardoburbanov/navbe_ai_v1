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
  step?: string;
  status?: string;
  live_url?: string;
};

type DagActions = {
  resetRun: (workflowId: string) => void;
  patchStep: (
    workflowId: string,
    step: string,
    status: "idle" | "running" | "succeeded" | "failed" | "skipped",
  ) => void;
};

type LiveActions = {
  upsert: (partial: {
    runId: string;
    workflowId: string;
    processSlug?: string | null;
    status?: "running" | "completed" | "failed";
    step?: string | null;
  }) => void;
  setStep: (runId: string, step: string) => void;
  complete: (runId: string) => void;
  fail: (runId: string) => void;
};

type ProcessActions = {
  patchStatus: (workflowId: string, status: string) => void;
};

/** Map a hub SSE payload to dag + live + process store actions. Pure — unit-tested. */
export function handleSsePayload(
  event: SseEvent,
  dag: DagActions,
  live?: LiveActions,
  process?: ProcessActions,
): void {
  const wf = event.workflow_id;
  if (!wf || !event.type) return;

  const runId = event.run_id;
  const slug = event.process_slug ?? null;

  if (event.type === "run.started" || event.type === "run.preview.started") {
    dag.resetRun(wf);
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
    dag.patchStep(wf, event.step, "running");
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
    dag.patchStep(wf, event.step, "succeeded");
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
    if (event.step) dag.patchStep(wf, event.step, "failed");
    if (runId && live) live.fail(runId);
  }
}
