'use client';

import { createStaticStyles } from 'antd-style';
import React, { memo, useCallback } from 'react';

export interface AssistantTopMascotProps {
  /** 助理唯一 ID */
  assistantId?: string;
  /** 助理显示名称 */
  name?: string;
  /** 在线或执行状态 */
  status?: 'online' | 'busy' | 'offline';
  /** 点击唤起右侧状态抽屉的回调 */
  onOpenDrawer?: (assistantId?: string) => void;
  /** 兼容通用点击回调 */
  onClick?: () => void;
  /** 自定义类名 */
  className?: string;
  /** 自定义内联样式 */
  style?: React.CSSProperties;
}

const styles = createStaticStyles(({ css, cssVar }) => {
  return {
    container: css`
      display: inline-flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      user-select: none;
      padding: 4px 12px;
      border-radius: 20px;
      transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
      background: transparent;

      &:hover {
        background: ${cssVar.colorFillTertiary};
        transform: translateY(-1px);

        .mascot-avatar-wrapper {
          transform: scale(1.06);
        }

        .mascot-name-pill {
          color: ${cssVar.colorPrimary};
        }
      }

      &:active {
        transform: scale(0.97);
      }
    `,
    avatarWrapper: css`
      position: relative;
      width: 44px;
      height: 44px;
      display: flex;
      align-items: center;
      justify-content: center;
      transition: transform 0.25s ease;
    `,
    haloGlow: css`
      position: absolute;
      inset: -2px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(200, 231, 255, 0.6) 0%, rgba(200, 231, 255, 0) 70%);
      animation: haloPulse 3.6s ease-in-out infinite;
      pointer-events: none;

      @keyframes haloPulse {
        0%,
        100% {
          opacity: 0.3;
          transform: scale(0.95);
        }
        50% {
          opacity: 0.75;
          transform: scale(1.12);
        }
      }
    `,
    mascotSvg: css`
      width: 40px;
      height: 40px;
      animation: mascotBreath 3.2s ease-in-out infinite;
      transform-origin: center bottom;

      @keyframes mascotBreath {
        0%,
        100% {
          transform: translateY(0px) scale(1);
        }
        50% {
          transform: translateY(-2.8px) scale(1.03);
        }
      }

      .mascot-eye {
        transform-origin: center;
        animation: mascotBlink 4.5s infinite;

        @keyframes mascotBlink {
          0%,
          92%,
          100% {
            transform: scaleY(1);
          }
          95% {
            transform: scaleY(0.1);
          }
        }
      }
    `,
    statusDot: css`
      position: absolute;
      right: 2px;
      bottom: 2px;
      width: 10px;
      height: 10px;
      border-radius: 50%;
      border: 2px solid ${cssVar.colorBgContainer};
      background: #52c41a;
      box-shadow: 0 0 6px rgba(82, 196, 26, 0.6);

      &.busy {
        background: #faad14;
        box-shadow: 0 0 6px rgba(250, 173, 20, 0.6);
      }
      &.offline {
        background: #8c8c8c;
        box-shadow: none;
      }
    `,
    namePill: css`
      display: flex;
      align-items: center;
      gap: 4px;
      margin-top: 2px;
      font-size: 13px;
      font-weight: 600;
      color: ${cssVar.colorText};
      transition: color 0.2s ease;
      line-height: 16px;
    `,
    caretIcon: css`
      font-size: 10px;
      opacity: 0.6;
      transition: transform 0.2s ease;
    `,
  };
});

/**
 * 顶栏居中动态呼吸 Mascot 组件 (Muse Style Top Mascot)
 *
 * 渲染水豚灵动形象，具备呼吸起伏微动、眨眼动画与呼吸光晕；
 * 点击后右侧滑出 Status Drawer，展现 IDENTITY / MEMORY / Workspace 卡片。
 */
