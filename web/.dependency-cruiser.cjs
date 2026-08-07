/** @type {import('dependency-cruiser').IConfiguration} */
module.exports = {
  forbidden: [
    {
      name: "no-react-below-renderers",
      severity: "error",
      from: {
        path: "^src/(contracts|journal-log|projectors|transport)/",
      },
      to: {
        path: "node_modules/(react|react-dom)",
      },
    },
    {
      name: "projectors-no-renderers",
      severity: "error",
      from: { path: "^src/projectors/" },
      to: { path: "^src/renderers/" },
    },
    {
      name: "core-no-shell",
      severity: "error",
      from: {
        path: "^src/(contracts|journal-log|projectors|transport|renderers)/",
      },
      to: { path: "^src/shell/" },
    },
  ],
  options: {
    doNotFollow: { path: "node_modules" },
    tsPreCompilationDeps: true,
    enhancedResolveOptions: {
      exportsFields: ["exports"],
      conditionNames: ["import", "require", "node", "default"],
    },
  },
};
