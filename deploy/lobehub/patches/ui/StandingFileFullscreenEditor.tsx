'use client';

import { Alert, Button, Flex, Modal, Spin, Tag, Tooltip, Typography, message } from 'antd';
import { createStaticStyles } from 'antd-style';
import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';

const { Text, Title } = Typography;

export interface StandingFileFullscreenEditorProps {
  /** 编辑器是否展开 */
  open: boolean;
  /** 关闭模态窗回调 */
  onClose: () => void;
  /** 助理唯一标识 */
  assistantId?: string;
  /** 助理名称 */
  assistantName?: string;
  /** 当前编辑文件名 (如 IDENTITY.md) */
  filename?: string;
  /** 磁盘真实路径 */
  filePath?: string;
  /** 初始预期 Hash */
  initialHash?: string;
  /** 保存成功后的回调 */
  onSaveSuccess?: (filename: string, newContent: string, newHash: string) => void;
}

const styles = createStaticStyles(({ css, cssVar }) => {
  return {
    modalContent: css`
      .ant-modal-content {
        padding: 0 !important;
        border-radius: 16px;
        overflow: hidden;
        background: ${cssVar.colorBgElevated};
        box-shadow: 0 12px 48px rgba(0, 0, 0, 0.2);
      }
      .ant-modal-header {
        margin: 0 !important;
        padding: 16px 24px !important;
        border-bottom: 1px solid ${cssVar.colorBorderSecondary};
        background: ${cssVar.colorBgElevated};
      }
      .ant-modal-body {
        padding: 0 !important;
      }
    `,
    headerWrapper: css`
      display: flex;
      align-items: center;
      justify-content: space-between;
      width: 100%;
    `,
    titleGroup: css`
      display: flex;
      align-items: center;
      gap: 10px;
    `,
    filenameTitle: css`
      font-weight: 700;
      font-size: 16px;
      color: ${cssVar.colorText};
      display: flex;
      align-items: center;
      gap: 8px;
    `,
    editorLayout: css`
      display: flex;
      height: 75vh;
      min-height: 520px;
      position: relative;
      background: ${cssVar.colorBgContainer};
    `,
    gutterCol: css`
      width: 48px;
      padding: 16px 0;
      background: ${cssVar.colorFillQuaternary};
      border-right: 1px solid ${cssVar.colorBorderSecondary};
      user-select: none;
      text-align: right;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 13px;
      line-height: 22px;
      color: ${cssVar.colorTextQuaternary};
      overflow: hidden;
    `,
    gutterLine: css`
      padding-right: 10px;
    `,
    textareaWrapper: css`
      flex: 1;
      position: relative;
      display: flex;
      height: 100%;
    `,
    editorTextarea: css`
      width: 100%;
      height: 100%;
      padding: 16px;
      border: none;
      outline: none;
      resize: none;
      background: transparent;
      color: ${cssVar.colorText};
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 13px;
      line-height: 22px;
      tab-size: 2;
      white-space: pre;
      overflow-wrap: normal;
      overflow-x: auto;
      overflow-y: auto;

      &:focus {
        outline: none;
      }
    `,
    footerBar: css`
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 10px 24px;
      border-top: 1px solid ${cssVar.colorBorderSecondary};
      background: ${cssVar.colorBgElevated};
      font-size: 12px;
      color: ${cssVar.colorTextSecondary};
    `,
    conflictPanel: css`
      padding: 16px 24px;
      background: #fff1f0;
      border-bottom: 1px solid #ffa39e;
    `,
  };
});

/**
 * 全屏沉浸式 Markdown 编辑器模态窗 (Standing File Fullscreen Editor)
 *
 * 遵循文件即唯一真值源（File as SSOT）架构：
 * 1. Monospace 等宽代码字体与行号（lineNumbers）渲染；
 * 2. 快捷键 Ctrl+S / Cmd+S 触发静默保存与自动提示；
 * 3. 严格校验 expected_hash 乐观并发锁，409 冲突时展示 Diff 并支持回填；
 * 4. 保存成功直接生效，无需重启 LCA 运行时。
 */
