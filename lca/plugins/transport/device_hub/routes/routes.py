"""HTTP /api/device/* + WS /api/device/ws — LobeHub GatewayClient protocol."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast

import structlog
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.websockets import WebSocket, WebSocketDisconnect

from lca.infrastructure.tools.lca_computer.manifest import LOCAL_SYSTEM_ID as _COMPUTER_IDENTIFIER
from lca.plugins.transport.device_hub.auth.auth import AuthenticatedUser, AuthError, verify_token
from lca.plugins.transport.device_hub.hub.hub import DeviceHub, encode_arguments
from lca.plugins.transport.device_hub.models.models import DeviceConnection
from lca.plugins.transport.device_hub.pairing.pairing import DevicePairingService
from lca.plugins.transport.device_hub.registry.registry import DeviceRegistry
from lca.plugins.transport.device_hub.settings.settings import DeviceHubSettings
from lca.plugins.transport.webserver.handlers.cors.cors import cors_headers

_log = structlog.get_logger(__name__)


def _registry(request: Request) -> DeviceRegistry:
    return cast("DeviceRegistry", request.app.state.devices)


def _hub(request: Request) -> DeviceHub:
    return cast("DeviceHub", request.app.state.device_hub)


def _settings(request: Request) -> DeviceHubSettings:
    return cast("DeviceHubSettings", request.app.state.device_settings)


def _pairing(request: Request) -> DevicePairingService:
    service = getattr(request.app.state, "device_pairing", None)
    if service is None:
        service = DevicePairingService()
        request.app.state.device_pairing = service
    return cast("DevicePairingService", service)


def _auth_from_body(request: Request, body: dict[str, Any]) -> AuthenticatedUser:
    token = str(body.get("token") or request.headers.get("authorization") or "")
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    token_type = str(body.get("tokenType") or body.get("token_type") or "serviceToken")
    if not token:
        token = _settings(request).service_token
        token_type = "serviceToken"  # noqa: S105
    pairing_service = getattr(request.app.state, "device_pairing", None)
    return verify_token(token, token_type, _settings(request), pairing_service=pairing_service)


async def _read_json(request: Request) -> dict[str, Any]:
    if request.method == "OPTIONS":
        return {}
    try:
        body = await request.json()
    except Exception:
        return {}
    return body if isinstance(body, dict) else {}


async def device_status(request: Request) -> JSONResponse:
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    body = await _read_json(request)
    try:
        user = _auth_from_body(request, body)
    except AuthError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401, headers=cors_headers())
    online = _registry(request).list_online(user.user_id, user.workspace_id)
    return JSONResponse(
        {"online": bool(online), "count": len(online)},
        headers=cors_headers(),
    )


async def list_devices(request: Request) -> JSONResponse:
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    body = await _read_json(request)
    try:
        user = _auth_from_body(request, body)
    except AuthError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401, headers=cors_headers())
    devices = _registry(request).list_online(user.user_id, user.workspace_id)
    return JSONResponse(
        {"devices": [d.as_dict() for d in devices]},
        headers=cors_headers(),
    )


async def tool_call(request: Request) -> JSONResponse:
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    body = await _read_json(request)
    try:
        _auth_from_body(request, body)
    except AuthError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401, headers=cors_headers())
    device_id = str(body.get("deviceId") or body.get("device_id") or "")
    if not device_id:
        return JSONResponse({"error": "deviceId required"}, status_code=400, headers=cors_headers())
    api_name = str(body.get("apiName") or body.get("api_name") or "")
    identifier = str(body.get("identifier") or _COMPUTER_IDENTIFIER)
    arguments = body.get("arguments") or body.get("params") or {}
    timeout_s = float(body.get("timeout_s") or 60)
    try:
        result = await _hub(request).call_tool(
            device_id,
            {
                "identifier": identifier,
                "apiName": api_name,
                "arguments": encode_arguments(arguments),
                "type": "tool",
            },
            timeout_s=timeout_s,
        )
    except (TimeoutError, ConnectionError) as exc:
        return JSONResponse(
            {"success": False, "error": str(exc)},
            status_code=504,
            headers=cors_headers(),
        )
    return JSONResponse(result, headers=cors_headers())


async def system_info(request: Request) -> JSONResponse:
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    body = await _read_json(request)
    try:
        _auth_from_body(request, body)
    except AuthError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401, headers=cors_headers())
    device_id = str(body.get("deviceId") or body.get("device_id") or "")
    try:
        result = await _hub(request).call_rpc(device_id, "systemInfo", {}, timeout_s=15)
    except (TimeoutError, ConnectionError) as exc:
        return JSONResponse(
            {"success": False, "error": str(exc)}, status_code=504, headers=cors_headers()
        )
    return JSONResponse(result, headers=cors_headers())


async def rpc(request: Request) -> JSONResponse:
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    body = await _read_json(request)
    try:
        _auth_from_body(request, body)
    except AuthError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401, headers=cors_headers())
    device_id = str(body.get("deviceId") or body.get("device_id") or "")
    method = str(body.get("method") or "")
    params = body.get("params")
    try:
        result = await _hub(request).call_rpc(device_id, method, params, timeout_s=30)
    except (TimeoutError, ConnectionError) as exc:
        return JSONResponse(
            {"success": False, "error": str(exc)}, status_code=504, headers=cors_headers()
        )
    return JSONResponse(result, headers=cors_headers())


async def agent_run(request: Request) -> JSONResponse:
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    body = await _read_json(request)
    try:
        _auth_from_body(request, body)
    except AuthError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401, headers=cors_headers())
    _log.info("agent_run_requested", body_keys=list(body.keys()))
    return JSONResponse(
        {"success": True, "operationId": "", "status": "accepted"},
        headers=cors_headers(),
    )


async def upload_files(request: Request) -> JSONResponse:
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    body = await _read_json(request)
    try:
        _auth_from_body(request, body)
    except AuthError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401, headers=cors_headers())
    device_id = str(body.get("deviceId") or body.get("device_id") or "")
    files = body.get("files") or {}
    base_dir = str(body.get("baseDir") or body.get("base_dir") or "/home/sandbox-user")
    try:
        result = await _hub(request).call_tool(
            device_id,
            {
                "identifier": _COMPUTER_IDENTIFIER,
                "apiName": "writeFiles",
                "arguments": json.dumps({"files": files, "base_dir": base_dir}),
                "type": "tool",
            },
            timeout_s=60,
        )
    except (TimeoutError, ConnectionError) as exc:
        return JSONResponse(
            {"success": False, "error": str(exc)}, status_code=504, headers=cors_headers()
        )
    return JSONResponse(result, headers=cors_headers())


async def pair_code(request: Request) -> JSONResponse:
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    body = await _read_json(request)
    device_id = str(body.get("deviceId") or body.get("device_id") or "")
    label = str(body.get("label") or "Companion")
    platform = str(body.get("platform") or "")
    user_code = str(body.get("userCode") or body.get("user_code") or "").strip() or None
    if not device_id:
        return JSONResponse(
            {"error": "deviceId is required"}, status_code=400, headers=cors_headers()
        )

    pairing = _pairing(request)
    req = pairing.request_code(
        device_id=device_id, label=label, platform=platform, user_code=user_code
    )
    resp_data: dict[str, Any] = {
        "deviceCode": req.device_code,
        "userCode": req.user_code,
        "verificationUri": "/pair",
        "expiresIn": req.expires_in,
        "interval": 2,
    }
    if req.machine_token:
        resp_data["machineToken"] = req.machine_token
        resp_data["status"] = req.status
        resp_data["userId"] = req.user_id
        resp_data["workspaceId"] = req.workspace_id
    return JSONResponse(resp_data, headers=cors_headers())


async def pair_verify(request: Request) -> JSONResponse:
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    body = await _read_json(request)
    user_code = str(body.get("userCode") or body.get("user_code") or "").strip()
    if not user_code:
        return JSONResponse(
            {"error": "userCode is required"}, status_code=400, headers=cors_headers()
        )

    user_id = str(body.get("userId") or body.get("user_id") or "")
    workspace_id = str(body.get("workspaceId") or body.get("workspace_id") or "")
    if not user_id:
        try:
            user = _auth_from_body(request, body)
            user_id = user.user_id
            workspace_id = user.workspace_id or workspace_id
        except AuthError:
            user_id = "default-user"

    pairing = _pairing(request)
    result = pairing.verify_code(
        user_code=user_code,
        user_id=user_id,
        workspace_id=workspace_id or "default-workspace",
    )
    if not result.success:
        return JSONResponse(
            {"success": False, "error": result.error},
            status_code=400,
            headers=cors_headers(),
        )
    return JSONResponse(
        {
            "success": True,
            "deviceId": result.device_id,
            "label": result.label,
        },
        headers=cors_headers(),
    )


async def pair_poll(request: Request) -> JSONResponse:
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    body = await _read_json(request)
    device_code = str(body.get("deviceCode") or body.get("device_code") or "").strip()
    if not device_code:
        return JSONResponse(
            {"error": "deviceCode is required"}, status_code=400, headers=cors_headers()
        )

    pairing = _pairing(request)
    result = pairing.poll_token(device_code=device_code)
    return JSONResponse(
        {
            "status": result.status,
            "machineToken": result.machine_token,
            "tokenType": "machineToken" if result.machine_token else None,
            "userId": result.user_id,
            "workspaceId": result.workspace_id,
            "error": result.error,
        },
        headers=cors_headers(),
    )


async def pair_preauth(request: Request) -> JSONResponse:
    if request.method == "OPTIONS":
        return JSONResponse({}, headers=cors_headers())
    body = await _read_json(request)
    user_id = str(body.get("userId") or body.get("user_id") or "")
    workspace_id = str(body.get("workspaceId") or body.get("workspace_id") or "")
    if not user_id:
        try:
            user = _auth_from_body(request, body)
            user_id = user.user_id
            workspace_id = user.workspace_id or workspace_id
        except AuthError:
            user_id = "default-user"
            workspace_id = workspace_id or "default-workspace"

    pairing = _pairing(request)
    req = pairing.preauth_code(user_id=user_id, workspace_id=workspace_id or "default-workspace")

    host = request.headers.get("host") or "127.0.0.1:8765"
    scheme = request.url.scheme or "http"
    base_url = f"{scheme}://{host}"

    ps_cmd = f"irm {base_url}/api/device/install.ps1?code={req.user_code} | iex"
    sh_cmd = f"curl -fsSL {base_url}/api/device/install.sh?code={req.user_code} | bash"

    return JSONResponse(
        {
            "success": True,
            "userCode": req.user_code,
            "deviceCode": req.device_code,
            "expiresIn": req.expires_in,
            "installCommands": {
                "windows": ps_cmd,
                "bash": sh_cmd,
            },
        },
        headers=cors_headers(),
    )


async def install_ps1(request: Request) -> Response:
    if request.method == "OPTIONS":
        return Response("", headers=cors_headers())
    code = str(request.query_params.get("code") or "").strip()
    host = request.headers.get("host") or "127.0.0.1:8765"
    scheme = request.url.scheme or "http"
    server_url = f"{scheme}://{host}"

    script = f'''# LCA Companion Installer for Windows (PowerShell)
$ErrorActionPreference = "Stop"
$Server = "{server_url}"
$PreauthCode = "{code}"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " LCA Local Companion Installer (PowerShell) " -ForegroundColor Cyan
Write-Host " Server: $Server" -ForegroundColor Gray
Write-Host "==========================================" -ForegroundColor Cyan

# 0. UTF-8 so logs do not crash under gbk consoles
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
try {{ [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new() }} catch {{}}

# Function to test whether a candidate python executable actually works and is >= 3.10
function Test-PythonCandidate($exePath) {{
    if (-not $exePath) {{ return $false }}
    if (-not (Test-Path $exePath -PathType Leaf)) {{ return $false }}
    if ($exePath -match "[.]cmd$") {{ return $false }}
    try {{
        $out = & $exePath -c "import sys; print('LCA_PY_' + str(sys.version_info[0]) + '_' + str(sys.version_info[1]))" 2>$null
        if ($LASTEXITCODE -eq 0 -and $out -match "LCA_PY_(\\d+)_(\\d+)") {{
            $major = [int]$matches[1]
            $minor = [int]$matches[2]
            if ($major -eq 3 -and $minor -ge 10) {{
                return $true
            }}
        }}
    }} catch {{}}
    return $false
}}

# Function to refresh PATH from Windows Registry (Machine + User)
function Update-SessionPath {{
    try {{
        $machinePath = [System.Environment]::GetEnvironmentVariable("Path", [System.EnvironmentVariableTarget]::Machine)
        $userPath = [System.Environment]::GetEnvironmentVariable("Path", [System.EnvironmentVariableTarget]::User)
        $combined = @($userPath, $machinePath, $env:Path) -join ";"
        $unique = ($combined -split ";" | Where-Object {{ $_ -and (Test-Path $_) }} | Select-Object -Unique) -join ";"
        $env:Path = $unique
    }} catch {{}}
}}

# 1. Discover existing Python on system
function Find-Python {{
    Update-SessionPath

    $candidates = [System.Collections.Generic.List[string]]::new()

    # 1.1 Check PATH commands
    foreach ($name in @("python.exe", "py.exe", "python3.exe", "python", "py", "python3")) {{
        $cmd = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($cmd -and $cmd.Source -and ($cmd.Source -notmatch "[.]cmd$")) {{
            $candidates.Add($cmd.Source)
        }}
    }}

    # 1.2 Check Windows Registry (Current User & Local Machine)
    $regRoots = @("HKCU:\\Software\\Python\\PythonCore", "HKLM:\\Software\\Python\\PythonCore")
    foreach ($root in $regRoots) {{
        if (Test-Path $root) {{
            $subkeys = Get-ChildItem $root -ErrorAction SilentlyContinue | Sort-Object Name -Descending
            foreach ($key in $subkeys) {{
                $regKey = Join-Path $key.PSPath "InstallPath"
                $installPath = (Get-ItemProperty $regKey -ErrorAction SilentlyContinue)."(default)"
                if ($installPath) {{
                    $candidates.Add((Join-Path $installPath "python.exe"))
                }}
            }}
        }}
    }}

    # 1.3 Check standard Windows directory locations
    $stdPaths = @(
        (Join-Path $env:LOCALAPPDATA "Programs\\Python\\Python313\\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\\Python\\Python312\\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\\Python\\Python311\\python.exe"),
        (Join-Path $env:LOCALAPPDATA "Programs\\Python\\Python310\\python.exe"),
        (Join-Path $env:ProgramFiles "Python313\\python.exe"),
        (Join-Path $env:ProgramFiles "Python312\\python.exe"),
        (Join-Path $env:ProgramFiles "Python311\\python.exe"),
        (Join-Path $env:ProgramFiles "Python310\\python.exe"),
        (Join-Path ${{env:ProgramFiles(x86)}} "Python313\\python.exe"),
        (Join-Path ${{env:ProgramFiles(x86)}} "Python312\\python.exe"),
        (Join-Path ${{env:ProgramFiles(x86)}} "Python311\\python.exe"),
        (Join-Path ${{env:ProgramFiles(x86)}} "Python310\\python.exe"),
        "C:\\Python313\\python.exe",
        "C:\\Python312\\python.exe",
        "C:\\Python311\\python.exe",
        "C:\\Python310\\python.exe",
        (Join-Path $env:USERPROFILE "scoop\apps\\python\\current\\python.exe"),
        (Join-Path $env:USERPROFILE "scoop\\shims\\python.exe"),
        (Join-Path $env:USERPROFILE ".pyenv\\pyenv-win\\shims\\python.exe"),
        (Join-Path $env:USERPROFILE "miniconda3\\python.exe"),
        (Join-Path $env:USERPROFILE "anaconda3\\python.exe"),
        (Join-Path $env:ProgramData "miniconda3\\python.exe"),
        (Join-Path $env:ProgramData "anaconda3\\python.exe")
    )
    foreach ($p in $stdPaths) {{
        if ($p) {{ $candidates.Add($p) }}
    }}

    # 1.4 Scan UV and Programs directories recursively if present
    $scanDirs = @(
        (Join-Path $env:LOCALAPPDATA "Programs\\Python"),
        (Join-Path $env:LOCALAPPDATA "uv\\python")
    )
    foreach ($sdir in $scanDirs) {{
        if (Test-Path $sdir) {{
            Get-ChildItem -Path $sdir -Filter "python.exe" -Recurse -ErrorAction SilentlyContinue | ForEach-Object {{
                $candidates.Add($_.FullName)
            }}
        }}
    }}

    # Test each candidate
    foreach ($cand in ($candidates | Select-Object -Unique)) {{
        if ($cand -and (Test-PythonCandidate $cand)) {{
            return $cand
        }}
    }}

    return $null
}}

$pythonCmd = Find-Python

# 2. If Python not found, attempt automated installation
if (-not $pythonCmd) {{
    Write-Host "[!] Python 3.10+ not found in PATH or standard directories." -ForegroundColor Yellow
    Write-Host "[*] Attempting automated Python 3 installation..." -ForegroundColor Cyan

    $installed = $false

    # Option A: Windows Package Manager (winget) specifying --source winget
    $hasWinget = Get-Command winget -ErrorAction SilentlyContinue
    if ($hasWinget) {{
        Write-Host "[*] Installing Python 3.11 via winget (source: winget)..." -ForegroundColor Gray
        try {{
            & winget install --id Python.Python.3.11 --source winget --exact --silent --accept-package-agreements --accept-source-agreements
            if ($LASTEXITCODE -ne 0) {{
                & winget install Python.Python.3.11 --source winget --silent --accept-package-agreements --accept-source-agreements
            }}
            Update-SessionPath
            $pythonCmd = Find-Python
            if ($pythonCmd) {{
                $installed = $true
            }}
        }} catch {{
            Write-Host "[!] Winget install error: $_" -ForegroundColor DarkGray
        }}
    }}

    # Option B: Direct download of official python.org installer
    if (-not $installed) {{
        Write-Host "[*] Downloading official Python 3.11 installer from python.org..." -ForegroundColor Gray
        try {{
            $arch = if ([System.Environment]::Is64BitOperatingSystem) {{ "amd64" }} else {{ "win32" }}
            $installerUrl = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-$arch.exe"
            $tempInstaller = Join-Path ([System.IO.Path]::GetTempPath()) "python-3.11.9-installer.exe"
            [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 -bor [Net.SecurityProtocolType]::Tls13
            Invoke-WebRequest -Uri $installerUrl -OutFile $tempInstaller -UseBasicParsing
            if (Test-Path $tempInstaller) {{
                $targetDir = Join-Path $env:LOCALAPPDATA "Programs\\Python\\Python311"
                $logPath = Join-Path ([System.IO.Path]::GetTempPath()) "python-installer.log"
                Write-Host "[*] Running silent Python installer to $targetDir..." -ForegroundColor Gray
                $argStr = "/quiet InstallAllUsers=0 TargetDir=`"$targetDir`" PrependPath=1 Include_pip=1 Shortcuts=0 /log `"$logPath`""
                $installProc = Start-Process -FilePath $tempInstaller -ArgumentList $argStr -Wait -PassThru
                Remove-Item $tempInstaller -Force -ErrorAction SilentlyContinue
                Update-SessionPath
                $pythonCmd = Find-Python
                if (-not $pythonCmd) {{
                    $directExe = Join-Path $targetDir "python.exe"
                    if (Test-PythonCandidate $directExe) {{
                        $pythonCmd = $directExe
                    }}
                }}
                if ($pythonCmd) {{
                    $installed = $true
                }}
            }}
        }} catch {{
            Write-Host "[!] Direct installer error: $_" -ForegroundColor DarkGray
        }}
    }}

    if (-not $pythonCmd) {{
        Write-Host "[!] Python 3.10+ installation could not be completed automatically." -ForegroundColor Red
        Write-Host "Please install Python 3 manually using one of the following methods:" -ForegroundColor Yellow
        Write-Host "  1. Run: winget install Python.Python.3.11 --source winget" -ForegroundColor Gray
        Write-Host "  2. Download from: https://www.python.org/downloads/" -ForegroundColor Gray
        Write-Host "     (Make sure to check 'Add python.exe to PATH' during installation)" -ForegroundColor Gray
        exit 1
    }}
}}

Write-Host "[OK] Found Python: $pythonCmd" -ForegroundColor Green

# 3. Ensure pip & dependencies
Write-Host "[*] Checking dependencies (httpx, websockets)..." -ForegroundColor Gray
try {{
    & $pythonCmd -m pip --version 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {{
        & $pythonCmd -m ensurepip --default-pip 2>$null | Out-Null
    }}
}} catch {{}}

$prevEAP = $ErrorActionPreference; $ErrorActionPreference = "SilentlyContinue"
$pipRes = & $pythonCmd -m pip install -q --no-warn-script-location httpx websockets 2>&1
$ErrorActionPreference = $prevEAP
if ($LASTEXITCODE -ne 0) {{
    $prevEAP = $ErrorActionPreference; $ErrorActionPreference = "SilentlyContinue"
    & $pythonCmd -m pip install -q --user --no-warn-script-location httpx websockets 2>&1
    $ErrorActionPreference = $prevEAP
}}

# 4. Setup directory
$lcaDir = Join-Path $HOME ".lca"
$binDir = Join-Path $lcaDir "bin"
if (-not (Test-Path $binDir)) {{
    New-Item -ItemType Directory -Path $binDir -Force | Out-Null
}}

# 5. Download Companion
$companionScript = Join-Path $binDir "lca-companion.py"
Write-Host "[*] Downloading companion client..." -ForegroundColor Gray
Invoke-RestMethod -Uri "$Server/api/device/download/companion.py" -OutFile $companionScript -ErrorAction SilentlyContinue
if (-not (Test-Path $companionScript)) {{
    $repoUrl = "$Server/scripts/lca-companion"
    Invoke-RestMethod -Uri $repoUrl -OutFile $companionScript -ErrorAction SilentlyContinue
}}

# 6. Connect & Run
Write-Host "[*] Connecting and pairing with gateway..." -ForegroundColor Gray
$runArgs = @("$companionScript", "run", "--server", "$Server")
if ($PreauthCode) {{
    $runArgs += @("--preauth-code", "$PreauthCode")
}}

Write-Host "[OK] Starting LCA Companion in background..." -ForegroundColor Green
Start-Process -FilePath $pythonCmd -ArgumentList ($runArgs -join " ") -WindowStyle Hidden
Write-Host "[OK] Local Companion is now running and connected to $Server!" -ForegroundColor Green
'''
    return Response(
        content=script,
        media_type="text/plain; charset=utf-8",
        headers={
            **cors_headers(),
            "Content-Disposition": 'inline; filename="install.ps1"',
        },
    )


async def install_sh(request: Request) -> Response:
    if request.method == "OPTIONS":
        return Response("", headers=cors_headers())
    code = str(request.query_params.get("code") or "").strip()
    host = request.headers.get("host") or "127.0.0.1:8765"
    scheme = request.url.scheme or "http"
    server_url = f"{scheme}://{host}"

    script = f'''#!/usr/bin/env bash
set -e

SERVER="{server_url}"
PREAUTH_CODE="{code}"

echo "=========================================="
echo " LCA Local Companion Installer (Bash)"
echo " Server: $SERVER"
echo "=========================================="

# 1. Find python3 (>= 3.10)
find_python() {{
    for cmd in python3 python python3.12 python3.11 python3.10; do
        if command -v "$cmd" >/dev/null 2>&1; then
            if "$cmd" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null; then
                echo "$cmd"
                return 0
            fi
        fi
    done
    return 1
}}

PYTHON=$(find_python || true)

if [ -z "$PYTHON" ]; then
    echo "[!] Python 3.10+ not found in PATH. Attempting automated installation..."
    if command -v apt-get >/dev/null 2>&1; then
        sudo apt-get update -y && sudo apt-get install -y python3 python3-pip python3-venv || true
    elif command -v brew >/dev/null 2>&1; then
        brew install python3 || true
    elif command -v dnf >/dev/null 2>&1; then
        sudo dnf install -y python3 python3-pip || true
    elif command -v apk >/dev/null 2>&1; then
        apk add --no-cache python3 py3-pip || true
    fi
    PYTHON=$(find_python || true)
fi

if [ -z "$PYTHON" ]; then
    echo "[!] Python 3.10+ not found. Please install Python 3.10 or higher and try again." >&2
    exit 1
fi
echo "[OK] Found Python: $($PYTHON --version 2>&1)"

echo "[*] Checking dependencies (httpx, websockets)..."
$PYTHON -m pip install -q httpx websockets 2>/dev/null || $PYTHON -m pip install -q --user httpx websockets 2>/dev/null || true

# 2. Setup directory
LCA_DIR="$HOME/.lca"
BIN_DIR="$LCA_DIR/bin"
mkdir -p "$BIN_DIR"

COMPANION_BIN="$BIN_DIR/lca-companion.py"
echo "[*] Downloading companion client..."
curl -fsSL "$SERVER/api/device/download/companion.py" -o "$COMPANION_BIN" 2>/dev/null || \\
curl -fsSL "$SERVER/scripts/lca-companion" -o "$COMPANION_BIN" 2>/dev/null || true

# 3. Launch
CMD=("$PYTHON" "$COMPANION_BIN" "run" "--server" "$SERVER")
if [ -n "$PREAUTH_CODE" ]; then
    CMD+=("--preauth-code" "$PREAUTH_CODE")
fi

echo "[*] Launching Companion in background..."
nohup "${{CMD[@]}}" > "$LCA_DIR/companion.log" 2>&1 &
echo "[OK] Local Companion is running (PID: $!) and connected to $SERVER!"
'''
    return Response(
        content=script,
        media_type="text/x-shellscript; charset=utf-8",
        headers={
            **cors_headers(),
            "Content-Disposition": 'inline; filename="install.sh"',
        },
    )


async def download_companion(request: Request) -> Response:
    if request.method == "OPTIONS":
        return Response("", headers=cors_headers())
    from pathlib import Path

    standalone = (
        Path(__file__).resolve().parents[4]  # noqa: ASYNC240
        / "infrastructure"
        / "computer"
        / "companion"
        / "standalone.py"
    )
    if standalone.exists():
        content = standalone.read_text(encoding="utf-8")
    else:
        candidate = Path(__file__).resolve().parents[5] / "scripts" / "lca-companion"  # noqa: ASYNC240
        if candidate.exists():
            content = candidate.read_text(encoding="utf-8")
        else:
            content = "#!/usr/bin/env python3\nimport sys\nprint('Companion runner')\n"
    return Response(
        content=content,
        media_type="text/x-python; charset=utf-8",
        headers={
            **cors_headers(),
            "Content-Disposition": 'attachment; filename="lca-companion.py"',
        },
    )


async def connect_device(websocket: WebSocket) -> None:
    await websocket.accept()
    registry: DeviceRegistry = websocket.app.state.devices
    hub: DeviceHub = websocket.app.state.device_hub
    settings: DeviceHubSettings = websocket.app.state.device_settings
    params = websocket.query_params
    device_id = str(params.get("deviceId") or "").strip()
    connection_id = str(params.get("connectionId") or "").strip()
    hostname = str(params.get("hostname") or "")
    platform = str(params.get("platform") or "")
    channel_name = str(params.get("channel") or "cli")
    if not device_id or not connection_id:
        await websocket.send_json(
            {"type": "auth_failed", "reason": "deviceId and connectionId required"}
        )
        await websocket.close(code=4400)
        return
    try:
        hello = await websocket.receive_json()
    except WebSocketDisconnect:
        return
    if not isinstance(hello, dict) or hello.get("type") != "auth":
        await websocket.send_json({"type": "auth_failed", "reason": "expected auth"})
        await websocket.close(code=4400)
        return
    try:
        pairing_service = getattr(websocket.app.state, "device_pairing", None)
        user = verify_token(
            str(hello.get("token") or ""),
            str(hello.get("tokenType") or "serviceToken"),
            settings,
            pairing_service=pairing_service,
        )
    except AuthError as exc:
        await websocket.send_json({"type": "auth_failed", "reason": str(exc)})
        await websocket.close(code=4403)
        return
    home = str(hello.get("home") or params.get("home") or "")
    workspace = str(hello.get("workspace") or params.get("workspace") or "/home/sandbox-user")
    registry.register_device(
        device_id=device_id,
        hostname=hostname,
        platform=platform,
        home=home,
        workspace=workspace,
        user_id=user.user_id,
        workspace_id=user.workspace_id,
    )
    conn = DeviceConnection(
        connection_id=connection_id,
        channel=channel_name,
        connected_at=datetime.now(UTC),
        websocket=websocket,
    )
    registry.attach_channel(device_id, conn)
    await websocket.send_json({"type": "auth_success"})
    _log.info("device_online", device_id=device_id, channel=channel_name)
    try:
        while True:
            msg = await websocket.receive_json()
            if not isinstance(msg, dict):
                continue
            kind = msg.get("type")
            if kind == "heartbeat":
                await websocket.send_json({"type": "heartbeat_ack"})
            elif kind in {
                "tool_call_response",
                "rpc_response",
                "system_info_response",
            }:
                request_id = str(msg.get("requestId") or "")
                result = msg.get("result")
                hub.complete(request_id, result if isinstance(result, dict) else {})
            elif kind == "agent_run_ack":
                hub.complete(str(msg.get("operationId") or ""), msg)
    except WebSocketDisconnect:
        # INTENTIONAL: 客户端断开 → 走 finally 清理 hub/registry;
        # WebSocket 关闭是预期结束,不是错误。
        pass
    finally:
        live = registry.channel(device_id)
        if live is not None and live.connection_id == connection_id:
            hub.fail_device(device_id, f"device {device_id} offline")
        registry.detach_channel(device_id, connection_id)
        _log.info("device_offline", device_id=device_id, connection_id=connection_id)
