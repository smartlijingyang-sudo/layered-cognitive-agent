/** Regression test for LcaRunDriver pickArgs ordering.

The Inspector header chip (ToolTitle) renders
``Object.entries(args).slice(0, MAX_PARAMS)``; chip text is whatever the
*first* args key is.  For tools with both a short label and a long body
(``code``, ``command``, ``content`` ...), we want the chip to show the
short label — pushing the long-text keys to the tail of the args dict
preserves the JSON.stringify iteration order seen by the renderer.

LobeHub's ``ExecuteCodeRender`` etc. still read ``args.code`` directly,
so reordering is safe (lookup is key-based, not positional).
*/

import { describe, expect, it } from 'vitest';

import { __test__ } from './LcaRunDriver';

const { pickArgs } = __test__;

describe('pickArgs — Inspector chip keeps long-text keys out of the first slot', () => {
  it('executeCode: code / language / description — chip should show description, not code', () => {
    const args = pickArgs({
      code: 'import openpyxl\n\nwb = openpyxl.load_workbook("/mnt/data/x.xlsx")',
      description: 'Read Excel file structure and content',
      language: 'python',
    });
    const keys = Object.keys(args);
    expect(keys).toEqual(['description', 'language', 'code']);
    // The chip reads entries[0].value; make sure it is the short label.
    const [first] = Object.entries(args);
    expect(first[0]).toBe('description');
    expect(first[1]).toBe('Read Excel file structure and content');
  });

  it('runCommand: command present — chip should show description first', () => {
    const args = pickArgs({
      description: 'Inspect git log',
      command: 'git log --oneline -20 | head',
    });
    expect(Object.keys(args)).toEqual(['description', 'command']);
  });

  it('readFile: path / content — chip should show path, not content', () => {
    const args = pickArgs({
      path: '/mnt/data/2025年度工作计划表.xlsx',
      content: '<big blob>',
    });
    expect(Object.keys(args)).toEqual(['path', 'content']);
  });

  it('preserves every whitelisted key, drops unknown ones', () => {
    const args = pickArgs({
      path: '/x',
      code: 'print(1)',
      // unknown keys must be dropped (ARG_KEYS whitelist)
      bogus: 'ignored',
      another_bogus: 42,
    } as Record<string, unknown>);
    expect(args).toEqual({ path: '/x', code: 'print(1)' });
    expect(Object.keys(args)).toEqual(['path', 'code']);
  });

  it('empty / undefined state returns empty dict', () => {
    expect(pickArgs(undefined)).toEqual({});
    expect(pickArgs({})).toEqual({});
  });

  it('omits whitelisted keys with undefined value', () => {
    const args = pickArgs({
      path: '/x',
      code: undefined,
    });
    expect(args).toEqual({ path: '/x' });
  });
});
