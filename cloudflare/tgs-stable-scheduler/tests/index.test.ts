import {
  createExecutionContext,
  createScheduledController,
} from "cloudflare:test";
import { describe, expect, it, vi } from "vitest";

import workflowConfig from "../../../.github/workflows/tgs-stable-cloud-paper.yml?raw";
import smokeScript from "../scripts/smoke-dispatch.ts?raw";
import wranglerConfig from "../wrangler.jsonc?raw";
import worker, {
  ACCEPTED_CRONS,
  GITHUB_API_VERSION,
  asOfFromScheduledTime,
  buildScheduledDispatchPayload,
  buildSmokeDispatchCommand,
  buildSmokeDispatchPayload,
  dispatchKeyFromScheduledTime,
  dispatchScheduledGithubWorkflow,
  dispatchSmokeGithubWorkflow,
  handleScheduled,
  parseSmokeArguments,
  type DispatchCommand,
  type Env,
} from "../src/index.js";

const PRODUCTION_CRON = "37 7 * * MON-FRI";
const REMOVED_LATE_CRON = "7 8 * * MON-FRI";
const SCHEDULED_TIME = "2026-07-16T07:37:00.000Z";
const TOKEN = "unit-test-secret-token";
const RUN_DETAILS = {
  workflow_run_id: 123456,
  run_url: "https://api.github.com/repos/tatsunori-ioka/ai-stock-reporter/actions/runs/123456",
  html_url: "https://github.com/tatsunori-ioka/ai-stock-reporter/actions/runs/123456",
};

function command(overrides: Partial<DispatchCommand> = {}): DispatchCommand {
  return {
    token: TOKEN,
    asOf: "2026-07-16",
    dispatchKey: `cloudflare_cron:${SCHEDULED_TIME}`,
    scheduledTime: SCHEDULED_TIME,
    ...overrides,
  };
}

function successResponse(): Response {
  return Response.json(RUN_DETAILS, { status: 200 });
}

describe("scheduled date and identity", () => {
  it("derives the JST score date from controller.scheduledTime", () => {
    expect(asOfFromScheduledTime(Date.parse(SCHEDULED_TIME))).toBe("2026-07-16");
  });

  it("does not use the delayed Worker start time", () => {
    const now = vi.spyOn(Date, "now").mockReturnValue(Date.parse("2026-07-16T14:30:00.000Z"));
    expect(asOfFromScheduledTime(Date.parse(SCHEDULED_TIME))).toBe("2026-07-16");
    expect(now).not.toHaveBeenCalled();
    now.mockRestore();
  });

  it("keeps a delayed Friday event on Friday", () => {
    expect(asOfFromScheduledTime(Date.parse("2026-07-17T07:37:00.000Z"))).toBe("2026-07-17");
  });

  it("generates dispatch_key from the canonical scheduledTime", () => {
    expect(dispatchKeyFromScheduledTime(Date.parse(SCHEDULED_TIME))).toBe(
      `cloudflare_cron:${SCHEDULED_TIME}`,
    );
  });
});

