#!/usr/bin/env python3
import argparse
import html
import json
import re
import webbrowser
from datetime import datetime
from pathlib import Path

from github import Github


def parse_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return True
    return str(value).lower() in ("1", "true", "yes", "y", "on")


def slugify(text):
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", str(text).strip().lower())
    return normalized.strip("-") or "checklist"


def read_token():
    script_dir = Path(__file__).resolve().parent
    token_path = script_dir / "github.secret"
    if not token_path.exists():
        token_path = Path.cwd() / "github.secret"
    if not token_path.exists():
        raise FileNotFoundError("github.secret not found")
    return token_path.read_text().strip()


def resolve_path(base_dir, maybe_path):
    if not maybe_path:
        return None
    path = Path(maybe_path)
    if path.is_absolute():
        return path
    return (base_dir / path).resolve()


def load_input(input_path):
    data = json.loads(input_path.read_text())
    if "title" not in data:
        raise ValueError("Missing required field: title")
    if "cases" not in data or not isinstance(data["cases"], list):
        raise ValueError("Missing required field: cases[]")
    description_md = ""
    if data.get("description_markdown"):
        md_path = resolve_path(input_path.parent, data["description_markdown"])
        if md_path and md_path.exists():
            description_md = md_path.read_text()
        else:
            raise FileNotFoundError(f"Description markdown not found: {md_path}")
    elif data.get("description"):
        description_md = str(data["description"])
    return data, description_md


def normalize_environment(data):
    env = data.get("environment") or {}
    return {
        "platform": str(env.get("platform", "")).strip(),
        "os_version": str(env.get("os_version", "")).strip(),
        "app_version": str(env.get("app_version", "")).strip(),
        "revision": str(env.get("revision", env.get("build", ""))).strip(),
        "channels": env.get("channels", []) if isinstance(env.get("channels", []), list) else [],
    }


def normalize_templates(data):
    templates = data.get("environment_templates") or []
    normalized = []
    for template in templates:
        if not isinstance(template, dict) or not template.get("name"):
            continue
        normalized.append(
            {
                "name": str(template.get("name")).strip(),
                "platform": str(template.get("platform", "")).strip(),
                "os_version": str(template.get("os_version", "")).strip(),
                "app_version": str(template.get("app_version", "")).strip(),
                "build": str(template.get("build", "")).strip(),
            }
        )
    return normalized


def load_environment_config():
    config_path = Path(__file__).resolve().parent / "configs/environment_config.json"
    if not config_path.exists():
        return {
            "platform_options": ["Desktop", "Mobile", "Android", "iOS"],
            "os_options": [
                "macOS 14",
                "Windows 11",
                "Windows 10",
                "Ubuntu 22.04",
                "Debian 13",
                "Android 14",
                "iOS 18",
            ],
        }
    return json.loads(config_path.read_text())


def load_qa_users():
    config_path = Path(__file__).resolve().parent / "configs/qa_users.json"
    if not config_path.exists():
        return {"placeholder": "Select QA Engineer", "users": []}
    return json.loads(config_path.read_text())


def load_github_issue_config():
    config_path = Path(__file__).resolve().parent / "configs/github_issue_config.json"
    if not config_path.exists():
        return {"repo_url": "", "title_prefix": "Bug"}
    return json.loads(config_path.read_text())