export const AssistantTopMascot = memo<AssistantTopMascotProps>(
  ({
    assistantId,
    name = '架构小助',
    status = 'online',
    onOpenDrawer,
    onClick,
    className,
    style,
  }) => {
    const handleClick = useCallback(() => {
      onOpenDrawer?.(assistantId);
      onClick?.();
    }, [assistantId, onOpenDrawer, onClick]);

    return (
      <div
        className={`${styles.container} ${className || ''}`}
        style={style}
        onClick={handleClick}
        role="button"
        tabIndex={0}
        aria-label={`Open status drawer for assistant ${name}`}
      >
        <div className={`${styles.avatarWrapper} mascot-avatar-wrapper`}>
          <div className={styles.haloGlow} />
          {/* 精致可爱的灵动吉祥物 SVG (warm friendly capybara) */}
          <svg
            className={styles.mascotSvg}
            viewBox="0 0 100 100"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            {/* 柔和阴影 */}
            <ellipse cx="50" cy="92" rx="34" ry="6" fill="rgba(0, 0, 0, 0.08)" />

            {/* 身体底色 */}
            <path
              d="M26 84C24 68 28 54 40 50C48 48 54 48 62 50C74 54 78 68 76 84C76 88 72 90 66 90H36C30 90 26 88 26 84Z"
              fill="#D49A6A"
            />
            {/* 肚皮高光淡色 */}
            <path
              d="M38 88C36 78 39 66 51 64C63 66 66 78 64 88C64 90 60 90 51 90C42 90 38 90 38 88Z"
              fill="#F2DFC2"
            />

            {/* 左耳 */}
            <circle cx="28" cy="28" r="9" fill="#B87D4F" />
            <circle cx="28" cy="28" r="5" fill="#E8B0A0" />

            {/* 右耳 */}
            <circle cx="72" cy="28" r="9" fill="#B87D4F" />
            <circle cx="72" cy="28" r="5" fill="#E8B0A0" />

            {/* 头部大轮廓 (经典水豚方形温和头型) */}
            <rect x="24" y="24" width="52" height="46" rx="20" fill="#E8B87D" />

            {/* 嘴筒与口鼻区 (圆润温和的口鼻突起) */}
            <rect x="33" y="44" width="34" height="26" rx="13" fill="#D49A6A" />

            {/* 鼻子 */}
            <ellipse cx="50" cy="49" rx="5" ry="3.5" fill="#4A3423" />
            {/* 鼻孔高光 */}
            <ellipse cx="48.5" cy="49.5" rx="1" ry="1.2" fill="#2E2015" />
            <ellipse cx="51.5" cy="49.5" rx="1" ry="1.2" fill="#2E2015" />

            {/* 微笑嘴线 */}
            <path
              d="M46 54C48 56 52 56 54 54"
              stroke="#4A3423"
              strokeWidth="2"
              strokeLinecap="round"
            />

            {/* 腮红 */}
            <circle cx="29" cy="48" r="4.5" fill="rgba(242, 140, 140, 0.45)" />
            <circle cx="71" cy="48" r="4.5" fill="rgba(242, 140, 140, 0.45)" />

            {/* 萌萌的大眼睛 (带微眨眼动画) */}
            <g className="mascot-eye">
              <ellipse cx="37" cy="38" rx="4" ry="4.5" fill="#2A1B10" />
              <circle cx="35.5" cy="36.5" r="1.5" fill="#FFFFFF" />
            </g>
            <g className="mascot-eye">
              <ellipse cx="63" cy="38" rx="4" ry="4.5" fill="#2A1B10" />
              <circle cx="61.5" cy="36.5" r="1.5" fill="#FFFFFF" />
            </g>
          </svg>

          {/* 在线状态指示微光 */}
          <span className={`${styles.statusDot} ${status}`} />
        </div>

        {/* 名字药丸条 */}
        <div className={`${styles.namePill} mascot-name-pill`}>
          <span>{name}</span>
          <span className={styles.caretIcon}>▾</span>
        </div>
      </div>
    );
  },
);

AssistantTopMascot.displayName = 'AssistantTopMascot';

export default AssistantTopMascot;
