#!/usr/bin/env node
import { Command } from 'commander';

import { connect, status, stop } from './commands/connect.js';

const program = new Command();
program.name('lca').description('LCA device CLI');

program
  .command('connect')
  .description('Connect this machine to an LCA gateway')
  .option('--gateway <url>', 'Gateway HTTP/WS base URL', 'http://127.0.0.1:8765')
  .option('--token <token>', 'serviceToken / JWT')
  .option('--token-type <type>', 'serviceToken | jwt | apiKey', 'serviceToken')
  .option('--workspace <path>', 'Workspace root', process.env['HOME'] || '/home/sandbox-user')
  .option('--daemon', 'Detach and write PID to ~/.lca/connect.pid')
  .action(async (opts) => {
    await connect(opts);
  });

program.command('stop').description('Stop a daemonized connect').action(async () => {
  await stop();
});

program.command('status').description('Show connect daemon status').action(async () => {
  await status();
});

program.parseAsync(process.argv);
