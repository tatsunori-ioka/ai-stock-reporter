import {
  buildSmokeDispatchCommand,
  dispatchSmokeGithubWorkflow,
  parseSmokeArguments,
} from "../src/index.js";

async function main(): Promise<void> {
  const asOf = parseSmokeArguments(process.argv.slice(2));
  const token = process.env.GITHUB_ACTIONS_TOKEN ?? "";
  const command = buildSmokeDispatchCommand(asOf, token);
  const result = await dispatchSmokeGithubWorkflow(command);
  console.log(
    JSON.stringify({
      event: "smoke_dispatch_completed",
      workflow_run_id: result.workflowRunId,
      run_url: result.runUrl,
      html_url: result.htmlUrl,
    }),
  );
}

main().catch((error: unknown) => {
  const message = error instanceof Error ? error.message : "Smoke dispatch failed.";
  console.error(message);
  process.exitCode = 1;
});
