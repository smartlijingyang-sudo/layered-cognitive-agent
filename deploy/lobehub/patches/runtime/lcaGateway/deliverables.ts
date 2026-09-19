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
  /** Record the artifact closure carried by ``agent_runtime_end``. */
  collectClosure: (closure: unknown) => void;
  /** Harvested deliverables, one per basename. */
  files: () => ArtifactFile[];
  /** Native message lists for the answer row; empty when nothing was produced. */
  lists: () => LcaDeliverableLists;
};

export function createLcaDeliverables(): LcaDeliverables {
  let files: ArtifactFile[] = [];

  return {
    collectClosure(closure: unknown) {
      const record = asRecord(closure);
      if (!record) return;
      const harvested = collectArtifactFiles(record.files);
      if (harvested.length === 0) return;
      files = latestDeliverables([...files, ...harvested]);
    },
    files: () => files,
    lists() {
      return { fileList: toFileList(files), imageList: toImageList(files) };
    },
  };
}
