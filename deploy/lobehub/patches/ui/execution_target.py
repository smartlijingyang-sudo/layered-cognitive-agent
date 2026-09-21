"""Patch: execution environment picker — 用电脑 / 云沙箱 / 自动. No none, no download desktop.

LCA CONV-INSTALL: one-liner local machine pairing section reuses the native
OptionRow visual language (icon tile + title + desc) and CopyButton from
@lobehub/ui instead of inline styles.
"""

from __future__ import annotations

from deploy.lobehub.engine import PatchContext, PatchMeta

meta = PatchMeta(
    name="execution_target",
    description="Execution picker: use-computer instead of download desktop; drop none; add local-machine pairing section",
    files=(
        "src/features/ChatInput/ControlBar/HeteroDeviceSwitcher.tsx",
        "src/features/ExecutionTargetPicker/index.tsx",
        "packages/types/src/agent/agencyConfig.ts",
        "locales/zh-CN/chat.json",
        "locales/en-US/chat.json",
        "packages/locales/src/default/chat.ts",
    ),
    risk="medium",
    category="ui",
    depends_on=(),
    why="LCA sidecar is the computer; LobeHub desktop download is the wrong CTA",
    technical_detail=(
        "Hide none. Show local on web as 用电脑. Drop download-desktop header and card. "
        "Honour stored local on web so the chip does not coerce to sandbox. "
        "Add a pairing section at the bottom of the popover that reuses native "
        "OptionRow patterns and CopyButton for the one-liner install flow."
    ),
    verify_file="src/features/ChatInput/ControlBar/HeteroDeviceSwitcher.tsx",
    verify_marker="LCA: sidecar is use-computer",
)

_SWITCHER = "src/features/ChatInput/ControlBar/HeteroDeviceSwitcher.tsx"


def apply(ctx: PatchContext) -> bool:
    text = ctx.read(_SWITCHER)
    original = text
    text = _patch_imports(text)
    text = _patch_styles(text)
    text = _patch_switcher(text)
    text = _patch_pairing_state(text)
    text = _patch_pairing_jsx(text)
    changed = text != original
    if changed:
        ctx.write(_SWITCHER, text)
    _patch_types(ctx)
    _patch_locales(ctx)
    return changed


def _patch_imports(text: str) -> str:
    text = text.replace("import { DOWNLOAD_URL } from '@/const/url';\n", "")
    text = text.replace(
        "import { Flexbox, Icon, Popover, Tooltip } from '@lobehub/ui';",
        "import { CopyButton, Flexbox, Icon, Popover, Tooltip } from '@lobehub/ui';",
    )
    text = text.replace(
        "  ExternalLinkIcon,\n  InfoIcon,\n  MonitorDownIcon,\n  SettingsIcon,\n",
        "  InfoIcon,\n  SettingsIcon,\n  TerminalIcon,\n",
    )
    return text


