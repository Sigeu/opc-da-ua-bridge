# OPC DA ↔ OPC UA Bridge

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/Platform-Windows-lightgrey)
![Protocol](https://img.shields.io/badge/Protocols-OPC%20DA%20%7C%20OPC%20UA-blueviolet)
![License](https://img.shields.io/badge/License-AGPLv3-blue)

> Industrial protocol bridge that reads data from legacy **OPC DA** (Classic) servers and exposes them as **OPC UA** tags via a FreeOPCUA server, with bidirectional real-time synchronization.

---

## Fork Overview

This repository is a **fork with enhancements** based on the original open-source project by **Salma Alfaramawy**. The original work provided the core bidirectional bridge between OPC DA and OPC UA; this fork adds the following improvements:

- **Config file format** — changed from inline `config.py` (Python dict) to external `config.json` (JSON file), enabling runtime configuration without code modification
- **Configurable log levels** — `log_level` support in `config.json` (DEBUG / INFO / WARNING / ERROR)
- **Graceful shutdown** — proper cleanup of DA client and UA server on `Ctrl+C`
- **Fallback tag export** — exports all tags when none match the configured `group_name`, instead of failing silently
- **Health status detection** — optional tag quality/health column in CSV output
- **Standalone EXE packaging** — PyInstaller spec and build script for Windows deployment
- **COM DLL management** — convenience scripts for registering/unregistering `gbda_aut.dll`

---

## Architecture

```
OPC DA Server  →  OpenOPC Client  →  FreeOPCUA Server  →  OPC UA Client
   (COM/DCOM)       (bridge.py)       (opc.tcp://...)     (SCADA, HMI, ...)
```

---

## Features

- **Dynamic tag discovery** — automatically detects OPC DA tags matching the configured group and creates corresponding OPC UA variables
- **Bidirectional sync** — writes from OPC UA clients are forwarded back to the OPC DA server
- **Write conflict prevention** — prevents echo loops by tracking last read/write values
- **Timestamp preservation** — OPC DA source timestamps are carried over to OPC UA
- **Data-type mapping** — maps DA integer type IDs to appropriate UA data types (Int16/32/64, Float, Double, Boolean, String, DateTime, etc.)
- **CSV tag table export** — generates `tag_table.csv` with node IDs, tag names, data types, and health status at startup
- **Configurable logging** — supports DEBUG, INFO, WARNING, ERROR levels
- **Standalone EXE** — can be packaged via PyInstaller for deployment without Python

---

## Requirements

- **OS:** Windows (required by OPC DA COM/DCOM)
- **Python:** 3.10+

### Dependencies

| Package | Version | Purpose |
|---|---|---|
| `opcua` (FreeOPCUA) | 0.98.13 | OPC UA server implementation |
| `OpenOPC_DA` | 1.5.1 | OPC DA client via COM/DCOM |
| `pyinstaller` | 6.20.0 | Optional — for building standalone EXE |

---

## Configuration

All runtime settings are in **`config.json`** (see `config.example.json` for a template):

```json
{
    "da_server": "Kepware.KEPServerEX.V6",
    "group_name": "Channel2.Device1",
    "endpoint": "opc.tcp://0.0.0.0:4840/freeopcua/server/",
    "namespace_url": "https://example.com/opcua",
    "ua_object_name": "Micrologix 1400 Series B",
    "log_level": "info"
}
```

| Key | Description | Example |
|---|---|---|
| `da_server` | OPC DA server ProgID | `"Kepware.KEPServerEX.V6"` |
| `group_name` | Tag group prefix to filter | `"Channel2.Device1"` |
| `endpoint` | OPC UA server endpoint URL | `"opc.tcp://0.0.0.0:4840/"` |
| `namespace_url` | URI registered as the OPC UA namespace | `"https://example.com/opcua"` |
| `ua_object_name` | Name of the device object in the UA address space | `"Micrologix 1400 Series B"` |
| `log_level` | Logging verbosity | `"DEBUG"`, `"INFO"`, `"WARNING"`, `"ERROR"` |

The bridge searches for `config.json` in the same directory as the executable (when frozen) or in the project root (when running as a script).

---

## Usage

### 1. Register the COM DLL

OPC DA communication requires the `gbda_aut.dll` COM Automation wrapper to be registered:

```batch
regsvr32 gbda_aut.dll
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure

Copy `config.example.json` to `config.json` and adjust for your environment.

### 4. Run

```bash
python bridge/bridge.py
```

The bridge creates a CSV tag table (`tag_table.csv`) listing all discovered tags and their OPC UA node IDs, then starts the update loop. Logs are printed to the console.

### Building a Standalone EXE

```batch
build.bat
```

Or manually:

```batch
pyinstaller --onefile --clean --noconfirm --hidden-import=win32timezone --name OpcDaUaBridge bridge/bridge.py
```

Output: `dist/OpcDaUaBridge.exe`

Deploy the EXE together with `config.json` and register `gbda_aut.dll` on the target machine.

---

## Output: tag_table.csv

On startup, the bridge writes a CSV file with all discovered tags:

| Column | Description |
|---|---|
| NodeId | OPC UA Node ID (e.g. `ns=2;i=3`) |
| TagName | Full DA tag path |
| DataType | Mapped data type (e.g. `FLOAT`, `BOOL`, `INT32`) |
| Health | `good` / `bad` (if quality info is available) |

---

## Project Structure

```
├── bridge/
│   └── bridge.py            # Main application source
├── build.bat                # PyInstaller build script
├── uninstall_dll.bat        # COM DLL unregistration
├── install_dll.bat          # COM DLL registration
├── gbda_aut.dll             # OPC DA Automation wrapper DLL
├── config.json              # Runtime configuration
├── config.example.json      # Example configuration template
├── requirements.txt         # Python dependencies
├── OpcDaUaBridge.spec       # PyInstaller spec file
├── LICENSE                  # GNU AGPL v3
└── README.md
```

---

## Limitations

- **Windows-only** — OPC DA relies on COM/DCOM
- **No automatic reconnection** — restart required if a server connection drops
- **No security** — OPC UA server runs without authentication or encryption
- **No high availability** — single-instance, no failover
- **No performance tuning** — not stress-tested for thousands of tags
- **Minimal error handling** — no retry backoff or exception classification

---

## License

**GNU Affero General Public License v3.0 (AGPL-3.0)**

---

## Original Author

**Salma Alfaramawy** — original creator of the OPC DA ↔ OPC UA Bridge

- LinkedIn: https://www.linkedin.com/in/salma-alf/
- Email: salmakh.1627@gmail.com
