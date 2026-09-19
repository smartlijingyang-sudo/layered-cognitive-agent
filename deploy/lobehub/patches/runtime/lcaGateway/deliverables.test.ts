// Unit test for the gateway deliverable fold.
//
// Copied into
// `lobehub-ui/src/store/chat/agents/transports/lcaGateway/deliverables.test.ts`
// by `lca_runtime_agent_gateway`; run from the lobehub-ui root:
//   bun vitest run src/store/chat/agents/transports/lcaGateway/deliverables.test.ts

import { describe, expect, it } from 'vitest';

import { appendDeliverableClosure } from '../lcaArtifacts';
import { createLcaDeliverables } from './deliverables';

const pdfPart = {
  attachmentId: 'file_1',
  mimeType: 'application/pdf',
  name: 'report.pdf',
  previewable: true,
  sizeBytes: 17_777,
  url: '/files/file_1',
};

describe('createLcaDeliverables', () => {
  it('projects the terminal artifact closure onto the answer row file list', () => {
    const deliverables = createLcaDeliverables();

    deliverables.collectClosure({ text: '已生成以下文件：', files: [pdfPart] });

    expect(deliverables.lists()).toEqual({
      fileList: [
        {
          fileType: 'application/pdf',
          id: 'file_1',
          name: 'report.pdf',
          size: 17_777,
          url: '/files/file_1',
        },
      ],
      imageList: [],
    });
  });

  it('routes images to imageList and keeps them out of fileList', () => {
    const deliverables = createLcaDeliverables();

    deliverables.collectClosure({
      files: [
        { mimeType: 'image/png', name: 'chart.png', sizeBytes: 10, url: '/files/file_2' },
        pdfPart,
      ],
    });

    const { fileList, imageList } = deliverables.lists();
    expect(imageList).toEqual([{ alt: 'chart.png', id: '/files/file_2', url: '/files/file_2' }]);
    expect(fileList.map((file) => file.name)).toEqual(['report.pdf']);
  });

  it('keeps the latest harvest for one basename', () => {
    const deliverables = createLcaDeliverables();

    deliverables.collectClosure({ files: [pdfPart] });
    deliverables.collectClosure({
      files: [{ ...pdfPart, attachmentId: 'file_9', url: '/files/file_9' }],
    });

    expect(deliverables.lists().fileList).toEqual([
      {
        fileType: 'application/pdf',
        id: 'file_9',
        name: 'report.pdf',
        size: 17_777,
        url: '/files/file_9',
      },
    ]);
  });

  it('ignores closures that carry no file parts', () => {
    const deliverables = createLcaDeliverables();

    deliverables.collectClosure(undefined);
    deliverables.collectClosure({ text: 'no files here' });
    deliverables.collectClosure({ files: [] });
    deliverables.collectClosure({ files: [{ name: '', url: '' }] });

    expect(deliverables.lists()).toEqual({ fileList: [], imageList: [] });
  });

  it('does not depend on per-tool state.files', () => {
    // exportFile's projected state historically carries no ``files`` field.
    // The closure comes from the backend ledger instead, so a tool_end result
    // with no file parts must not feed the answer row.
    const deliverables = createLcaDeliverables();

    deliverables.collectClosure({ files: [pdfPart] });
    // A tool_end-shaped object with empty state.files is NOT a closure source.
    expect(deliverables.lists().fileList.map((file) => file.url)).toEqual(['/files/file_1']);
  });

  it('exposes the harvested deliverables for the answer text', () => {
    const deliverables = createLcaDeliverables();

    deliverables.collectClosure({ files: [pdfPart] });

    expect(deliverables.files().map((file) => file.name)).toEqual(['report.pdf']);
  });
});

describe('appendDeliverableClosure', () => {
  const files = [
    { mimeType: 'application/pdf', name: 'report.pdf', previewable: true, url: '/files/file_1' },
  ];

  it('appends the download list to the answer', () => {
    expect(appendDeliverableClosure('已生成 report.pdf。', files)).toBe(
      '已生成 report.pdf。\n\n已生成以下文件：\n- [📥 report.pdf](/files/file_1)',
    );
  });

  it('is the whole answer when the model said nothing', () => {
    expect(appendDeliverableClosure('  ', files)).toBe(
      '已生成以下文件：\n- [📥 report.pdf](/files/file_1)',
    );
  });

  it('leaves the answer alone when the link is already there', () => {
    const text = '已生成以下文件：\n- [📥 report.pdf](/files/file_1)';

    expect(appendDeliverableClosure(text, files)).toBe(text);
  });

  it('leaves the answer alone when nothing was harvested', () => {
    expect(appendDeliverableClosure('done', [])).toBe('done');
  });
});
