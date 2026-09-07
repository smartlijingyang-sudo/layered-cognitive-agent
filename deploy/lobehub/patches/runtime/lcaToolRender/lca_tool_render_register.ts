/** Register LCA tool-render helpers (native LobeHub renderers remain primary). */

let registered = false;

export function ensureLcaToolRenderRegistered(): void {
  if (registered) return;
  registered = true;
  // Builtin LobeHub renderers resolve via identifier/apiName; projection.ts
  // supplies pluginState. No additional renderer registration required in P1.
}
