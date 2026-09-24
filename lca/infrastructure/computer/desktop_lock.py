"""Desktop lock manager for single-screen mutual exclusion (ADR-0248 §5.3 / s13)."""

from __future__ import annotations

import asyncio
import time

from lca.contracts.models.browser.models import DesktopLock


class DesktopLockManager:
    """单屏桌面互斥锁管理器（allocateWindow / freeWindow 落地实现）。

    不变量：
    - INV-06: 任何时刻最多只能有一个 Agent 独占屏幕与前台交互。
    - 120s TTL（可配置）超时自动回收防死锁。
    - 只有锁持有者本人（或锁超时后）才能释放/接管锁。
    """

    def __init__(self, default_ttl_s: int = 120) -> None:
        self.default_ttl_s = default_ttl_s
        self._current_lock: DesktopLock | None = None
        self._mutex = asyncio.Lock()

    def _now_ms(self) -> int:
        return int(time.time() * 1000)

    def _is_expired(self) -> bool:
        if self._current_lock is None:
            return True
        return self._current_lock.is_expired(self._now_ms())

    def is_locked(self) -> bool:
        """检查当前是否有未过期的桌面锁。"""
        if self._current_lock is None:
            return False
        return not self._is_expired()

    def get_current_owner(self) -> str | None:
        """获取当前桌面锁持有者 Agent ID（如果锁已超时返回 None）。"""
        if self.is_locked() and self._current_lock is not None:
            return self._current_lock.agent_id
        return None

    async def allocate_window(
        self,
        agent_id: str,
        session_id: str,
        ttl_seconds: int | None = None,
    ) -> bool:
        """尝试抢占单屏桌面独占锁。

        成功抢占返回 True；已被他人持有且未超时返回 False。
        """
        async with self._mutex:
            ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_s
            now = self._now_ms()

            # 如果当前无锁，或当前锁已超时，允许抢占
            if self._current_lock is None or self._is_expired():
                self._current_lock = DesktopLock(
                    agent_id=agent_id,
                    session_id=session_id,
                    acquired_at_ms=now,
                    ttl_seconds=ttl,
                )
                return True

            # 如果当前持有者就是自己，允许续期
            if self._current_lock.agent_id == agent_id:
                self._current_lock = DesktopLock(
                    agent_id=agent_id,
                    session_id=session_id,
                    acquired_at_ms=now,
                    ttl_seconds=ttl,
                )
                return True

            return False

    async def free_window(
        self,
        agent_id: str,
        session_id: str,
    ) -> bool:
        """释放单屏桌面锁。

        仅当调用方是锁持有者时释放成功返回 True，否则返回 False。
        """
        async with self._mutex:
            if self._current_lock is None:
                return True

            # 只有持有者才能释放锁
            if self._current_lock.agent_id == agent_id:
                self._current_lock = None
                return True

            # 如果锁已经超时失效，清理并返回 True
            if self._is_expired():
                self._current_lock = None
                return True

            return False


__all__ = ["DesktopLockManager"]