def _patch_styles(text: str) -> str:
    if "pairingSection:" in text:
        return text
    anchor = "  groupLabel: css`"
    insert = (
        "  pairingSection: css`\n"
        "    margin-block-start: 2px;\n"
        "    padding-block-start: 8px;\n"
        "    border-block-start: 1px solid ${cssVar.colorBorderSecondary};\n"
        "  `,\n"
        "  pairingHeader: css`\n"
        "    display: flex;\n"
        "    gap: 6px;\n"
        "    align-items: center;\n"
        "\n"
        "    padding-block: 2px 4px;\n"
        "    padding-inline: 8px;\n"
        "\n"
        "    font-size: 11px;\n"
        "    font-weight: 500;\n"
        "    color: ${cssVar.colorTextTertiary};\n"
        "  `,\n"
        "  pairingOsRow: css`\n"
        "    display: flex;\n"
        "    gap: 4px;\n"
        "    align-items: center;\n"
        "\n"
        "    padding-block: 2px 4px;\n"
        "    padding-inline: 8px;\n"
        "  `,\n"
        "  pairingOsToggle: css`\n"
        "    cursor: pointer;\n"
        "\n"
        "    padding-block: 1px;\n"
        "    padding-inline: 6px;\n"
        "    border: 1px solid ${cssVar.colorBorderSecondary};\n"
        "    border-radius: 4px;\n"
        "\n"
        "    font-size: 10px;\n"
        "    line-height: 16px;\n"
        "    color: ${cssVar.colorTextSecondary};\n"
        "\n"
        "    background: transparent;\n"
        "\n"
        "    transition: all 0.15s;\n"
        "\n"
        "    &:hover {\n"
        "      color: ${cssVar.colorText};\n"
        "      border-color: ${cssVar.colorBorder};\n"
        "    }\n"
        "  `,\n"
        "  pairingOsToggleActive: css`\n"
        "    color: ${cssVar.colorPrimary};\n"
        "    border-color: ${cssVar.colorPrimary};\n"
        "    background: ${cssVar.colorPrimaryBg};\n"
        "\n"
        "    &:hover {\n"
        "      color: ${cssVar.colorPrimary};\n"
        "      border-color: ${cssVar.colorPrimary};\n"
        "    }\n"
        "  `,\n"
        "  pairingCodeBlock: css`\n"
        "    display: flex;\n"
        "    gap: 8px;\n"
        "    align-items: center;\n"
        "\n"
        "    margin-block: 4px 6px;\n"
        "    margin-inline: 8px;\n"
        "    padding-block: 8px;\n"
        "    padding-inline: 10px;\n"
        "    border: 1px solid ${cssVar.colorBorderSecondary};\n"
        "    border-radius: ${cssVar.borderRadius};\n"
        "\n"
        "    background: ${cssVar.colorFillQuaternary};\n"
        "  `,\n"
        "  pairingCode: css`\n"
        "    overflow: hidden;\n"
        "    flex: 1;\n"
        "\n"
        "    font-family: ${cssVar.fontFamilyCode};\n"
        "    font-size: 11px;\n"
        "    color: ${cssVar.colorText};\n"
        "    word-break: break-all;\n"
        "  `,\n"
        "  pairingHint: css`\n"
        "    padding-block: 0 4px;\n"
        "    padding-inline: 8px;\n"
        "\n"
        "    font-size: 11px;\n"
        "    color: ${cssVar.colorTextTertiary};\n"
        "  `,\n"
        "  pairingInputRow: css`\n"
        "    display: flex;\n"
        "    gap: 6px;\n"
        "    align-items: center;\n"
        "\n"
        "    padding-block: 2px 4px;\n"
        "    padding-inline: 8px;\n"
        "  `,\n"
        "  pairingInput: css`\n"
        "    flex: 1;\n"
        "\n"
        "    height: 28px;\n"
        "    padding-inline: 8px;\n"
        "    border: 1px solid ${cssVar.colorBorderSecondary};\n"
        "    border-radius: ${cssVar.borderRadius};\n"
        "\n"
        "    font-size: 12px;\n"
        "    color: ${cssVar.colorText};\n"
        "\n"
        "    background: transparent;\n"
        "\n"
        "    transition: border-color 0.15s;\n"
        "\n"
        "    &::placeholder {\n"
        "      color: ${cssVar.colorTextQuaternary};\n"
        "    }\n"
        "\n"
        "    &:focus {\n"
        "      border-color: ${cssVar.colorPrimary};\n"
        "      outline: none;\n"
        "    }\n"
        "  `,\n"
        "  pairingSubmit: css`\n"
        "    cursor: pointer;\n"
        "\n"
        "    height: 28px;\n"
        "    padding-inline: 10px;\n"
        "    border: none;\n"
        "    border-radius: ${cssVar.borderRadius};\n"
        "\n"
        "    font-size: 12px;\n"
        "    color: #fff;\n"
        "\n"
        "    background: ${cssVar.colorPrimary};\n"
        "\n"
        "    transition: opacity 0.15s;\n"
        "\n"
        "    &:hover {\n"
        "      opacity: 0.85;\n"
        "    }\n"
        "\n"
        "    &:disabled {\n"
        "      cursor: not-allowed;\n"
        "      opacity: 0.5;\n"
        "    }\n"
        "  `,\n"
        "  pairingStatus: css`\n"
        "    padding-block: 2px 4px;\n"
        "    padding-inline: 8px;\n"
        "\n"
        "    font-size: 11px;\n"
        "  `,\n"
        "  pairingStatusOk: css`\n"
        "    color: ${cssVar.colorSuccess};\n"
        "  `,\n"
        "  pairingStatusErr: css`\n"
        "    color: ${cssVar.colorError};\n"
        "  `,\n"
        "  pairingGetBtn: css`\n"
        "    cursor: pointer;\n"
        "\n"
        "    display: flex;\n"
        "    gap: 6px;\n"
        "    align-items: center;\n"
        "    justify-content: center;\n"
        "\n"
        "    width: calc(100% - 16px);\n"
        "    margin-block: 2px 4px;\n"
        "    margin-inline: 8px;\n"
        "    padding-block: 6px;\n"
        "    border: 1px dashed ${cssVar.colorBorderSecondary};\n"
        "    border-radius: ${cssVar.borderRadius};\n"
        "\n"
        "    font-size: 11px;\n"
        "    color: ${cssVar.colorTextSecondary};\n"
        "\n"
        "    background: transparent;\n"
        "\n"
        "    transition: all 0.15s;\n"
        "\n"
        "    &:hover {\n"
        "      color: ${cssVar.colorPrimary};\n"
        "      border-color: ${cssVar.colorPrimary};\n"
        "    }\n"
        "  `,\n"
    )
    text = text.replace(anchor, insert + anchor, 1)
    return text


