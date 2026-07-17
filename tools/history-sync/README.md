# AI History Sync Tool

One-shot sync of Claude Code and/or Codex history from local machine to NebulaShare server.

## Files

- `export_codex.py`: Export Codex history from `~/.codex` to a unified format.
- `sync_history.py`: Detect local Claude Code / Codex history, package and upload to NebulaShare.

## mac one-shot migration

```bash
python3 /Users/aw/vibeProjects/codex-exporter/sync_history.py \
  --server http://100.101.154.44:8080 \
  --hostname mbpm3
```

## Raspberry Pi one-shot migration

First copy the scripts from the server:

```bash
scp aw@100.101.154.44:/home/aw/vibeProjects/NebulaShare/tools/history-sync/sync_history.py .
scp aw@100.101.154.44:/home/aw/vibeProjects/NebulaShare/tools/history-sync/export_codex.py .
```

Then run:

```bash
python3 sync_history.py \
  --server http://100.101.154.44:8080 \
  --hostname raspberry-pi
```

## How it works

1. Looks for `~/.claude/history.jsonl` (Claude Code CLI)
2. Looks for `~/.codex` directory (Codex desktop app)
3. Exports everything into a temporary directory
4. Packages as a zip file
5. Uploads to `/api/claude-history/upload`

## Environment variables

- `NEBULA_SERVER`: NebulaShare server URL
- `NEBULA_HOSTNAME`: Device hostname identifier

Example:

```bash
export NEBULA_SERVER=http://100.101.154.44:8080
export NEBULA_HOSTNAME=mbpm3
python3 sync_history.py
```