def render_markdown(title, description_md, cases):
    lines = [f"# {title}", ""]
    if description_md:
        lines.append(description_md.strip())
        lines.append("")
    lines.append("## Checklist")
    lines.append("")
    for case in cases:
        case_title = case.get("title", "Untitled case")
        case_id = case.get("id")
        header = f"- [ ] **{case_title}**"
        if case_id:
            header += f" ({case_id})"
        lines.append(header)
        steps = case.get("steps", [])
        if steps:
            lines.append("  - Steps to reproduce:")
            for idx, step in enumerate(steps, start=1):
                lines.append(f"    {idx}. {step}")
        expected = case.get("expected")
        if expected:
            lines.append(f"  - Expected: {expected}")
        tags = case.get("tags", [])
        if tags:
            lines.append(f"  - Tags: {', '.join(tags)}")
        links = case.get("links", [])
        if links:
            lines.append(f"  - Links: {', '.join(links)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_html(title, description_md, cases, metadata, run_id, run_name):
    escaped_title = html.escape(title)
    collector_placeholder = "QA Engineer"
    raw_collector = str(metadata.get("collector") or "")
    if raw_collector.strip() == collector_placeholder:
        raw_collector = ""
    escaped_collector = html.escape(raw_collector)
    qa_users = load_qa_users()
    env = metadata.get("environment") or {}
    issue_config = load_github_issue_config()
    issue_repo = html.escape(issue_config.get("repo_url", ""))
    issue_title_prefix = html.escape(issue_config.get("title_prefix", "Bug"))
    env_placeholders = {
        "platform": "Which platform are you testing on?",
        "os_version": "Which OS version are you testing on?",
        "app_version": "Which app version are you testing on?",
        "revision": "Which revision are you testing on?",
    }
    channel_defaults = set((env.get("channels") or []))
    def env_value_and_placeholder(key):
        raw = str(env.get(key, "") or "")
        placeholder = env_placeholders.get(key, "")
        if raw.strip() == placeholder:
            return "", placeholder
        return raw, placeholder
    templates = metadata.get("environment_templates") or []
    base_file_name = (
        f"{slugify(run_name)}-"
        f"{slugify(env.get('app_version') or 'unknown')}-"
        f"{run_id[:13].replace('T', '-')}"
    )
    lines = [
        "<!doctype html>",
        "<html>",
        "<head>",
        '  <meta charset="utf-8" />',
        f"  <title>{escaped_title}</title>",
        "  <style>",
        "    :root { color-scheme: light dark; }",
        "    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif; margin: 24px; }",
        "    h1 { margin-bottom: 4px; }",
        "    .case {",
        "      padding: 14px 16px;",
        "      border: 1px solid #e5e7eb;",
        "      border-radius: 12px;",
        "      margin: 12px 0;",
        "      background: #ffffff;",
        "      box-shadow: 0 1px 2px rgba(0,0,0,0.04);",
        "    }",
        "    .case h3 { margin: 0 0 8px; font-size: 16px; }",
        "    .meta { color: #6b7280; font-size: 0.9em; margin-top: 6px; }",
        "    pre { background: #f6f8fa; padding: 12px; border-radius: 8px; }",
        "    ol { margin: 6px 0 0 20px; }",
        "    input[type='checkbox'] { width: 16px; height: 16px; vertical-align: text-top; }",
        "    .case-actions { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 10px; align-items: flex-start; }",
        "    .case-actions .notes-block { width: 100%; }",
        "    .case-actions .actual-block { width: 100%; }",
        "    .case-actions .copy-actions { width: 100%; display: flex; gap: 8px; flex-wrap: wrap; }",
        "    .block-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }",
        "    .case-actions label { font-size: 0.9em; color: #374151; }",
        "    .case-actions input[type='file'] { font-size: 0.9em; }",
        "    .copy-btn { padding: 6px 10px; border-radius: 8px; border: 1px solid #e5e7eb; background: #f8fafc; cursor: pointer; font-size: 0.85em; transition: transform 0.12s ease, box-shadow 0.12s ease; }",
        "    .copy-btn.copied { box-shadow: 0 0 0 2px rgba(34,197,94,0.25); transform: translateY(-1px); }",
        "    .copy-status { font-size: 0.8em; color: #16a34a; opacity: 0; transition: opacity 0.2s ease; }",
        "    .copy-status.show { opacity: 1; }",
        "    .bug-link-input { width: 100%; padding: 8px; border-radius: 8px; border: 1px solid #e5e7eb; }",
        "    .case-notes { width: 100%; min-height: 64px; padding: 8px; border-radius: 8px; border: 1px solid #e5e7eb; }",
        "    .case-actual { width: 100%; min-height: 64px; padding: 8px; border-radius: 8px; border: 1px solid #e5e7eb; }",
        "    #version-raw { width: 100%; min-height: 72px; padding: 8px; border-radius: 8px; border: 1px solid #e5e7eb; }",
        "    .case-status { min-width: 160px; padding: 6px; border-radius: 8px; border: 1px solid #e5e7eb; }",
        "    .status-indicator { display: inline-block; width: 10px; height: 10px; border-radius: 999px; margin: 0 6px; background: #9ca3af; }",
        "    .status-pass .status-indicator { background: #16a34a; }",
        "    .status-fail .status-indicator { background: #dc2626; }",
        "    .status-blocked .status-indicator { background: #f59e0b; }",
        "    .status-skipped .status-indicator { background: #6b7280; }",
        "    .bug-link { display: none; }",
        "    .case-proof { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 8px; }",
        "    .case-proof img { max-width: 220px; border-radius: 8px; border: 1px solid #e5e7eb; }",
        "    .toolbar { display: flex; gap: 12px; flex-wrap: wrap; margin: 12px 0 20px; }",
        "    .toolbar button { padding: 8px 12px; border-radius: 8px; border: 1px solid #e5e7eb; background: #f8fafc; cursor: pointer; }",
        "    .meta-block { padding: 12px 16px; border: 1px solid #e5e7eb; border-radius: 12px; background: #ffffff; }",
        "    .meta-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; }",
        "    .meta-grid label { display: block; font-size: 0.85em; color: #6b7280; margin-bottom: 4px; }",
        "    .meta-grid input, .meta-grid select { width: 100%; padding: 8px; border-radius: 8px; border: 1px solid #e5e7eb; }",
        "    .env-channel { margin-right: 6px; }",
        "    .channel-list { display: grid; gap: 6px; margin-top: 6px; }",
        "    .env-row { display: flex; gap: 8px; align-items: center; }",
        "    .env-clear { padding: 6px 8px; border-radius: 8px; border: 1px solid #e5e7eb; background: #f8fafc; cursor: pointer; font-size: 0.8em; }",
        "    .env-copy { margin-top: 10px; display: flex; gap: 8px; align-items: center; }",
        "    .activity-log { margin-top: 10px; }",
        "    .activity-log ul { padding-left: 18px; }",
        "    .status-chart { margin-top: 18px; padding: 14px 16px; border: 1px solid #e5e7eb; border-radius: 12px; background: #ffffff; }",
        "    .status-bars { display: grid; gap: 10px; }",
        "    .status-row { display: grid; grid-template-columns: 100px 1fr 40px; align-items: center; gap: 10px; }",
        "    .status-label { font-size: 0.9em; color: #6b7280; }",
        "    .status-bar { height: 10px; background: #e5e7eb; border-radius: 999px; overflow: hidden; }",
        "    .status-bar span { display: block; height: 100%; border-radius: 999px; }",
        "    .status-bar .pass { background: #16a34a; }",
        "    .status-bar .fail { background: #dc2626; }",
        "    .status-bar .blocked { background: #f59e0b; }",
        "    .status-bar .skipped { background: #6b7280; }",
        "    .status-bar .not_set { background: #9ca3af; }",
        "    .issue-btn { padding: 6px 10px; border-radius: 8px; border: 1px solid #e5e7eb; background: #eef2ff; color: #3730a3; cursor: pointer; font-size: 0.85em; }",
        "    .issue-modal { position: fixed; inset: 0; background: rgba(0,0,0,0.4); display: none; align-items: center; justify-content: center; z-index: 999; }",
        "    .issue-modal.open { display: flex; }",
        "    .issue-card { width: min(760px, 92vw); background: #fff; border-radius: 12px; padding: 16px; box-shadow: 0 10px 25px rgba(0,0,0,0.2); }",
        "    .issue-card label { display: block; font-size: 0.85em; margin-bottom: 4px; color: #6b7280; }",
        "    .issue-card input, .issue-card textarea { width: 100%; padding: 8px; border-radius: 8px; border: 1px solid #e5e7eb; }",
        "    .issue-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 10px; }",
        "    @media (prefers-color-scheme: dark) {",
        "      body { background: #0b0f14; color: #e5e7eb; }",
        "      .case { background: #111827; border-color: #1f2937; box-shadow: none; }",
        "      pre { background: #0f172a; }",
        "      .meta { color: #9ca3af; }",
        "      .case-actions label { color: #9ca3af; }",
        "      .case-notes { background: #0f172a; color: #e5e7eb; border-color: #1f2937; }",
        "      .case-actual { background: #0f172a; color: #e5e7eb; border-color: #1f2937; }",
        "      #version-raw { background: #0f172a; color: #e5e7eb; border-color: #1f2937; }",
        "      .case-status { background: #0f172a; color: #e5e7eb; border-color: #1f2937; }",
        "      .case-proof img { border-color: #1f2937; }",
        "      .toolbar button { background: #111827; color: #e5e7eb; border-color: #1f2937; }",
        "      .copy-btn { background: #111827; color: #e5e7eb; border-color: #1f2937; }",
        "      .bug-link-input { background: #0f172a; color: #e5e7eb; border-color: #1f2937; }",
        "      .meta-block { background: #111827; border-color: #1f2937; }",
        "      .meta-grid input, .meta-grid select { background: #0f172a; color: #e5e7eb; border-color: #1f2937; }",
        "      .copy-btn.copied { box-shadow: 0 0 0 2px rgba(34,197,94,0.25); }",
        "      .status-chart { background: #111827; border-color: #1f2937; }",
        "      .env-clear { background: #111827; color: #e5e7eb; border-color: #1f2937; }",
        "      .status-bar { background: #1f2937; }",
        "      .bug-link { background: #2a1a12; color: #fbbf24; border-color: #1f2937; }",
        "      .issue-btn { background: #1e1b4b; color: #c7d2fe; border-color: #1f2937; }",
        "      .issue-card { background: #111827; color: #e5e7eb; }",
        "      .issue-card input, .issue-card textarea { background: #0f172a; color: #e5e7eb; border-color: #1f2937; }",
        "    }",
        "  </style>",
        "</head>",
        "<body>",
        f"  <h1>{escaped_title}</h1>",
        f"  <div class=\"meta\"><strong>Run ID:</strong> {html.escape(run_id)}</div>",
    ]
    lines.append('  <div class="meta-block">')
    lines.append("    <h2>Environment</h2>")
    if templates:
        template_data = html.escape(json.dumps(templates))
        lines.append('    <div class="meta-grid">')
        lines.append("      <div>")
        lines.append("        <label>Template</label>")
        lines.append(
            f'        <select id="env-template" data-templates="{template_data}">'
        )
        lines.append("          <option value=\"\">Select template</option>")
        for template in templates:
            tmpl_name = html.escape(template["name"])
            lines.append(f'          <option value="{tmpl_name}">{tmpl_name}</option>')
        lines.append("        </select>")
        lines.append("      </div>")
        lines.append("    </div>")
    lines.append('    <div class="meta-grid">')
    lines.append("      <div>")
    lines.append("        <label>QA Engineer</label>")
    lines.append('        <select id="collector">')
    placeholder = html.escape(qa_users.get("placeholder", "Select QA Engineer"))
    lines.append(f'          <option value="">{placeholder}</option>')
    for user in qa_users.get("users", []):
        selected = "selected" if user == raw_collector else ""
        lines.append(
            f'          <option value="{html.escape(user)}" {selected}>{html.escape(user)}</option>'
        )
    lines.append("        </select>")
    lines.append("      </div>")
    lines.append("      <div>")
    lines.append("        <label>Platform</label>")
    platform_value, platform_ph = env_value_and_placeholder("platform")
    lines.append('        <div class="env-row">')
    lines.append(
        f'          <input id="env-platform" list="platform-options" type="text" value="{html.escape(platform_value)}" placeholder="{html.escape(platform_ph)}" />'
    )
    lines.append('          <button class="env-clear" type="button" data-target="env-platform">Clear</button>')
    lines.append("        </div>")
    lines.append("      </div>")
    lines.append("      <div>")
    lines.append("        <label>OS version</label>")
    os_value, os_ph = env_value_and_placeholder("os_version")
    lines.append('        <div class="env-row">')
    lines.append(
        f'          <input id="env-os" list="os-options" type="text" value="{html.escape(os_value)}" placeholder="{html.escape(os_ph)}" />'
    )
    lines.append('          <button class="env-clear" type="button" data-target="env-os">Clear</button>')
    lines.append("        </div>")
    lines.append("      </div>")
    lines.append("      <div>")
    lines.append("        <label>App version</label>")
    app_value, app_ph = env_value_and_placeholder("app_version")
    lines.append(
        f'        <input id="env-version" type="text" value="{html.escape(app_value)}" placeholder="{html.escape(app_ph)}" />'
    )
    lines.append("      </div>")
    lines.append("      <div>")
    lines.append("        <label>Revision</label>")
    build_value, build_ph = env_value_and_placeholder("revision")
    lines.append(
        f'        <input id="env-revision" type="text" value="{html.escape(build_value)}" placeholder="{html.escape(build_ph)}" />'
    )
    lines.append("      </div>")
    lines.append("    </div>")
    lines.append("    <div>")
    lines.append("      <label>Channel information</label>")
    lines.append("      <div class=\"channel-list\">")
    env_config = load_environment_config()
    for option in env_config.get("channel_options", []):
        checked = "checked" if option in channel_defaults else ""
        lines.append(
            f'        <label><input type="checkbox" class="env-channel" value="{html.escape(option)}" {checked}/> {html.escape(option)}</label>'
        )
    lines.append("      </div>")
    lines.append("    </div>")
    lines.append("    <div>")
    lines.append("      <label>Auto-fill from brave://version</label>")
    lines.append("      <div class=\"block-head\">")
    lines.append("        <button class=\"copy-btn\" data-copy=\"version\">Paste + Parse</button>")
    lines.append("        <span class=\"copy-status\"></span>")
    lines.append("      </div>")
    lines.append(
        "      <textarea id=\"version-raw\" placeholder=\"Paste brave://version output here...\"></textarea>"
    )
    lines.append("    </div>")
    env_config = load_environment_config()
    lines.append('    <datalist id="platform-options">')
    for option in env_config.get("platform_options", []):
        lines.append(f'      <option value="{html.escape(option)}"></option>')
    lines.append("    </datalist>")
    lines.append('    <datalist id="os-options">')
    for option in env_config.get("os_options", []):
        lines.append(f'      <option value="{html.escape(option)}"></option>')
    lines.append("    </datalist>")
    lines.append('    <div class="env-copy">')
    lines.append('      <button class="copy-btn" data-copy="environment">Copy environment</button>')
    lines.append('      <span class="copy-status"></span>')
    lines.append("    </div>")
    lines.append("  </div>")
    if description_md:
        lines.extend(
            [
                "  <h2>Description</h2>",
                f"  <pre>{html.escape(description_md.strip())}</pre>",
            ]
        )
    lines.append("  <div class=\"toolbar\">")
    lines.append("    <button id=\"export-json\">Export report JSON</button>")
    lines.append("    <button id=\"save-final\">Save final HTML</button>")
    lines.append("    <button id=\"export-log\">Export activity log</button>")
    lines.append("  </div>")
    lines.append("  <h2>Checklist</h2>")
    for index, case in enumerate(cases, start=1):
        case_title = html.escape(case.get("title", "Untitled case"))
        case_id = case.get("id")
        storage_key = html.escape(case_id or f"case-{index}")
        header = f'{case_title} ({html.escape(case_id)})' if case_id else case_title
        lines.append(
            f'  <div class="case" data-case-key="{storage_key}" data-case-title="{case_title}">'
        )
        lines.append(
            f'    <h3><input type="checkbox" class="case-check" /> {header}</h3>'
        )
        steps = case.get("steps", [])
        if steps:
            lines.append('    <div class="block-head"><strong>Steps:</strong>')
            lines.append('      <button class="copy-btn" data-copy="steps">Copy</button>')
            lines.append('      <span class="copy-status"></span></div>')
            lines.append("    <ol>")
            for step in steps:
                lines.append(f"      <li>{html.escape(str(step))}</li>")
            lines.append("    </ol>")
        expected = case.get("expected")
        if expected:
            lines.append(
                f'    <div class="meta"><strong>Expected:</strong> {html.escape(str(expected))}</div>'
            )
        tags = case.get("tags", [])
        if tags:
            lines.append(
                f'    <div class="meta"><strong>Tags:</strong> {html.escape(", ".join(tags))}</div>'
            )
        links = case.get("links", [])
        if links:
            link_items = []
            for link in links:
                safe = html.escape(link)
                link_items.append(
                    f'<a href="{safe}" target="_blank" rel="noreferrer">{safe}</a>'
                )
            lines.append(
                f'    <div class="meta"><strong>Links:</strong> {", ".join(link_items)}</div>'
            )
        lines.append('    <div class="case-actions">')
        lines.append('      <label>Status</label>')
        lines.append('      <select class="case-status">')
        lines.append('        <option value="not_set">Not set</option>')
        lines.append('        <option value="pass">Pass</option>')
        lines.append('        <option value="fail">Fail</option>')
        lines.append('        <option value="blocked">Blocked</option>')
        lines.append('        <option value="skipped">Skipped</option>')
        lines.append("      </select>")
        lines.append('      <span class="status-indicator"></span>')
        lines.append('      <div class="block-head">')
        lines.append('        <label>Bug link</label>')
        lines.append('        <button class="copy-btn" data-copy="bug">Copy</button>')
        lines.append('        <span class="copy-status"></span></div>')
        lines.append('      <input class="bug-link-input" type="url" placeholder="Paste bug link (your repo)..." />')
        lines.append('      <div class="notes-block">')
        lines.append('        <div class="block-head"><label>Notes</label>')
        lines.append('          <button class="copy-btn" data-copy="notes">Copy</button>')
        lines.append('          <span class="copy-status"></span></div>')
        lines.append(
            '        <textarea class="case-notes" placeholder="Notes or evidence..."></textarea>'
        )
        lines.append("      </div>")
        lines.append('      <div class="actual-block">')
        lines.append('        <div class="block-head"><label>Actual result</label>')
        lines.append('          <button class="copy-btn" data-copy="actual">Copy</button>')
        lines.append('          <span class="copy-status"></span></div>')
        lines.append(
            '        <textarea class="case-actual" placeholder="Actual result..."></textarea>'
        )
        lines.append('        <div class="block-head">')
        lines.append('          <label>Proof (screenshots)</label>')
        lines.append('          <button class="copy-btn" data-copy="attachments">Copy</button>')
        lines.append('          <span class="copy-status"></span></div>')
        lines.append('        <input class="case-file" type="file" accept="image/*" multiple />')
        lines.append("      </div>")
        lines.append('      <div class="block-head">')
        lines.append('        <label>Summary</label>')
        lines.append('        <button class="copy-btn" data-copy="summary">Copy</button>')
        lines.append('        <span class="copy-status"></span></div>')
        lines.append('      <button class="issue-btn" data-action="open-issue">Create GitHub Issue</button>')
        lines.append("    </div>")
        lines.append('    <div class="case-proof"></div>')
        lines.append("  </div>")
    lines.extend(
        [
            "  <div class=\"activity-log\">",
            "    <h2>Activity log</h2>",
            "    <ul id=\"activity-list\"></ul>",
            "  </div>",
            "  <div class=\"status-chart\">",
            "    <h2>Status summary</h2>",
            "    <div class=\"status-bars\" id=\"status-bars\"></div>",
            "  </div>",
            "  <div class=\"issue-modal\" id=\"issue-modal\">",
            "    <div class=\"issue-card\">",
            "      <h2>Create GitHub Issue</h2>",
            "      <label>Repository URL</label>",
            f"      <input id=\"issue-repo\" type=\"text\" value=\"{issue_repo}\" />",
            "      <label>Title</label>",
            f"      <input id=\"issue-title\" type=\"text\" value=\"{issue_title_prefix}: \" />",
            "      <label>Body</label>",
            "      <textarea id=\"issue-body\" rows=\"10\"></textarea>",
            "      <div class=\"issue-actions\">",
            "        <button id=\"issue-close\" class=\"copy-btn\">Close</button>",
            "        <button id=\"issue-open\" class=\"issue-btn\">Open in GitHub</button>",
            "      </div>",
            "    </div>",
            "  </div>",
            "  <details>",
            "    <summary>QA report data (machine-readable)</summary>",
            "    <pre id=\"qa-report-data\"></pre>",
            "    <script type=\"application/json\" id=\"qa-report-json\"></script>",
            "  </details>",
            "  <script>",
            f"    const runId = '{html.escape(run_id)}';",
            f"    const baseFileName = '{html.escape(base_file_name)}';",
            "    const storageKey = 'customChecklist:' + document.title + ':' + runId;",
            "    const state = JSON.parse(localStorage.getItem(storageKey) || '{}');",
            "    const saveState = () => localStorage.setItem(storageKey, JSON.stringify(state));",
            "    const slugify = (text) => text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/(^-|-$)/g, '') || 'checklist';",
            "    state.meta = state.meta || {};",
            "    state.meta.environment = state.meta.environment || {};",
            "    state.logs = state.logs || [];",
            "    const activityList = document.getElementById('activity-list');",
            "    const renderLogs = () => {",
            "      activityList.innerHTML = '';",
            "      state.logs.forEach((entry) => {",
            "        const li = document.createElement('li');",
            "        li.textContent = `[${entry.at}] ${entry.action}`;",
            "        activityList.appendChild(li);",
            "      });",
            "    };",
            "    const copyText = (text, button, statusEl) => {",
            "      if (!text) return;",
            "      const showCopied = () => {",
            "        const status = statusEl || (button ? button.closest('.block-head')?.querySelector('.copy-status') : null);",
            "        if (!status) return;",
            "        status.textContent = 'Copied';",
            "        status.classList.add('show');",
            "        setTimeout(() => {",
            "          status.textContent = '';",
            "          status.classList.remove('show');",
            "        }, 1500);",
            "      };",
            "      if (button) {",
            "        button.classList.add('copied');",
            "        setTimeout(() => button.classList.remove('copied'), 1500);",
            "      }",
            "      if (navigator.clipboard && navigator.clipboard.writeText) {",
            "        navigator.clipboard.writeText(text).then(showCopied).catch(showCopied);",
            "        return;",
            "      }",
            "      const area = document.createElement('textarea');",
            "      area.value = text;",
            "      document.body.appendChild(area);",
            "      area.select();",
            "      document.execCommand('copy');",
            "      area.remove();",
            "      showCopied();",
            "    };",
            "    const renderStatusChart = () => {",
            "      const summary = { pass: 0, fail: 0, blocked: 0, skipped: 0, not_set: 0 };",
            "      document.querySelectorAll('.case').forEach((card) => {",
            "        const status = card.querySelector('.case-status');",
            "        const value = status ? status.value : 'not_set';",
            "        summary[value] = (summary[value] || 0) + 1;",
            "      });",
            "      const total = Object.values(summary).reduce((a, b) => a + b, 0) || 1;",
            "      const barRoot = document.getElementById('status-bars');",
            "      barRoot.innerHTML = '';",
            "      const order = [",
            "        ['pass', 'Pass'],",
            "        ['fail', 'Fail'],",
            "        ['blocked', 'Blocked'],",
            "        ['skipped', 'Skipped'],",
            "        ['not_set', 'Not set'],",
            "      ];",
            "      order.forEach(([key, label]) => {",
            "        const count = summary[key] || 0;",
            "        const row = document.createElement('div');",
            "        row.className = 'status-row';",
            "        row.innerHTML = `",
            "          <div class=\"status-label\">${label}</div>",
            "          <div class=\"status-bar\"><span class=\"${key}\" style=\"width:${(count / total) * 100}%\"></span></div>",
            "          <div class=\"status-label\">${count}</div>",
            "        `;",
            "        barRoot.appendChild(row);",
            "      });",
            "    };",
            "    const logEvent = (action) => {",
            "      state.logs.push({ at: new Date().toISOString(), action });",
            "      saveState();",
            "      renderLogs();",
            "    };",
            "    const bindMetaInput = (id, key, label) => {",
            "      const input = document.getElementById(id);",
            "      if (!input) return;",
            "      if (state.meta.environment[key]) {",
            "        input.value = state.meta.environment[key];",
            "      } else if (input.value) {",
            "        state.meta.environment[key] = input.value;",
            "      }",
            "      input.addEventListener('input', () => {",
            "        state.meta.environment[key] = input.value;",
            "        saveState();",
            "      });",
            "      input.addEventListener('change', () => {",
            "        logEvent(`${label} set to ${input.value}`);",
            "      });",
            "    };",
            "    const collectorInput = document.getElementById('collector');",
            "    if (collectorInput) {",
            "      if (state.meta.collector) collectorInput.value = state.meta.collector;",
            "      collectorInput.addEventListener('input', () => {",
            "        state.meta.collector = collectorInput.value;",
            "        saveState();",
            "      });",
            "      collectorInput.addEventListener('change', () => {",
            "        logEvent(`Collector set to ${collectorInput.value}`);",
            "      });",
            "    }",
            "    bindMetaInput('env-platform', 'platform', 'Platform');",
            "    bindMetaInput('env-os', 'os_version', 'OS version');",
            "    bindMetaInput('env-version', 'app_version', 'App version');",
            "    bindMetaInput('env-revision', 'revision', 'Revision');",
            "    const channelCheckboxes = document.querySelectorAll('.env-channel');",
            "    const savedChannels = state.meta.environment.channels || [];",
            "    channelCheckboxes.forEach((box) => {",
            "      if (savedChannels.includes(box.value)) {",
            "        box.checked = true;",
            "      }",
            "    });",
            "    const updateChannels = () => {",
            "      const selected = Array.from(channelCheckboxes)",
            "        .filter((box) => box.checked)",
            "        .map((box) => box.value);",
            "      state.meta.environment.channels = selected;",
            "      saveState();",
            "    };",
            "    channelCheckboxes.forEach((box) => {",
            "      box.addEventListener('change', () => {",
            "        updateChannels();",
            "        logEvent(`Channel selection: ${Array.from(channelCheckboxes).filter((b) => b.checked).map((b) => b.value).join(', ')}`);",
            "      });",
            "    });",
            "    document.querySelectorAll('.env-row input').forEach((input) => {",
            "      input.addEventListener('focus', () => input.select());",
            "    });",
            "    const versionRaw = document.getElementById('version-raw');",
            "    const parseVersion = (raw) => {",
            "      const lines = raw.split(/\\r?\\n/).map((l) => l.trim()).filter(Boolean);",
            "      const braveLine = lines.find((l) => l.startsWith('Brave')) || '';",
            "      const osLine = lines.find((l) => l.startsWith('OS')) || '';",
            "      let appVersion = '';",
            "      let chromiumVersion = '';",
            "      let revision = '';",
            "      let channel = '';",
            "      if (braveLine) {",
            "        const match = braveLine.match(/Brave\\s+([^\\s]+).*?(nightly|beta|stable)/i);",
            "        if (match) {",
            "          appVersion = match[1] || '';",
            "          channel = match[2] || '';",
            "        } else {",
            "          const parts = braveLine.split(/\\s+/);",
            "          appVersion = parts[1] || '';",
            "        }",
            "        const chromiumMatch = braveLine.match(/Chromium:\\s*([^\\s]+)/i);",
            "        if (chromiumMatch) chromiumVersion = chromiumMatch[1] || '';",
            "      }",
            "      const revisionLine = lines.find((l) => l.startsWith('Revision')) || '';",
            "      if (revisionLine) {",
            "        const match = revisionLine.match(/Revision\\s+(.*)$/i);",
            "        revision = match ? match[1] : '';",
            "      }",
            "      let osVersion = '';",
            "      if (osLine) {",
            "        const match = osLine.match(/OS\\s+(.*)$/i);",
            "        osVersion = match ? match[1] : '';",
            "      }",
            "      return { appVersion, chromiumVersion, osVersion, channel, revision };",
            "    };",
            "    const applyParsed = (parsed) => {",
            "      if (parsed.appVersion) {",
            "        const input = document.getElementById('env-version');",
            "        const chromium = parsed.chromiumVersion ? ` (Chromium ${parsed.chromiumVersion})` : '';",
            "        input.value = `${parsed.appVersion}${chromium}`;",
            "        input.dispatchEvent(new Event('input'));",
            "      }",
            "      if (parsed.osVersion) {",
            "        const input = document.getElementById('env-os');",
            "        input.value = parsed.osVersion;",
            "        input.dispatchEvent(new Event('input'));",
            "      }",
            "      if (parsed.revision) {",
            "        const input = document.getElementById('env-revision');",
            "        input.value = parsed.revision;",
            "        input.dispatchEvent(new Event('input'));",
            "      }",
            "      if (parsed.channel) {",
            "        const normalized = parsed.channel.toLowerCase();",
            "        document.querySelectorAll('.env-channel').forEach((box) => {",
            "          const val = box.value.toLowerCase();",
            "          box.checked = val.includes(normalized);",
            "        });",
            "        updateChannels();",
            "      }",
            "    };",
            "    const versionCopyBtn = document.querySelector('[data-copy=\"version\"]');",
            "    if (versionCopyBtn && versionRaw) {",
            "      versionCopyBtn.addEventListener('click', async () => {",
            "        try {",
            "          if (navigator.clipboard && navigator.clipboard.readText) {",
            "            versionRaw.value = await navigator.clipboard.readText();",
            "          }",
            "        } catch (err) {}",
            "        const parsed = parseVersion(versionRaw.value || '');",
            "        applyParsed(parsed);",
            "        copyText('Parsed', versionCopyBtn, versionCopyBtn.parentElement?.querySelector('.copy-status'));",
            "      });",
            "    }",
            "    document.querySelectorAll('.env-clear').forEach((btn) => {",
            "      btn.addEventListener('click', () => {",
            "        const target = btn.getAttribute('data-target');",
            "        const input = document.getElementById(target);",
            "        if (!input) return;",
            "        input.value = '';",
            "        input.dispatchEvent(new Event('input'));",
            "        input.focus();",
            "      });",
            "    });",
            "    const templateSelect = document.getElementById('env-template');",
            "    if (templateSelect) {",
            "      const templates = JSON.parse(templateSelect.dataset.templates || '[]');",
            "      templateSelect.addEventListener('change', () => {",
            "        const selected = templates.find((t) => t.name === templateSelect.value);",
            "        if (!selected) return;",
            "        document.getElementById('env-platform').value = selected.platform || '';",
            "        document.getElementById('env-os').value = selected.os_version || '';",
            "        document.getElementById('env-version').value = selected.app_version || '';",
            "        document.getElementById('env-revision').value = selected.revision || selected.build || '';",
            "        state.meta.environment = {",
            "          platform: selected.platform || '',",
            "          os_version: selected.os_version || '',",
            "          app_version: selected.app_version || '',",
            "          build: selected.build || '',",
            "        };",
            "        saveState();",
            "        logEvent(`Template applied: ${selected.name}`);",
            "      });",
            "    }",
            "    document.querySelectorAll('.case').forEach((card) => {",
            "      const key = card.getAttribute('data-case-key');",
            "      const checkbox = card.querySelector('.case-check');",
            "      const notes = card.querySelector('.case-notes');",
            "      const actual = card.querySelector('.case-actual');",
            "      const status = card.querySelector('.case-status');",
            "      const indicator = card.querySelector('.status-indicator');",
            "      const fileInput = card.querySelector('.case-file');",
            "      const proof = card.querySelector('.case-proof');",
            "      const bugInput = card.querySelector('.bug-link-input');",
            "      const copyButtons = card.querySelectorAll('.copy-btn');",
            "      const saved = state[key] || {};",
            "      checkbox.checked = !!saved.checked;",
            "      notes.value = saved.notes || '';",
            "      if (actual) actual.value = saved.actual_result || '';",
            "      status.value = saved.status || 'not_set';",
            "      const setStatusClass = (value) => {",
            "        card.classList.remove('status-pass', 'status-fail', 'status-blocked', 'status-skipped');",
            "        if (value && value !== 'not_set') {",
            "          card.classList.add(`status-${value}`);",
            "        }",
            "        if (indicator) {",
            "          indicator.setAttribute('data-status', value || 'not_set');",
            "        }",
            "      };",
            "      setStatusClass(status.value);",
            "      if (bugInput) {",
            "        bugInput.value = saved.bug_link || '';",
            "      }",
            "      checkbox.addEventListener('change', () => {",
            "        state[key] = state[key] || {};",
            "        state[key].checked = checkbox.checked;",
            "        saveState();",
            "        logEvent(`Case ${key} checkbox set to ${checkbox.checked}`);",
            "      });",
            "      status.addEventListener('change', () => {",
            "        state[key] = state[key] || {};",
            "        state[key].status = status.value;",
            "        saveState();",
            "        logEvent(`Case ${key} status set to ${status.value}`);",
            "        setStatusClass(status.value);",
            "        renderStatusChart();",
            "      });",
            "      if (bugInput) {",
            "        bugInput.addEventListener('input', () => {",
            "          state[key] = state[key] || {};",
            "          state[key].bug_link = bugInput.value.trim();",
            "          saveState();",
            "        });",
            "        bugInput.addEventListener('change', () => {",
            "          if (bugInput.value) {",
            "            logEvent(`Case ${key} bug link set to ${bugInput.value}`);",
            "          }",
            "        });",
            "      }",
            "      notes.addEventListener('input', () => {",
            "        state[key] = state[key] || {};",
            "        state[key].notes = notes.value;",
            "        saveState();",
            "      });",
            "      notes.addEventListener('change', () => {",
            "        logEvent(`Case ${key} notes updated`);",
            "      });",
            "      if (actual) {",
            "        actual.addEventListener('input', () => {",
            "          state[key] = state[key] || {};",
            "          state[key].actual_result = actual.value;",
            "          saveState();",
            "        });",
            "        actual.addEventListener('change', () => {",
            "          logEvent(`Case ${key} actual result updated`);",
            "        });",
            "      }",
            "      fileInput.addEventListener('change', () => {",
            "        const files = Array.from(fileInput.files || []);",
            "        if (!files.length) return;",
            "        files.forEach((file) => {",
            "          const reader = new FileReader();",
            "          reader.onload = () => {",
            "            const dataUrl = reader.result;",
            "            const img = document.createElement('img');",
            "            img.src = dataUrl;",
            "            img.dataset.name = file.name;",
            "            proof.appendChild(img);",
            "            saveState();",
            "            logEvent(`Case ${key} added screenshot ${file.name}`);",
            "          };",
            "          reader.readAsDataURL(file);",
            "        });",
            "        fileInput.value = '';",
            "      });",
            "      const collectSteps = () => {",
            "        const items = Array.from(card.querySelectorAll('ol li')).map((li) => li.textContent.trim());",
            "        if (!items.length) return '';",
            "        return items.map((step, idx) => `${idx + 1}. ${step}`).join('\\n');",
            "      };",
            "      const collectNotes = () => notes ? notes.value.trim() : '';",
            "      const collectActual = () => actual ? actual.value.trim() : '';",
            "      const collectBugLink = () => bugInput ? bugInput.value.trim() : '';",
            "      const collectAttachments = () => {",
            "        const images = Array.from(card.querySelectorAll('.case-proof img'));",
            "        if (!images.length) return '';",
            "        return images.map((img, idx) => {",
            "          const name = img.dataset.name || `screenshot-${idx + 1}`;",
            "          return `${name}: ${img.src}`;",
            "        }).join('\\n');",
            "      };",
            "      const collectSummary = () => {",
            "        const title = card.getAttribute('data-case-title') || key;",
            "        const statusValue = status ? status.value : 'not_set';",
            "        const parts = [",
            "          `Title: ${title}`,",
            "          `Status: ${statusValue}`,",
            "        ];",
            "        const bugLink = collectBugLink();",
            "        if (bugLink) parts.push(`Bug: ${bugLink}`);",
            "        const steps = collectSteps();",
            "        if (steps) parts.push('Steps:\\n' + steps);",
            "        const notesText = collectNotes();",
            "        if (notesText) parts.push('Notes:\\n' + notesText);",
            "        const actualText = collectActual();",
            "        if (actualText) parts.push('Actual result:\\n' + actualText);",
            "        const attachments = collectAttachments();",
            "        if (attachments) parts.push('Attachments:\\n' + attachments);",
            "        return parts.join('\\n\\n');",
            "      };",
            "      copyButtons.forEach((btn) => {",
            "        btn.addEventListener('click', () => {",
            "          const kind = btn.getAttribute('data-copy');",
            "          if (kind === 'steps') copyText(collectSteps(), btn);",
            "          if (kind === 'notes') copyText(collectNotes(), btn);",
            "          if (kind === 'attachments') copyText(collectAttachments(), btn);",
            "          if (kind === 'actual') copyText(collectActual(), btn);",
            "          if (kind === 'summary') copyText(collectSummary(), btn);",
            "          if (kind === 'bug') copyText(collectBugLink(), btn);",
            "        });",
            "      });",
            "    });",
            "    const envCopyBtn = document.querySelector('.env-copy .copy-btn');",
            "    if (envCopyBtn) {",
            "      const envStatus = document.querySelector('.env-copy .copy-status');",
            "      envCopyBtn.addEventListener('click', () => {",
            "        const channels = Array.from(document.querySelectorAll('.env-channel'))",
            "          .filter((box) => box.checked)",
            "          .map((box) => box.value)",
            "          .join(', ');",
            "        const envText = [",
            "          `Platform: ${document.getElementById('env-platform').value || ''}`,",
            "          `OS version: ${document.getElementById('env-os').value || ''}`,",
            "          `App version: ${document.getElementById('env-version').value || ''}`,",
            "          `Revision: ${document.getElementById('env-revision').value || ''}`,",
            "          `Channel: ${channels}`",
            "        ].join('\\n');",
            "        copyText(envText, envCopyBtn, envStatus);",
            "      });",
            "    }",
            "    renderLogs();",
            "    renderStatusChart();",
            "    const buildReport = () => {",
            "      const cases = [];",
            "      document.querySelectorAll('.case').forEach((card) => {",
            "        const key = card.getAttribute('data-case-key');",
            "        const title = card.getAttribute('data-case-title');",
            "        const checkbox = card.querySelector('.case-check');",
            "        const notes = card.querySelector('.case-notes');",
            "        const actual = card.querySelector('.case-actual');",
            "        const status = card.querySelector('.case-status');",
            "        const images = Array.from(card.querySelectorAll('.case-proof img')).map((img) => img.src);",
            "        const bugInput = card.querySelector('.bug-link-input');",
            "        const bugLink = bugInput ? bugInput.value.trim() : '';",
            "        cases.push({",
            "          key,",
            "          title,",
            "          checked: checkbox.checked,",
            "          status: status.value,",
            "          notes: notes.value,",
                "          actual_result: actual ? actual.value : '',",
                "          bug_link: bugLink,",
            "          images,",
            "        });",
            "      });",
            "      return {",
            "        title: document.title,",
            "        generatedAt: new Date().toISOString(),",
            "        collector: state.meta.collector || document.getElementById('collector').value || '',",
            "        environment: {",
            "          platform: document.getElementById('env-platform').value || '',",
            "          os_version: document.getElementById('env-os').value || '',",
            "          app_version: document.getElementById('env-version').value || '',",
            "          revision: document.getElementById('env-revision').value || '',",
            "          channels: Array.from(document.querySelectorAll('.env-channel')).filter((box) => box.checked).map((box) => box.value),",
            "        },",
            "        logs: state.logs || [],",
            "        cases,",
            "      };",
            "    };",
            "    class IssueHelper {",
            "      constructor() {",
            "        this.modal = document.getElementById('issue-modal');",
            "        this.repoInput = document.getElementById('issue-repo');",
            "        this.titleInput = document.getElementById('issue-title');",
            "        this.bodyInput = document.getElementById('issue-body');",
            "        this.openBtn = document.getElementById('issue-open');",
            "        this.closeBtn = document.getElementById('issue-close');",
            "        this.currentCard = null;",
            "        this.bind();",
            "      }",
            "      bind() {",
            "        document.querySelectorAll('[data-action=\"open-issue\"]').forEach((btn) => {",
            "          btn.addEventListener('click', () => {",
            "            const card = btn.closest('.case');",
            "            if (card) this.open(card);",
            "          });",
            "        });",
            "        if (this.closeBtn) this.closeBtn.addEventListener('click', () => this.close());",
            "        if (this.openBtn) this.openBtn.addEventListener('click', () => this.openGitHub());",
            "      }",
            "      open(card) {",
            "        this.currentCard = card;",
            "        const issue = this.buildIssue(card);",
            "        this.titleInput.value = issue.title;",
            "        this.bodyInput.value = issue.body;",
            "        this.modal.classList.add('open');",
            "      }",
            "      close() {",
            "        this.modal.classList.remove('open');",
            "      }",
            "      openGitHub() {",
            "        const repo = (this.repoInput.value || '').trim().replace(/\\/+$/, '');",
            "        if (!repo) return;",
            "        const title = this.titleInput.value || 'Bug report';",
            "        const body = this.bodyInput.value || '';",
            "        const url = `${repo}/issues/new?title=${encodeURIComponent(title)}&body=${encodeURIComponent(body)}`;",
            "        window.open(url, '_blank');",
            "      }",
            "      buildIssue(card) {",
            "        const title = card.getAttribute('data-case-title') || 'Bug report';",
            "        const status = card.querySelector('.case-status')?.value || 'not_set';",
            "        const steps = Array.from(card.querySelectorAll('ol li')).map((li) => li.textContent.trim());",
            "        const notes = card.querySelector('.case-notes')?.value || '';",
            "        const actual = card.querySelector('.case-actual')?.value || '';",
            "        const attachments = Array.from(card.querySelectorAll('.case-proof img')).map((img, idx) => {",
            "          const name = img.dataset.name || `screenshot-${idx + 1}`;",
            "          return `${name}: ${img.src}`;",
            "        });",
            "        const env = buildReport().environment;",
            "        const qa = (document.getElementById('collector')?.value || '').trim();",
            "        const body = [",
            "          `### Summary`,",
            "          `- Case: ${title}` ,",
            "          `- Status: ${status}` ,",
            "          qa ? `- QA: ${qa}` : '',",
            "          '',",
            "          `### Environment`,",
            "          `- Platform: ${env.platform}` ,",
            "          `- OS version: ${env.os_version}` ,",
            "          `- App version: ${env.app_version}` ,",
            "          `- Revision: ${env.revision}` ,",
            "          `- Channel: ${(env.channels || []).join(', ')}` ,",
            "          '',",
            "          steps.length ? `### Steps\\n${steps.map((s, i) => `${i + 1}. ${s}`).join('\\n')}` : '',",
            "          notes ? `### Notes\\n${notes}` : '',",
            "          actual ? `### Actual result\\n${actual}` : '',",
            "          attachments.length ? `### Attachments\\n${attachments.join('\\n')}` : ''",
            "        ].filter(Boolean).join('\\n');",
            "        const prefix = this.titleInput?.value?.split(':')[0] || 'Bug';",
            "        return { title: `${prefix}: ${title}`, body };",
            "      }",
            "    }",
            "    new IssueHelper();",
            "    const downloadFile = (filename, content, type) => {",
            "      const blob = new Blob([content], { type });",
            "      const url = URL.createObjectURL(blob);",
            "      const link = document.createElement('a');",
            "      link.href = url;",
            "      link.download = filename;",
            "      document.body.appendChild(link);",
            "      link.click();",
            "      link.remove();",
            "      setTimeout(() => URL.revokeObjectURL(url), 1000);",
            "    };",
            "    const exportHtml = (filename, isFinal) => {",
            "      const clone = document.documentElement.cloneNode(true);",
            "      const originalCollector = document.getElementById('collector');",
            "      const originalStatusMap = {};",
            "      const originalChannels = new Set(Array.from(document.querySelectorAll('.env-channel')).filter((b) => b.checked).map((b) => b.value));",
            "      document.querySelectorAll('.case').forEach((card) => {",
            "        const key = card.getAttribute('data-case-key');",
            "        const status = card.querySelector('.case-status');",
            "        if (key && status) originalStatusMap[key] = status.value;",
            "      });",
            "      clone.querySelectorAll('.case').forEach((card) => {",
            "        const checkbox = card.querySelector('.case-check');",
            "        const notes = card.querySelector('.case-notes');",
                "        const actual = card.querySelector('.case-actual');",
            "        const status = card.querySelector('.case-status');",
            "        const bugInput = card.querySelector('.bug-link-input');",
            "        if (checkbox && checkbox.checked) {",
            "          checkbox.setAttribute('checked', 'checked');",
            "        } else if (checkbox) {",
            "          checkbox.removeAttribute('checked');",
            "        }",
            "        if (notes) {",
            "          notes.textContent = notes.value;",
            "        }",
                "        if (actual) {",
                "          actual.textContent = actual.value;",
                "        }",
            "        if (status) {",
            "          status.querySelectorAll('option').forEach((opt) => {",
            "            if (opt.value === status.value) {",
            "              opt.setAttribute('selected', 'selected');",
            "            } else {",
            "              opt.removeAttribute('selected');",
            "            }",
            "          });",
            "        }",
            "        if (bugInput) {",
            "          bugInput.setAttribute('value', bugInput.value);",
            "        }",
            "      });",
            "      clone.querySelectorAll('input').forEach((input) => {",
            "        if (input.type === 'checkbox') {",
            "          if (input.classList.contains('env-channel')) {",
            "            if (originalChannels.has(input.value)) {",
            "              input.setAttribute('checked', 'checked');",
            "              input.checked = true;",
            "            } else {",
            "              input.removeAttribute('checked');",
            "              input.checked = false;",
            "            }",
            "          } else if (input.checked) {",
            "            input.setAttribute('checked', 'checked');",
            "          } else {",
            "            input.removeAttribute('checked');",
            "          }",
            "          return;",
            "        }",
            "        input.setAttribute('value', input.value);",
            "      });",
            "      clone.querySelectorAll('select').forEach((select) => {",
            "        let selectedValue = select.value;",
            "        if (select.id === 'collector' && originalCollector) {",
            "          selectedValue = originalCollector.value;",
            "        }",
            "        if (select.classList.contains('case-status')) {",
            "          const card = select.closest('.case');",
            "          const key = card ? card.getAttribute('data-case-key') : null;",
            "          if (key && originalStatusMap[key]) selectedValue = originalStatusMap[key];",
            "        }",
            "        select.querySelectorAll('option').forEach((opt) => {",
            "          if (opt.value === selectedValue) {",
            "            opt.setAttribute('selected', 'selected');",
            "          } else {",
            "            opt.removeAttribute('selected');",
            "          }",
            "        });",
            "      });",
            "      clone.querySelectorAll('textarea').forEach((area) => {",
            "        area.textContent = area.value;",
            "      });",
            "      const envText = [",
            "        `Platform: ${document.getElementById('env-platform').value || ''}`,",
            "        `OS version: ${document.getElementById('env-os').value || ''}`,",
            "        `App version: ${document.getElementById('env-version').value || ''}`,",
            "        `Revision: ${document.getElementById('env-revision').value || ''}`,",
            "        `Channel: ${Array.from(originalChannels).join(', ')}`",
            "      ].join('\\n');",
            "      const originalCases = {};",
            "      document.querySelectorAll('.case').forEach((card) => {",
            "        const key = card.getAttribute('data-case-key');",
            "        const title = card.getAttribute('data-case-title') || key;",
            "        const status = card.querySelector('.case-status')?.value || 'not_set';",
            "        const steps = Array.from(card.querySelectorAll('ol li')).map((li) => li.textContent.trim());",
            "        const notes = card.querySelector('.case-notes')?.value || '';",
            "        const actual = card.querySelector('.case-actual')?.value || '';",
            "        const bug = card.querySelector('.bug-link-input')?.value || '';",
            "        const attachments = Array.from(card.querySelectorAll('.case-proof img')).map((img, idx) => {",
            "          const name = img.dataset.name || `screenshot-${idx + 1}`;",
            "          return `${name}: ${img.src}`;",
            "        });",
            "        const summary = [",
            "          `Title: ${title}`,",
            "          `Status: ${status}`,",
            "          bug ? `Bug: ${bug}` : '',",
            "          steps.length ? `Steps:\\n${steps.map((s, i) => `${i + 1}. ${s}`).join('\\n')}` : '',",
            "          notes ? `Notes:\\n${notes}` : '',",
            "          actual ? `Actual result:\\n${actual}` : '',",
            "          attachments.length ? `Attachments:\\n${attachments.join('\\n')}` : ''",
            "        ].filter(Boolean).join('\\n\\n');",
            "        originalCases[key] = { steps: steps.map((s, i) => `${i + 1}. ${s}`).join('\\n'), notes, actual, bug, attachments: attachments.join('\\n'), summary };",
            "      });",
            "      const envCopyBtn = clone.querySelector('.env-copy .copy-btn');",
            "      if (envCopyBtn) envCopyBtn.setAttribute('data-copy-text', envText);",
            "      clone.querySelectorAll('.case').forEach((card) => {",
            "        const key = card.getAttribute('data-case-key');",
            "        const data = originalCases[key] || {};",
            "        card.querySelectorAll('.copy-btn').forEach((btn) => {",
            "          const kind = btn.getAttribute('data-copy');",
            "          if (kind === 'steps') btn.setAttribute('data-copy-text', data.steps || '');",
            "          if (kind === 'notes') btn.setAttribute('data-copy-text', data.notes || '');",
            "          if (kind === 'actual') btn.setAttribute('data-copy-text', data.actual || '');",
            "          if (kind === 'attachments') btn.setAttribute('data-copy-text', data.attachments || '');",
            "          if (kind === 'summary') btn.setAttribute('data-copy-text', data.summary || '');",
            "          if (kind === 'bug') btn.setAttribute('data-copy-text', data.bug || '');",
            "        });",
            "      });",
            "      const report = buildReport();",
            "      const reportJson = JSON.stringify(report, null, 2);",
            "      const reportPre = clone.querySelector('#qa-report-data');",
            "      if (reportPre) reportPre.textContent = reportJson;",
            "      const reportScript = clone.querySelector('#qa-report-json');",
            "      if (reportScript) reportScript.textContent = reportJson;",
            "      if (isFinal) {",
            "        clone.querySelectorAll('button').forEach((btn) => {",
            "          if (!btn.classList.contains('copy-btn')) btn.remove();",
            "        });",
            "        clone.querySelectorAll('.env-clear').forEach((btn) => btn.remove());",
            "        clone.querySelectorAll('input[type=\"file\"]').forEach((input) => input.remove());",
            "        clone.querySelectorAll('input').forEach((input) => {",
            "          if (input.type === 'checkbox') {",
            "            input.disabled = true;",
            "          } else {",
            "            input.readOnly = true;",
            "          }",
            "        });",
            "        clone.querySelectorAll('select').forEach((select) => {",
            "          select.disabled = true;",
            "        });",
            "        clone.querySelectorAll('textarea').forEach((area) => {",
            "          area.readOnly = true;",
            "        });",
            "        clone.querySelectorAll('script').forEach((script) => script.remove());",
            "        const copyScript = clone.ownerDocument.createElement('script');",
            "        copyScript.textContent = `",
            "          document.querySelectorAll('.copy-btn').forEach((btn) => {",
            "            btn.addEventListener('click', () => {",
            "              const text = btn.getAttribute('data-copy-text') || '';",
            "              if (!text) return;",
            "              const status = btn.closest('.block-head')?.querySelector('.copy-status') || btn.parentElement?.querySelector('.copy-status');",
            "              if (navigator.clipboard && navigator.clipboard.writeText) {",
            "                navigator.clipboard.writeText(text);",
            "              } else {",
            "                const area = document.createElement('textarea');",
            "                area.value = text;",
            "                document.body.appendChild(area);",
            "                area.select();",
            "                document.execCommand('copy');",
            "                area.remove();",
            "              }",
            "              btn.classList.add('copied');",
            "              if (status) {",
            "                status.textContent = 'Copied';",
            "                status.classList.add('show');",
            "                setTimeout(() => {",
            "                  status.textContent = '';",
            "                  status.classList.remove('show');",
            "                }, 1500);",
            "              }",
            "              setTimeout(() => btn.classList.remove('copied'), 1500);",
            "            });",
            "          });",
            "        `;",
            "        const cloneBody = clone.querySelector('body');",
            "        if (cloneBody) cloneBody.appendChild(copyScript);",
            "      }",
            "      const htmlContent = '<!doctype html>\\n' + clone.outerHTML;",
            "      if (!isFinal) {",
            "        downloadFile(filename, htmlContent, 'text/html');",
            "      }",
            "      return htmlContent;",
            "    };",
            "    document.getElementById('export-json').addEventListener('click', () => {",
            "      const report = buildReport();",
            "      const filename = `${slugify(report.title)}-report.json`;",
            "      downloadFile(filename, JSON.stringify(report, null, 2), 'application/json');",
            "    });",
            "    document.getElementById('export-log').addEventListener('click', () => {",
            "      const report = buildReport();",
            "      const filename = `${slugify(report.title)}-activity-log.json`;",
            "      downloadFile(filename, JSON.stringify(report.logs || [], null, 2), 'application/json');",
            "    });",
            "    document.getElementById('save-final').addEventListener('click', async () => {",
            "      const filename = `${baseFileName}-final.html`;",
            "      const htmlContent = exportHtml(filename, true);",
            "      if (window.showSaveFilePicker) {",
            "        try {",
            "          const handle = await window.showSaveFilePicker({",
            "            suggestedName: filename,",
            "            types: [{ description: 'HTML File', accept: { 'text/html': ['.html'] } }],",
            "          });",
            "          const writable = await handle.createWritable();",
            "          await writable.write(htmlContent);",
            "          await writable.close();",
            "          return;",
            "        } catch (err) {",
            "          // fall back to download",
            "        }",
            "      }",
            "      downloadFile(filename, htmlContent, 'text/html');",
            "    });",
            "  </script>",
            "</body>",
            "</html>",
        ]
    )
    return "\n".join(lines) + "\n"


def resolve_output_path(data, input_path, output_dir, run_id, environment, run_name):
    if data.get("output_html"):
        return resolve_path(input_path.parent, data["output_html"])
    output_dir = Path(output_dir)
    if not output_dir.is_absolute():
        script_dir = Path(__file__).resolve().parent
        output_dir = (script_dir / output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    app_version = environment.get("app_version") or "unknown"
    base_name = (
        f"{slugify(run_name)}-"
        f"{slugify(app_version)}-"
        f"{run_id[:13].replace('T', '-')}"
    )
    candidate = output_dir / f"{base_name}.html"
    if not candidate.exists():
        return candidate
    counter = 2
    while True:
        candidate = output_dir / f"{base_name}-{counter}.html"
        if not candidate.exists():
            return candidate
        counter += 1


def get_milestone(repo, title):
    if not title:
        return None
    for milestone in repo.get_milestones(state="open"):
        if milestone.title == title:
            return milestone
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Path to JSON checklist")
    parser.add_argument("--output-dir", default="history", help="HTML output folder")
    parser.add_argument("--repo", help="GitHub repo, e.g. brave/brave-browser")
    parser.add_argument("--milestone", help="Milestone title override")
    parser.add_argument("--collector", help="Collector name")
    parser.add_argument("--run-name", help="Run name for output filename")
    open_group = parser.add_mutually_exclusive_group()
    open_group.add_argument(
        "--open",
        dest="open_html",
        action="store_true",
        help="Open HTML output in browser (default)",
    )
    open_group.add_argument(
        "--no-open",
        dest="open_html",
        action="store_false",
        help="Do not open HTML output",
    )
    parser.add_argument(
        "--test",
        nargs="?",
        const=True,
        default=False,
        type=parse_bool,
        help="Test Mode, do not create Github issues",
    )
    parser.set_defaults(open_html=True)
    args = parser.parse_args()

    input_path = Path(args.input).expanduser().resolve()
    data, description_md = load_input(input_path)

    repo_name = args.repo or data.get("repo")
    if not repo_name:
        raise ValueError("Missing repo. Provide --repo or repo in JSON.")

    token = read_token()
    if not token:
        raise ValueError("github.secret is empty")

    github = Github(token, timeout=1000)
    repo = github.get_repo(repo_name)

    milestone_title = args.milestone or data.get("milestone")
    milestone = get_milestone(repo, milestone_title)
    if milestone_title and not milestone:
        print(f"Warning: milestone not found: {milestone_title}")

    run_id = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    environment = normalize_environment(data)
    metadata = {
        "collector": args.collector or data.get("collector", ""),
        "environment": environment,
        "environment_templates": normalize_templates(data),
    }
    run_name = args.run_name or data.get("run_name") or data["title"]
    markdown_body = render_markdown(data["title"], description_md, data["cases"])
    html_body = render_html(
        data["title"], description_md, data["cases"], metadata, run_id, run_name
    )

    output_path = resolve_output_path(
        data, input_path, args.output_dir, run_id, environment, run_name
    )
    output_path.write_text(html_body)
    print(f"HTML output written to: {output_path}")
    if args.open_html:
        webbrowser.open(output_path.as_uri())

    issue_title = data.get("issue_title", f"Custom checklist: {data['title']}")
    labels = data.get("labels", [])

    if args.test:
        print("\n--- Test mode ---")
        print(f"Issue title: {issue_title}")
        print(f"Repo: {repo_name}")
        if milestone:
            print(f"Milestone: {milestone.title}")
        if labels:
            print(f"Labels: {', '.join(labels)}")
        print("\nIssue body preview:\n")
        print(markdown_body)
        return 0

    repo.create_issue(
        title=issue_title,
        body=markdown_body,
        milestone=milestone,
        labels=labels,
    )
    print("Issue created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
