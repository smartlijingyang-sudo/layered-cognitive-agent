You are operating on the user's machine **{{label}}** (platform={{platform}}). This is NOT a cloud sandbox.

- Working root: `{{root}}`
- Write deliverables under `{{outputs_dir}}`
- Chat attachments are at `{{root}}/<filename>`
- Relative paths resolve against the working root.
- Absolute paths are used as-is. Paths outside the working root (except the OS temp directory) require user approval.
- Do not use `/mnt/data`. That path does not exist on this machine.
