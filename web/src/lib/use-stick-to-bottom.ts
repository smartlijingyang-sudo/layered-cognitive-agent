import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

const SCROLL_THRESHOLD_PX = 64;

function isScrollable(el: HTMLElement): boolean {
  const style = window.getComputedStyle(el);
  return /auto|scroll/.test(style.overflowY);
}

function findScrollParent(el: HTMLElement | null): HTMLElement | null {
  let node = el?.parentElement ?? null;
  while (node) {
    if (isScrollable(node)) return node;
    node = node.parentElement;
  }
  return null;
}

function distanceFromBottom(el: HTMLElement): number {
  return el.scrollHeight - el.scrollTop - el.clientHeight;
}

function scrollContainerToBottom(el: HTMLElement): void {
  el.scrollTop = el.scrollHeight;
}

/**
 * 贴底跟随：用户未主动上滚时，内容增长后滚到底部。
 * 用户滚轮向上或离开底部区域后立即停止跟随，直到点击「回到底部」或发送新消息。
 */
export function useStickToBottom(contentKey: string | number) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const scrollParentRef = useRef<HTMLElement | null>(null);
  const pinnedRef = useRef(true);
  const [showScrollButton, setShowScrollButton] = useState(false);

  const syncPinnedFromScroll = useCallback(() => {
    const scrollParent = scrollParentRef.current;
    if (!scrollParent) return;
    const atBottom = distanceFromBottom(scrollParent) <= SCROLL_THRESHOLD_PX;
    pinnedRef.current = atBottom;
    setShowScrollButton(!atBottom);
  }, []);

  const scrollToBottom = useCallback(() => {
    pinnedRef.current = true;
    setShowScrollButton(false);
    const scrollParent = scrollParentRef.current;
    if (scrollParent) {
      scrollContainerToBottom(scrollParent);
      return;
    }
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, []);

  /** 新消息发送后恢复贴底（仅由调用方在新 turn 时触发）。 */
  const pinForNewTurn = useCallback(() => {
    pinnedRef.current = true;
    setShowScrollButton(false);
    requestAnimationFrame(() => scrollToBottom());
  }, [scrollToBottom]);

  useEffect(() => {
    const anchor = bottomRef.current;
    if (!anchor) return;
    const scrollParent = findScrollParent(anchor);
    scrollParentRef.current = scrollParent;
    if (!scrollParent) return;

    const onScroll = () => syncPinnedFromScroll();

    const onWheel = (event: WheelEvent) => {
      if (event.deltaY < 0) {
        pinnedRef.current = false;
        setShowScrollButton(true);
      }
    };

    scrollParent.addEventListener("scroll", onScroll, { passive: true });
    scrollParent.addEventListener("wheel", onWheel, { passive: true });
    syncPinnedFromScroll();

    return () => {
      scrollParent.removeEventListener("scroll", onScroll);
      scrollParent.removeEventListener("wheel", onWheel);
    };
  }, [syncPinnedFromScroll]);

  useLayoutEffect(() => {
    if (!pinnedRef.current) return;
    const scrollParent = scrollParentRef.current;
    if (scrollParent) {
      scrollContainerToBottom(scrollParent);
    }
  }, [contentKey]);

  return { bottomRef, scrollToBottom, pinForNewTurn, showScrollButton };
}