export const StandingFileFullscreenEditor = memo<StandingFileFullscreenEditorProps>(
  ({
    open,
    onClose,
    assistantId,
    assistantName = '架构小助',
    filename = 'SOUL.md',
    filePath,
    initialHash,
    onSaveSuccess,
  }) => {
    const [content, setContent] = useState('');
    const [originalContent, setOriginalContent] = useState('');
    const [expectedHash, setExpectedHash] = useState(initialHash || '');
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);
    const [conflictData, setConflictData] = useState<{
      current_hash: string;
      current_content: string;
    } | null>(null);

    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const gutterRef = useRef<HTMLDivElement>(null);

    // 1. 打开时从后端拉取该 Standing File 的最新磁盘真值
    const loadFileContent = useCallback(async () => {
      if (!assistantId || !filename) return;
      setLoading(true);
      setConflictData(null);
      try {
        const token = process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local';
        const url = `/lca-api/v1/assistants/${assistantId}/standing-files/${filename}`;
        const res = await fetch(url, {
          headers: {
            Authorization: `Bearer ${token}`,
            'x-lca-token': token,
          },
        });
        const contentType = res.headers.get('content-type') || '';
        if (!res.ok) {
          if (contentType.includes('application/json')) {
            const errData = await res.json().catch(() => null);
            throw new Error(errData?.error?.detail || `加载文件失败 (HTTP ${res.status})`);
          }
          throw new Error(`加载文件失败 (HTTP ${res.status})`);
        }
        if (!contentType.includes('application/json')) {
          throw new Error(`接口返回非 JSON 响应 (HTTP ${res.status})`);
        }
        const data = await res.json();
        setContent(data.content || '');
        setOriginalContent(data.content || '');
        setExpectedHash(data.content_hash || '');
      } catch (err: any) {
        message.error(err.message || '加载文件失败');
      } finally {
        setLoading(false);
      }
    }, [assistantId, filename]);

    useEffect(() => {
      if (open && assistantId && filename) {
        loadFileContent();
      }
    }, [open, assistantId, filename, loadFileContent]);

    const isDirty = useMemo(() => content !== originalContent, [content, originalContent]);
    const lines = useMemo(() => content.split('\n'), [content]);

    // 2. 滚动同步 (textarea 与 line-number gutter)
    const handleScroll = useCallback(() => {
      if (textareaRef.current && gutterRef.current) {
        gutterRef.current.scrollTop = textareaRef.current.scrollTop;
      }
    }, []);

    // 3. 乐观锁保存 (携带 expected_hash)
    const handleSave = useCallback(async () => {
      if (!assistantId || !filename || saving) return;
      setSaving(true);
      setConflictData(null);
      try {
        const token = process.env.NEXT_PUBLIC_LCA_TOKEN || 'lca-local';
        const url = `/lca-api/v1/assistants/${assistantId}/standing-files/${filename}`;
        const payload = {
          content,
          expected_hash: expectedHash || undefined,
          actor: 'user_ui',
        };

        const res = await fetch(url, {
          method: 'PUT',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${token}`,
            'x-lca-token': token,
          },
          body: JSON.stringify(payload),
        });

        const contentType = res.headers.get('content-type') || '';

        if (res.status === 409) {
          // 409 Conflict: 乐观锁并发冲突
          const errData = contentType.includes('application/json')
            ? await res.json().catch(() => null)
            : null;
          setConflictData({
            current_hash: errData?.error?.current_hash || '',
            current_content: errData?.error?.current_content || '',
          });
          message.warning('检测到并发修改冲突！磁盘真值已被更新，请核对后再提交。');
          return;
        }

        if (!res.ok) {
          if (contentType.includes('application/json')) {
            const errData = await res.json().catch(() => null);
            throw new Error(errData?.error?.detail || `保存失败 (HTTP ${res.status})`);
          }
          throw new Error(`保存失败 (HTTP ${res.status})`);
        }

        if (!contentType.includes('application/json')) {
          throw new Error(`接口返回非 JSON 响应 (HTTP ${res.status})`);
        }

        const data = await res.json();
        setOriginalContent(content);
        setExpectedHash(data.new_hash);
        message.success(`${filename} 已成功写盘，下轮对话实时注入生效 🎉`);
        onSaveSuccess?.(filename, content, data.new_hash);
      } catch (err: any) {
        message.error(err.message || '保存失败');
      } finally {
        setSaving(false);
      }
    }, [assistantId, filename, content, expectedHash, saving, onSaveSuccess]);

    // 4. 全局快捷键 Ctrl+S / Cmd+S 拦截与触发
    useEffect(() => {
      if (!open) return;
      const onKeyDown = (e: KeyboardEvent) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 's') {
          e.preventDefault();
          handleSave();
        }
      };
      window.addEventListener('keydown', onKeyDown);
      return () => window.removeEventListener('keydown', onKeyDown);
    }, [open, handleSave]);

    return (
      <Modal
        open={open}
        onCancel={onClose}
        width="88vw"
        style={{ top: 28, maxWidth: 1200 }}
        className={styles.modalContent}
        footer={null}
        destroyOnClose
        title={
          <div className={styles.headerWrapper}>
            <div className={styles.titleGroup}>
              <span className={styles.filenameTitle}>
                <span>📄</span>
                <span>{filename}</span>
                {isDirty ? (
                  <Tag color="orange">未保存变更</Tag>
                ) : (
                  <Tag color="green">已同步磁盘</Tag>
                )}
              </span>
              <Text type="secondary" style={{ fontSize: 12 }}>
                {filePath || `~/.lca/assistants/${assistantId}/${filename}`}
              </Text>
            </div>

            <Flex align="center" gap={12}>
              <Tooltip title="使用 Ctrl+S 或 Cmd+S 快捷保存">
                <Tag style={{ cursor: 'help' }}>快捷键: Ctrl+S / Cmd+S</Tag>
              </Tooltip>
              <Button onClick={onClose} size="middle">
                关闭
              </Button>
              <Button
                type="primary"
                onClick={handleSave}
                loading={saving}
                disabled={loading || !isDirty}
                size="middle"
              >
                保存并写盘
              </Button>
            </Flex>
          </div>
        }
      >
        {/* 并发冲突警告横幅 */}
        {conflictData && (
          <div className={styles.conflictPanel}>
            <Alert
              type="error"
              showIcon
              message="乐观锁并发冲突 (409 Conflict)"
              description={
                <div>
                  <Paragraph style={{ margin: '4px 0 8px 0' }}>
                    文件已被其他进程（如 Agent 认知工具或后台反思任务）修改。最新版本哈希：
                    <code>{conflictData.current_hash.slice(0, 16)}...</code>
                  </Paragraph>
                  <Flex gap={8}>
                    <Button
                      size="small"
                      danger
                      onClick={() => {
                        setContent(conflictData.current_content);
                        setOriginalContent(conflictData.current_content);
                        setExpectedHash(conflictData.current_hash);
                        setConflictData(null);
                        message.info('已拉取最新磁盘真值内容');
                      }}
                    >
                      加载最新磁盘内容覆盖
                    </Button>
                    <Button
                      size="small"
                      onClick={() => {
                        setExpectedHash(conflictData.current_hash);
                        setConflictData(null);
                        message.warning('已更新版本锁，再次点击保存将覆盖磁盘');
                      }}
                    >
                      保留当前输入并强行覆盖
                    </Button>
                  </Flex>
                </div>
              }
            />
          </div>
        )}

        {/* 编辑器核心区域 */}
        {loading ? (
          <Flex justify="center" align="center" style={{ height: '70vh' }}>
            <Spin tip="正在从磁盘读取最新文件真值..." />
          </Flex>
        ) : (
          <div className={styles.editorLayout}>
            {/* 行号栏 */}
            <div ref={gutterRef} className={styles.gutterCol}>
              {lines.map((_, idx) => (
                <div key={idx} className={styles.gutterLine}>
                  {idx + 1}
                </div>
              ))}
            </div>

            {/* 代码文本域 */}
            <div className={styles.textareaWrapper}>
              <textarea
                ref={textareaRef}
                className={styles.editorTextarea}
                value={content}
                onChange={(e) => setContent(e.target.value)}
                onScroll={handleScroll}
                spellCheck={false}
                placeholder="在此输入 Markdown 内容..."
              />
            </div>
          </div>
        )}

        {/* 底部状态信息栏 */}
        <div className={styles.footerBar}>
          <div>
            <span>
              {lines.length} 行 · {content.length} 字符
            </span>
            {expectedHash && (
              <span style={{ marginLeft: 16, opacity: 0.7 }}>
                Hash: {expectedHash.slice(0, 20)}...
              </span>
            )}
          </div>
          <div>
            <span>💡 修改后直接原子写盘，下轮对话实时注入生效，无需重启</span>
          </div>
        </div>
      </Modal>
    );
  },
);

StandingFileFullscreenEditor.displayName = 'StandingFileFullscreenEditor';

export default StandingFileFullscreenEditor;
