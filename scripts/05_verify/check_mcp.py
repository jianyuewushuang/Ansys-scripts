"""Validate the configured Fluent MCP server: spawn it over stdio, initialize, list tools."""
import json, subprocess, sys, os

PY = r"C:\Users\jianyuewushuang\document\model\ansys\UAVdesign20261004\.venv\Scripts\python.exe"
env = dict(os.environ)
env["AWP_ROOT261"] = r"C:\Program Files\ANSYS Inc\ANSYS Student\v261"
env["FLUIDS_MCP_LOG_LEVEL"] = "ERROR"
env["PYTHONIOENCODING"] = "utf-8"

proc = subprocess.Popen([PY, "-m", "ansys.fluent.mcp"],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE, env=env, text=True, bufsize=1)


def send(obj):
    proc.stdin.write(json.dumps(obj) + "\n")
    proc.stdin.flush()


def read():
    line = proc.stdout.readline()
    return json.loads(line) if line.strip() else None


send({"jsonrpc": "2.0", "id": 1, "method": "initialize",
      "params": {"protocolVersion": "2024-11-05",
                 "capabilities": {},
                 "clientInfo": {"name": "workbuddy-check", "version": "1.0"}}})
init = read()
print("=== initialize ===")
print(json.dumps(init, indent=2, ensure_ascii=False)[:1200])

send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
tools = read()
names = [t["name"] for t in tools.get("result", {}).get("tools", [])]
print(f"\n=== tools/list : {len(names)} tools ===")
for n in names:
    print("  -", n)

proc.terminate()
try:
    proc.wait(timeout=10)
except Exception:
    proc.kill()
print("\n=== MCP SERVER OK ===")
