/** Harvested sandbox files on the wire → download list on the final answer.
 *
 * `tool_end.result.state.files` carries the FileStore parts the backend
 * harvested from `outputs/` (name / url / mimeType / attachmentId). The
 * gateway stream has no answer-level artifact fact, so the transport folds
 * them here and hands the final assistant row a native `fileList` /
 * `imageList`.
 */

import {
  type ArtifactFile,
  collectArtifactFiles,
  type FileRow,
  type ImageRow,
  latestDeliverables,
  toFileList,
  toImageList,
} from '../lcaArtifacts';

const asRecord = (value: unknown): Record<string, unknown> | undefined =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined;

export type LcaDeliverableLists = { fileList: FileRow[]; imageList: ImageRow[] };

export type LcaDeliverables = {
  /** Record the file parts of one `tool_end` result. Later harvests win. */
  collect: (result: unknown) => void;
  /** Harvested deliverables, one per basename. */
  files: () => ArtifactFile[];
  /** Native message lists for the answer row; empty when nothing was produced. */
  lists: () => LcaDeliverableLists;
};

export function createLcaDeliverables(): LcaDeliverables {
  let files: ArtifactFile[] = [];

  return {
    collect(result: unknown) {
      const record = asRecord(result);
      if (!record) return;
      const state = asRecord(record.state);
      const harvested = collectArtifactFiles(record.files, state?.files);
      if (harvested.length === 0) return;
      files = latestDeliverables([...files, ...harvested]);
    },
    files: () => files,
    lists() {
      return { fileList: toFileList(files), imageList: toImageList(files) };
    },
  };
}
