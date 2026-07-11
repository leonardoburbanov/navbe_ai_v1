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

/** Map a hub SSE payload to dagStore actions. Pure — unit-tested. */
export function handleSsePayload(
  event: {
    type?: string;
    workflow_id?: string;
    step?: string;
  },
  actions: {
    resetRun: (workflowId: string) => void;
    patchStep: (
      workflowId: string,
      step: string,
      status: "idle" | "running" | "succeeded" | "failed" | "skipped",
    ) => void;
  },
): void {
  const wf = event.workflow_id;
  if (!wf || !event.type) return;

  if (event.type === "run.started" || event.type === "run.preview.started") {
    actions.resetRun(wf);
    return;
  }
  if (event.type === "run.step.started" && event.step) {
    actions.patchStep(wf, event.step, "running");
    return;
  }
  if (event.type === "run.step" && event.step) {
    actions.patchStep(wf, event.step, "succeeded");
    return;
  }
  if (event.type === "run.failed" && event.step) {
    actions.patchStep(wf, event.step, "failed");
  }
}
