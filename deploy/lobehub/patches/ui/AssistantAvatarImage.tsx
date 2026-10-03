'use client';

import { Avatar } from 'antd';
import type { ReactNode } from 'react';
import React, { memo, useEffect, useState } from 'react';

import AssistantTopMascot, {
  AnimalSvgRenderer,
  resolveAnimalSpecies,
  type AnimalSpecies,
} from '@/features/Conversation/components/AssistantTopMascot';

export interface AvatarVariantPayload {
  size: string;
  url: string;
}

export interface AvatarActivePayload {
  candidate_id: string;
  variants: AvatarVariantPayload[];
}

export interface AvatarStatePayload {
  assistant_id: string;
  active: AvatarActivePayload | null;
  updated_at: string;
}

const AVATAR_ENDPOINT = (assistantId: string) =>
  `/lca-api/v1/assistants/${assistantId}/avatar`;

// 同一助理的多个消息气泡共享一次 GET /avatar，避免 N 个气泡发 N 个请求。
// avatar_updated / avatar_video_ready 到达时由 WS 事件清掉对应缓存再拉取。
const activeUrlCache = new Map<string, string | null>();
const inflightFetches = new Map<string, Promise<string | null>>();

function authHeaders(): Record<string, string> {
  const envToken =
    typeof process !== 'undefined'
      ? (process as { env?: Record<string, string | undefined> }).env
          ?.NEXT_PUBLIC_LCA_TOKEN
      : undefined;
  const token = envToken || 'lca-local';
  const mockDevUserId =
    typeof process !== 'undefined'
      ? (process as { env?: Record<string, string | undefined> }).env
          ?.NEXT_PUBLIC_MOCK_DEV_USER_ID
      : undefined;
  const userId =
    (typeof window !== 'undefined' &&
      (window as { __LCA_USER_ID?: string } | undefined)?.__LCA_USER_ID) ||
    mockDevUserId ||
    'local-dev-user';
  return {
    Authorization: `Bearer ${token}`,
    'x-lca-token': token,
    'x-lca-user-id': userId,
  };
}

async function fetchActiveAvatarUrl(assistantId: string): Promise<string | null> {
  const cached = activeUrlCache.get(assistantId);
  if (cached !== undefined) return cached;
  const inflight = inflightFetches.get(assistantId);
  if (inflight) return inflight;
  const promise = (async () => {
    try {
      const res = await fetch(AVATAR_ENDPOINT(assistantId), { headers: authHeaders() });
      if (!res.ok) return null;
      const data: AvatarStatePayload = await res.json();
      const original = data.active?.variants.find((v) => v.size === 'original');
      const url = original?.url || data.active?.variants[0]?.url || null;
      activeUrlCache.set(assistantId, url);
      return url;
    } catch {
      /* 保持当前头像 */
      return null;
    } finally {
      inflightFetches.delete(assistantId);
    }
  })();
  inflightFetches.set(assistantId, promise);
  return promise;
}

export interface AssistantAvatarImageProps {
  /** 助理唯一标识 */
  assistantId?: string;
  /** 头像尺寸 (px) */
  size?: number;
  /** 头像形状（消息气泡用 square，顶栏默认 circle） */
  shape?: 'circle' | 'square';
  /** active 为空时渲染的默认头像节点；缺省为 SVG 萌宠回退 */
  fallback?: ReactNode;
  /** 助理显示名称 */
  name?: string;
  /** 点击唤起右侧状态抽屉的回调 */
  onOpenDrawer?: (assistantId?: string) => void;
  /** 兼容通用点击回调 */
  onClick?: () => void;
  /** 是否展示名字药丸 (默认 true) */
  showName?: boolean;
}

export const AssistantAvatarImage = memo<AssistantAvatarImageProps>(
  ({
    assistantId,
    size = 32,
    shape = 'circle',
    fallback,
    name,
    onOpenDrawer,
    onClick,
    showName = true,
  }) => {
    const [activeUrl, setActiveUrl] = useState<string | null>(null);

    useEffect(() => {
      const key = assistantId || 'default';
      let cancelled = false;
      const refresh = async () => {
        const url = await fetchActiveAvatarUrl(key);
        if (!cancelled) setActiveUrl(url);
      };
      void refresh();

      const onAvatarChanged = (event: Event) => {
        const detail = (event as CustomEvent<{ assistantId?: string; assistant_id?: string }>).detail;
        const changedId = detail?.assistantId || detail?.assistant_id;
        if (changedId && changedId !== assistantId) return;
        activeUrlCache.delete(key);
        void refresh();
      };
      window.addEventListener('lca-assistant-avatar-changed', onAvatarChanged);
      return () => {
        cancelled = true;
        window.removeEventListener('lca-assistant-avatar-changed', onAvatarChanged);
      };
    }, [assistantId]);

    // 1. 消息气泡场景 (shape === 'square')：仅呈现纯方形头像，不带顶栏动效与名字药丸
    if (shape === 'square') {
      if (activeUrl) {
        return <Avatar src={activeUrl} size={size} shape="square" />;
      }
      if (fallback) return <>{fallback}</>;
      const species = resolveAnimalSpecies(undefined, undefined, assistantId) as AnimalSpecies;
      return (
        <Avatar size={size} shape="square">
          <AnimalSvgRenderer species={species} size={size} />
        </Avatar>
      );
    }

    // 2. 顶栏/通用场景 (shape === 'circle')：必须完整保有 Muse 动效（呼吸、量子环、光晕）与点击抽屉交互
    if (React.isValidElement(fallback)) {
      return React.cloneElement(fallback as React.ReactElement<any>, {
        avatarUrl: activeUrl || undefined,
        assistantId: assistantId || (fallback.props as any)?.assistantId,
        size: size || (fallback.props as any)?.size,
        name: name || (fallback.props as any)?.name,
        onOpenDrawer: onOpenDrawer || (fallback.props as any)?.onOpenDrawer,
        onClick: onClick || (fallback.props as any)?.onClick,
      });
    }

    return (
      <AssistantTopMascot
        assistantId={assistantId}
        name={name}
        avatarUrl={activeUrl || undefined}
        size={size}
        showName={showName}
        onOpenDrawer={onOpenDrawer}
        onClick={onClick}
      />
    );
  },
);

AssistantAvatarImage.displayName = 'AssistantAvatarImage';

export default AssistantAvatarImage;