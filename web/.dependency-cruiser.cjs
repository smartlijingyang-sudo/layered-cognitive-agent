/** @type {import('dependency-cruiser').IConfiguration} */
const coreNoShellFrom = "^src/(contracts|journal-log|projectors|transport|renderers|domain|api)/";

module.exports = {
  forbidden: [
    {
      name: "no-react-below-core",
      severity: "error",
      from: { path: "^src/(contracts|journal-log|projectors|transport|domain|api)/" },
      to: { path: "node_modules/(react|react-dom)" },
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
      from: { path: coreNoShellFrom },
      to: { path: "^src/shell/" },
    },
    {
      name: "domain-no-ui",
      severity: "error",
      from: { path: "^src/domain/" },
      to: { path: "^src/(renderers|components|shell)/" },
    },
    {
      name: "components-no-transport",
      severity: "error",
      from: { path: "^src/components/" },
      to: { path: "^src/transport/" },
    },
    {
      name: "api-no-components",
      severity: "error",
      from: { path: "^src/api/" },
      to: { path: "^src/components/" },
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
