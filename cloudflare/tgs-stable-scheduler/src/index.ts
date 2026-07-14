export const EXPECTED_CRON = "37 7 * * MON-FRI";
export const GITHUB_API_VERSION = "2026-03-10";
export const GITHUB_OWNER = "tatsunori-ioka";
export const GITHUB_REPO = "ai-stock-reporter";
export const GITHUB_WORKFLOW = "tgs-stable-cloud-paper.yml";
export const GITHUB_REF = "main";
export const TRIGGER_ORIGIN = "cloudflare_cron" as const;

const GITHUB_DISPATCH_URL =
  `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}` +
  `/actions/workflows/${GITHUB_WORKFLOW}/dispatches`;
const USER_AGENT = "tgs-stable-cloudflare-scheduler";
const JST_TIME_ZONE = "Asia/Tokyo";
const SCORE_DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

export interface Env {
  GITHUB_ACTIONS_TOKEN: string;
}

export interface DispatchCommand {
  readonly token: string;
  readonly asOf: string;
  readonly dryRun: boolean;
  readonly skipDashboard: boolean;
  readonly triggerOrigin: "cloudflare_cron" | "manual_ui";
  readonly dispatchKey: string;
  readonly scheduledTime: string;
}

export interface DispatchPayload {
  readonly ref: "main";
  readonly inputs: {
    readonly as_of: string;
    readonly dry_run: boolean;
    readonly skip_dashboard: boolean;
    readonly trigger_origin: "cloudflare_cron" | "manual_ui";
    readonly dispatch_key: string;
  };
}

export interface DispatchResult {
  readonly workflowRunId: number;
  readonly runUrl: string;
  readonly htmlUrl: string;
}

export interface DispatchDependencies {
  readonly fetchImpl?: typeof fetch;
  readonly auditLogger?: (message: string) => void;
}

function scheduledDate(value: number): Date {
  const result = new Date(value);
  if (Number.isNaN(result.getTime())) {
    throw new Error("controller.scheduledTime must be a valid epoch timestamp.");
  }
  return result;
}

function assertScoreDate(value: string): void {
  if (!SCORE_DATE_PATTERN.test(value)) {
    throw new Error("as_of must use YYYY-MM-DD format.");
  }
  const parsed = new Date(`${value}T00:00:00.000Z`);
  if (Number.isNaN(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== value) {
    throw new Error("as_of must be a valid calendar date.");
  }
}

export function scheduledTimeIso(value: number): string {
  return scheduledDate(value).toISOString();
}

export function asOfFromScheduledTime(value: number): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: JST_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(scheduledDate(value));
  const values = new Map(parts.map((part) => [part.type, part.value]));
  const year = values.get("year");
  const month = values.get("month");
  const day = values.get("day");
  if (!year || !month || !day) {
    throw new Error("Unable to resolve controller.scheduledTime in Asia/Tokyo.");
  }
  return `${year}-${month}-${day}`;
}

export function dispatchKeyFromScheduledTime(value: number): string {
  return `${TRIGGER_ORIGIN}:${scheduledTimeIso(value)}`;
}

export function buildDispatchPayload(command: DispatchCommand): DispatchPayload {
  assertScoreDate(command.asOf);
  if (command.triggerOrigin === TRIGGER_ORIGIN) {
    if (!command.dispatchKey) {
      throw new Error("dispatch_key is required for cloudflare_cron.");
    }
    const expectedKey = `${TRIGGER_ORIGIN}:${command.scheduledTime}`;
    if (command.dispatchKey !== expectedKey) {
      throw new Error("dispatch_key must match the Cloudflare scheduledTime.");
    }
    const scheduledTime = Date.parse(command.scheduledTime);
    if (Number.isNaN(scheduledTime) || asOfFromScheduledTime(scheduledTime) !== command.asOf) {
      throw new Error("Cloudflare scheduledTime does not match as_of in Asia/Tokyo.");
    }
  }

  return {
    ref: GITHUB_REF,
    inputs: {
      as_of: command.asOf,
      dry_run: command.dryRun,
      skip_dashboard: command.skipDashboard,
      trigger_origin: command.triggerOrigin,
      dispatch_key: command.dispatchKey,
    },
  };
}

