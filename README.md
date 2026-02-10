# genTcr

Custom QA checklist runner that turns JSON test plans into interactive HTML reports and optional GitHub issues.

`genTcr` is built for fast smoke/regression execution, clean evidence capture, and structured outputs that can be consumed by automation and AI agents.

---

## Features

- [x] Read a JSON checklist with test cases, steps, expected results, tags, and links.
- [x] Generate an interactive HTML checklist UI for manual QA execution.
- [x] Parse data from `brave://version` to auto-fill environment fields (version, OS, revision, channel).
- [x] Create or prepare GitHub issue content from checklist/case data.
- [x] Track execution changes in an activity log.
- [x] Show a status summary dashboard (Pass/Fail/Blocked/Skipped/Not set).
- [x] Export machine-readable QA report data (JSON) for downstream tooling and AI-agent workflows.
- [ ] Add dedicated AI-agent tools (Leo, Atlas, Comet) for even faster issue triage and reporting.

---

## Table of Contents

- [Requirements](#requirements)
- [Quick Start](#quick-start)
- [How It Works](#how-it-works)
- [Project Structure](#project-structure)
- [Checklist JSON Format](#checklist-json-format)
- [CLI Options](#cli-options)
- [Configuration](#configuration)
- [Troubleshooting](#troubleshooting)
- [Security Notes](#security-notes)
- [Roadmap](#roadmap)
- [License](#license)

---

## Requirements

- Python `3.8+`
- `PyGithub`
- GitHub Personal Access Token (for repository access and issue workflows)

Install dependency:

```bash
pip install PyGithub
```

---

## Quick Start

### 1) Configure GitHub token

Create `github.secret` in project root or `main/`:

```bash
echo "ghp_xxxxxxxxxxxx" > github.secret
chmod 600 github.secret
```

Token file is ignored by Git via `.gitignore`.

### 2) Run checklist in test mode (no issue is created)

```bash
cd main
./run_checklist.sh
```

Or run with an explicit file:

```bash
cd main
./run_checklist.sh custom_checklists/CL-1.json
```

### 3) Full run with issue creation

```bash
cd main
python3 custom_checklist_generator.py \
  --input custom_checklists/CL-1.json \
  --repo owner/repo-name \
  --open
```

### 4) Create a new checklist from template

```bash
cd main
./createCheckList MyChecklist
# creates: main/custom_checklists/MyChecklist.json
```

---

## How It Works

1. Load checklist JSON from `main/custom_checklists/`.
2. Resolve metadata (repo, milestone, labels, environment defaults).
3. Generate HTML report with:
   - statuses and notes per case,
   - attachments/screenshots,
   - bug link and issue helper,
   - activity log and status chart,
   - report export actions.
4. Optionally create a GitHub issue (disabled in `--test` mode).

---

## Project Structure

```text
genTcr/
├── .github/
│   └── ISSUE_TEMPLATE/                 # GitHub issue templates
├── main/
│   ├── custom_checklist_generator.py   # core generator (HTML + GitHub integration)
│   ├── run_checklist.sh                # interactive launcher (runs with --test true)
│   ├── runTest                         # thin wrapper around run_checklist.sh
│   ├── createCheckList                 # create new checklist from template.json
│   ├── custom_checklists/
│   │   ├── template.json
│   │   ├── CL-1.json
│   │   └── example_description.md
│   ├── configs/
│   │   ├── github_issue_config.json
│   │   ├── environment_config.json
│   │   └── qa_users.json
│   └── history/                        # generated HTML reports
└── README.md
```

---

## Checklist JSON Format

Minimal required fields are `title` and `cases`, but practical runs usually also set `repo` and `issue_title`.

```json
{
  "title": "CL-1",
  "issue_title": "CL-1 - Verify the build",
  "repo": "owner/repo-name",
  "milestone": "1.89.x - Nightly",
  "labels": ["tests", "QA/Yes", "OS/Desktop"],
  "collector": "QA Engineer",
  "collector_email": "qa@example.com",
  "run_name": "Nightly Smoke",
  "environment": {
    "platform": "",
    "os_version": "",
    "app_version": "",
    "revision": ""
  },
  "environment_templates": [
    {
      "name": "Desktop macOS",
      "platform": "Desktop",
      "os_version": "macOS 26.1",
      "app_version": "",
      "build": ""
    }
  ],
  "description_markdown": "example_description.md",
  "cases": [
    {
      "id": "CaseID-1",
      "title": "Launch browser",
      "steps": ["Install the build", "Launch the app"],
      "expected": "Browser starts without crashes",
      "tags": ["smoke", "desktop"],
      "links": ["https://example.com/spec"]
    }
  ]
}
```

Field notes:

- `repo`: GitHub repository in `owner/repo` format.
- `description_markdown`: path relative to checklist file directory.
- `environment.revision`: supports `build` alias in templates.
- `labels`, `milestone`: applied when creating issue.

---

## CLI Options

`main/custom_checklist_generator.py`:

| Option | Description |
|---|---|
| `--input` | Path to checklist JSON (required) |
| `--output-dir` | Output directory for HTML report (default: `history`) |
| `--repo` | Override repository (`owner/repo`) |
| `--milestone` | Override milestone title |
| `--collector` | Override collector name |
| `--run-name` | Name used for output file generation |
| `--open` / `--no-open` | Open generated HTML in browser (default: open) |
| `--test [true/false]` | Test mode; prints issue preview and skips issue creation |

Example:

```bash
cd main
python3 custom_checklist_generator.py \
  --input custom_checklists/CL-1.json \
  --repo brave/brave-browser \
  --milestone "1.89.x - Nightly" \
  --collector "QA Engineer" \
  --test true
```

---

## Configuration

Files in `main/configs/`:

- `github_issue_config.json`
  - `repo_url`: repository URL used in issue helper UI
  - `title_prefix`: default issue title prefix (for example, `Bug`)
- `environment_config.json`
  - `platform_options`, `os_options`, `channel_options`
- `qa_users.json`
  - QA dropdown placeholder and user list

---

## Troubleshooting

- `github.secret not found`
  - Ensure file exists in project root or `main/`.
- `Missing repo. Provide --repo or repo in JSON`
  - Add `repo` to checklist JSON or pass `--repo`.
- `Milestone not found`
  - Check exact title in GitHub; script warns and continues.
- `No JSON checklists found`
  - Add files to `main/custom_checklists/`.

---

## Security Notes

- Never commit `github.secret`.
- Use minimal token scope needed for your workflow.
- Prefer fine-grained tokens where possible.
- Rotate token if it is ever exposed.

---

## Roadmap

- [ ] Native integrations for AI agents (Leo, Atlas, Comet).
- [ ] Add `requirements.txt` with pinned versions.
- [ ] Add CI validation for checklist JSON schema.
- [ ] Add optional offline mode without GitHub API dependency.

---

## License

See `LICENSE`.