describe("scheduled GitHub workflow dispatch", () => {
  it("rejects a blank dispatch_key before fetch", async () => {
    const fetchImpl = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) => successResponse(),
    );
    const failure = dispatchScheduledGithubWorkflow(command({ dispatchKey: "" }), {
      fetchImpl,
      auditLogger: vi.fn(),
    });

    await expect(failure).rejects.toThrow("dispatch_key is required");
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("sends the fixed execute payload and explicit GitHub headers", async () => {
    const fetchImpl = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) => successResponse(),
    );
    await dispatchScheduledGithubWorkflow(command(), { fetchImpl, auditLogger: vi.fn() });

    const [url, init] = fetchImpl.mock.calls[0];
    expect(url).toBe(
      "https://api.github.com/repos/tatsunori-ioka/ai-stock-reporter/actions/workflows/tgs-stable-cloud-paper.yml/dispatches",
    );
    expect(JSON.parse(String(init?.body))).toEqual({
      ref: "main",
      inputs: {
        as_of: "2026-07-16",
        dry_run: false,
        skip_dashboard: false,
        trigger_origin: "cloudflare_cron",
        dispatch_key: `cloudflare_cron:${SCHEDULED_TIME}`,
      },
    });
    expect(init?.headers).toMatchObject({
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${TOKEN}`,
      "User-Agent": "tgs-stable-cloudflare-scheduler",
      "X-GitHub-Api-Version": GITHUB_API_VERSION,
    });
  });

  it("cannot change the scheduled execute policy with extra command fields", () => {
    const forgedCommand = {
      ...command(),
      dryRun: true,
      skipDashboard: true,
      triggerOrigin: "manual_ui",
    } as unknown as DispatchCommand;
    const payload = buildScheduledDispatchPayload(forgedCommand);

    expect(payload.ref).toBe("main");
    expect(payload.inputs.dry_run).toBe(false);
    expect(payload.inputs.skip_dashboard).toBe(false);
    expect(payload.inputs.trigger_origin).toBe("cloudflare_cron");
  });

  it("returns and safely audits run details from a 200 response", async () => {
    const logs: string[] = [];
    const result = await dispatchScheduledGithubWorkflow(command(), {
      fetchImpl: vi.fn(async () => successResponse()),
      auditLogger: (message) => logs.push(message),
    });

    expect(result).toEqual({
      workflowRunId: RUN_DETAILS.workflow_run_id,
      runUrl: RUN_DETAILS.run_url,
      htmlUrl: RUN_DETAILS.html_url,
    });
    expect(JSON.parse(logs[0])).toMatchObject({
      dispatch_key: `cloudflare_cron:${SCHEDULED_TIME}`,
      dry_run: false,
      skip_dashboard: false,
      workflow_run_id: RUN_DETAILS.workflow_run_id,
      run_url: RUN_DETAILS.run_url,
      html_url: RUN_DETAILS.html_url,
    });
    expect(logs.join("\n")).not.toContain(TOKEN);
  });

  it.each([400, 401, 500])("fails without logging a %s response body", async (status) => {
    const logs: string[] = [];
    const response = new Response(`response body containing ${TOKEN}`, { status });
    const failure = dispatchScheduledGithubWorkflow(command(), {
      fetchImpl: vi.fn(async () => response),
      auditLogger: (message) => logs.push(message),
    });

    await expect(failure).rejects.toThrow(`HTTP ${status}`);
    await expect(failure).rejects.not.toThrow(TOKEN);
    expect(logs.join("\n")).not.toContain(TOKEN);
  });

  it("does not include the token in payload, logs, or network errors", async () => {
    const logs: string[] = [];
    const fetchImpl = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
      expect(String(init?.body)).not.toContain(TOKEN);
      throw new Error(`transport accidentally included ${TOKEN}`);
    });
    const failure = dispatchScheduledGithubWorkflow(command(), {
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
    const failure = dispatchScheduledGithubWorkflow(command(), {
      fetchImpl: vi.fn(async () => Response.json(unsafeDetails, { status: 200 })),
      auditLogger: (message) => logs.push(message),
    });

    await expect(failure).rejects.toThrow("invalid run details");
    await expect(failure).rejects.not.toThrow(TOKEN);
    expect(logs).toEqual([]);
  });
});

describe("smoke policy", () => {
  it("keeps the smoke payload fixed to dry-run without Dashboard writes", () => {
    const smoke = buildSmokeDispatchCommand("2026-07-16", TOKEN);
    const payload = buildSmokeDispatchPayload(smoke);

    expect(Object.isFrozen(smoke)).toBe(true);
    expect(payload.ref).toBe("main");
    expect(payload.inputs.dry_run).toBe(true);
    expect(payload.inputs.skip_dashboard).toBe(true);
    expect(payload.inputs.trigger_origin).toBe("cloudflare_cron");
  });

  it("uses only the dry-run dispatch entrypoint", async () => {
    const fetchImpl = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) => successResponse(),
    );
    await dispatchSmokeGithubWorkflow(buildSmokeDispatchCommand("2026-07-16", TOKEN), {
      fetchImpl,
      auditLogger: vi.fn(),
    });

    const [, init] = fetchImpl.mock.calls[0];
    const payload = JSON.parse(String(init?.body));
    expect(payload.inputs.dry_run).toBe(true);
    expect(payload.inputs.skip_dashboard).toBe(true);
    expect(smokeScript).toContain("dispatchSmokeGithubWorkflow");
    expect(smokeScript).not.toContain("dispatchScheduledGithubWorkflow");
  });

  it("cannot generate execute with extra smoke command fields", () => {
    const forgedCommand = {
      ...buildSmokeDispatchCommand("2026-07-16", TOKEN),
      dryRun: false,
      skipDashboard: false,
    } as unknown as DispatchCommand;
    const payload = buildSmokeDispatchPayload(forgedCommand);

    expect(payload.inputs.dry_run).toBe(true);
    expect(payload.inputs.skip_dashboard).toBe(true);
  });

  it("rejects smoke arguments that attempt to set dry_run=false", () => {
    expect(() =>
      parseSmokeArguments(["--as-of", "2026-07-16", "--dry-run", "false"]),
    ).toThrow("Usage");
  });
});

describe("scheduled handler", () => {
  it("accepts only 16:37 and directly awaits its fixed execute dispatch", async () => {
    const controller = createScheduledController({
      cron: PRODUCTION_CRON,
      scheduledTime: new Date(SCHEDULED_TIME),
    });
    const noRetry = vi.spyOn(controller, "noRetry");
    const fetchImpl = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) => successResponse(),
    );

    const result = await handleScheduled(
      controller,
      { GITHUB_ACTIONS_TOKEN: TOKEN },
      { fetchImpl, auditLogger: vi.fn() },
    );

    const [, init] = fetchImpl.mock.calls[0];
    expect(noRetry).toHaveBeenCalledOnce();
    expect(result.workflowRunId).toBe(RUN_DETAILS.workflow_run_id);
    expect(JSON.parse(String(init?.body))).toEqual({
      ref: "main",
      inputs: {
        as_of: "2026-07-16",
        dry_run: false,
        skip_dashboard: false,
        trigger_origin: "cloudflare_cron",
        dispatch_key: `cloudflare_cron:${SCHEDULED_TIME}`,
      },
    });
  });

  it("rejects the removed 17:07 Cron before dispatch", async () => {
    const controller = createScheduledController({
      cron: REMOVED_LATE_CRON,
      scheduledTime: new Date("2026-07-16T08:07:00.000Z"),
    });
    const noRetry = vi.spyOn(controller, "noRetry");
    const fetchImpl = vi.fn(async () => successResponse());

    await expect(
      handleScheduled(controller, { GITHUB_ACTIONS_TOKEN: TOKEN }, { fetchImpl }),
    ).rejects.toThrow("Unsupported Cloudflare cron");
    expect(noRetry).toHaveBeenCalledOnce();
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("rejects every other Cron before dispatch", async () => {
    const controller = createScheduledController({
      cron: "0 0 * * *",
      scheduledTime: new Date(SCHEDULED_TIME),
    });
    const noRetry = vi.spyOn(controller, "noRetry");
    const fetchImpl = vi.fn(async () => successResponse());

    await expect(
      handleScheduled(controller, { GITHUB_ACTIONS_TOKEN: TOKEN }, { fetchImpl }),
    ).rejects.toThrow("Unsupported Cloudflare cron");
    expect(noRetry).toHaveBeenCalledOnce();
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("fails the scheduled handler when GitHub returns an error", async () => {
    const controller = createScheduledController({
      cron: PRODUCTION_CRON,
      scheduledTime: new Date(SCHEDULED_TIME),
    });
    const noRetry = vi.spyOn(controller, "noRetry");
    const failure = handleScheduled(
      controller,
      { GITHUB_ACTIONS_TOKEN: TOKEN },
      {
        fetchImpl: vi.fn(async () => new Response(null, { status: 503 })),
        auditLogger: vi.fn(),
      },
    );

    await expect(failure).rejects.toThrow("HTTP 503");
    expect(noRetry).toHaveBeenCalledOnce();
  });

  it("exports only the scheduled Worker handler", () => {
    expect(worker).toHaveProperty("scheduled");
    expect(worker).not.toHaveProperty("fetch");
    const _env: Env = { GITHUB_ACTIONS_TOKEN: TOKEN };
    expect(createExecutionContext()).toBeDefined();
    expect(_env.GITHUB_ACTIONS_TOKEN).toBe(TOKEN);
  });
});

describe("production scheduler configuration", () => {
  it("configures exactly the adopted 16:37 Cron", () => {
    const parsed = JSON.parse(wranglerConfig) as {
      workers_dev?: boolean;
      triggers?: { crons?: string[] };
    };

    expect(ACCEPTED_CRONS).toEqual([PRODUCTION_CRON]);
    expect(parsed.workers_dev).toBe(false);
    expect(parsed.triggers?.crons).toEqual([PRODUCTION_CRON]);
  });

  it("removes GitHub schedule while preserving workflow_dispatch", () => {
    expect(workflowConfig).not.toMatch(/^  schedule:\s*$/m);
    expect(workflowConfig).not.toContain('cron: "17 20 * * 1-5"');
    expect(workflowConfig).toMatch(/^  workflow_dispatch:\s*$/m);
  });
});
