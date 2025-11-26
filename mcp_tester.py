#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


def _timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


# ANSI colors (auto-disable in basic consoles)
ANSI_SUPPORTED = os.name != "nt" or os.environ.get("WT_SESSION") or os.environ.get("ANSICON")
RESET = "\x1b[0m" if ANSI_SUPPORTED else ""
GREEN = "\x1b[32m" if ANSI_SUPPORTED else ""
RED = "\x1b[31m" if ANSI_SUPPORTED else ""
YELLOW = "\x1b[33m" if ANSI_SUPPORTED else ""
CYAN = "\x1b[36m" if ANSI_SUPPORTED else ""

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


class MCPTester:
    def __init__(self, config_path: Optional[str] = None) -> None:
        self.working_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_path = config_path
        self.session_stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.log_path = os.path.join(self.working_dir, f"session-{self.session_stamp}.txt")

        self.process: Optional[subprocess.Popen[str]] = None
        self.id_to_response: Dict[int, Dict[str, Any]] = {}
        self.id_lock = threading.Lock()
        self.id_cv = threading.Condition(self.id_lock)
        self.stdout_buffer: deque[str] = deque(maxlen=1000)
        self.stderr_buffer: deque[str] = deque(maxlen=1000)
        self.next_id: int = 1
        self.last_status_colored: Optional[str] = None
        self.last_result_preview: Optional[str] = None
        self.last_status_time: float = 0.0
        # server selection support
        self.servers: List[Tuple[str, List[str], str]] = []  # (name, command_with_args, cwd)
        self.selected_index: int = -1
        self.selected_cmd: Optional[List[str]] = None
        self.selected_cwd: Optional[str] = None

    # ---------- logging ----------
    def log_line(self, line: str) -> None:
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(_strip_ansi(line) + "\n")
        except Exception:
            pass

    def print_and_log(self, line: str) -> None:
        print(line)
        self.log_line(line)

    def summary(self, title: str, attempted: str, response: Optional[Dict[str, Any]]) -> None:
        success = response is not None and "error" not in response
        status = f"{GREEN}SUCCESS{RESET}" if success else f"{RED}ERROR{RESET}"
        msg = f"[{_timestamp()}] {title}: {attempted} -> {status}"
        # Console: colored; Log: stripped
        print(msg)
        self.log_line(_strip_ansi(msg))
        self.last_status_colored = msg
        self.last_status_time = time.time()
        if not success:
            if response is None:
                errline = "No response received. The server may have exited or timed out."
            else:
                err = response.get("error", {})
                errline = f"Error: code={err.get('code')} message={err.get('message')} data={err.get('data')}"
            print(errline)
            self.log_line(errline)
            # Include detail in last preview, too
            self.last_result_preview = errline

    # ---------- config ----------
    def load_config_path(self) -> Optional[str]:
        if self.config_path:
            return self.config_path
        if len(sys.argv) >= 2 and sys.argv[1].strip():
            return sys.argv[1]
        local = os.path.join(self.working_dir, "mcp.json")
        if os.path.exists(local):
            return local
        home_cursor = os.path.join(os.path.expanduser("~"), ".cursor", "mcp.json")
        if os.path.exists(home_cursor):
            return home_cursor
        return None

    def load_servers(self) -> None:
        """Populate self.servers from config. Supports Cursor-style mcp.json with multiple servers."""
        cfg_path = self.load_config_path()
        self.servers = []
        if cfg_path and os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                self.print_and_log(f"[{_timestamp()}] Loaded config from {cfg_path}")
                if "mcpServers" in cfg and isinstance(cfg["mcpServers"], dict):
                    for name, server in cfg["mcpServers"].items():
                        command = server.get("command")
                        if not command:
                            continue
                        args = server.get("args", [])
                        cmd = [command] + list(args)
                        cwd_from_args = None
                        for i, token in enumerate(args):
                            if token == "--directory" and i + 1 < len(args):
                                cwd_from_args = args[i + 1]
                                break
                        self.servers.append((name, cmd, cwd_from_args or self.working_dir))
                elif "command" in cfg:
                    name = cfg.get("name") or "default"
                    args = cfg.get("args", [])
                    cmd = [cfg["command"]] + list(args)
                    cwd_from_args = None
                    for i, token in enumerate(args):
                        if token == "--directory" and i + 1 < len(args):
                            cwd_from_args = args[i + 1]
                            break
                    self.servers.append((name, cmd, cwd_from_args or self.working_dir))
            except Exception as e:
                self.print_and_log(f"[{_timestamp()}] Failed to read config: {e}")
        if not self.servers:
            # Fallback single server
            self.servers.append(("fallback", ["uv", "run", "main.py"], self.working_dir))

    def choose_server_menu(self) -> bool:
        """Let the user choose a server when multiple are configured. Returns True if selected."""
        if not self.servers:
            self.load_servers()
        if len(self.servers) == 1:
            self.selected_index = 0
            name, cmd, cwd = self.servers[0]
            self.selected_cmd, self.selected_cwd = cmd, cwd
            self.print_and_log(f"[{_timestamp()}] Using server: {name} -> {cmd} (cwd={cwd})")
            return True
        # Interactive selection
        print("Available MCP servers:")
        for idx, (name, cmd, cwd) in enumerate(self.servers):
            print(f"{idx}: {name} -> {cmd} (cwd={cwd})")
        sel = input("Select server index (or blank to cancel): ").strip()
        if not sel:
            return False
        try:
            index = int(sel)
        except Exception:
            print("Invalid index.")
            return False
        if index < 0 or index >= len(self.servers):
            print("Index out of range.")
            return False
        self.selected_index = index
        name, cmd, cwd = self.servers[index]
        self.selected_cmd, self.selected_cwd = cmd, cwd
        self.print_and_log(f"[{_timestamp()}] Selected server: {name} -> {cmd} (cwd={cwd})")
        return True

    # ---------- process & I/O ----------
    def start(self) -> None:
        if not self.selected_cmd or not self.selected_cwd:
            # Load and choose default if not already selected
            self.load_servers()
            if not self.choose_server_menu():
                raise RuntimeError("No server selected")
        command, cwd = self.selected_cmd, self.selected_cwd
        try:
            self.process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                cwd=cwd,
            )
        except FileNotFoundError:
            # If multiple servers are configured, don't silently fall back; let user pick another
            if len(self.servers) > 1:
                self.print_and_log(f"[{_timestamp()}] Command not found: {command[0]}. Please choose another server.")
                # Clear selection and prompt again
                self.selected_cmd = None
                self.selected_cwd = None
                if not self.choose_server_menu():
                    raise RuntimeError("No server selected")
                return self.start()
            # Single-server case: fall back to python main.py in working dir
            fallback_cmd = [sys.executable or "python", "main.py"]
            self.print_and_log(
                f"[{_timestamp()}] Command not found: {command[0]}; falling back to: {fallback_cmd}"
            )
            self.process = subprocess.Popen(
                fallback_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                cwd=self.working_dir,
            )

        threading.Thread(target=self._stdout_reader, daemon=True).start()
        threading.Thread(target=self._stderr_reader, daemon=True).start()

    def _stdout_reader(self) -> None:
        assert self.process and self.process.stdout
        for raw_line in self.process.stdout:
            line = raw_line.strip()
            if not line:
                continue
            msg = f"[{_timestamp()}] ← STDOUT: {line}"
            self.print_and_log(msg)
            self.stdout_buffer.append(line)
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg_id = obj.get("id")
            if msg_id is not None and ("result" in obj or "error" in obj):
                with self.id_cv:
                    self.id_to_response[msg_id] = obj
                    self.id_cv.notify_all()

    def _stderr_reader(self) -> None:
        assert self.process and self.process.stderr
        for raw_line in self.process.stderr:
            line = raw_line.rstrip("\n")
            if line:
                msg = f"[{_timestamp()}] ! STDERR: {line}"
                self.print_and_log(msg)
                self.stderr_buffer.append(line)

    def send_notification(self, notification: Dict[str, Any]) -> None:
        payload = json.dumps(notification)
        header = f"[{_timestamp()}] → NOTIFY:"
        self.print_and_log(header)
        self.print_and_log(json.dumps(notification, indent=2))
        assert self.process and self.process.stdin
        self.process.stdin.write(payload + "\n")
        self.process.stdin.flush()

    def send_request(self, request: Dict[str, Any], timeout: float = 10.0, interactive_extend: bool = False) -> Optional[Dict[str, Any]]:
        payload = json.dumps(request)
        header = f"[{_timestamp()}] → REQUEST:"
        self.print_and_log(header)
        self.print_and_log(json.dumps(request, indent=2))
        msg_id = request.get("id")
        assert self.process and self.process.stdin
        with self.id_lock:
            if msg_id in self.id_to_response:
                del self.id_to_response[msg_id]
        self.process.stdin.write(payload + "\n")
        self.process.stdin.flush()

        if msg_id is None:
            return None

        start = time.time()
        with self.id_cv:
            while True:
                if msg_id in self.id_to_response:
                    resp = self.id_to_response.pop(msg_id)
                    header = f"[{_timestamp()}] ⇐ RESPONSE (id={msg_id}):"
                    self.print_and_log(header)
                    self.print_and_log(json.dumps(resp, indent=2))
                    return resp
                remaining = timeout - (time.time() - start)
                if remaining <= 0:
                    if not interactive_extend:
                        self.print_and_log(f"[{_timestamp()}] ✖ Timeout waiting for response id={msg_id}")
                        return None
                    # Ask user to extend wait without resending
                    method = request.get("method", "?")
                    try:
                        choice = input(
                            f"Timed out waiting for {method} (id={msg_id}). Wait 30s more? [Y/n]: "
                        ).strip().lower()
                    except EOFError:
                        choice = "y"
                    if choice in ("", "y", "yes"):
                        self.print_and_log(f"[{_timestamp()}] Extending wait by 30s for id={msg_id}")
                        # Reset timer and continue waiting
                        start = time.time()
                        timeout = 30.0
                        continue
                    else:
                        self.print_and_log(f"[{_timestamp()}] User chose to stop waiting for id={msg_id}")
                        return None
                self.id_cv.wait(timeout=remaining)

    # ---------- protocol helpers ----------
    def next_request_id(self) -> int:
        rid = self.next_id
        self.next_id += 1
        return rid

    def initialize(self) -> Optional[Dict[str, Any]]:
        req = {
            "jsonrpc": "2.0",
            "id": self.next_request_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "mcp_tester", "version": "0.1.0"},
            },
        }
        resp = self.send_request(req, timeout=15.0, interactive_extend=True)
        self.summary("Initialize", "Send initialize with clientInfo", resp)
        return resp

    def send_initialized(self) -> None:
        note = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        self.send_notification(note)
        self.summary("Initialized", "Send notifications/initialized", {"result": {"ok": True}})

    # ---------- feature flows ----------
    def list_tools(self) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        req = {"jsonrpc": "2.0", "id": self.next_request_id(), "method": "tools/list"}
        resp = self.send_request(req)
        self.summary("Tools/List", "Request available tools", resp)
        tools: List[Dict[str, Any]] = []
        try:
            if resp and "result" in resp:
                tools = resp["result"].get("tools", []) or []
        except Exception:
            tools = []
        return resp, tools

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        req = {
            "jsonrpc": "2.0",
            "id": self.next_request_id(),
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
        resp = self.send_request(req, timeout=60.0)
        self.summary("Tools/Call", f"Call {name}", resp)
        # Capture a concise preview for menu recap
        preview = None
        if resp and "result" in resp and isinstance(resp["result"], dict):
            content = resp["result"].get("content")
            if isinstance(content, list) and content:
                first = content[0]
                preview = first.get("text") if isinstance(first, dict) else str(first)
        if preview:
            if len(preview) > 200:
                preview = preview[:200] + "…"
            self.last_result_preview = f"Result preview: {preview}"
        else:
            self.last_result_preview = None
        return resp

    def list_resources(self) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        req = {"jsonrpc": "2.0", "id": self.next_request_id(), "method": "resources/list"}
        resp = self.send_request(req)
        self.summary("Resources/List", "Request available resources", resp)
        items: List[Dict[str, Any]] = []
        try:
            if resp and "result" in resp:
                items = resp["result"].get("resources", []) or []
        except Exception:
            items = []
        return resp, items

    def read_resource(self, uri: str) -> Optional[Dict[str, Any]]:
        req = {
            "jsonrpc": "2.0",
            "id": self.next_request_id(),
            "method": "resources/read",
            "params": {"uri": uri},
        }
        resp = self.send_request(req, timeout=60.0)
        self.summary("Resources/Read", f"Read {uri}", resp)
        if resp and "result" in resp:
            self.last_result_preview = f"Read {uri}: ok"
        else:
            self.last_result_preview = None
        return resp

    def list_prompts(self) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
        req = {"jsonrpc": "2.0", "id": self.next_request_id(), "method": "prompts/list"}
        resp = self.send_request(req)
        self.summary("Prompts/List", "Request available prompts", resp)
        items: List[Dict[str, Any]] = []
        try:
            if resp and "result" in resp:
                items = resp["result"].get("prompts", []) or []
        except Exception:
            items = []
        return resp, items

    def get_prompt(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        params: Dict[str, Any] = {"name": name}
        if arguments:
            params["arguments"] = arguments
        req = {
            "jsonrpc": "2.0",
            "id": self.next_request_id(),
            "method": "prompts/get",
            "params": params,
        }
        resp = self.send_request(req, timeout=60.0)
        self.summary("Prompts/Get", f"Get {name}", resp)
        if resp and "result" in resp:
            self.last_result_preview = f"Prompt {name}: ok"
        else:
            self.last_result_preview = None
        return resp

    # ---------- interactive helpers ----------
    @staticmethod
    def _infer_default(prop_schema: Dict[str, Any]) -> Any:
        if "default" in prop_schema:
            return prop_schema["default"]
        t = prop_schema.get("type")
        if t == "integer":
            return 0
        if t == "number":
            return 0
        if t == "boolean":
            return False
        if t == "array":
            return []
        if t == "object":
            return {}
        return ""

    @staticmethod
    def _coerce_value(text: str, prop_schema: Dict[str, Any]) -> Any:
        # If user entered valid JSON, use it directly
        try:
            return json.loads(text)
        except Exception:
            pass
        t = prop_schema.get("type")
        if t == "integer":
            try:
                return int(text)
            except Exception:
                return 0
        if t == "number":
            try:
                return float(text)
            except Exception:
                return 0.0
        if t == "boolean":
            return text.strip().lower() in ("1", "true", "yes", "y")
        return text

    def prompt_for_args_from_schema(self, input_schema: Dict[str, Any]) -> Dict[str, Any]:
        properties: Dict[str, Any] = input_schema.get("properties", {}) or {}
        required: List[str] = input_schema.get("required", []) or []
        args: Dict[str, Any] = {}
        if not properties:
            self.print_and_log(f"[{_timestamp()}] No input schema; enter raw JSON for arguments (or blank for {{}}):")
            raw = input("> ").strip()
            if not raw:
                return {}
            try:
                return json.loads(raw)
            except Exception:
                self.print_and_log("Invalid JSON; using empty arguments {}")
                return {}
        for name, prop in properties.items():
            title = prop.get("title") or name
            t = prop.get("type")
            is_required = name in required
            default_val = self._infer_default(prop)
            hint = f"type={t}" if t else ""
            if not is_required:
                hint += f" default={json.dumps(default_val)}"
            prompt = f"Enter value for {title} ({hint}) {'[required]' if is_required else '[optional]'}: "
            text = input(prompt).strip()
            if not text:
                if is_required:
                    args[name] = default_val
                else:
                    # optional with blank -> skip, unless default explicitly present
                    if "default" in prop:
                        args[name] = default_val
                continue
            args[name] = self._coerce_value(text, prop)
        return args

    # ---------- main menu ----------
    def run_menu(self) -> None:
        while True:
            print()
            # Recap of last operation status + preview
            if self.last_status_colored:
                # Avoid immediate duplicate right after an operation
                if time.time() - self.last_status_time > 0.75:
                    print(self.last_status_colored)
                    self.log_line(_strip_ansi(self.last_status_colored))
            if self.last_result_preview:
                self.print_and_log(self.last_result_preview)
            self.print_and_log(f"{CYAN}=== MCP Tester Menu ==={RESET}")
            print("[t] List and call tools")
            print("[r] List and read resources")
            print("[p] List and get prompts")
            print("[o] Show recent stdout/stderr")
            print("[l] Show session log path")
            print("[s] Switch server")
            print("[q] Quit")
            choice = input("> ").strip().lower()
            self.log_line(f"[USER] menu choice: {choice or 'enter'}")

            if choice == "t":
                # Submenu loop to keep using tools without returning to main menu
                tools_cache: Optional[List[Dict[str, Any]]] = None
                while True:
                    if tools_cache is None:
                        _, tools_cache = self.list_tools()
                    tools = tools_cache or []
                    if not tools:
                        print("No tools available or tools/list failed.")
                        break
                    print(f"{CYAN}--- Tools ---{RESET}")
                    for idx, tool in enumerate(tools):
                        print(f"{idx}: {tool.get('name')} - {tool.get('description','')}")
                    print("Options: enter index to call, 'r' refresh, 'b' back to main")
                    sel = input("> ").strip().lower()
                    if not sel:
                        # empty -> back
                        break
                    if sel == "b":
                        break
                    if sel == "r":
                        tools_cache = None
                        continue
                    try:
                        index = int(sel)
                    except Exception:
                        print("Invalid selection.")
                        continue
                    if index < 0 or index >= len(tools):
                        print("Index out of range.")
                        continue
                    tool = tools[index]
                    name = tool.get("name")
                    input_schema = tool.get("inputSchema") or {}
                    args = self.prompt_for_args_from_schema(input_schema)
                    self.call_tool(name, args)
                    # After a tool call, allow repeated calls or selecting another tool
                    again = input("Call another tool? [Enter=yes / b=back]: ").strip().lower()
                    if again == "b":
                        break
                    # otherwise loop to tool list again

            elif choice == "r":
                _, resources = self.list_resources()
                if not resources:
                    print("No resources available or resources/list failed.")
                    continue
                for idx, res in enumerate(resources):
                    print(f"{idx}: {res.get('uri')} - {res.get('name','')}")
                sel = input("Select resource index to read (or blank to cancel): ").strip()
                if not sel:
                    continue
                try:
                    index = int(sel)
                except Exception:
                    print("Invalid index.")
                    continue
                if index < 0 or index >= len(resources):
                    print("Index out of range.")
                    continue
                uri = resources[index].get("uri")
                if not uri:
                    print("Selected resource has no uri.")
                    continue
                self.read_resource(uri)

            elif choice == "p":
                _, prompts = self.list_prompts()
                if not prompts:
                    print("No prompts available or prompts/list failed.")
                    continue
                for idx, pr in enumerate(prompts):
                    print(f"{idx}: {pr.get('name')} - {pr.get('description','')}")
                sel = input("Select prompt index to get (or blank to cancel): ").strip()
                if not sel:
                    continue
                try:
                    index = int(sel)
                except Exception:
                    print("Invalid index.")
                    continue
                if index < 0 or index >= len(prompts):
                    print("Index out of range.")
                    continue
                prompt = prompts[index]
                name = prompt.get("name")
                # Optional: attempt to read arguments schema if present
                args_schema = prompt.get("arguments", {}).get("properties") if isinstance(prompt.get("arguments"), dict) else None
                args: Optional[Dict[str, Any]] = None
                if args_schema:
                    args = self.prompt_for_args_from_schema({"properties": args_schema})
                else:
                    raw = input("Enter JSON for prompt arguments (or blank for none): ").strip()
                    if raw:
                        try:
                            args = json.loads(raw)
                        except Exception:
                            print("Invalid JSON; ignoring arguments.")
                            args = None
                self.get_prompt(name, args)

            elif choice == "o":
                print(f"[{_timestamp()}] --- Recent STDOUT ---")
                for line in list(self.stdout_buffer)[-50:]:
                    print(line)
                print(f"[{_timestamp()}] --- Recent STDERR ---")
                for line in list(self.stderr_buffer)[-50:]:
                    print(line)
                self.log_line("[Shown recent stdout/stderr]")

            elif choice == "l":
                print(f"Log file: {self.log_path}")

            elif choice == "s":
                # Switch server: stop process, choose, restart and re-init
                try:
                    if self.process and self.process.poll() is None:
                        self.process.terminate()
                        try:
                            self.process.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            self.process.kill()
                except Exception:
                    pass
                if not self.choose_server_menu():
                    continue
                self.start()
                init_resp = self.initialize()
                if not init_resp or "error" in init_resp:
                    self.print_and_log("Initialize failed on switched server.")
                    continue
                self.send_initialized()

            elif choice == "q":
                return

            else:
                print("Unknown option.")

    # ---------- top-level ----------
    def run(self) -> None:
        self.start()
        init_resp = self.initialize()
        if not init_resp or "error" in init_resp:
            self.print_and_log("Initialize failed; cannot continue.")
            return
        self.send_initialized()
        self.run_menu()
        time.sleep(0.2)
        try:
            if self.process and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
        except Exception:
            pass


if __name__ == "__main__":
    tester = MCPTester()
    tester.run()


