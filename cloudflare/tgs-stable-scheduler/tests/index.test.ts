import {
  createExecutionContext,
  createScheduledController,
} from "cloudflare:test";
import { describe, expect, it, vi } from "vitest";

import worker, {
  EXPECTED_CRON,
  GITHUB_API_VERSION,
  asOfFromScheduledTime,
  buildDispatchPayload,
  buildSmokeDispatchCommand,
  dispatchGithubWorkflow,
  dispatchKeyFromScheduledTime,
  handleScheduled,
  parseSmokeArguments,
  type DispatchCommand,
  type Env,
} from "../src/index.js";

const TOKEN = "unit-test-secret-token";
const RUN_DETAILS = {
  workflow_run_id: 123456,
  run_url: "https://api.github.com/repos/tatsunori-ioka/ai-stock-reporter/actions/runs/123456",
  html_url: "https://github.com/tatsunori-ioka/ai-stock-reporter/actions/runs/123456",
};

function command(overrides: Partial<DispatchCommand> = {}): DispatchCommand {
  const scheduledTime = "2026-07-14T07:37:00.000Z";
  return {
    token: TOKEN,
    asOf: "2026-07-14",
    dryRun: false,
    skipDashboard: false,
    triggerOrigin: "cloudflare_cron",
    dispatchKey: `cloudflare_cron:${scheduledTime}`,
    scheduledTime,
    ...overrides,
  };
}

function successResponse(): Response {
  return Response.json(RUN_DETAILS, { status: 200 });
}

describe("scheduled date and identity", () => {
  it("derives the 2026-07-14 JST score date from scheduledTime", () => {
    expect(asOfFromScheduledTime(Date.parse("2026-07-14T07:37:00.000Z"))).toBe("2026-07-14");
  });

  it("does not use the actual delayed Worker start time", () => {
    const now = vi.spyOn(Date, "now").mockReturnValue(Date.parse("2026-07-14T14:30:00.000Z"));
    expect(asOfFromScheduledTime(Date.parse("2026-07-14T07:37:00.000Z"))).toBe("2026-07-14");
    expect(now).not.toHaveBeenCalled();
    now.mockRestore();
  });

  it("keeps a delayed Friday event on Friday", () => {
    expect(asOfFromScheduledTime(Date.parse("2026-07-17T07:37:00.000Z"))).toBe("2026-07-17");
  });

  it("generates dispatch_key from the canonical ISO scheduledTime", () => {
    expect(dispatchKeyFromScheduledTime(Date.parse("2026-07-14T07:37:00.000Z"))).toBe(
      "cloudflare_cron:2026-07-14T07:37:00.000Z",
    );
  });
});

