# Codex Tool Checklist

This project does not currently require extra Codex plugins or MCP tools for
the core podcast bot pipeline.

## Current Codex Capabilities

Codex already has enough built-in or enabled tools for the current milestones:

- Read and edit files inside this project workspace.
- Run local Python commands and tests.
- Search the web when current information is needed.
- Use the Browser plugin for local web testing if a frontend is added.
- Use document, spreadsheet, and presentation plugins if those file types are
  needed later.

## Recommended For This Project

For now, do not install the Claude Code MCP tools from the course file. They are
for Claude Code, not Codex.

Focus on the podcast bot milestones:

1. Minimal Discord bot with `/ping`.
2. RSS parsing.
3. SQLite episode storage.
4. Audio download.
5. Local transcription.
6. Obsidian Markdown export.
7. Episode summaries and searchable indexes.

## Optional Later

Only consider extra tooling if the project actually needs it:

- External filesystem access: only if the Obsidian vault is outside this
  workspace and Codex cannot access the target path.
- Browser automation: only if a web UI or login-based web workflow is added.
- Firecrawl-like web extraction: only if web articles become a data source.
- Google Workspace access: only if the workflow needs Gmail, Calendar, Drive,
  Sheets, Docs, or Slides.

## Reminder

Do not grant broad filesystem or account access just because a course lists it.
Install the smallest tool that solves the current project need.
