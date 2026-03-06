# CLAUDE.md

This file provides guidance to AI assistants (Claude Code and similar tools) working in this repository.

## Repository Overview

**Repository**: SONOS-CR2002S2
**Remote**: handyandy87/SONOS-CR2002S2
**Status**: Newly initialized — no source files have been committed yet.

This repository is in its initial state. When source code is added, update this file to reflect the actual project structure, tooling, and conventions.

---

## Git Workflow

### Branch Naming
- Feature branches: `feature/<short-description>`
- Bug fixes: `fix/<short-description>`
- Documentation: `docs/<short-description>`
- AI/Claude branches: `claude/<description>-<session-id>`

### Commit Messages
Write clear, imperative commit messages:
```
Add user authentication flow
Fix null pointer in device handler
Update README with setup instructions
```

Avoid vague messages like "fix stuff" or "WIP".

### Push Protocol
Always use:
```bash
git push -u origin <branch-name>
```

On network failure, retry with exponential backoff: 2s → 4s → 8s → 16s (max 4 retries).

### Pull Requests
- Keep PRs focused on a single concern
- Write a clear description of what changed and why
- Reference any related issues

---

## Development Conventions (To Be Updated)

> **Note**: The following sections are placeholders. Once source code is added to this repository, update each section to reflect actual tooling and conventions.

### Project Type
*Not yet determined — update when code is added.*

### Directory Structure
*Not yet established — update when code is added.*

### Build & Run
*No build system configured yet. Add commands here once established.*

```bash
# Example placeholders — replace with real commands
# npm install       # install dependencies
# npm run build     # build the project
# npm start         # run the application
```

### Testing
*No test framework configured yet. Add commands here once established.*

```bash
# Example placeholders — replace with real commands
# npm test          # run all tests
# npm run test:watch  # watch mode
```

### Linting & Formatting
*No linter/formatter configured yet. Add commands here once established.*

```bash
# Example placeholders — replace with real commands
# npm run lint      # check for lint errors
# npm run format    # auto-format code
```

---

## AI Assistant Guidelines

### General Principles
1. **Read before editing**: Always read a file fully before modifying it.
2. **Minimal changes**: Only change what is necessary for the task at hand.
3. **No unnecessary files**: Do not create files unless they are clearly needed.
4. **Security first**: Never introduce SQL injection, XSS, command injection, or other OWASP vulnerabilities.
5. **No over-engineering**: Avoid premature abstractions, unused error handling, or speculative features.

### Before Making Changes
- Check for an existing implementation before creating new code.
- Understand the project's existing patterns and follow them.
- Verify that your changes don't break unrelated functionality.

### Commits
- Commit frequently with descriptive messages.
- Do not amend published commits — create new commits instead.
- Never skip commit hooks (`--no-verify`) unless explicitly instructed.

### Risky Operations
Always confirm with the user before:
- Deleting files or branches
- Force-pushing (`git push --force`)
- Dropping database tables or running destructive migrations
- Modifying CI/CD pipelines or shared infrastructure

---

## Updating This File

When source code is added to this repository, update the following sections:
- **Project Type**: language, framework, purpose
- **Directory Structure**: layout of `src/`, `lib/`, `test/`, etc.
- **Build & Run**: actual commands
- **Testing**: actual test commands and framework
- **Linting & Formatting**: actual tools and config files
- **Environment Setup**: `.env.example`, required env vars, secrets management
- **CI/CD**: pipeline description and how to interpret failures