def _patch_switcher(text: str) -> str:
    text = text.replace(
        "  ExternalLinkIcon,\n  InfoIcon,\n  MonitorDownIcon,\n  SettingsIcon,\n",
        "  InfoIcon,\n  SettingsIcon,\n",
    )
    text = text.replace(
        "  const { data: devices, isLoading } = useDeviceList();\n",
        "  const { data: devices, isLoading, mutate: refreshDevices } = useDeviceList();\n",
        1,
    )

    text = text.replace(
        "  const showWebDownloadCard = !isDesktop && !isWorkspaceAgent && hasNoDevices && !isLoading;\n",
        "",
    )
    if "LCA: sidecar is use-computer" not in text:
        needle = (
            "  const chipExecutionTarget = canShowExecutionTargetSelector\n"
            "    ? executionTarget\n"
            "    : (agencyConfig?.executionTarget ?? executionTarget);\n"
        )
        insert = (
            "\n"
            "  /* LCA: sidecar is use-computer; never surface none */\n"
            "  const storedExecutionTarget = agencyConfig?.executionTarget;\n"
            "  const lcaDisplayTarget =\n"
            "    storedExecutionTarget === 'local' ||\n"
            "    storedExecutionTarget === 'device' ||\n"
            "    storedExecutionTarget === 'sandbox' ||\n"
            "    storedExecutionTarget === 'auto'\n"
            "      ? storedExecutionTarget\n"
            "      : 'auto';\n"
        )
        if needle not in text:
            raise SystemExit("[execution_target] chipExecutionTarget anchor not found")
        text = text.replace(needle, insert, 1)
    else:
        leftover = (
            "  const chipExecutionTarget = canShowExecutionTargetSelector\n"
            "    ? executionTarget\n"
            "    : (agencyConfig?.executionTarget ?? executionTarget);\n"
        )
        text = text.replace(leftover, "", 1)

    text = text.replace(
        "  if (chipExecutionTarget === 'none') {\n"
        "    chipIcon = <ExecutionTargetIcon target={'none'} />;\n"
        "    chipLabel = t('heteroAgent.executionTarget.none');\n"
        "  } else if (chipExecutionTarget === 'auto') {\n"
        "    chipIcon = <ExecutionTargetIcon target={'auto'} />;\n"
        "    chipLabel = t('heteroAgent.executionTarget.auto');\n"
        "  } else if (chipExecutionTarget === 'local') {\n",
        "  if (lcaDisplayTarget === 'auto') {\n"
        "    chipIcon = <ExecutionTargetIcon target={'auto'} />;\n"
        "    chipLabel = t('heteroAgent.executionTarget.auto');\n"
        "  } else if (lcaDisplayTarget === 'local') {\n",
        1,
    )

    text = text.replace(
        "  } else if (chipExecutionTarget === 'device') {\n",
        "  } else if (lcaDisplayTarget === 'device') {\n",
        1,
    )

    text = text.replace(
        "  const isActive = (target: DeviceExecutionTarget, deviceId?: string) => {\n"
        "    if (target === 'device') return executionTarget === 'device' && boundDeviceId === deviceId;\n"
        "    return executionTarget === target;\n"
        "  };\n",
        "  const isActive = (target: DeviceExecutionTarget, deviceId?: string) => {\n"
        "    if (target === 'device')\n"
        "      return storedExecutionTarget === 'device' && boundDeviceId === deviceId;\n"
        "    if (target === 'auto')\n"
        "      return storedExecutionTarget === 'auto' || storedExecutionTarget === undefined;\n"
        "    return storedExecutionTarget === target;\n"
        "  };\n",
        1,
    )

    text = text.replace(
        "        {isDesktop || showWebDownloadCard ? (\n"
        "          <button\n"
        "            className={styles.manageButton}\n"
        '            type="button"\n'
        "            onClick={() => {\n"
        "              setOpen(false);\n"
        "              navigate('/settings/devices');\n"
        "            }}\n"
        "          >\n"
        "            <Icon icon={SettingsIcon} size={11} />\n"
        "            <span>{t('heteroAgent.executionTarget.manage')}</span>\n"
        "          </button>\n"
        "        ) : (\n"
        "          <a\n"
        "            className={styles.headerLink}\n"
        "            href={DOWNLOAD_URL.default}\n"
        '            rel="noreferrer"\n'
        '            target="_blank"\n'
        "          >\n"
        "            <Icon icon={ExternalLinkIcon} size={11} />\n"
        "            <span>{t('heteroAgent.executionTarget.downloadDesktop')}</span>\n"
        "          </a>\n"
        "        )}\n",
        "        {isDesktop ? (\n"
        "          <button\n"
        "            className={styles.manageButton}\n"
        '            type="button"\n'
        "            onClick={() => {\n"
        "              setOpen(false);\n"
        "              navigate('/settings/devices');\n"
        "            }}\n"
        "          >\n"
        "            <Icon icon={SettingsIcon} size={11} />\n"
        "            <span>{t('heteroAgent.executionTarget.manage')}</span>\n"
        "          </button>\n"
        "        ) : null}\n",
        1,
    )

    text = text.replace(
        "      {isHetero ? null : (\n"
        "        <OptionRow\n"
        "          active={isActive('none')}\n"
        "          desc={t('heteroAgent.executionTarget.noneDesc')}\n"
        "          icon={<ExecutionTargetIcon target={'none'} />}\n"
        "          label={t('heteroAgent.executionTarget.none')}\n"
        "          onClick={() => void handleSelect('none')}\n"
        "        />\n"
        "      )}\n"
        "      {isHetero ? null : (\n",
        "      {isHetero ? null : (\n",
        1,
    )

    text = text.replace(
        "      <OptionRow\n"
        "        active={isActive('local')}\n"
        "        desc={t('heteroAgent.executionTarget.localDesc')}\n"
        "        icon={<ExecutionTargetIcon target={'local'} />}\n"
        "        label={t('heteroAgent.executionTarget.local')}\n"
        "        onClick={() => void handleSelect('local')}\n"
        "      />\n"
        "      <OptionRow\n"
        "        active={isActive('dsh')}\n"
        "        desc={t('heteroAgent.executionTarget.dshDesc')}\n"
        "        icon={<ExecutionTargetIcon target={'dsh'} />}\n"
        "        label={t('heteroAgent.executionTarget.dsh')}\n"
        "        onClick={() => void handleSelect('dsh')}\n"
        "      />\n",
        "      {isDesktop ? (\n"
        "        <OptionRow\n"
        "          active={isActive('local')}\n"
        "          desc={t('heteroAgent.executionTarget.localDesc')}\n"
        "          icon={<ExecutionTargetIcon target={'local'} />}\n"
        "          // 本机统一显示「本地设备」，不再带具体设备名称\n"
        "          label={t('heteroAgent.executionTarget.local')}\n"
        "          onClick={() => void handleSelect('local')}\n"
        "        />\n"
        "      ) : null}\n",
        1,
    )

    card_start = "      {showWebDownloadCard ? (\n"
    if card_start in text:
        start = text.index(card_start)
        end = text.find("      ) : null}\n", start)
        if end < 0:
            raise SystemExit("[execution_target] download card end not found")
        end = text.find("\n", end) + 1
        text = text[:start] + text[end:]

    return text


