# Sentinel Agent

Lightweight log shipping agent for SentinelAI. The agent watches one or more local log files, converts each line into the SentinelAI ingestion schema, and sends the events to the backend `POST /logs` endpoint.

It is designed to be small and easy to run on Linux hosts, containers, or lab environments where you want to forward auth, syslog, nginx, or similar text logs into the SentinelAI pipeline.

## What It Does

- Tails multiple files using a polling loop
- Handles basic log rotation and file truncation
- Parses each line into the backend log format
- Infers `log_level`, `timestamp`, and `ip_address` when possible
- Buffers events in memory before flushing
- Retries transient delivery failures with exponential backoff
- Authenticates with the SentinelAI API using `X-API-Key`

## How It Works

The agent runs two background threads:

- `LogWatcher`: polls configured files, reads newly appended lines, and pushes parsed payloads into an in-memory queue
- `LogSender`: drains the queue and posts each payload to `POST /logs`

Shutdown is graceful on `SIGINT` and `SIGTERM`. The sender attempts to flush remaining queued logs before exit.

## Architecture

```text
log file(s) -> LogWatcher -> in-memory queue -> LogSender -> SentinelAI /logs
```

## Requirements

- Python 3.11+
- Network access to the SentinelAI backend
- A valid SentinelAI API key if backend auth is enabled

## Installation

### Local Python

```bash
cd sentinel-agent

python -m venv .venv
.venv\Scripts\activate

pip install -r requirements.txt
```

### Docker

```bash
cd sentinel-agent
docker build -t sentinel-agent .
```

## Configuration

The agent reads a YAML config file. By default it looks for `config.yaml` in the working directory, or you can pass a custom path with `--config`.

Example:

```yaml
sentinel:
  server: http://localhost:8000
  api_key: SECRET_KEY
  batch_size: 20
  flush_interval: 1
  request_timeout: 5
  max_backoff: 30

poll_interval: 0.25
queue_size: 10000

logs:
  - path: /var/log/auth.log
    source: linux-auth
  - path: /var/log/syslog
    source: linux-syslog
  - path: /var/log/nginx/access.log
    source: nginx
```

### Config Reference

#### `sentinel`

- `server`: Base URL for the SentinelAI backend. The agent posts to `<server>/logs`.
- `api_key`: Value sent in the `X-API-Key` header.
- `batch_size`: Number of queued log entries collected before an immediate flush. Must be between `1` and `20`.
- `flush_interval`: Maximum seconds to wait before flushing a partial batch. Must be greater than `0`.
- `request_timeout`: Per-request HTTP timeout in seconds. Must be greater than `0`.
- `max_backoff`: Maximum retry backoff in seconds for transient failures. Must be at least `1`.

#### Top-level

- `poll_interval`: Seconds between file polls. Must be greater than `0`.
- `queue_size`: In-memory queue capacity. Must be at least `100`.

#### `logs`

List of watched files:

- `path`: Absolute or relative path to the log file
- `source`: Source label sent to SentinelAI, such as `linux-auth` or `nginx`

## Running the Agent

### Local

```bash
cd sentinel-agent
python agent.py --config config.yaml
```

### Docker

The image expects the config file at `/app/config.yaml` by default.

```bash
docker run --rm \
  -v /var/log:/var/log:ro \
  sentinel-agent
```

If you want to use a custom config file:

```bash
docker run --rm \
  -v /absolute/path/config.yaml:/app/config.yaml:ro \
  -v /var/log:/var/log:ro \
  sentinel-agent
```

## Backend Contract

Each parsed line is sent as JSON shaped like this:

```json
{
  "source": "linux-auth",
  "log_level": "ERROR",
  "message": "Failed password for invalid user admin from 192.168.1.50 port 22 ssh2",
  "timestamp": "2026-03-11T12:34:56+00:00",
  "ip_address": "192.168.1.50"
}
```

The backend route is protected by `X-API-Key` when SentinelAI `API_KEY` is configured. If the backend `API_KEY` is empty, auth is effectively disabled in development.

## Parsing Rules

The parser applies simple heuristics to each line:

- `log_level`
  - `CRITICAL` if the line contains `CRITICAL`, `FATAL`, `PANIC`, `EMERG`, or `ALERT`
  - `ERROR` if it contains `ERROR`, `ERR`, `FAILED`, `FAILURE`, `DENIED`, or `EXCEPTION`
  - `WARNING` if it contains `WARNING`, `WARN`, `INVALID`, `REJECTED`, or `TIMEOUT`
  - otherwise `INFO`
- `timestamp`
  - uses an ISO-8601 timestamp if present
  - otherwise parses leading syslog timestamps like `Mar 11 12:34:56`
  - otherwise falls back to current UTC time
- `ip_address`
  - extracts the first IPv4 match from the line
  - falls back to `127.0.0.1` if no IPv4 address is found

## Delivery Semantics

- Logs are buffered in memory and flushed based on `batch_size` or `flush_interval`
- Requests are sent one log at a time to `POST /logs`
- HTTP `400`, `401`, `403`, `404`, and `422` responses are treated as permanent failures and dropped
- Other HTTP failures and network errors are retried with exponential backoff up to `max_backoff`
- If the process is stopping, unsent logs may remain in memory and be lost

## Rotation Behavior

The watcher keeps a file signature and current offset for each target. It reopens a file when:

- the inode/device signature changes
- the file size becomes smaller than the current read offset

This covers common rotation and truncation cases for plain text logs.

## Notes

- The watcher is polling-based, not inotify-based
- Only complete newline-terminated lines are forwarded
- Log parsing is heuristic, not source-specific
- The current sender does not persist its queue to disk
- The current Docker example in `config.yaml` uses `http://sentinelai:8000`; if you are running against this repository's default Compose stack, you will usually want the backend host reachable from the agent container, such as `http://backend:8000`

## Files

```text
sentinel-agent/
├── agent.py         # Entry point and thread lifecycle
├── config.py        # YAML config loading and validation
├── config.yaml      # Example config
├── parser.py        # Line parsing heuristics
├── sender.py        # Buffered HTTP delivery and retries
├── watcher.py       # Polling file tailer with rotation handling
├── requirements.txt
└── Dockerfile
```
