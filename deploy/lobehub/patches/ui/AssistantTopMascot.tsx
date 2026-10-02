'use client';

import { createStaticStyles } from 'antd-style';
import React, { memo, useCallback, useMemo } from 'react';

export type AnimalSpecies =
  | 'capybara'
  | 'dino'
  | 'fox'
  | 'owl'
  | 'dolphin'
  | 'panda'
  | 'cat'
  | 'rabbit';

export const SPECIES_LIST: AnimalSpecies[] = [
  'capybara',
  'dino',
  'fox',
  'owl',
  'dolphin',
  'panda',
  'cat',
  'rabbit',
];

export interface AssistantTopMascotProps {
  /** 助理唯一 ID */
  assistantId?: string;
  /** 助理显示名称 */
  name?: string;
  /** 显式指定形象或物种 */
  avatar?: string;
  /** 形象视觉尺寸 (默认 42px) */
  size?: number;
  /** 是否展示名字药丸 (默认 true) */
  showName?: boolean;
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

/**
 * 四级确定性动物解析策略：
 * 1. 显式配置：props.avatar 指定物种
 * 2. 语义推导：助理名称或描述中包含的物种关键词
 * 3. 稳定哈希：依据 assistantId / name 稳定映射取模
 * 4. 默认兜底：capybara (水豚)
 */
export function resolveAnimalSpecies(
  avatar?: string,
  name?: string,
  assistantId?: string,
): AnimalSpecies {
  const normAvatar = (avatar || '').toLowerCase().trim();
  if (SPECIES_LIST.includes(normAvatar as AnimalSpecies)) {
    return normAvatar as AnimalSpecies;
  }
  if (normAvatar.includes('dino') || normAvatar.includes('恐龙')) return 'dino';
  if (normAvatar.includes('fox') || normAvatar.includes('狐')) return 'fox';
  if (normAvatar.includes('owl') || normAvatar.includes('鸮') || normAvatar.includes('猫头鹰'))
    return 'owl';
  if (normAvatar.includes('dolphin') || normAvatar.includes('海豚')) return 'dolphin';
  if (normAvatar.includes('panda') || normAvatar.includes('熊猫')) return 'panda';
  if (normAvatar.includes('cat') || normAvatar.includes('猫')) return 'cat';
  if (normAvatar.includes('rabbit') || normAvatar.includes('兔')) return 'rabbit';
  if (normAvatar.includes('capybara') || normAvatar.includes('水豚')) return 'capybara';

  const normName = (name || '').toLowerCase();
  if (normName.includes('恐龙') || normName.includes('dino') || normName.includes('霸王龙'))
    return 'dino';
  if (normName.includes('狐') || normName.includes('fox')) return 'fox';
  if (normName.includes('猫头鹰') || normName.includes('owl') || normName.includes('博学'))
    return 'owl';
  if (normName.includes('海豚') || normName.includes('dolphin') || normName.includes('敏捷'))
    return 'dolphin';
  if (normName.includes('熊猫') || normName.includes('panda')) return 'panda';
  if (normName.includes('猫') || normName.includes('cat') || normName.includes('喵'))
    return 'cat';
  if (normName.includes('兔') || normName.includes('rabbit')) return 'rabbit';
  if (normName.includes('水豚') || normName.includes('capybara') || normName.includes('豚'))
    return 'capybara';

  const seed = assistantId || name || 'capybara_seed';
  let hash = 0;
  for (let i = 0; i < seed.length; i++) {
    hash = (hash * 31 + seed.charCodeAt(i)) | 0;
  }
  const idx = Math.abs(hash) % SPECIES_LIST.length;
  return SPECIES_LIST[idx] || 'capybara';
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
      padding: 6px 12px 3px 12px;
      border-radius: 20px;
      transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
      background: transparent;
      overflow: visible;

      &:hover {
        background: ${cssVar.colorFillTertiary};
        transform: translateY(-1px);

        .mascot-avatar-wrapper {
          transform: scale(1.06);
        }

        .mascot-quantum-orbit {
          animation-duration: 4s;
          opacity: 0.9;
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
      display: flex;
      align-items: center;
      justify-content: center;
      transition: transform 0.25s ease;
      overflow: visible;
    `,
    haloGlow: css`
      position: absolute;
      inset: -4px;
      border-radius: 50%;
      background: radial-gradient(
        circle,
        rgba(56, 189, 248, 0.45) 0%,
        rgba(147, 51, 234, 0.25) 50%,
        rgba(255, 255, 255, 0) 75%
      );
      animation: haloPulse 3.6s ease-in-out infinite;
      pointer-events: none;

      @keyframes haloPulse {
        0%,
        100% {
          opacity: 0.35;
          transform: scale(0.94);
        }
        50% {
          opacity: 0.85;
          transform: scale(1.12);
        }
      }
    `,
    quantumOrbit: css`
      position: absolute;
      inset: -3px;
      border-radius: 50%;
      border: 1.5px dashed rgba(56, 189, 248, 0.45);
      animation: quantumSpin 9s linear infinite;
      pointer-events: none;

      &::before {
        content: '';
        position: absolute;
        top: -2px;
        left: 50%;
        transform: translateX(-50%);
        width: 5px;
        height: 5px;
        border-radius: 50%;
        background: #38bdf8;
        box-shadow: 0 0 6px #38bdf8;
      }

      &::after {
        content: '';
        position: absolute;
        bottom: -2px;
        left: 50%;
        transform: translateX(-50%);
        width: 4px;
        height: 4px;
        border-radius: 50%;
        background: #c084fc;
        box-shadow: 0 0 6px #c084fc;
      }

      @keyframes quantumSpin {
        0% {
          transform: rotate(0deg);
        }
        100% {
          transform: rotate(360deg);
        }
      }
    `,
    mascotSvg: css`
      overflow: visible;
      animation: mascotBreath 3.2s ease-in-out infinite;
      transform-origin: center bottom;

      @keyframes mascotBreath {
        0%,
        100% {
          transform: translateY(0px) scale(1);
        }
        50% {
          transform: translateY(-2.5px) scale(1.03);
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
      right: 0px;
      bottom: 0px;
      width: 10px;
      height: 10px;
      border-radius: 50%;
      border: 2px solid ${cssVar.colorBgContainer};
      background: #52c41a;
      box-shadow: 0 0 6px rgba(82, 196, 26, 0.6);
      z-index: 2;

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
      margin-top: 3px;
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
 * 8 大萌宠动物矢量图形渲染子组件 (统一 viewBox 0 0 100 100，顶端留有充足安全边距)
 */
export const AnimalSvgRenderer = memo<{ species: AnimalSpecies; size: number }>(
  ({ species, size }) => {
    switch (species) {
      case 'dino':
        // 萌萌绿色小恐龙
        return (
          <svg width={size} height={size} viewBox="0 0 100 100" fill="none">
            <ellipse cx="50" cy="92" rx="32" ry="5" fill="rgba(0, 0, 0, 0.08)" />
            {/* 恐龙背鳍刺 */}
            <path d="M42 22L46 30L38 30Z" fill="#FBBF24" />
            <path d="M32 28L36 36L28 36Z" fill="#FBBF24" />
            <path d="M22 38L26 46L18 46Z" fill="#FBBF24" />
            {/* 恐龙圆润头部与躯干 */}
            <path
              d="M32 86C26 70 28 42 46 32C64 22 84 34 84 56C84 76 74 88 56 88H36C34 88 32 88 32 86Z"
              fill="#4ADE80"
            />
            {/* 肚皮浅色 */}
            <path
              d="M48 88C42 74 46 56 60 52C70 54 74 68 70 88C64 88 56 88 48 88Z"
              fill="#BBF7D0"
            />
            {/* 鼻吻突起 */}
            <ellipse cx="76" cy="54" rx="10" ry="8" fill="#4ADE80" />
            <circle cx="78" cy="52" r="1.5" fill="#166534" />
            {/* 微笑嘴线 */}
            <path
              d="M70 60C74 62 80 61 82 58"
              stroke="#166534"
              strokeWidth="2"
              strokeLinecap="round"
            />
            {/* 腮红 */}
            <circle cx="58" cy="58" r="4.5" fill="rgba(244, 114, 182, 0.5)" />
            {/* 大眼睛 */}
            <g className="mascot-eye">
              <ellipse cx="56" cy="42" rx="4.5" ry="5" fill="#14532D" />
              <circle cx="54.5" cy="40.5" r="1.8" fill="#FFFFFF" />
            </g>
          </svg>
        );

      case 'fox':
        // 灵动机敏小赤狐
        return (
          <svg width={size} height={size} viewBox="0 0 100 100" fill="none">
            <ellipse cx="50" cy="92" rx="32" ry="5" fill="rgba(0, 0, 0, 0.08)" />
            {/* 尖耳 */}
            <path d="M26 24L38 46L20 46Z" fill="#EA580C" />
            <path d="M26 27L34 44L22 44Z" fill="#1E293B" />
            <path d="M74 24L80 46L62 46Z" fill="#EA580C" />
            <path d="M74 27L78 44L66 44Z" fill="#1E293B" />
            {/* 狐狸头部主轮廓 */}
            <path
              d="M20 46C20 46 16 66 50 82C84 66 80 46 80 46C80 46 68 34 50 34C32 34 20 46 20 46Z"
              fill="#F97316"
            />
            {/* 白吻与两颊白毛 */}
            <path
              d="M30 62C30 62 38 78 50 82C62 78 70 62 70 62C70 62 58 72 50 72C42 72 30 62 30 62Z"
              fill="#FFFBEB"
            />
            {/* 小黑鼻 */}
            <polygon points="47,78 53,78 50,82" fill="#0F172A" />
            {/* 腮红 */}
            <circle cx="28" cy="60" r="4" fill="rgba(239, 68, 68, 0.4)" />
            <circle cx="72" cy="60" r="4" fill="rgba(239, 68, 68, 0.4)" />
            {/* 灵动大眼睛 */}
            <g className="mascot-eye">
              <ellipse cx="37" cy="50" rx="4" ry="4.5" fill="#1E293B" />
              <circle cx="35.5" cy="48.5" r="1.5" fill="#FFFFFF" />
            </g>
            <g className="mascot-eye">
              <ellipse cx="63" cy="50" rx="4" ry="4.5" fill="#1E293B" />
              <circle cx="61.5" cy="48.5" r="1.5" fill="#FFFFFF" />
            </g>
          </svg>
        );

      case 'owl':
        // 智慧猫头鹰
        return (
          <svg width={size} height={size} viewBox="0 0 100 100" fill="none">
            <ellipse cx="50" cy="92" rx="30" ry="5" fill="rgba(0, 0, 0, 0.08)" />
            {/* 耳羽簇 */}
            <path d="M26 26L34 42L22 40Z" fill="#7C3AED" />
            <path d="M74 26L78 40L66 42Z" fill="#7C3AED" />
            {/* 身体/圆头 */}
            <ellipse cx="50" cy="58" rx="30" ry="28" fill="#8B5CF6" />
            {/* 肚皮羽毛 */}
            <path
              d="M36 64C36 78 42 86 50 86C58 86 64 78 64 64C64 64 50 68 36 64Z"
              fill="#EDE9FE"
            />
            {/* 大眼眶白圈 */}
            <circle cx="38" cy="48" r="11" fill="#FFFFFF" />
            <circle cx="62" cy="48" r="11" fill="#FFFFFF" />
            {/* 金黄小鸟喙 */}
            <polygon points="46,55 54,55 50,63" fill="#F59E0B" />
            {/* 猫头鹰大黑眸 */}
            <g className="mascot-eye">
              <circle cx="38" cy="48" r="6" fill="#1E1B4B" />
              <circle cx="36" cy="46" r="2" fill="#FFFFFF" />
            </g>
            <g className="mascot-eye">
              <circle cx="62" cy="48" r="6" fill="#1E1B4B" />
              <circle cx="60" cy="46" r="2" fill="#FFFFFF" />
            </g>
          </svg>
        );

      case 'dolphin':
        // 聪慧湛蓝小海豚
        return (
          <svg width={size} height={size} viewBox="0 0 100 100" fill="none">
            <ellipse cx="50" cy="92" rx="30" ry="5" fill="rgba(0, 0, 0, 0.08)" />
            {/* 背鳍 */}
            <path d="M46 22C48 30 42 36 34 38L42 32Z" fill="#0284C7" />
            {/* 海豚身体流线型 */}
            <path
              d="M24 72C20 48 38 28 64 30C78 32 84 46 84 58C84 74 68 86 44 86C32 86 26 80 24 72Z"
              fill="#38BDF8"
            />
            {/* 白腹 */}
            <path
              d="M32 78C32 64 42 54 58 52C68 54 74 64 70 82C58 86 42 84 32 78Z"
              fill="#F0F9FF"
            />
            {/* 嘴吻 */}
            <path
              d="M74 48C84 50 88 56 82 60C76 62 70 58 74 48Z"
              fill="#38BDF8"
            />
            {/* 腮红 */}
            <circle cx="60" cy="56" r="4" fill="rgba(244, 114, 182, 0.5)" />
            {/* 眼睛 */}
            <g className="mascot-eye">
              <ellipse cx="54" cy="44" rx="4" ry="4.5" fill="#0C4A6E" />
              <circle cx="52.5" cy="42.5" r="1.5" fill="#FFFFFF" />
            </g>
          </svg>
        );

      case 'panda':
        // 憨态可掬萌大熊猫
        return (
          <svg width={size} height={size} viewBox="0 0 100 100" fill="none">
            <ellipse cx="50" cy="92" rx="32" ry="5" fill="rgba(0, 0, 0, 0.08)" />
            {/* 圆黑耳 */}
            <circle cx="27" cy="30" r="9" fill="#18181B" />
            <circle cx="73" cy="30" r="9" fill="#18181B" />
            {/* 头部大轮廓 */}
            <rect x="23" y="27" width="54" height="48" rx="22" fill="#FAFAFA" />
            {/* 身体底圈 */}
            <path
              d="M26 82C24 70 30 62 50 62C70 62 76 70 74 82C74 86 70 88 64 88H36C30 88 26 86 26 82Z"
              fill="#18181B"
            />
            {/* 熊猫标志性八字黑眼圈 */}
            <ellipse cx="37" cy="46" rx="7" ry="9" transform="rotate(-15 37 46)" fill="#18181B" />
            <ellipse cx="63" cy="46" rx="7" ry="9" transform="rotate(15 63 46)" fill="#18181B" />
            {/* 萌黑眼球 */}
            <g className="mascot-eye">
              <circle cx="37" cy="46" r="3" fill="#FFFFFF" />
              <circle cx="36" cy="45" r="1.2" fill="#000000" />
            </g>
            <g className="mascot-eye">
              <circle cx="63" cy="46" r="3" fill="#FFFFFF" />
              <circle cx="64" cy="45" r="1.2" fill="#000000" />
            </g>
            {/* 鼻子与微笑嘴 */}
            <ellipse cx="50" cy="56" rx="4" ry="2.8" fill="#18181B" />
            <path
              d="M46 60C48 62 52 62 54 60"
              stroke="#18181B"
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
        );

      case 'cat':
        // 软萌奶橘小猫咪
        return (
          <svg width={size} height={size} viewBox="0 0 100 100" fill="none">
            <ellipse cx="50" cy="92" rx="30" ry="5" fill="rgba(0, 0, 0, 0.08)" />
            {/* 三角猫耳 */}
            <polygon points="24,24 38,44 18,44" fill="#FB923C" />
            <polygon points="26,27 35,42 20,42" fill="#FECDD3" />
            <polygon points="76,24 82,44 62,44" fill="#FB923C" />
            <polygon points="74,27 80,42 65,42" fill="#FECDD3" />
            {/* 猫咪脸蛋 */}
            <ellipse cx="50" cy="54" rx="29" ry="25" fill="#FDBA74" />
            {/* 奶白口鼻 */}
            <ellipse cx="50" cy="62" rx="14" ry="9" fill="#FFF7ED" />
            {/* 粉鼻与ω猫嘴 */}
            <polygon points="48,58 52,58 50,61" fill="#F43F5E" />
            <path
              d="M44 63C47 65 50 63 50 61C50 63 53 65 56 63"
              stroke="#9A3412"
              strokeWidth="1.8"
              strokeLinecap="round"
            />
            {/* 胡须 */}
            <line x1="26" y1="58" x2="16" y2="56" stroke="#C2410C" strokeWidth="1.5" />
            <line x1="26" y1="63" x2="15" y2="65" stroke="#C2410C" strokeWidth="1.5" />
            <line x1="74" y1="58" x2="84" y2="56" stroke="#C2410C" strokeWidth="1.5" />
            <line x1="74" y1="63" x2="85" y2="65" stroke="#C2410C" strokeWidth="1.5" />
            {/* 大猫眼 */}
            <g className="mascot-eye">
              <ellipse cx="36" cy="48" rx="4.5" ry="5" fill="#7C2D12" />
              <circle cx="34.5" cy="46" r="1.6" fill="#FFFFFF" />
            </g>
            <g className="mascot-eye">
              <ellipse cx="64" cy="48" rx="4.5" ry="5" fill="#7C2D12" />
              <circle cx="62.5" cy="46" r="1.6" fill="#FFFFFF" />
            </g>
          </svg>
        );

      case 'rabbit':
        // 垂耳白白小萌兔
        return (
          <svg width={size} height={size} viewBox="0 0 100 100" fill="none">
            <ellipse cx="50" cy="92" rx="30" ry="5" fill="rgba(0, 0, 0, 0.08)" />
            {/* 长长竖兔耳 (预留充足顶高) */}
            <ellipse cx="36" cy="28" rx="6" ry="15" fill="#F8FAFC" />
            <ellipse cx="36" cy="28" rx="3" ry="10" fill="#FBCFE8" />
            <ellipse cx="64" cy="28" rx="6" ry="15" fill="#F8FAFC" />
            <ellipse cx="64" cy="28" rx="3" ry="10" fill="#FBCFE8" />
            {/* 兔头 */}
            <ellipse cx="50" cy="58" rx="27" ry="24" fill="#F8FAFC" />
            {/* 腮红 */}
            <circle cx="30" cy="62" r="5" fill="rgba(244, 114, 182, 0.5)" />
            <circle cx="70" cy="62" r="5" fill="rgba(244, 114, 182, 0.5)" />
            {/* 小粉鼻与嘴 */}
            <polygon points="48,58 52,58 50,61" fill="#FB7185" />
            <path
              d="M46 63C48 65 50 63 50 61C50 63 52 65 54 63"
              stroke="#475569"
              strokeWidth="1.6"
              strokeLinecap="round"
            />
            {/* 兔眼 */}
            <g className="mascot-eye">
              <ellipse cx="37" cy="50" rx="4" ry="4.5" fill="#334155" />
              <circle cx="35.5" cy="48.5" r="1.5" fill="#FFFFFF" />
            </g>
            <g className="mascot-eye">
              <ellipse cx="63" cy="50" rx="4" ry="4.5" fill="#334155" />
              <circle cx="61.5" cy="48.5" r="1.5" fill="#FFFFFF" />
            </g>
          </svg>
        );

      case 'capybara':
      default:
        // 温暖治愈系水豚 (温和方头与大鼻子)
        return (
          <svg width={size} height={size} viewBox="0 0 100 100" fill="none">
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
            {/* 左耳 (下移以防切头) */}
            <circle cx="28" cy="32" r="8" fill="#B87D4F" />
            <circle cx="28" cy="32" r="4.5" fill="#E8B0A0" />
            {/* 右耳 */}
            <circle cx="72" cy="32" r="8" fill="#B87D4F" />
            <circle cx="72" cy="32" r="4.5" fill="#E8B0A0" />
            {/* 头部大轮廓 */}
            <rect x="24" y="27" width="52" height="46" rx="20" fill="#E8B87D" />
            {/* 嘴筒与口鼻区 */}
            <rect x="33" y="46" width="34" height="26" rx="13" fill="#D49A6A" />
            {/* 鼻子 */}
            <ellipse cx="50" cy="51" rx="5" ry="3.5" fill="#4A3423" />
            <ellipse cx="48.5" cy="51.5" rx="1" ry="1.2" fill="#2E2015" />
            <ellipse cx="51.5" cy="51.5" rx="1" ry="1.2" fill="#2E2015" />
            {/* 微笑嘴线 */}
            <path
              d="M46 56C48 58 52 58 54 56"
              stroke="#4A3423"
              strokeWidth="2"
              strokeLinecap="round"
            />
            {/* 腮红 */}
            <circle cx="29" cy="50" r="4.5" fill="rgba(242, 140, 140, 0.45)" />
            <circle cx="71" cy="50" r="4.5" fill="rgba(242, 140, 140, 0.45)" />
            {/* 眼睛 */}
            <g className="mascot-eye">
              <ellipse cx="37" cy="40" rx="4" ry="4.5" fill="#2A1B10" />
              <circle cx="35.5" cy="38.5" r="1.5" fill="#FFFFFF" />
            </g>
            <g className="mascot-eye">
              <ellipse cx="63" cy="40" rx="4" ry="4.5" fill="#2A1B10" />
              <circle cx="61.5" cy="38.5" r="1.5" fill="#FFFFFF" />
            </g>
          </svg>
        );
    }
  },
);

AnimalSvgRenderer.displayName = 'AnimalSvgRenderer';

/**
 * 顶栏居中动态呼吸 Mascot 组件 (Muse Style Universal Dynamic Avatar)
 *
 * 普惠全助理动态萌宠引擎：四级确定性解析 + 呼吸起伏 + 眨眼微动 + OpenAI/Muse 风格双旋轨道光晕；
 * 彻底消除头部切头现象，支持点击滑出 Status Drawer 与形象编辑。
 */
export const AssistantTopMascot = memo<AssistantTopMascotProps>(
  ({
    assistantId,
    name = '架构小助',
    avatar,
    size = 42,
    showName = true,
    status = 'online',
    onOpenDrawer,
    onClick,
    className,
    style,
  }) => {
    const species = useMemo(
      () => resolveAnimalSpecies(avatar, name, assistantId),
      [avatar, name, assistantId],
    );

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
        <div
          className={`${styles.avatarWrapper} mascot-avatar-wrapper`}
          style={{ width: size, height: size }}
        >
          {/* OpenAI / Muse 风格量子环与微光晕 */}
          <div className={styles.haloGlow} />
          <div className={`${styles.quantumOrbit} mascot-quantum-orbit`} />

          {/* 灵动动物矢量 SVG (支持 8 大物种自适应与动画) */}
          <div className={styles.mascotSvg}>
            <AnimalSvgRenderer species={species} size={size} />
          </div>

          {/* 在线状态指示微光 */}
          <span className={`${styles.statusDot} ${status}`} />
        </div>

        {/* 名字药丸条 */}
        {showName && (
          <div className={`${styles.namePill} mascot-name-pill`}>
            <span>{name}</span>
            <span className={styles.caretIcon}>▾</span>
          </div>
        )}
      </div>
    );
  },
);

AssistantTopMascot.displayName = 'AssistantTopMascot';

export default AssistantTopMascot;
