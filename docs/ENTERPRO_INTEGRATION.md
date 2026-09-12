# FinSight EnterPro Integration

## Phase 5 status

**Blocked for live execution.**

The current official Enter documentation adds one concrete integration
mechanism: Enter Agent Builder supports a Custom MCP configuration using a
JSON `mcpServers` entry with a remote `url` and optional `headers`.
Enter supports URL-based Streamable HTTP MCP (including legacy SSE
compatibility), but does not support local `command`/stdio MCP servers.

The available browser session only exposes the public Agent Builder page; it
does not contain an authenticated Enter project, Agent Panel, MCPs panel, or
published agent workspace. The local environment also contains no Enter
credentials, SDK, CLI, or public HTTPS deployment for FinSight.

The public Enter AI model reference lists several hosted models but does not
list Qwen. Qwen therefore cannot be verified as an Enter-native model from
the available workspace/documentation. FinSight's existing Qwen service
remains the only verified Qwen engine.

No EnterPro SDK, CLI, package, account configuration, endpoint, or credential
is available in this repository or local environment. A live integration
cannot be claimed or tested without those account/workspace details.

## Intended architecture

```text
React
  -> EnterPro Agent Builder/runtime workflow
  -> Qwen reasoning and explanation
  -> approved FinSight financial tool
  -> FastAPI deterministic service
  -> SQLite
  -> deterministic evidence
  -> Qwen explanation
  -> EnterPro workflow result
  -> React
```

Responsibilities remain separated:

- **EnterPro:** enterprise agent/workflow orchestration, workflow state,
  deployment, and supported runtime observability.
- **Qwen:** natural-language understanding, tool selection, reasoning,
  explanation, and recommendation narrative.
- **FastAPI:** deterministic financial calculations and database-backed tools.
- **SQLite:** persistent financial data.
- **React:** presentation and user interaction.

## Workflows to configure in EnterPro Agent Builder

These are the documented FinSight workflow designs. They are not represented
as fabricated local EnterPro workflow files because the reference does not
define a local file format.

### Financial question

1. Receive a user question.
2. Validate the question.
3. Ask Qwen to interpret the intent.
4. Permit Qwen to select only an approved FinSight tool.
5. Invoke the existing FastAPI-backed tool.
6. Return deterministic evidence to Qwen.
7. Ask Qwen for a grounded explanation.
8. Validate and return the structured result to React.

### Decision evaluation

Use the same flow with one of the existing decision tools:

- `evaluate_hiring`
- `evaluate_purchase`
- `evaluate_budget_change`
- `evaluate_loan`
- `evaluate_expense_reduction`
- `evaluate_decision`

The result must preserve decision, risk score, risk level, evidence,
assumptions, risks, recommendation, and provenance labels.

### Anomaly investigation

Invoke `detect_anomalies`, then ask Qwen to explain the returned indicators.
Anomalies must remain review indicators and must not be described as proven
fraud or misconduct.

### Cash forecast

Invoke `forecast_cashflow`, then ask Qwen to explain the forecast, assumptions,
uncertainty, and risks. Forecast values must remain labelled `FORECAST`.

## Existing FinSight integration points

The Qwen/FastAPI boundary already exists at `POST /ai/ask`. The approved
deterministic tools are:

- `get_cashflow`
- `get_expense_breakdown`
- `get_vendor_analysis`
- `detect_anomalies`
- `forecast_cashflow`
- `budget_analysis`
- `evaluate_hiring`
- `evaluate_purchase`
- `evaluate_budget_change`
- `evaluate_loan`
- `evaluate_expense_reduction`
- `evaluate_decision`

The existing backend validates tool names and arguments through the explicit
allowlist before calling deterministic services. EnterPro should call this
existing boundary rather than accessing SQLite or executing local code.

## Documented MCP configuration mechanism

The official Enter MCP documentation specifies this configuration shape in
the authenticated Enter Agent Panel:

```json
{
  "mcpServers": {
    "finsight": {
      "url": "https://PUBLIC-FINSIGHT-MCP-HOST/mcp",
      "headers": {
        "Authorization": "Bearer <ENTER_CONFIGURED_SECRET>"
      }
    }
  }
}
```

This is a configuration template only. The URL and secret above are
placeholders and have not been used as credentials.

For FinSight, the remote server would expose only the approved financial
operations and would validate every tool call before delegating to FastAPI.
Financial calculations would remain in the existing deterministic services.

## Configuration and authentication

The MCP documentation establishes that Enter accepts HTTP headers and supports
OAuth for MCP servers that require it, but it does not define FinSight's
actual secret name, tenant configuration, or a hosted FinSight endpoint.
Therefore no EnterPro variables or credentials have been invented or added.

Once the EnterPro workspace is available, record the actual values here:

- Agent/ workflow identifier:
- Tool or Skill configuration:
- FastAPI callback URL:
- Authentication mechanism:
- Secret variable names:
- Runtime/deployment target:
- Timeout and retry settings:

Secrets must remain in the EnterPro account/secret store or server-side
environment configuration and must never be sent to React.

## Security model

EnterPro and Qwen must only reach the approved FinSight tools. They must not
receive arbitrary Python, shell, SQL, filesystem, unrestricted HTTP, or
direct SQLite access. Tool arguments must continue to be validated by the
FinSight backend.

Financial output must preserve:

- `ACTUAL`
- `CALCULATED`
- `FORECAST`
- `SCENARIO`
- `AI_RECOMMENDATION`

All displayed amounts remain INR. The anomaly disclaimer remains neutral:

> These are anomaly indicators for review and should not be treated as
> definitive accusations of misconduct.

## Error handling and observability

The eventual EnterPro workflow should surface, where supported by the actual
runtime:

