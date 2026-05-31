# Deployment Guide
## Connecting to Claude Desktop on Windows

---

This guide walks you through connecting all 9 MCP servers to Claude Desktop
so you can talk to your supply chain system in plain English.

Estimated time: 15 minutes.

---

## Prerequisites

Before starting this guide, make sure you have:
- Completed `python scripts/setup_project.py` successfully
- Claude Desktop installed ([download here](https://claude.ai/download))
- Python 3.8 or higher installed

---

## Step 1 — Find Your Python Path

You need the exact path to your Python executable.
Open PowerShell and run:

```powershell
where python
```

The output will look something like:
```
C:\Users\YourName\AppData\Local\Programs\Python\Python310\python.exe
```

Copy this path — you will need it in Step 3.

---

## Step 2 — Find Your Project Path

Open PowerShell, navigate to your project folder, and run:

```powershell
cd "C:\path\to\supply-chain-control-tower"
pwd
```

Copy the full path shown. For example:
```
C:\Users\YourName\Documents\supply-chain-control-tower
```

---

## Step 3 — Open Claude Desktop Config

Claude Desktop stores its configuration in a JSON file.
Open it with Notepad or VS Code:

```
C:\Users\YourName\AppData\Roaming\Claude\claude_desktop_config.json
```

If the file does not exist, create it. If it already has content,
you will add to the existing `"mcpServers"` section.

---

## Step 4 — Add the MCP Servers

Replace `YOUR_PYTHON_PATH` and `YOUR_PROJECT_PATH` in the block below
with the values you found in Steps 1 and 2.

Then paste this entire block into your `claude_desktop_config.json`:

```json
{
  "mcpServers": {

    "shipping-delay-agent": {
      "command": "YOUR_PYTHON_PATH",
      "args": ["YOUR_PROJECT_PATH\\mcp_server\\shipping_mcp_server.py"],
      "env": { "PYTHONPATH": "YOUR_PROJECT_PATH\\src" }
    },

    "inventory-agent": {
      "command": "YOUR_PYTHON_PATH",
      "args": ["YOUR_PROJECT_PATH\\mcp_server\\inventory_mcp_server.py"],
      "env": { "PYTHONPATH": "YOUR_PROJECT_PATH\\src" }
    },

    "po-agent": {
      "command": "YOUR_PYTHON_PATH",
      "args": ["YOUR_PROJECT_PATH\\mcp_server\\po_mcp_server.py"],
      "env": { "PYTHONPATH": "YOUR_PROJECT_PATH\\src" }
    },

    "freight-agent": {
      "command": "YOUR_PYTHON_PATH",
      "args": ["YOUR_PROJECT_PATH\\mcp_server\\freight_mcp_server.py"],
      "env": { "PYTHONPATH": "YOUR_PROJECT_PATH\\src" }
    },

    "warehouse-agent": {
      "command": "YOUR_PYTHON_PATH",
      "args": ["YOUR_PROJECT_PATH\\mcp_server\\warehouse_mcp_server.py"],
      "env": { "PYTHONPATH": "YOUR_PROJECT_PATH\\src" }
    },

    "investigation-agent": {
      "command": "YOUR_PYTHON_PATH",
      "args": ["YOUR_PROJECT_PATH\\mcp_server\\investigation_mcp_server.py"],
      "env": { "PYTHONPATH": "YOUR_PROJECT_PATH\\src" }
    },

    "recommendation-agent": {
      "command": "YOUR_PYTHON_PATH",
      "args": ["YOUR_PROJECT_PATH\\mcp_server\\recommendation_mcp_server.py"],
      "env": { "PYTHONPATH": "YOUR_PROJECT_PATH\\src" }
    },

    "ci-agent": {
      "command": "YOUR_PYTHON_PATH",
      "args": ["YOUR_PROJECT_PATH\\mcp_server\\ci_mcp_server.py"],
      "env": { "PYTHONPATH": "YOUR_PROJECT_PATH\\src" }
    },

    "memory-agent": {
      "command": "YOUR_PYTHON_PATH",
      "args": ["YOUR_PROJECT_PATH\\mcp_server\\memory_mcp_server.py"],
      "env": { "PYTHONPATH": "YOUR_PROJECT_PATH\\src" }
    }

  }
}
```

### Example with real paths filled in:

```json
"shipping-delay-agent": {
  "command": "C:\\Users\\YourName\\AppData\\Local\\Programs\\Python\\Python310\\python.exe",
  "args": ["C:\\Users\\YourName\\Documents\\supply-chain-control-tower\\mcp_server\\shipping_mcp_server.py"],
  "env": { "PYTHONPATH": "C:\\Users\\YourName\\Documents\\supply-chain-control-tower\\src" }
}
```

**Important:** In JSON, backslashes must be doubled (`\\` not `\`).

---

## Step 5 — Create Your settings.yaml

The project uses `config/settings.yaml` to store your database path.
A template is provided at `config/settings.example.yaml`.

Copy it and fill in your path:

```powershell
copy config\settings.example.yaml config\settings.yaml
```

Then open `config/settings.yaml` in a text editor and update:

```yaml
database:
  path: "C:\\Users\\YourName\\Documents\\supply-chain-control-tower\\data\\supply_chain.db"
```

Use double backslashes on Windows.

---

## Step 6 — Restart Claude Desktop

Close Claude Desktop completely — check the system tray (bottom-right
of your taskbar) and right-click → Quit if it is still running.

Then reopen Claude Desktop.

---

## Step 7 — Verify Connection

In Claude Desktop, go to:
**Settings → Developer → MCP Servers**

You should see all 9 servers listed with a green dot next to each one:
- shipping-delay-agent ●
- inventory-agent ●
- po-agent ●
- freight-agent ●
- warehouse-agent ●
- investigation-agent ●
- recommendation-agent ●
- ci-agent ●
- memory-agent ●

If any show red or are missing, see the Troubleshooting section below.

---

## Step 8 — Test It

Open a new Claude Desktop conversation and type:

```
Read my project memory
```

Claude should respond with your project state — phases completed,
any active escalations, and recent decisions.

Then try:

```
Give me today's management summary
```

You should see a briefing with real order counts and delay information
from your database.

---

## Troubleshooting

**Server shows red in Claude Desktop**

The most common causes:
1. Python path is wrong — re-run `where python` to confirm
2. Project path has a typo — check every backslash is doubled in JSON
3. PYTHONPATH is missing the `src` folder — confirm the `env` block is present
4. The server file has a Python error — test it manually:
   ```
   python mcp_server\shipping_mcp_server.py
   ```
   If it crashes, you will see the error.

**"ModuleNotFoundError" when testing a server**

The `PYTHONPATH` in your config is not pointing to the `src` folder.
Check that the `env` block in your JSON looks exactly like this:
```json
"env": { "PYTHONPATH": "YOUR_PROJECT_PATH\\src" }
```

**Claude says it cannot find any tools**

Restart Claude Desktop fully (including system tray) after any config change.
Claude Desktop only loads MCP servers on startup.

**Server starts but returns errors**

Run `python scripts/setup_project.py` to verify your database is set up correctly.
Check that `config/settings.yaml` exists and has the correct database path.

---

## Running on Mac or Linux

The setup is the same but paths use forward slashes:

```json
"shipping-delay-agent": {
  "command": "/usr/bin/python3",
  "args": ["/home/yourname/supply-chain-control-tower/mcp_server/shipping_mcp_server.py"],
  "env": { "PYTHONPATH": "/home/yourname/supply-chain-control-tower/src" }
}
```

Find your Python path with: `which python3`
Find your project path with: `pwd`

---

## Optional — Start the Background Scheduler

The scheduler runs automatic briefings and scans without you asking.
Open a separate terminal and run:

```powershell
python scripts\scheduler.py
```

Or double-click `scripts\run_scheduler.bat` to run it in its own window.

To start it automatically with Windows, add a shortcut to `run_scheduler.bat`
in your Windows Startup folder:
1. Press `Win+R`, type `shell:startup`, press Enter
2. Copy a shortcut to `run_scheduler.bat` into that folder
