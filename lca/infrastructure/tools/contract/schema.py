"""Common FieldSpec table for tool contracts."""

from __future__ import annotations

from lca.infrastructure.tools.contract.render import FieldSpec

COMMON: dict[str, FieldSpec] = {
    # Execution environment
    "command": FieldSpec("command", "command", "string", "argument"),
    "language": FieldSpec("language", "language", "string", "argument"),
    "code": FieldSpec("code", "code", "string", "argument"),
    "description": FieldSpec("description", "description", "string", "argument"),
    "execution_env": FieldSpec("execution_env", "executionEnv", "string", "observation"),
    # Skill identity
    "skill_id": FieldSpec("skill_id", "id", "string", "argument"),
    # File paths
    "path": FieldSpec("path", "path", "string", "argument"),
    "directory_path": FieldSpec("directory_path", "directoryPath", "string", "argument"),
    "file_path": FieldSpec("file_path", "filePath", "string", "argument"),
    "filename": FieldSpec("filename", "filename", "string", "argument"),
    # Edit operations
    "new_string": FieldSpec("new_string", "newString", "string", "argument"),
    "old_string": FieldSpec("old_string", "oldString", "string", "argument"),
    # Search
    "query": FieldSpec("query", "query", "string", "argument"),
    "pattern": FieldSpec("pattern", "pattern", "string", "argument"),
    "glob": FieldSpec("glob", "glob", "string", "argument"),
    "scope": FieldSpec("scope", "scope", "string", "argument"),
    "search": FieldSpec("search", "search", "string", "argument"),
    "replace": FieldSpec("replace", "replace", "string", "argument"),
    # Execution control
    "timeout": FieldSpec("timeout", "timeout", "int", "argument"),
    "timeout_s": FieldSpec("timeout_s", "timeout", "int", "argument"),
    "background": FieldSpec("background", "background", "bool", "argument"),
    "run_in_background": FieldSpec("run_in_background", "runInBackground", "bool", "argument"),
    # Metadata
    "name": FieldSpec("name", "name", "string", "observation"),
    "title": FieldSpec("title", "title", "string", "observation"),
    "has_resources": FieldSpec("has_resources", "hasResources", "bool", "observation"),
    "content": FieldSpec("content", "content", "string", "observation"),
    "size": FieldSpec("size", "size", "int", "observation"),
    "file_type": FieldSpec("file_type", "fileType", "string", "observation"),
    "encoding": FieldSpec("encoding", "encoding", "string", "observation"),
    # Resource references
    "identifier": FieldSpec("identifier", "identifier", "string", "argument"),
    "url": FieldSpec("url", "url", "string", "observation"),
    "kind": FieldSpec("kind", "kind", "string", "observation"),
    "version": FieldSpec("version", "version", "string", "argument"),
    "page": FieldSpec("page", "page", "int", "argument"),
    "page_size": FieldSpec("page_size", "pageSize", "int", "argument"),
    # Script execution
    "script": FieldSpec("script", "script", "string", "argument"),
    "skill_name": FieldSpec("skill_name", "skillName", "string", "argument"),
    "reference": FieldSpec("reference", "reference", "string", "argument"),
    "args": FieldSpec("args", "args", "string", "argument"),
    # Sandbox output
    "stdout": FieldSpec("stdout", "stdout", "string", "observation"),
    "stderr": FieldSpec("stderr", "stderr", "string", "observation"),
    "files": FieldSpec("files", "files", "json", "observation"),
    "exit_code": FieldSpec("exit_code", "exitCode", "int", "observation"),
    "error_summary": FieldSpec("error_summary", "errorSummary", "string", "observation"),
    "error_kind": FieldSpec("error_kind", "errorKind", "string", "observation"),
    "partial": FieldSpec("partial", "partial", "bool", "observation", required=False),
    # File export
    "mounted_files": FieldSpec("mounted_files", "mountedFiles", "json", "observation"),
    # Sandbox / computer extra args
    "create_directories": FieldSpec(
        "create_directories", "createDirectories", "bool", "argument", required=False
    ),
    "replace_all": FieldSpec("replace_all", "all", "bool", "argument", required=False),
    "directory": FieldSpec("directory", "directory", "string", "argument", required=False),
    "keyword": FieldSpec("keyword", "keyword", "string", "argument", required=False),
    "command_id": FieldSpec("command_id", "commandId", "string", "argument"),
    "file_pattern": FieldSpec("file_pattern", "filePattern", "string", "argument", required=False),
    "recursive": FieldSpec("recursive", "recursive", "bool", "argument", required=False),
    "operations": FieldSpec("operations", "operations", "json", "argument", required=False),
    "content_arg": FieldSpec("content", "content", "string", "argument"),
    "mount_manifest": FieldSpec(
        "mount_manifest", "mountManifest", "json", "observation", required=False
    ),
    # Web search / user interaction
    "topic": FieldSpec("topic", "topic", "string", "argument", required=False),
    "time_range": FieldSpec("time_range", "timeRange", "string", "argument", required=False),
    "questions": FieldSpec("questions", "questions", "json", "argument"),
    "total": FieldSpec("total", "total", "int", "observation"),
}
