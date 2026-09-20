"""Patch: execution environment picker — 用电脑 / 云沙箱 / 自动. No none, no download desktop."""

from __future__ import annotations

from deploy.lobehub.engine import PatchContext, PatchMeta

meta = PatchMeta(
    name="execution_target",
    description="Execution picker: use-computer instead of download desktop; drop none",
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
        "Honour stored local on web so the chip does not coerce to sandbox."
    ),
    verify_file="src/features/ChatInput/ControlBar/HeteroDeviceSwitcher.tsx",
    verify_marker="LCA: sidecar is use-computer",
)

_SWITCHER = "src/features/ChatInput/ControlBar/HeteroDeviceSwitcher.tsx"


def apply(ctx: PatchContext) -> bool:
    text = ctx.read(_SWITCHER)
    original = text
    text = _patch_switcher(text)
    changed = text != original
    if changed:
        ctx.write(_SWITCHER, text)
    changed = _patch_types(ctx) or changed
    changed = _patch_icon(ctx) or changed
    changed = _patch_locales(ctx) or changed
    return changed


def _patch_switcher(text: str) -> str:
    text = text.replace("import { DOWNLOAD_URL } from '@/const/url';\n", "")
    text = text.replace(
        "  ExternalLinkIcon,\n  InfoIcon,\n  MonitorDownIcon,\n  SettingsIcon,\n",
        "  InfoIcon,\n  SettingsIcon,\n",
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

    text = _patch_pairing_ui(text)

    return text


def _patch_pairing_ui(text: str) -> str:
    if "/* LCA: CONV-INSTALL-4 One-Liner Auto-Install */" in text:
        return text

    # If old M4 state code exists, strip it
    old_state = "  /* LCA: ADR-0246 M4 Device Code Pairing */\n"
    if old_state in text:
        start = text.index(old_state)
        end = text.find("  }, [pairCode, refreshDevices]);\n", start)
        if end > 0:
            text = text[:start] + text[end + len("  }, [pairCode, refreshDevices]);\n") :]

    # If old M4 JSX exists, strip it
    old_jsx = "      {/* LCA: Device Code Pairing card (ADR-0246 M4) */}\n"
    if old_jsx in text:
        start = text.index(old_jsx)
        end = text.find("    </Flexbox>\n  );\n\n  const chip = (", start)
        if end > 0:
            text = text[:start] + text[end:]

    # 1. mutate hook
    if "mutate: refreshDevices" not in text:
        text = text.replace(
            "  const { data: devices, isLoading } = useDeviceList();\n",
            "  const { data: devices, isLoading, mutate: refreshDevices } = useDeviceList();\n",
            1,
        )

    # 2. state & callback
    state_anchor = "  const selectExecutionTarget = useSelectExecutionTarget(agentId);\n"
    state_code = (
        "  /* LCA: CONV-INSTALL-4 One-Liner Auto-Install */\n"
        "  const [pairCode, setPairCode] = useState('');\n"
        "  const [pairingStatus, setPairStatus] = useState<{ ok?: boolean; msg?: string } | null>(null);\n"
        "  const [isPairing, setIsPairing] = useState(false);\n"
        "  const [installCmd, setInstallCmd] = useState<string>('');\n"
        "  const [cmdOs, setCmdOs] = useState<'windows' | 'bash'>('windows');\n"
        "  const [copied, setCopied] = useState(false);\n"
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
        "    } catch (e: any) {\n"
        "      console.error('Failed to get install command', e);\n"
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
        "        setPairStatus({ ok: true, msg: `已自动绑定本机: ${newlyJoined.label || newlyJoined.deviceId}` });\n"
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
        "        if (refreshDevices) void refreshDevices();\n"
        "      } else {\n"
        "        setPairStatus({ ok: false, msg: `配对失败: ${data.error || '无效配对码'}` });\n"
        "      }\n"
        "    } catch (e: any) {\n"
        "      setPairStatus({ ok: false, msg: `网络错误: ${e.message}` });\n"
        "    } finally {\n"
        "      setIsPairing(false);\n"
        "    }\n"
        "  }, [pairCode, refreshDevices, selectExecutionTarget]);\n"
    )
    if state_anchor in text:
        text = text.replace(state_anchor, state_anchor + state_code, 1)

    # 3. JSX card
    jsx_anchor = "    </Flexbox>\n  );\n\n  const chip = ("
    jsx_code = (
        "      {/* LCA: Device Code Pairing card (ADR-0246 M4) */}\n"
        "      <div style={{ padding: '8px 12px', borderTop: '1px solid rgba(128,128,128,0.2)', marginTop: 6 }}>\n"
        "        <div style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginBottom: 6, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>\n"
        "          <span style={{ fontWeight: 500 }}>一键接入本机 (免输码)</span>\n"
        "          <div style={{ display: 'flex', gap: 4 }}>\n"
        "            <button\n"
        '              type="button"\n'
        "              onClick={() => void fetchInstallCmd('windows')}\n"
        "              style={{ fontSize: 10, padding: '1px 5px', border: '1px solid rgba(128,128,128,0.3)', borderRadius: 3, background: cmdOs === 'windows' ? 'var(--color-primary, #1677ff)' : 'transparent', color: cmdOs === 'windows' ? '#fff' : 'inherit', cursor: 'pointer' }}\n"
        "            >\n"
        "              PowerShell\n"
        "            </button>\n"
        "            <button\n"
        '              type="button"\n'
        "              onClick={() => void fetchInstallCmd('bash')}\n"
        "              style={{ fontSize: 10, padding: '1px 5px', border: '1px solid rgba(128,128,128,0.3)', borderRadius: 3, background: cmdOs === 'bash' ? 'var(--color-primary, #1677ff)' : 'transparent', color: cmdOs === 'bash' ? '#fff' : 'inherit', cursor: 'pointer' }}\n"
        "            >\n"
        "              Bash\n"
        "            </button>\n"
        "          </div>\n"
        "        </div>\n"
        "        {installCmd ? (\n"
        "          <div style={{ marginBottom: 8 }}>\n"
        "            <div style={{ fontSize: 10, background: 'rgba(128,128,128,0.08)', padding: '6px 8px', borderRadius: 4, fontFamily: 'monospace', wordBreak: 'break-all', display: 'flex', alignItems: 'center', gap: 6 }}>\n"
        "              <span style={{ flex: 1, userSelect: 'all' }}>{installCmd}</span>\n"
        "              <button\n"
        '                type="button"\n'
        "                onClick={() => {\n"
        "                  navigator.clipboard.writeText(installCmd);\n"
        "                  setCopied(true);\n"
        "                  setTimeout(() => setCopied(false), 2000);\n"
        "                }}\n"
        "                style={{ fontSize: 10, padding: '2px 8px', background: 'var(--color-primary, #1677ff)', color: '#fff', border: 'none', borderRadius: 3, cursor: 'pointer' }}\n"
        "              >\n"
        "                {copied ? '已复制' : '复制'}\n"
        "              </button>\n"
        "            </div>\n"
        "            <div style={{ fontSize: 10, color: 'var(--color-text-secondary)', marginTop: 3 }}>\n"
        "              在本地终端粘贴回车，将自动完成安装建联并切换\n"
        "            </div>\n"
        "          </div>\n"
        "        ) : (\n"
        "          <button\n"
        '            type="button"\n'
        "            onClick={() => void fetchInstallCmd(cmdOs)}\n"
        "            style={{ width: '100%', fontSize: 11, padding: '5px 8px', marginBottom: 8, borderRadius: 4, border: '1px dashed rgba(128,128,128,0.3)', background: 'transparent', color: 'inherit', cursor: 'pointer' }}\n"
        "          >\n"
        "            + 获取本地一键安装启动命令\n"
        "          </button>\n"
        "        )}\n"
        "        <div style={{ fontSize: 11, color: 'var(--color-text-secondary)', marginBottom: 4 }}>\n"
        "          或输入已有配对码\n"
        "        </div>\n"
        "        <div style={{ display: 'flex', gap: 6 }}>\n"
        "          <input\n"
        '            placeholder="配对码 (如 ABCD-1234)"\n'
        "            value={pairCode}\n"
        "            onChange={(e) => setPairCode(e.target.value)}\n"
        "            onKeyDown={(e) => {\n"
        "              if (e.key === 'Enter') void handlePairSubmit();\n"
        "            }}\n"
        "            style={{\n"
        "              flex: 1,\n"
        "              height: 26,\n"
        "              padding: '0 8px',\n"
        "              fontSize: 12,\n"
        "              borderRadius: 4,\n"
        "              border: '1px solid rgba(128,128,128,0.2)',\n"
        "              background: 'transparent',\n"
        "              color: 'inherit',\n"
        "            }}\n"
        "          />\n"
        "          <button\n"
        '            type="button"\n'
        "            onClick={() => void handlePairSubmit()}\n"
        "            disabled={isPairing || !pairCode.trim()}\n"
        "            style={{\n"
        "              height: 26,\n"
        "              padding: '0 8px',\n"
        "              fontSize: 12,\n"
        "              borderRadius: 4,\n"
        "              cursor: isPairing || !pairCode.trim() ? 'not-allowed' : 'pointer',\n"
        "              background: 'var(--color-primary, #1677ff)',\n"
        "              color: '#fff',\n"
        "              border: 'none',\n"
        "            }}\n"
        "          >\n"
        "            {isPairing ? '验证中' : '配对'}\n"
        "          </button>\n"
        "        </div>\n"
        "        {pairingStatus ? (\n"
        "          <div style={{ fontSize: 11, marginTop: 4, color: pairingStatus.ok ? '#52c41a' : '#ff4d4f' }}>\n"
        "            {pairingStatus.msg}\n"
        "          </div>\n"
        "        ) : null}\n"
        "      </div>\n"
        "    </Flexbox>\n  );\n\n  const chip = ("
    )
    if jsx_anchor in text:
        text = text.replace(jsx_anchor, jsx_code, 1)

    return text


def _patch_types(ctx: PatchContext) -> bool:
    rel = "packages/types/src/agent/agencyConfig.ts"
    text = ctx.read(rel)
    old = "export type DeviceExecutionTarget = 'auto' | 'device' | 'dsh' | 'local' | 'none' | 'sandbox';"
    new = "export type DeviceExecutionTarget = 'auto' | 'device' | 'local' | 'none' | 'sandbox';"
    if new in text:
        return False
    if old not in text:
        raise SystemExit("[execution_target] DeviceExecutionTarget union not found")
    ctx.write(rel, text.replace(old, new, 1))
    return True


def _patch_icon(ctx: PatchContext) -> bool:
    rel = "src/features/ExecutionTargetPicker/index.tsx"
    text = ctx.read(rel)
    # No-op after ADR-0090 retired the DSH execution target.
    del rel, text
    return False


def _patch_locales(ctx: PatchContext) -> bool:
    changed = False
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
        text = ctx.read(rel)
        if new in text:
            continue
        if old not in text:
            raise SystemExit(f"[execution_target] locale needle missing in {rel}")
        ctx.write(rel, text.replace(old, new, 1))
        changed = True
    return changed