describe("GitHub workflow dispatch", () => {
  it("rejects a blank cloudflare dispatch_key before fetch", async () => {
    const fetchImpl = vi.fn(async () => successResponse());
    const failure = dispatchGithubWorkflow(command({ dispatchKey: "" }), {
      fetchImpl,
      auditLogger: vi.fn(),
    });

    await expect(failure).rejects.toThrow("dispatch_key is required");
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("accepts a blank manual_ui dispatch_key", () => {
    const payload = buildDispatchPayload(
      command({
        triggerOrigin: "manual_ui",
        dispatchKey: "",
        scheduledTime: "",
      }),
    );

    expect(payload.inputs.trigger_origin).toBe("manual_ui");
    expect(payload.inputs.dispatch_key).toBe("");
  });

  it("sends the fixed payload and explicit GitHub headers", async () => {
    const fetchImpl = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) => successResponse(),
    );
    await dispatchGithubWorkflow(command(), { fetchImpl, auditLogger: vi.fn() });

    const [url, init] = fetchImpl.mock.calls[0];
    const payload = JSON.parse(String(init?.body));
    expect(url).toBe(
      "https://api.github.com/repos/tatsunori-ioka/ai-stock-reporter/actions/workflows/tgs-stable-cloud-paper.yml/dispatches",
    );
    expect(payload).toEqual({
      ref: "main",
      inputs: {
        as_of: "2026-07-14",
        dry_run: false,
        skip_dashboard: false,
        trigger_origin: "cloudflare_cron",
        dispatch_key: "cloudflare_cron:2026-07-14T07:37:00.000Z",
      },
    });
    expect(init?.headers).toMatchObject({
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${TOKEN}`,
      "User-Agent": "tgs-stable-cloudflare-scheduler",
      "X-GitHub-Api-Version": GITHUB_API_VERSION,
    });
  });

  it("returns and safely audits run details from a 200 response", async () => {
    const logs: string[] = [];
    const result = await dispatchGithubWorkflow(command(), {
      fetchImpl: vi.fn(async () => successResponse()),
      auditLogger: (message) => logs.push(message),
    });

    expect(result).toEqual({
      workflowRunId: RUN_DETAILS.workflow_run_id,
      runUrl: RUN_DETAILS.run_url,
      htmlUrl: RUN_DETAILS.html_url,
    });
    expect(JSON.parse(logs[0])).toMatchObject({
      workflow_run_id: RUN_DETAILS.workflow_run_id,
      run_url: RUN_DETAILS.run_url,
      html_url: RUN_DETAILS.html_url,
      dispatch_key: "cloudflare_cron:2026-07-14T07:37:00.000Z",
    });
    expect(logs.join("\n")).not.toContain(TOKEN);
  });

  it.each([400, 401, 500])("fails without logging a %s response body", async (status) => {
    const logs: string[] = [];
    const response = new Response(`response body containing ${TOKEN}`, { status });
    const failure = dispatchGithubWorkflow(command(), {
      fetchImpl: vi.fn(async () => response),
      auditLogger: (message) => logs.push(message),
    });

    await expect(failure).rejects.toThrow(`HTTP ${status}`);
    await expect(failure).rejects.not.toThrow(TOKEN);
    expect(logs.join("\n")).not.toContain(TOKEN);
  });

  it("does not include the token in payload, audit logs, or network errors", async () => {
    const logs: string[] = [];
    const fetchImpl = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      expect(String(init?.body)).not.toContain(TOKEN);
      throw new Error(`transport accidentally included ${TOKEN}`);
    });
    const failure = dispatchGithubWorkflow(command(), {
      fetchImpl,
      auditLogger: (message) => logs.push(message),
    });

    await expect(failure).rejects.toThrow("request failed");
    await expect(failure).rejects.not.toThrow(TOKEN);
    expect(logs.join("\n")).not.toContain(TOKEN);
  });

  it("rejects unexpected run URLs before audit logging", async () => {
    const logs: string[] = [];
    const unsafeDetails = {
      ...RUN_DETAILS,
      html_url: `https://github.com/${TOKEN}`,
    };
    const failure = dispatchGithubWorkflow(command(), {
      fetchImpl: vi.fn(async () => Response.json(unsafeDetails, { status: 200 })),
      auditLogger: (message) => logs.push(message),
    });

    await expect(failure).rejects.toThrow("invalid run details");
    await expect(failure).rejects.not.toThrow(TOKEN);
    expect(logs).toEqual([]);
  });
});

describe("smoke policy", () => {
  it("has no input capable of changing dry_run or skip_dashboard to false", () => {
    const smoke = buildSmokeDispatchCommand("2026-07-14", TOKEN);
    const payload = buildDispatchPayload(smoke);

    expect(Object.isFrozen(smoke)).toBe(true);
    expect(payload.ref).toBe("main");
    expect(payload.inputs.dry_run).toBe(true);
    expect(payload.inputs.skip_dashboard).toBe(true);
    expect(payload.inputs.trigger_origin).toBe("cloudflare_cron");
  });

  it("rejects smoke arguments that attempt to set dry_run=false", () => {
    expect(() =>
      parseSmokeArguments(["--as-of", "2026-07-14", "--dry-run", "false"]),
    ).toThrow("Usage");
  });
});

describe("scheduled handler", () => {
  it("calls noRetry and directly awaits a successful dispatch", async () => {
    const controller = createScheduledController({
      cron: EXPECTED_CRON,
      scheduledTime: new Date("2026-07-14T07:37:00.000Z"),
    });
    const noRetry = vi.spyOn(controller, "noRetry");
    const result = await handleScheduled(controller, { GITHUB_ACTIONS_TOKEN: TOKEN }, {
      fetchImpl: vi.fn(async () => successResponse()),
      auditLogger: vi.fn(),
    });

    expect(noRetry).toHaveBeenCalledOnce();
    expect(result.workflowRunId).toBe(RUN_DETAILS.workflow_run_id);
  });

  it("fails the scheduled handler when GitHub returns an error", async () => {
    const controller = createScheduledController({
      cron: EXPECTED_CRON,
      scheduledTime: new Date("2026-07-14T07:37:00.000Z"),
    });
    const noRetry = vi.spyOn(controller, "noRetry");
    const failure = handleScheduled(controller, { GITHUB_ACTIONS_TOKEN: TOKEN }, {
      fetchImpl: vi.fn(async () => new Response(null, { status: 503 })),
      auditLogger: vi.fn(),
    });

    await expect(failure).rejects.toThrow("HTTP 503");
    expect(noRetry).toHaveBeenCalledOnce();
  });

  it("rejects an unexpected cron before dispatch", async () => {
    const controller = createScheduledController({
      cron: "0 0 * * *",
      scheduledTime: new Date("2026-07-14T07:37:00.000Z"),
    });
    const noRetry = vi.spyOn(controller, "noRetry");
    const fetchImpl = vi.fn(async () => successResponse());

    await expect(
      handleScheduled(controller, { GITHUB_ACTIONS_TOKEN: TOKEN }, { fetchImpl }),
    ).rejects.toThrow("Unsupported Cloudflare cron");
    expect(noRetry).toHaveBeenCalledOnce();
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("exports only the scheduled Worker handler", () => {
    expect(worker).toHaveProperty("scheduled");
    expect(worker).not.toHaveProperty("fetch");
    const _env: Env = { GITHUB_ACTIONS_TOKEN: TOKEN };
    expect(createExecutionContext()).toBeDefined();
    expect(_env.GITHUB_ACTIONS_TOKEN).toBe(TOKEN);
  });
});