function parseDispatchResult(value: unknown): DispatchResult {
  if (typeof value !== "object" || value === null) {
    throw new Error("GitHub workflow dispatch returned invalid run details.");
  }
  const details = value as Record<string, unknown>;
  if (typeof details.workflow_run_id !== "number" || !Number.isInteger(details.workflow_run_id)) {
    throw new Error("GitHub workflow dispatch returned invalid run details.");
  }
  const workflowRunId = details.workflow_run_id;
  const expectedRunUrl =
    `https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/actions/runs/${workflowRunId}`;
  const expectedHtmlUrl =
    `https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}/actions/runs/${workflowRunId}`;
  if (
    workflowRunId <= 0 ||
    details.run_url !== expectedRunUrl ||
    details.html_url !== expectedHtmlUrl
  ) {
    throw new Error("GitHub workflow dispatch returned invalid run details.");
  }
  return {
    workflowRunId,
    runUrl: expectedRunUrl,
    htmlUrl: expectedHtmlUrl,
  };
}

export async function dispatchGithubWorkflow(
  command: DispatchCommand,
  dependencies: DispatchDependencies = {},
): Promise<DispatchResult> {
  const payload = buildDispatchPayload(command);
  if (!command.token.trim()) {
    throw new Error("GITHUB_ACTIONS_TOKEN is required.");
  }

  const fetchImpl = dependencies.fetchImpl ?? fetch;
  let response: Response;
  try {
    response = await fetchImpl(GITHUB_DISPATCH_URL, {
      method: "POST",
      headers: {
        Accept: "application/vnd.github+json",
        Authorization: `Bearer ${command.token}`,
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
      },
      body: JSON.stringify(payload),
    });
  } catch {
    throw new Error("GitHub workflow dispatch request failed.");
  }

  if (response.status !== 200) {
    throw new Error(`GitHub workflow dispatch failed with HTTP ${response.status}.`);
  }

  let responseBody: unknown;
  try {
    responseBody = await response.json();
  } catch {
    throw new Error("GitHub workflow dispatch returned invalid JSON run details.");
  }
  const result = parseDispatchResult(responseBody);
  const auditLogger = dependencies.auditLogger ?? console.log;
  auditLogger(
    JSON.stringify({
      event: "github_workflow_dispatch_accepted",
      as_of: command.asOf,
      trigger_origin: command.triggerOrigin,
      scheduledTime: command.scheduledTime,
      dispatch_key: command.dispatchKey,
      workflow_run_id: result.workflowRunId,
      run_url: result.runUrl,
      html_url: result.htmlUrl,
    }),
  );
  return result;
}

export function buildSmokeDispatchCommand(asOf: string, token: string): DispatchCommand {
  assertScoreDate(asOf);
  const scheduledTime = `${asOf}T07:37:00.000Z`;
  return Object.freeze({
    token,
    asOf,
    dryRun: true,
    skipDashboard: true,
    triggerOrigin: TRIGGER_ORIGIN,
    dispatchKey: `${TRIGGER_ORIGIN}:${scheduledTime}`,
    scheduledTime,
  });
}

export function parseSmokeArguments(argv: readonly string[]): string {
  if (argv.length !== 2 || argv[0] !== "--as-of" || !argv[1]) {
    throw new Error("Usage: pnpm smoke:dispatch --as-of YYYY-MM-DD");
  }
  assertScoreDate(argv[1]);
  return argv[1];
}

export async function handleScheduled(
  controller: ScheduledController,
  env: Env,
  dependencies: DispatchDependencies = {},
): Promise<DispatchResult> {
  controller.noRetry();
  if (controller.cron !== EXPECTED_CRON) {
    throw new Error(`Unsupported Cloudflare cron: ${controller.cron}.`);
  }

  const scheduledTime = scheduledTimeIso(controller.scheduledTime);
  const command: DispatchCommand = {
    token: env.GITHUB_ACTIONS_TOKEN,
    asOf: asOfFromScheduledTime(controller.scheduledTime),
    dryRun: false,
    skipDashboard: false,
    triggerOrigin: TRIGGER_ORIGIN,
    dispatchKey: dispatchKeyFromScheduledTime(controller.scheduledTime),
    scheduledTime,
  };
  return await dispatchGithubWorkflow(command, dependencies);
}

export default {
  async scheduled(
    controller: ScheduledController,
    env: Env,
    _ctx: ExecutionContext,
  ): Promise<void> {
    await handleScheduled(controller, env);
  },
} satisfies ExportedHandler<Env>;
