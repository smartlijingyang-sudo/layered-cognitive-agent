"""SQLite-backed device registry.  Online state lives in memory."""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path

from gateway.device_gateway.models import Device, DeviceConnection


class DeviceRegistry:
    """Persist device identity; keep live channels in process memory."""

    def __init__(self, db_path: str) -> None:
        self._lock = threading.Lock()
        path = Path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._init_schema()
        self._live: dict[str, Device] = {}
        self._load_from_db()

    def _load_from_db(self) -> None:
        with self._lock:
            cursor = self._db.execute("SELECT * FROM devices")
            for row in cursor.fetchall():
                device_id = row["device_id"]
                if device_id not in self._live:
                    self._live[device_id] = Device(
                        device_id=device_id,
                        hostname=row["hostname"],
                        platform=row["platform"],
                        home=row["home"],
                        workspace=row["workspace"],
                        user_id=row["user_id"],
                        workspace_id=row["workspace_id"],
                        registered_at=datetime.fromtimestamp(row["registered_at"], UTC),
                    )

    def _init_schema(self) -> None:
        self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS devices (
                device_id TEXT PRIMARY KEY,
                hostname TEXT NOT NULL DEFAULT '',
                platform TEXT NOT NULL DEFAULT '',
                home TEXT NOT NULL DEFAULT '',
                workspace TEXT NOT NULL DEFAULT '',
                user_id TEXT NOT NULL DEFAULT '',
                workspace_id TEXT,
                registered_at REAL NOT NULL
            )
            """
        )
        self._db.commit()

    def register_device(
        self,
        *,
        device_id: str,
        hostname: str,
        platform: str,
        home: str,
        workspace: str,
        user_id: str,
        workspace_id: str | None = None,
    ) -> Device:
        now = datetime.now(UTC)
        with self._lock:
            self._db.execute(
                """
                INSERT INTO devices (
                    device_id, hostname, platform, home, workspace,
                    user_id, workspace_id, registered_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(device_id) DO UPDATE SET
                    hostname=excluded.hostname,
                    platform=excluded.platform,
                    home=excluded.home,
                    workspace=excluded.workspace,
                    user_id=excluded.user_id,
                    workspace_id=excluded.workspace_id
                """,
                (
                    device_id,
                    hostname,
                    platform,
                    home,
                    workspace,
                    user_id,
                    workspace_id,
                    now.timestamp(),
                ),
            )
            self._db.commit()
            existing = self._live.get(device_id)
            if existing is not None:
                existing.hostname = hostname
                existing.platform = platform
                existing.home = home
                existing.workspace = workspace
                existing.user_id = user_id
                existing.workspace_id = workspace_id
                return existing
            device = Device(
                device_id=device_id,
                hostname=hostname,
                platform=platform,
                home=home,
                workspace=workspace,
                user_id=user_id,
                workspace_id=workspace_id,
                registered_at=now,
            )
            self._live[device_id] = device
            return device

    def attach_channel(self, device_id: str, conn: DeviceConnection) -> None:
        with self._lock:
            device = self._live.get(device_id)
            if device is None:
                raise KeyError(device_id)
            device.channels = [c for c in device.channels if c.connection_id != conn.connection_id]
            device.channels.append(conn)

    def detach_channel(self, device_id: str, connection_id: str) -> None:
        with self._lock:
            device = self._live.get(device_id)
            if device is None:
                return
            device.channels = [c for c in device.channels if c.connection_id != connection_id]

    def get(self, device_id: str) -> Device | None:
        return self._live.get(device_id)

    def channel(self, device_id: str) -> DeviceConnection | None:
        device = self._live.get(device_id)
        if device is None or not device.channels:
            return None
        return device.channels[-1]

    def list_online(
        self,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> list[Device]:
        devices = [d for d in self._live.values() if d.online]
        if workspace_id:
            return [d for d in devices if d.workspace_id == workspace_id or d.user_id == user_id]
        if user_id:
            return [d for d in devices if d.user_id == user_id]
        return devices

    def list_all(self) -> list[Device]:
        return list(self._live.values())

    def select_online(self, device_id: str | None) -> Device | None:
        online = self.list_online()
        if device_id:
            for device in online:
                if device.device_id == device_id:
                    return device
            return None
        if len(online) == 1:
            return online[0]
        return None

    def summary(self) -> dict[str, int]:
        return {"online": len(self.list_online()), "devices": len(self._live)}