def _patch_pairing_state(text: str) -> str:
    if "/* LCA: CONV-INSTALL-4 One-Liner Auto-Install */" in text:
        return text

    state_anchor = "  const selectExecutionTarget = useSelectExecutionTarget(agentId);\n"
    state_code = (
        "  /* LCA: CONV-INSTALL-4 One-Liner Auto-Install */\n"
        "  const [pairCode, setPairCode] = useState('');\n"
        "  const [pairingStatus, setPairStatus] = useState<{ ok: boolean; msg: string } | null>(null);\n"
        "  const [isPairing, setIsPairing] = useState(false);\n"
        "  const [installCmd, setInstallCmd] = useState('');\n"
        "  const [cmdOs, setCmdOs] = useState<'windows' | 'bash'>('windows');\n"
        "  const [knownDevIds, setKnownDevIds] = useState<Set<string>>(new Set());\n"
        "\n"
        "  const fetchInstallCmd = useCallback(async (os: 'windows' | 'bash') => {\n"
        "    setCmdOs(os);\n"
        "    try {\n"
        "      const resp = await fetch('/lca-api/api/device/pair/preauth', {\n"
        "        method: 'POST',\n"
        "        headers: { 'Content-Type': 'application/json' },\n"
        "        body: JSON.stringify({}),\n"
        "      });\n"
        "      const data = await resp.json();\n"
        "      if (data.success && data.installCommands) {\n"
        "        setInstallCmd(data.installCommands[os] || '');\n"
        "      }\n"
        "    } catch {\n"
        "      /* LCA: network error surfaces as empty installCmd (button stays clickable) */\n"
        "    }\n"
        "  }, []);\n"
        "\n"
        "  useEffect(() => {\n"
        "    if (!devices) return;\n"
        "    const currentOnline = devices.filter((d: any) => d.online);\n"
        "    if (knownDevIds.size > 0) {\n"
        "      const newlyJoined = currentOnline.find((d: any) => !knownDevIds.has(d.deviceId));\n"
        "      if (newlyJoined && selectExecutionTarget) {\n"
        "        selectExecutionTarget('device', newlyJoined.deviceId);\n"
        "        setPairStatus({ ok: true, msg: `已自动绑定: ${newlyJoined.friendlyName || newlyJoined.deviceId}` });\n"
        "      }\n"
        "    }\n"
        "    setKnownDevIds(new Set(currentOnline.map((d: any) => d.deviceId)));\n"
        "  }, [devices, knownDevIds, selectExecutionTarget]);\n"
        "\n"
        "  const handlePairSubmit = useCallback(async () => {\n"
        "    const code = pairCode.trim();\n"
        "    if (!code) return;\n"
        "    setIsPairing(true);\n"
        "    setPairStatus(null);\n"
        "    try {\n"
        "      const resp = await fetch('/lca-api/api/device/pair/verify', {\n"
        "        method: 'POST',\n"
        "        headers: { 'Content-Type': 'application/json' },\n"
        "        body: JSON.stringify({ userCode: code }),\n"
        "      });\n"
        "      const data = await resp.json();\n"
        "      if (resp.ok && data.success) {\n"
        "        setPairStatus({ ok: true, msg: `设备已配对: ${data.label || data.deviceId}` });\n"
        "        setPairCode('');\n"
        "        if (selectExecutionTarget) selectExecutionTarget('device', data.deviceId);\n"
        "        void refreshDevices();\n"
        "      } else {\n"
        "        setPairStatus({ ok: false, msg: data.error || '无效配对码' });\n"
        "      }\n"
        "    } catch {\n"
        "      setPairStatus({ ok: false, msg: '网络错误' });\n"
        "    } finally {\n"
        "      setIsPairing(false);\n"
        "    }\n"
        "  }, [pairCode, selectExecutionTarget, refreshDevices]);\n"
    )
    if state_anchor in text:
        text = text.replace(state_anchor, state_anchor + state_code, 1)
    return text


