import { describe, expect, test } from "vitest";
import { STATUS_COLORS, statusColor } from "../statusColors";

describe("statusBadge colors", () => {
  test("maps each status to the canonical color", () => {
    expect(statusColor("idle")).toBe(STATUS_COLORS.idle);
    expect(statusColor("running")).toBe(STATUS_COLORS.running);
    expect(statusColor("succeeded")).toBe(STATUS_COLORS.succeeded);
    expect(statusColor("failed")).toBe(STATUS_COLORS.failed);
    expect(statusColor("skipped")).toBe(STATUS_COLORS.skipped);
  });

  test("unknown status falls back to idle", () => {
    expect(statusColor("weird")).toBe(STATUS_COLORS.idle);
    expect(statusColor(undefined)).toBe(STATUS_COLORS.idle);
  });
});
