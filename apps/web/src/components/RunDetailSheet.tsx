import { useEffect, useState } from "react";
import {
  type RunRow,
  type RunStepTiming,
  pauseRunApi,
  resumeRunApi,
  stopRunApi,
} from "../api/client";
import { formatDurationMs } from "../lib/formatDuration";
import { useDagStore } from "../store/dagStore";
import { RunMetrics } from "./RunMetrics";
import { StatusBadge } from "./StatusBadge";
import { NavbeFlow } from "./dag/NavbeFlow";
import { Button } from "./ui/button";
import {
  Sheet,
  SheetBody,
  SheetClose,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "./ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";

type Props = {
  run: RunRow;
  onClose: () => void;
  onUpdated?: () => void;
};

function stepTimings(run: RunRow): RunStepTiming[] {
  if (Array.isArray(run.steps) && run.steps.length > 0) return run.steps;
  const raw = run.output?.steps;
  if (!Array.isArray(raw)) return [];
  return raw.filter(
    (s): s is RunStepTiming =>
      !!s &&
      typeof s === "object" &&
      typeof (s as { id?: unknown }).id === "string",
  ) as RunStepTiming[];
}

/** Left drawer: per-run DAG + report, with Pause / Resume / Stop. */
export function RunDetailSheet({ run, onClose, onUpdated }: Props) {
  const [tab, setTab] = useState("dag");
  const [selectedStep, setSelectedStep] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const seedSteps = useDagStore((s) => s.seedSteps);
  const workflowId = run.workflow_id;
  const live =
    run.status === "running" ||
    run.status === "paused" ||
    run.control === "pause_requested" ||
    run.control === "cancel_requested";
  const timings = stepTimings(run);

  useEffect(() => {
    const steps = stepTimings(run);
    if (steps.length > 0 && run.run_id) {
      seedSteps(
        run.run_id,
        steps.map((s) => ({ id: s.id, status: s.status })),
      );
    }
  }, [run, seedSteps]);

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setErr(null);
    try {
      await fn();
      onUpdated?.();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (!workflowId) {
    return null;
  }

  return (
    <Sheet open onOpenChange={(o) => !o && onClose()}>
      <SheetHeader>
        <div className="flex items-start justify-between gap-2">
          <div>
            <SheetTitle className="flex items-center gap-2">
              Run · {run.slug ?? run.process_slug ?? "unnamed"}
              {live ? (
                <span className="text-[11px] font-bold tracking-wide text-blue-600">
                  LIVE
                </span>
              ) : null}
            </SheetTitle>
            <SheetDescription>{run.run_id}</SheetDescription>
          </div>
          <SheetClose onClick={onClose} />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={run.status} pulse={run.status === "running"} />
          <span className="text-xs text-muted-foreground">
            {formatDurationMs(run.duration_ms)}
          </span>
          {(run.status === "running" || run.control === "pause_requested") && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() => act(() => pauseRunApi(run.run_id))}
            >
              Pause
            </Button>
          )}
          {run.status === "paused" && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() => act(() => resumeRunApi(run.run_id))}
            >
              Resume
            </Button>
          )}
          {(run.status === "running" || run.status === "paused") && (
            <Button
              type="button"
              size="sm"
              variant="destructive"
              disabled={busy}
              onClick={() => act(() => stopRunApi(run.run_id))}
            >
              Stop
            </Button>
          )}
        </div>
        {err && <p className="m-0 text-xs text-destructive">{err}</p>}
      </SheetHeader>

      <Tabs
        value={tab}
        onValueChange={setTab}
        className="flex min-h-0 flex-1 flex-col"
      >
        <div className="border-b px-4 pt-2">
          <TabsList>
            <TabsTrigger value="dag">DAG</TabsTrigger>
            <TabsTrigger value="report">Report</TabsTrigger>
          </TabsList>
        </div>
        <SheetBody>
          <TabsContent value="dag">
            <NavbeFlow
              workflowId={workflowId}
              runId={run.run_id}
              selectedStep={selectedStep}
              onSelectStep={setSelectedStep}
              height={360}
            />
            {timings.length > 0 && (
              <ul className="mt-3 list-none space-y-0 p-0 text-sm">
                {timings.map((s) => (
                  <li key={`${s.id}-${s.attempt ?? 1}`}>
                    <button
                      type="button"
                      className={`flex w-full justify-between border-b border-border py-1.5 text-left ${
                        selectedStep === s.id
                          ? "font-semibold text-foreground"
                          : "text-muted-foreground"
                      }`}
                      onClick={() => setSelectedStep(s.id)}
                    >
                      <span>{s.id}</span>
                      <span>
                        {s.status}
                        {" · "}
                        {formatDurationMs(s.duration_ms)}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </TabsContent>
          <TabsContent value="report">
            <RunMetrics output={run.output} durationMs={run.duration_ms} />
            {typeof run.output?.report_date === "string" && (
              <p className="mt-3 text-sm">
                Report date: <strong>{run.output.report_date}</strong>
                {run.output.email_sent === true
                  ? " · emailed"
                  : run.output.email_skipped === true
                    ? " · email skipped (no recipients)"
                    : run.output.preview_path
                      ? " · preview only"
                      : ""}
              </p>
            )}
            {typeof run.output?.preview_path === "string" && (
              <p className="break-all text-xs text-muted-foreground">
                HTML: {run.output.preview_path}
              </p>
            )}
            {run.output?.totals != null && (
              <pre className="mt-3 overflow-auto rounded-lg bg-muted p-3 text-[11px]">
                {JSON.stringify(run.output.totals, null, 2)}
              </pre>
            )}
            {run.error && (
              <pre className="mt-3 whitespace-pre-wrap text-[11px] text-destructive">
                {run.error}
              </pre>
            )}
            {run.output?.compare_result != null && (
              <pre className="mt-3 overflow-auto rounded-lg bg-muted p-3 text-[11px]">
                {JSON.stringify(run.output.compare_result, null, 2)}
              </pre>
            )}
          </TabsContent>
        </SheetBody>
      </Tabs>
    </Sheet>
  );
}