def _patch_pairing_jsx(text: str) -> str:
    if "/* LCA: CONV-INSTALL-4 pairing section */" in text:
        return text

    jsx_anchor = "    </Flexbox>\n  );\n\n  const chip = ("
    jsx_code = (
        "      {/* LCA: CONV-INSTALL-4 pairing section */}\n"
        "      <div className={styles.pairingSection}>\n"
        "        <div className={styles.pairingHeader}>\n"
        "          <Icon icon={TerminalIcon} size={12} />\n"
        "          <span>接入本机</span>\n"
        "        </div>\n"
        "        <div className={styles.pairingOsRow}>\n"
        "          <button\n"
        '            type="button"\n'
        "            className={cx(styles.pairingOsToggle, cmdOs === 'windows' && styles.pairingOsToggleActive)}\n"
        "            onClick={() => void fetchInstallCmd('windows')}\n"
        "          >\n"
        "            PowerShell\n"
        "          </button>\n"
        "          <button\n"
        '            type="button"\n'
        "            className={cx(styles.pairingOsToggle, cmdOs === 'bash' && styles.pairingOsToggleActive)}\n"
        "            onClick={() => void fetchInstallCmd('bash')}\n"
        "          >\n"
        "            Bash\n"
        "          </button>\n"
        "        </div>\n"
        "        {installCmd ? (\n"
        "          <>\n"
        "            <div className={styles.pairingCodeBlock}>\n"
        "              <code className={styles.pairingCode}>{installCmd}</code>\n"
        "              <CopyButton content={installCmd} size={'small'} />\n"
        "            </div>\n"
        "            <div className={styles.pairingHint}>\n"
        "              在本地终端粘贴回车，自动完成安装并连接\n"
        "            </div>\n"
        "          </>\n"
        "        ) : (\n"
        "          <button\n"
        '            type="button"\n'
        "            className={styles.pairingGetBtn}\n"
        "            onClick={() => void fetchInstallCmd(cmdOs)}\n"
        "          >\n"
        "            <Icon icon={TerminalIcon} size={12} />\n"
        "            获取一键安装命令\n"
        "          </button>\n"
        "        )}\n"
        "        <div className={styles.pairingHint} style={{ paddingBlockStart: 4 }}>\n"
        "          或输入配对码\n"
        "        </div>\n"
        "        <div className={styles.pairingInputRow}>\n"
        "          <input\n"
        '            className={styles.pairingInput}\n'
        '            placeholder="配对码"\n'
        "            value={pairCode}\n"
        "            onChange={(e) => setPairCode(e.target.value)}\n"
        "            onKeyDown={(e) => {\n"
        "              if (e.key === 'Enter') void handlePairSubmit();\n"
        "            }}\n"
        "          />\n"
        "          <button\n"
        '            type="button"\n'
        "            className={styles.pairingSubmit}\n"
        "            disabled={isPairing || !pairCode.trim()}\n"
        "            onClick={() => void handlePairSubmit()}\n"
        "          >\n"
        "            {isPairing ? '验证中' : '配对'}\n"
        "          </button>\n"
        "        </div>\n"
        "        {pairingStatus ? (\n"
        "          <div\n"
        "            className={cx(\n"
        "              styles.pairingStatus,\n"
        "              pairingStatus.ok ? styles.pairingStatusOk : styles.pairingStatusErr,\n"
        "            )}\n"
        "          >\n"
        "            {pairingStatus.msg}\n"
        "          </div>\n"
        "        ) : null}\n"
        "      </div>\n"
        "    </Flexbox>\n"
        "  );\n"
        "\n"
        "  const chip = ("
    )
    if jsx_anchor in text:
        text = text.replace(jsx_anchor, jsx_code, 1)
    return text


