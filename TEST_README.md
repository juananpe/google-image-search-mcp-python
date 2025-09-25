### MCP Manual Test Harness (`test_mcp.py`)

This script is a manual test harness for your MCP server. It opens the server via your configured launcher, performs the MCP handshake and basic tool operations, and provides rich, interactive debugging output.

### What it does

- **Initialization flow**: Sends `initialize`, then `notifications/initialized`.
- **Tool discovery**: Calls `tools/list` and prints discovered tool names.
- **Tool exercise**: Calls `tools/call` on `search_images_tool` with a small test payload.
- **Verbose logging**:
  - Colored one-line summaries after each step: SUCCESS in green, ERROR in red, plus a short explanation.
  - Echoes the exact JSON request and the JSON response for each step.
  - Live streaming of server `stdout` and `stderr` with timestamps.
  - Interactive menu after each step to reprint request/response, view recent stdout/stderr, show log path, continue, or exit.
  - Writes everything to a timestamped session log: `session-YYYYMMDD-HHMMSS.txt` in the repo root.

### Prerequisites

- A working MCP server (this repo’s `main.py`).
- Either:
  - `uv` available on PATH, or
  - A local Python able to run `main.py`.
- Required env for the server (e.g., `SERP_API_KEY` in a `.env` file).

### Configuration (mcp.json)

The test harness reads its launcher configuration from `mcp.json` (in the repo root by default), or from a path you pass on the command line, or as a fallback `~/.cursor/mcp.json`.

Two supported config shapes:

1) Flat:
```json
{
  "command": "uv",
  "args": [
    "--directory",
    "C:\\Users\\YOURNAME\\Documents\\GitHub\\google-image-search-mcp-python",
    "run",
    "main.py"
  ]
}
```

2) Cursor-style:
```json
{
  "mcpServers": {
    "search-images": {
      "command": "uv",
      "args": [
        "--directory",
        "C:\\Users\\YOURNAME\\Documents\\GitHub\\google-image-search-mcp-python",
        "run",
        "main.py"
      ]
    }
  }
}
```

Notes:
- If `args` includes `--directory <path>`, that path is used as the working directory when spawning the server.
- If the configured command is not found, the script falls back to running `[python, main.py]` in the repo directory.

### Usage

- With repo-local config:
```powershell
python test_mcp.py
```

- With an explicit config file:
```powershell
python test_mcp.py C:\path\to\mcp.json
```

- On systems where `python` alias isn’t available:
```powershell
py test_mcp.py
```

### Interactive controls

After each step you’ll see a prompt:
- Enter: continue
- `r`: reprint the request/response JSON
- `o`: show recent stdout/stderr (last ~30 lines each)
- `l`: print the current session log path
- `n`: exit

### Typical flow and what to expect

1) Initialize
   - Sends `initialize` with `protocolVersion`, empty `capabilities`, and `clientInfo`.
   - Expect a JSON-RPC response with `result.serverInfo` and negotiated `capabilities`.

2) Initialized notification
   - Sends `notifications/initialized`.
   - One-line SUCCESS summary (no response expected/required).

3) List tools
   - Sends `tools/list`.
   - Prints tool names from the response.

4) Call a tool
   - Sends `tools/call` for `search_images_tool` with a small payload.
   - Prints a short content preview (truncated) when present.

### Troubleshooting

- Invalid request parameters / validation errors:
  - Ensure `clientInfo` is present in the `initialize` request (the script includes it by default).
  - Verify `protocolVersion` matches your `mcp-server` package version expectations.

- Command not found:
  - The script prints the resolved command and CWD. If `uv` is missing, it falls back to `python main.py`.

- No color output on Windows:
  - Colors are auto-disabled in non-ANSI terminals. Summaries still appear; the session log strips ANSI codes.

- Server exits early:
  - Check `.env` variables (e.g., `SERP_API_KEY`). Missing env will cause `main.py` to exit and the script will show no/timeout responses.

### Customizing

- Edit the test call payload in `test_mcp.py` (search for `tools/call`).
- Change the config file path or content to point to a different server binary/arguments.

### Safety

- The script is read-only with respect to your repo; it only writes timestamped session logs in the project folder.


