# iClone RTX MCP

Connect an MCP client to a running iClone or Character Creator scene. The host plugin runs inside the application; the MCP server runs separately with Python 3.12 and `uv`.

## 1. Install the plugin in iClone and Character Creator

The plugin files are in [`plugin/`](plugin/). Build iClone and Character Creator with their post-build deployment step enabled. It copies this folder into each application's `OpenPlugin/ICMCP` directory:

```text
iClone .../OpenPlugin/ICMCP/
Character Creator .../OpenPlugin/ICMCP/
```

If installing manually, copy the **contents** of this repository's `plugin/` folder into the matching application's `OpenPlugin/ICMCP/` folder. Keep the `.py` files together in `ICMCP`; do not put them in a nested `plugin` folder.

Start iClone or Character Creator and check **Plugins > iClone MCP > Enable Listener** or **Plugins > Character Creator MCP > Enable Listener**. The default listener addresses are `127.0.0.1:9880` for iClone and `127.0.0.1:9881` for Character Creator.

### Run two iClone instances

Each instance needs its own plugin copy and `ICMCP.ini` file, located beside the plugin's `main.py` in that instance's `OpenPlugin/ICMCP/` folder. Keep the first instance on the default port `9880`. In the second instance's `ICMCP.ini`, set:

```ini
[General]
listener_port=9882
```

Restart the second listener (or iClone) to apply the change. Add a second MCP server entry with a unique name and matching port, for example in Codex:

```toml
[mcp_servers.iclone2]
command = 'C:\Users\YOUR_NAME\.local\bin\uv.exe'
args = ["run", "iclone-mcp"]
cwd = 'D:\path\to\iclone-rtx-mcp\server'
startup_timeout_sec = 20
tool_timeout_sec = 200
enabled = true

[mcp_servers.iclone2.env]
ICLONE_MCP_PORT = "9882"
```

Use separate plugin folders/config files for the two instances; a shared `ICMCP.ini` would give both listeners the same port.

## 2. Install the MCP server with `uv`

Install `uv` and Python 3.12, then open a terminal in this repository's `server/` directory and run:

```powershell
uv sync --python C:\dev\Python312\python.exe
```

Replace the Python path with your Python 3.12 executable. This creates the server environment from `pyproject.toml` and `uv.lock`. The MCP client starts the server on demand; do not launch `uv run iclone-mcp` manually.

## 3. Connect an MCP client

Use the absolute path to this repository's `server` directory and your `uv.exe` path in the client configuration.

### Codex

Add to `%USERPROFILE%\.codex\config.toml` (change the example paths to your machine):

```toml
[mcp_servers.iclone]
command = 'C:\Users\YOUR_NAME\.local\bin\uv.exe'
args = ["run", "iclone-mcp"]
cwd = 'D:\path\to\iclone-rtx-mcp\server'
startup_timeout_sec = 20
tool_timeout_sec = 200
enabled = true

[mcp_servers.iclone.env]
ICLONE_MCP_PORT = "9880"

[mcp_servers.cc]
command = 'C:\Users\YOUR_NAME\.local\bin\uv.exe'
args = ["run", "iclone-mcp"]
cwd = 'D:\path\to\iclone-rtx-mcp\server'
startup_timeout_sec = 20
tool_timeout_sec = 200
enabled = true

[mcp_servers.cc.env]
ICLONE_MCP_PORT = "9881"
```

Restart Codex and verify the server is connected. Codex desktop, CLI, and IDE extension share this configuration.

### Cursor

Add the following to the project `.cursor/mcp.json` or `%USERPROFILE%\.cursor\mcp.json`. Replace the example paths:

```json
{
  "mcpServers": {
    "iclone": {
      "command": "C:\\Users\\YOUR_NAME\\.local\\bin\\uv.exe",
      "args": ["--directory", "D:\\path\\to\\iclone-rtx-mcp\\server", "run", "iclone-mcp"],
      "env": { "ICLONE_MCP_PORT": "9880" }
    },
    "cc": {
      "command": "C:\\Users\\YOUR_NAME\\.local\\bin\\uv.exe",
      "args": ["--directory", "D:\\path\\to\\iclone-rtx-mcp\\server", "run", "iclone-mcp"],
      "env": { "ICLONE_MCP_PORT": "9881" }
    }
  }
}
```

Restart Cursor and enable the servers under **Settings > Tools & MCP**.

## 4. Check the connection

After starting the application, allow up to 90 seconds for it to finish initializing. Call `get_iclone_status()` from the MCP client and wait for `"ready": true` before using scene tools. If you change the plugin listener port, set the same port in that server's `ICLONE_MCP_PORT` configuration.

For tool behavior and runtime details, see [`server/README.md`](server/README.md).