def _patch_types(ctx: PatchContext) -> None:
    rel = "packages/types/src/agent/agencyConfig.ts"
    t = ctx.read(rel)
    old = "export type DeviceExecutionTarget = 'auto' | 'device' | 'dsh' | 'local' | 'none' | 'sandbox';"
    new = "export type DeviceExecutionTarget = 'auto' | 'device' | 'local' | 'none' | 'sandbox';"
    if new in t:
        pass
    elif old in t:
        ctx.write(rel, t.replace(old, new, 1))


def _patch_icon(ctx: PatchContext, text: str) -> str:
    return text


def _patch_locales(ctx: PatchContext) -> None:
    pairs = (
        (
            "locales/zh-CN/chat.json",
            '"heteroAgent.executionTarget.local": "本地设备"',
            '"heteroAgent.executionTarget.local": "用电脑"',
        ),
        (
            "locales/zh-CN/chat.json",
            '"heteroAgent.executionTarget.localDesc": "在当前桌面端以本地进程运行"',
            '"heteroAgent.executionTarget.localDesc": "通过本机 sidecar 操作这台电脑"',
        ),
        (
            "locales/en-US/chat.json",
            '"heteroAgent.executionTarget.local": "Local device"',
            '"heteroAgent.executionTarget.local": "Use this computer"',
        ),
        (
            "locales/en-US/chat.json",
            '"heteroAgent.executionTarget.localDesc": "Run as a local process on this desktop app"',
            '"heteroAgent.executionTarget.localDesc": "Run on this machine through the local sidecar"',
        ),
        (
            "packages/locales/src/default/chat.ts",
            "'heteroAgent.executionTarget.local': 'Local device'",
            "'heteroAgent.executionTarget.local': 'Use this computer'",
        ),
        (
            "packages/locales/src/default/chat.ts",
            "'heteroAgent.executionTarget.localDesc': 'Run as a local process on this desktop app'",
            "'heteroAgent.executionTarget.localDesc': 'Run on this machine through the local sidecar'",
        ),
    )
    for rel, old, new in pairs:
        t = ctx.read(rel)
        if new in t:
            continue
        if old not in t:
            raise SystemExit(f"[execution_target] locale needle missing in {rel}")
        ctx.write(rel, t.replace(old, new, 1))
