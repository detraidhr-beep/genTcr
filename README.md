# genTcr

A generator for custom QA checklists: from a JSON description it produces an interactive HTML page for test execution and, optionally, a GitHub issue with the checklist.

---

## What it does

1. **Reads a checklist** — a JSON file with test cases (steps, expected result, tags).
2. **Generates an HTML report** — a browser page where QA marks status (Pass/Fail/Blocked/Skipped), adds notes, screenshots, and bug links.
3. **Creates a GitHub issue** — an issue is created in the specified repository with a markdown checklist (unless test mode is enabled).

Useful for smoke checks, regressions, and any repeatable test scenarios.

---

## Requirements

- **Python 3** with the `PyGithub` package
- **GitHub Personal Access Token** (see Setup)

Install the dependency:

```bash
pip install PyGithub
```

---

## Quick start

### 1. Setup

Create a `github.secret` file in the repo root or in the `main/` folder. Put a single line in it: your [GitHub Personal Access Token](https://github.com/settings/tokens) (needs `repo` scope to create issues).

```bash
# Example: in project root
echo "ghp_xxxxxxxxxxxx" > github.secret
chmod 600 github.secret
```

The file is already in `.gitignore`, so it won’t be committed.

### 2. Run a checklist

From the `main/` folder:

```bash
# Run with checklist selection (interactive) — test only, no issue created
./run_checklist.sh

# Or specify the checklist explicitly
./run_checklist.sh custom_checklists/CL-1.json
```

The script opens the generated HTML in your browser. In this mode **no GitHub issue is created** (test mode).

### 3. Full run (with issue creation)

```bash
cd main
python3 custom_checklist_generator.py \
  --input custom_checklists/CL-1.json \
  --repo owner/repo-name \
  --open
```

This generates the HTML report and creates an issue in the given repo. The `--open` flag opens the HTML in the browser (default).

---

## Project structure

```
genTcr/
├── main/
│   ├── custom_checklist_generator.py   # main script
│   ├── createCheckList                 # create a new checklist from template
│   ├── run_checklist.sh                # run in test mode with checklist selection
│   ├── configs/
│   │   ├── github_issue_config.json    # repo URL for issues, title prefix
│   │   ├── environment_config.json    # platforms, OS, channels (optional)
│   │   └── qa_users.json              # list of QA engineers for the report
│   └── custom_checklists/              # JSON checklists
│       ├── template.json               # template for new checklists
│       ├── CL-1.json                  # example checklist
│       └── example_description.md     # example description (referenced from JSON)
├── issue_template/                     # GitHub issue templates (desktop, android, ios, etc.)
├── github.secret                       # token (create manually, do not commit)
└── README.md
```

---

## Checklist format (JSON)

Required fields: `title` and `cases`. Example:

```json
{
  "title": "CL-1",
  "issue_title": "CL-1 - Verify the build",
  "repo": "owner/repo-name",
  "milestone": "1.89.x - Nightly",
  "labels": ["tests", "QA/Yes"],
  "environment": {
    "platform": "",
    "os_version": "",
    "app_version": "",
    "revision": ""
  },
  "description_markdown": "optional_description.md",
  "cases": [
    {
      "id": "CaseID-1",
      "title": "Launch browser",
      "steps": ["Install the build", "Launch the app"],
      "expected": "Browser starts without crashes",
      "tags": ["smoke", "desktop"]
    }
  ]
}
```

- **title** — checklist name (required).
- **issue_title** — title of the GitHub issue to create.
- **repo** — repository `owner/repo` (can be overridden with `--repo`).
- **milestone** — name of an open milestone in the repo (optional).
- **labels** — list of issue labels.
- **environment** — hints for Platform, OS version, App version, Revision in the HTML form.
- **description_markdown** — path to a `.md` file with the description (relative to the checklist folder), or use **description** for inline text.
- **cases** — array of cases. Each can have **id**, **title**, **steps** (array of strings), **expected**, **tags**, **links** (optional).

---

## Creating a new checklist

The `createCheckList` script copies `template.json` into a new file:

```bash
cd main
./createCheckList MyChecklist
# creates custom_checklists/MyChecklist.json
```

Then edit `MyChecklist.json`: set `title`, `issue_title`, `repo`, add your **cases**, and optionally **description_markdown**.

---

## Generator options

| Option | Description |
|--------|-------------|
| `--input` | Path to JSON checklist (required) |
| `--output-dir` | Directory for HTML output (default: `history`) |
| `--repo` | Repository `owner/repo` (if not set in JSON) |
| `--milestone` | Milestone name |
| `--collector` | QA engineer name (shown in report) |
| `--run-name` | Run name (affects HTML filename) |
| `--open` / `--no-open` | Open HTML in browser |
| `--test` | Test mode: only generate HTML and print issue body, **do not create issue** |

Example:

```bash
python3 custom_checklist_generator.py \
  --input custom_checklists/CL-1.json \
  --repo brave/brave-browser \
  --milestone "1.89.x - Nightly" \
  --collector "Your Name" \
  --test
```

---

## Config files in `main/configs/`

- **github_issue_config.json** — `repo_url` (used in “Create GitHub Issue” form) and `title_prefix` (e.g. `"Bug"`).
- **environment_config.json** — options for platforms, OS, and channels (optional; built-in defaults if missing).
- **qa_users.json** — list of QA names for the dropdown in the report.

---

## HTML report features

- Select QA, platform, OS, app version, revision, and channels.
- Auto-fill from pasted `brave://version` output.
- Per case: checkbox, status (Pass/Fail/Blocked/Skipped), bug link, notes, actual result, screenshots.
- Copy steps, notes, actual result, or summary to clipboard.
- Create a GitHub issue from a case (button opens form with pre-filled body).
- Export report as JSON, save final HTML, export activity log.
- Progress is saved in `localStorage` by run key (title + run id).

---

## License

See [LICENSE](LICENSE).
