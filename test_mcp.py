#!/usr/bin/env python3
import json
import subprocess
import sys
import os
import threading
import time
import re
from datetime import datetime
from collections import deque


def _timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


# ANSI colors (with basic auto-disable support)
ANSI_SUPPORTED = os.name != "nt" or os.environ.get("WT_SESSION") or os.environ.get("ANSICON")
RESET = "\x1b[0m" if ANSI_SUPPORTED else ""
GREEN = "\x1b[32m" if ANSI_SUPPORTED else ""
RED = "\x1b[31m" if ANSI_SUPPORTED else ""
YELLOW = "\x1b[33m" if ANSI_SUPPORTED else ""

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def test_mcp_server():
    """Test the MCP server manually with verbose protocol logging and interactive prompts."""

    working_dir = os.path.dirname(os.path.abspath(__file__))
    # Load config: prefer CLI arg, then local mcp.json, then ~/.cursor/mcp.json
    def load_config_path() -> str | None:
        if len(sys.argv) >= 2 and sys.argv[1].strip():
            return sys.argv[1]
        local = os.path.join(working_dir, "mcp.json")
        if os.path.exists(local):
            return local
        home_cursor = os.path.join(os.path.expanduser("~"), ".cursor", "mcp.json")
        if os.path.exists(home_cursor):
            return home_cursor
        return None

    def load_server_from_config(cfg: dict) -> tuple[list[str], str | None]:
        """Return (command_with_args, cwd) from config.
        Supports either {command,args} or {mcpServers:{name:{command,args}}}.
        If args contains --directory <path>, use that path as cwd.
        """
        server = None
        if "command" in cfg:
            server = cfg
        elif isinstance(cfg.get("mcpServers"), dict) and cfg["mcpServers"]:
            name, server = next(iter(cfg["mcpServers"].items()))
        if not server:
            return ([], None)
        command = server.get("command")
        args = server.get("args", [])
        if not command:
            return ([], None)
        cmd = [command] + list(args)
        cwd_from_args = None
        for i, token in enumerate(args):
            if token == "--directory" and i + 1 < len(args):
                cwd_from_args = args[i + 1]
                break
        return (cmd, cwd_from_args)

    config_path = load_config_path()
    resolved_cmd: list[str] = []
    resolved_cwd: str | None = None
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            resolved_cmd, resolved_cwd = load_server_from_config(cfg)
            print(f"[{_timestamp()}] Loaded config from {config_path}")
        except Exception as e:
            print(f"[{_timestamp()}] Failed to read config {config_path}: {e}")
    if not resolved_cmd:
        resolved_cmd = ["uv", "run", "main.py"]
        resolved_cwd = working_dir
    if not resolved_cwd:
        resolved_cwd = working_dir
    session_stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = os.path.join(working_dir, f"session-{session_stamp}.txt")

    def log_line(line: str):
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(_strip_ansi(line) + "\n")
        except Exception:
            pass

    # Use configured command, fall back to python if missing
    command = resolved_cmd
    print(f"[{_timestamp()}] Command: {command}")
    print(f"[{_timestamp()}] CWD: {resolved_cwd}")

    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=resolved_cwd,
        )
    except FileNotFoundError:
        # Fallback if the configured command is not on PATH
        fallback_cmd = [sys.executable or "python", "main.py"]
        print(f"[{_timestamp()}] Command not found: {command[0]}; falling back to: {fallback_cmd}")
        process = subprocess.Popen(
            fallback_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=working_dir,
        )

    # Shared state for matching responses by id
    id_to_response = {}
    id_lock = threading.Lock()
    id_cv = threading.Condition(id_lock)

    stdout_buffer: deque[str] = deque(maxlen=500)
    stderr_buffer: deque[str] = deque(maxlen=500)

    def stdout_reader():
        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue
            msg = f"[{_timestamp()}] ← STDOUT: {line}"
            print(msg)
            log_line(msg)
            stdout_buffer.append(line)
            # Try to parse JSON and capture responses by id
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg_id = obj.get("id")
            if msg_id is not None and ("result" in obj or "error" in obj):
                with id_cv:
                    id_to_response[msg_id] = obj
                    id_cv.notify_all()

    def stderr_reader():
        for raw_line in process.stderr:
            line = raw_line.rstrip("\n")
            if line:
                msg = f"[{_timestamp()}] ! STDERR: {line}"
                print(msg)
                log_line(msg)
                stderr_buffer.append(line)

    t_out = threading.Thread(target=stdout_reader, daemon=True)
    t_err = threading.Thread(target=stderr_reader, daemon=True)
    t_out.start()
    t_err.start()

    def interactive_menu(last_request: dict | None, last_response: dict | None) -> bool:
        """Interactive post-step menu. Returns True to continue, False to exit."""
        if os.environ.get("MCP_TEST_NON_INTERACTIVE") == "1":
            # Auto-continue in non-interactive mode
            return True
        while True:
            try:
                prompt = (
                    "[Enter] continue | r: reprint req/resp | o: show recent stdout/stderr | l: show log path | n: exit > "
                )
                choice = input(prompt).strip().lower()
            except EOFError:
                return True

            log_line(f"[USER] choice: {choice or 'enter'}")

            if choice in ("", "c"):
                return True
            if choice in ("n", "q", "exit"):
                return False
            if choice == "l":
                msg = f"Log file: {log_path}"
                print(msg)
                log_line(msg)
                continue
            if choice == "r":
                if last_request is not None:
                    header = f"[{_timestamp()}] Reprint Request:"
                    print(header)
                    print(json.dumps(last_request, indent=2))
                    log_line(header)
                    log_line(json.dumps(last_request, indent=2))
                if last_response is not None:
                    header = f"[{_timestamp()}] Reprint Response:"
                    print(header)
                    print(json.dumps(last_response, indent=2))
                    log_line(header)
                    log_line(json.dumps(last_response, indent=2))
                continue
            if choice == "o":
                print(f"[{_timestamp()}] --- Recent STDOUT ---")
                for line in list(stdout_buffer)[-30:]:
                    print(line)
                print(f"[{_timestamp()}] --- Recent STDERR ---")
                for line in list(stderr_buffer)[-30:]:
                    print(line)
                log_line("[Shown recent stdout/stderr]")
                continue
            # Unknown option
            print("Unknown option. Please choose again.")

    def print_summary(title: str, attempted: str, response: dict | None):
        success = response is not None and "error" not in response
        status = f"{GREEN}SUCCESS{RESET}" if success else f"{RED}ERROR{RESET}"
        summary = f"[{_timestamp()}] {title}: {attempted} -> {status}"
        print(summary)
        log_line(_strip_ansi(summary))
        if not success:
            if response is None:
                msg = "No response received. The server may have exited or timed out."
            else:
                err = response.get("error", {})
                msg = f"Error: code={err.get('code')} message={err.get('message')} data={err.get('data')}"
            print(msg)
            log_line(msg)

    def show_req_resp(request_obj: dict | None, response_obj: dict | None):
        if request_obj is not None:
            header = f"[{_timestamp()}] Request (echo):"
            print(header)
            print(json.dumps(request_obj, indent=2))
            log_line(header)
            log_line(json.dumps(request_obj, indent=2))
        if response_obj is not None:
            header = f"[{_timestamp()}] Response (echo):"
            print(header)
            print(json.dumps(response_obj, indent=2))
            log_line(header)
            log_line(json.dumps(response_obj, indent=2))

    def send_notification(notification: dict):
        payload = json.dumps(notification)
        header = f"[{_timestamp()}] → NOTIFY:"
        print(header)
        print(json.dumps(notification, indent=2))
        log_line(header)
        log_line(json.dumps(notification, indent=2))
        assert process.stdin is not None
        process.stdin.write(payload + "\n")
        process.stdin.flush()

    def send_request(request: dict, timeout: float = 10.0):
        payload = json.dumps(request)
        header = f"[{_timestamp()}] → REQUEST:"
        print(header)
        print(json.dumps(request, indent=2))
        log_line(header)
        log_line(json.dumps(request, indent=2))
        msg_id = request.get("id")
        assert process.stdin is not None
        with id_lock:
            if msg_id in id_to_response:
                del id_to_response[msg_id]
        process.stdin.write(payload + "\n")
        process.stdin.flush()

        if msg_id is None:
            return None

        # Wait for matching response
        start = time.time()
        with id_cv:
            while True:
                if msg_id in id_to_response:
                    resp = id_to_response.pop(msg_id)
                    header = f"[{_timestamp()}] ⇐ RESPONSE (id={msg_id}):"
                    print(header)
                    print(json.dumps(resp, indent=2))
                    log_line(header)
                    log_line(json.dumps(resp, indent=2))
                    return resp
                remaining = timeout - (time.time() - start)
                if remaining <= 0:
                    print(f"[{_timestamp()}] ✖ Timeout waiting for response id={msg_id}")
                    return None
                id_cv.wait(timeout=remaining)

    try:
        print("=== Step 1: Initialize ===")
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {
                    "name": "test_mcp_client",
                    "version": "0.1.0"
                }
            }
        }
        init_response = send_request(init_request)
        print_summary("Initialize", "Send initialize with clientInfo", init_response)
        show_req_resp(init_request, init_response)
        if not interactive_menu(init_request, init_response):
            return

        print("\n=== Step 2: Initialized Notification ===")
        initialized_notification = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized"
        }
        send_notification(initialized_notification)
        print_summary("Initialized", "Send notifications/initialized", {"result": {"ok": True}})
        show_req_resp(initialized_notification, None)
        if not interactive_menu(initialized_notification, None):
            return

        print("\n=== Step 3: List Tools ===")
        tools_request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list"
        }
        tools_response = send_request(tools_request)
        print_summary("Tools/List", "Request available tools", tools_response)
        show_req_resp(tools_request, tools_response)
        if not interactive_menu(tools_request, tools_response):
            return
        if tools_response and "result" in tools_response:
            try:
                tools = tools_response["result"].get("tools", [])
                names = [t.get("name") for t in tools]
                print(f"[{_timestamp()}] Tools: {names}")
            except Exception:
                pass

        print("\n=== Step 4: Test Tool Call ===")
        query_text = os.environ.get("MCP_TEST_QUERY", "test")
        try:
            limit_val = int(os.environ.get("MCP_TEST_LIMIT", "2"))
        except ValueError:
            limit_val = 2
        tool_call_request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "search_images_tool",
                "arguments": {
                    "query": query_text,
                    "limit": limit_val
                }
            }
        }
        tool_response = send_request(tool_call_request, timeout=30.0)
        print_summary("Tools/Call", "Call search_images_tool", tool_response)
        show_req_resp(tool_call_request, tool_response)
        if tool_response and "result" in tool_response:
            result = tool_response.get("result", {})
            if isinstance(result, dict):
                content = result.get("content")
                if isinstance(content, list) and content:
                    first = content[0]
                    preview = first.get("text") if isinstance(first, dict) else str(first)
                    if preview and len(preview) > 200:
                        preview = preview[:200] + "…"
                    msg = f"[{_timestamp()}] Content preview: {preview}"
                    print(msg)
                    log_line(_strip_ansi(msg))
        if not interactive_menu(tool_call_request, tool_response):
            return

        # Brief grace period to drain any async output
        time.sleep(0.5)

    except KeyboardInterrupt:
        print("Interrupted by user")
    except Exception as e:
        print(f"Error during testing: {e}")
    finally:
        try:
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
        except Exception:
            pass


if __name__ == "__main__":
    test_mcp_server()
