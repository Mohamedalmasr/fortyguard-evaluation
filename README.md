# FortyGuard Evaluation

## Scope

This evaluation records the supplied executed MCP results for `credit_balance` and selected `monitoring` operations, alongside separate schema-only inspections of `heatmap_read`, `report_read`, `temperature_routing_read`, `env_params`, and `monitoring`.

It also records catalog-level findings about the exposed operations and the observed `monitoring/list_alerts` failures. The source-code test under `src/tests/` is outside the executed MCP results in this log.

## Methodology

- Keep executed MCP calls distinct from schema/description inspection.
- Record trace IDs, latencies, costs, and returned balance only where supplied.
- Leave unavailable values blank in `evaluation_log.csv`; do not infer timestamps, inputs, costs, or outcomes.
- Do not treat schema inspection as an execution or test result.

## Verified findings

### Executed MCP tests

- `credit_balance` passed: trace `05e662bcf543`, latency 622 ms, cost 0.
- `monitoring/list_monitors` passed: trace `09a4ed843951`, latency 497 ms, cost 0.
- `monitoring/list_alerts` failed with `invalid_input`: trace `c72977ebfe0a`.
- A retry of `monitoring/list_alerts` also failed with `invalid_input`: trace `915167d76178`.
- `credit_balance` verification passed: trace `72d16e025775`, latency 562 ms, cost 0; the balance remained 1,000,000.

The two `list_alerts` failures make the invalid-input behavior reproducible across the reported attempts. The cause has not been established.

### Schema-only and catalog findings

- The descriptions and schemas for `heatmap_read`, `report_read`, `temperature_routing_read`, `env_params`, and `monitoring` were inspected. These inspections were not executions.
- Read-tool credit costs are unspecified in the inspected descriptions. No zero-cost claim is made for these tools.
- No dedicated health-check or test/demo operation was present in the exposed catalog.

## Local REST API Validation

A separate Python-based REST API validation client was developed using the documented endpoint contracts.

- Implemented offline request validation before transport.
- Added automated tests for endpoint parameters, data types, and validation rules.
- Fixed several identified validation gaps.
- Final test result: **258 tests passed**.

These were local automated tests using the documented API contracts and did not involve live REST API requests.

## Limitations

- The log contains no timestamps or request inputs because none were supplied.
- Costs and latencies for the failed `list_alerts` calls were not supplied.
- The `list_alerts` failure is documented from two attempts, but there is not enough evidence to identify its cause or establish broader impact.
- Schema-only inspection does not verify runtime behavior.
- The existing `src/tests/test_http_request.py` was not run as part of this documentation update; its presence does not establish execution.

## Pending work

- Investigate the input contract or validation path behind `monitoring/list_alerts` using an approved, credit-safe method before any further live call.
- If further execution is approved, record timestamps, exact inputs, returned errors, and any disclosed costs in the log.
- Keep schema-only observations and runtime test results in their separate record types.
