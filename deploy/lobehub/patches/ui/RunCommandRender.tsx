'use client';

import type { RunCommandState } from '@lobechat/tool-runtime';
import type { BuiltinRenderProps } from '@lobechat/types';
import { ActionIcon, Block, FileTypeIcon, Flexbox, Highlighter, Text } from '@lobehub/ui';
import { Download } from 'lucide-react';
import { createStaticStyles } from 'antd-style';
import { memo } from 'react';

import { getRunCommandDisplayCommand } from '../../utils/runCommand';
import AnsiOutput from './AnsiOutput';


interface GeneratedFilePart {
  attachmentId?: string;
  mimeType?: string;
  mime_type?: string;
  name?: string;
  previewable?: boolean;
  size?: number;
  sizeBytes?: number;
  url?: string;
}

const formatBytes = (n?: number) => {
  if (!n || !Number.isFinite(n)) return '';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
};

const LcaGeneratedFileCard = memo<{ file: GeneratedFilePart }>(({ file }) => {
  const name = file.name || 'file';
  const href = file.url;
  const mime = file.mimeType || file.mime_type || '';
  const size = file.sizeBytes ?? file.size;
  const ext = name.split('.').pop()?.toUpperCase() || 'FILE';
  if (!href) return null;

  const open = () => {
    window.open(href, '_blank', 'noopener,noreferrer');
  };

  const download = (event: { stopPropagation: () => void }) => {
    event.stopPropagation();
    const link = document.createElement('a');
    link.href = href;
    link.download = name;
    link.rel = 'noopener noreferrer';
    document.body.append(link);
    link.click();
    link.remove();
  };

  return (
    <Block
      clickable
      horizontal
      align={'center'}
      gap={12}
      paddingBlock={8}
      paddingInline={'12px 16px'}
      variant={'outlined'}
      onClick={open}
    >
      <FileTypeIcon filetype={ext} size={32} type={'file'} />
      <Flexbox flex={1} style={{ minWidth: 0, overflow: 'hidden' }}>
        <Text ellipsis>{name}</Text>
        <Text fontSize={12} type={'secondary'}>
          {[mime || ext, formatBytes(typeof size === 'number' ? size : undefined)]
            .filter(Boolean)
            .join(' · ')}
        </Text>
      </Flexbox>
      <ActionIcon icon={Download} size={'small'} title="Download" onClick={download} />
    </Block>
  );
});

LcaGeneratedFileCard.displayName = 'LcaGeneratedFileCard';

const GeneratedFilesStrip = memo<{ files?: GeneratedFilePart[] }>(({ files }) => {
  if (!files?.length) return null;
  return (
    <Flexbox gap={8}>
      {files.map((file) => (
        <LcaGeneratedFileCard file={file} key={`${file.name || 'file'}-${file.url || ''}`} />
      ))}
    </Flexbox>
  );
});

GeneratedFilesStrip.displayName = 'GeneratedFilesStrip';

const styles = createStaticStyles(({ css }) => ({
  container: css`
    overflow: hidden;
    padding-inline: 8px 0;
  `,
}));

interface RunCommandArgs {
  background?: boolean;
  command: string;
  description?: string;
  timeout?: number;
}

const RunCommand = memo<BuiltinRenderProps<RunCommandArgs, RunCommandState>>(
  ({ args, content, pluginState }) => {
    const output = pluginState?.stdout || pluginState?.output || content;
    const stderr = pluginState?.stderr;
    const command = getRunCommandDisplayCommand(args?.command);

    return (
      <Flexbox className={styles.container} gap={8}>
        <Block gap={8} padding={8} variant={'outlined'}>
          <Highlighter
            wrap
            language={'sh'}
            showLanguage={false}
            style={{ maxHeight: 200, overflow: 'auto', paddingInline: 8 }}
            variant={'borderless'}
          >
            {command}
          </Highlighter>
          {output && <AnsiOutput text={output} />}
          {stderr?.trim() && <AnsiOutput text={stderr} />}
          <GeneratedFilesStrip files={(pluginState as { files?: GeneratedFilePart[] })?.files} />
        </Block>
      </Flexbox>
    );
  },
);

RunCommand.displayName = 'RunCommand';

export default RunCommand;
