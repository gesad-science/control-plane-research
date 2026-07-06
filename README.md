# A2A Control Plane

A local stack for discovering, invoking, and monitoring Agent-to-Agent services. The project includes a FastAPI control plane, a Streamlit frontend, and several mock agents used to test discovery, retries, health checks, and observability end to end.

## What the project does

- Discovers agents automatically from a list of targets or through explicit registration.
- Invokes agents through a simple API with retry and backoff behavior.
- Tracks health, latency, and failures, while exposing metrics in Prometheus format.
- Includes demo agents for echo, arithmetic, text reversal, translation, and flaky behavior.

## How to run it

Prerequisites:
- Docker
- Docker Compose

```bash
docker compose up --build
```

After startup, the main endpoints are:
- API: http://localhost:7000
- UI: http://localhost:8501
- Health check: http://localhost:7000/health

If you want fixed credentials before starting the stack, set them first:

```bash
export CP_API_KEY=devkey-change-me
export CP_REGISTRATION_TOKEN=devtoken-change-me
```

On the first run, the control plane generates default values if you do not define them. To inspect the values being used:

```bash
docker compose logs control-plane | grep -E "API KEY|Registration Token"
```

## How to use the API

Set the API key and list the discovered agents:

```bash
export KEY=devkey-change-me

curl -H "X-API-Key: $KEY" http://localhost:7000/agents
```

Call an agent:

```bash
curl -X POST http://localhost:7000/call \
  -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"agent_name":"echo_agent","input_data":"hello"}'
```

Test the calculator agent:

```bash
curl -X POST http://localhost:7000/call \
  -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"agent_name":"calculator_agent","input_data":{"expression":"(4 + 6) * 2"}}'
```

Register an agent proactively:

```bash
curl -X POST http://localhost:7000/agents/register \
  -H "X-Registration-Token: $CP_REGISTRATION_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"echo-proactive","url":"http://echo-agent:9001","metadata":{"tags":["demo"]}}'
```

## Test scenarios

### 1. Happy path
Use the echo agent to verify that discovery and invocation work correctly.

### 2. Retry and degradation
The flaky agent fails randomly and adds latency. Make several calls and observe the retries in the response and metrics.

```bash
curl -X POST http://localhost:7000/call \
  -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"agent_name":"flaky_agent","input_data":"ping"}'
```

### 3. Metrics and health
Check the service status and the exposed metrics:

```bash
curl http://localhost:7000/health
curl http://localhost:7000/metrics | grep -i "agent"
```

### 4. Full reset

```bash
docker compose down
```

## Demo agents

The stack includes these mock agents:
- echo_agent: returns the input unchanged.
- calculator_agent: evaluates simple arithmetic expressions.
- reverse_text_agent: reverses the provided text.
- translator_agent: performs a simple Portuguese-to-English word substitution.
- flaky_agent: fails occasionally and adds delay to exercise retries and adaptation.

## Useful configuration

The most common environment variables are:
- CP_API_KEY: API key for clients.
- CP_REGISTRATION_TOKEN: token required for agent registration.
- CP_SCAN_TARGETS: list of agent hosts and ports.
- CP_MAX_RETRIES: maximum number of retries per call.
- CP_FAILURE_THRESHOLD: number of consecutive failures before an agent is marked unavailable.
- CP_JSON_LOGS: enables structured JSON logging.