- workflow name
- execution status
- execution duration
- step status
- selected tool
- success/failure
- error reason

Failures from EnterPro, Qwen, FastAPI, invalid tool arguments, empty data,
malformed model output, and timeouts must be returned as explicit error states.
The workflow must never substitute invented financial values.

## Current recheck result

### Confirmed

- Agent Builder is publicly available.
- Skills and Knowledge are configurable in Agent Builder.
- Enter has an Agent Panel with an MCPs section.
- Custom MCP can be added with a JSON `mcpServers` configuration.
- Enter accepts remote URL-based Streamable HTTP MCP.
- Enter does not launch local stdio `command`/`args` MCP processes.

### Not verifiable from this environment

- An authenticated FinSight Enter project or Agent.
- MCP connection status for a FinSight server.
- A published Enter workflow/agent URL.
- Qwen selection inside Enter Agent Builder.
- Enter's external-agent/API invocation contract.
- A live end-to-end execution.

## Required account/workspace information

To implement and verify the live integration, provide access to the Enter
workspace or an Agent Builder export containing:

1. An authenticated Enter project/Agent Builder workspace.
2. A public HTTPS deployment for the FinSight MCP endpoint, or the approved
   Enter-supported hosting path.
3. MCP secret/header or OAuth configuration for that endpoint.
4. The Enter Agent configuration showing how Qwen is selected or how Enter
   invokes the existing FinSight Qwen service.
5. Agent/workflow publish URL and connection status.
6. Retry, timeout, and observability settings available in the workspace.

After those details are supplied, the next implementation can add or deploy
the real URL-based MCP server, configure the four workflows, route the React
assistant through the published Enter workflow, and run an authenticated
end-to-end hiring test.

## Verification performed in this repository

- Repository/environment search found no EnterPro package, SDK, CLI,
  endpoint, credentials, MCP package, or public MCP host.
- Current official MCP documentation was inspected. It confirms URL-based
  Streamable HTTP configuration and rejects local stdio as an option.
- The Enter Agent Builder public page was opened, but no authenticated
  workspace or MCP configuration panel was available.
- Existing Phase 1-4 functionality remains unchanged.
- No EnterPro live execution or Qwen-through-Enter execution was claimed.
- Phase 6 has not been started.

## Deployment-path investigation

### FinSight application requirements

The backend can be started with the existing application command:

```text
cd C:\Users\HP\FinSight\backend
uvicorn main:app --host 0.0.0.0 --port $PORT
```

The repository currently has no Dockerfile, Procfile, cloud-specific
manifest, deployment workflow, or Enter Infrastructure project configuration.
The backend listens on HTTP locally and does not terminate HTTPS itself.

The production process therefore needs to provide:

- a public HTTPS URL reachable by Enter's URL-based MCP client;
- a process command equivalent to `uvicorn main:app --host 0.0.0.0 --port $PORT`;
- server-side environment variables for Qwen configuration;
- a secret store for any MCP authentication header;
- persistent storage for `data/finsight.db`.

SQLite is suitable for the current single-process development/demo deployment,
but a host with ephemeral filesystems must attach persistent storage or the
synthetic database will be lost on restart/redeploy. No database migration was
performed.

### Enter Infrastructure result

The public `https://enter.converge.ai/infra` page and current public Enter
materials do not expose a documented deployment command, runtime manifest,
FastAPI import contract, HTTPS provisioning workflow, or secret-store schema
that can be applied to this repository. Enter Agent Builder documentation
describes deployment of Enter agents and products, not a verified mechanism
for deploying an arbitrary local FastAPI service.

Therefore direct FastAPI deployment through Enter Infrastructure is **not
verified** and must not be claimed.

### Legitimate deployment options

1. **Enter Infrastructure, if enabled in the authenticated workspace**

   This is the preferred path only after the workspace exposes an actual
   service deployment form or documented runtime contract. Configure the
   repository/backend as a Python web service, use the existing Uvicorn
   command, attach persistent SQLite storage, configure Qwen and MCP secrets
   in the platform secret store, and use the HTTPS URL supplied by Enter.
   The exact UI fields, manifest, domain, and secret names must come from the
   workspace; none are invented here.

2. **A managed HTTPS Python host selected by the project owner**

   A conventional managed web-service host can run the backend with the same
   Uvicorn command and provide a provider-assigned HTTPS URL. It must provide
   persistent disk for SQLite or the project must move persistence to a
   supported database later. Provider-specific credentials, domain, and
   configuration were not chosen or created.

3. **A self-managed HTTPS server**

   A server with a reverse proxy/TLS certificate can run Uvicorn privately and
   expose only the allowlisted API/MCP boundary. This requires the project
   owner to provide the server, DNS, certificate, firewall, secret storage,
   process supervision, and backup plan. No such infrastructure is available
   locally.

Tunneling is intentionally excluded because it was not requested and is not a
production deployment.

### Required next step before publishing Enter

Choose and provision one deployment target, then provide:

- the actual public HTTPS base URL;
- persistent-storage configuration for `data/finsight.db`;
- server-side `QWEN_API_KEY`, `QWEN_BASE_URL`, `QWEN_MODEL`, and
  `MOCK_QWEN=false` settings;
- the actual MCP authentication secret/header configuration;
- a health check response from the deployed backend;
- confirmation that `/ai/ask` and the approved MCP endpoint are reachable
  from Enter.

Only after these checks should the Enter agent be connected or published.

## Public references supplied by the reference document

- <https://enter.converge.ai/blog/introducing-enter-pro-agent-builder>
- <https://blog.enter.pro/blog/how-to-build-with-enter-agent-builder>
- <https://blog.enter.pro/blog/use-mcp-in-enter>
- <https://blog.enter.pro/blog/introducing-enter-ai-all>
- <https://enter.pro/>
