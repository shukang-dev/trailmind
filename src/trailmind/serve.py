from __future__ import annotations

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Trailmind — {repo_name}</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #f0f2f5;
      --panel: #ffffff;
      --ink: #1a1d23;
      --muted: #6b7280;
      --line: #e2e5ea;
      --accent: #2563eb;
      --accent-soft: #eff6ff;
      --accent-ink: #1d4ed8;
      --success: #059669;
      --success-soft: #ecfdf5;
      --warning: #d97706;
      --warning-soft: #fffbeb;
      --danger: #dc2626;
      --danger-soft: #fef2f2;
      --info: #7c3aed;
      --info-soft: #f5f3ff;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #0f1117;
        --panel: #1a1d27;
        --ink: #e4e6eb;
        --muted: #9ca3af;
        --line: #2a2e3a;
        --accent: #60a5fa;
        --accent-soft: #1e3a5f;
        --accent-ink: #93c5fd;
        --success: #34d399;
        --success-soft: #064e3b;
        --warning: #fbbf24;
        --warning-soft: #451a03;
        --danger: #f87171;
        --danger-soft: #450a0a;
        --info: #a78bfa;
        --info-soft: #2e1065;
      }}
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      color: var(--ink);
      background: var(--bg);
      line-height: 1.5;
    }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    main {{ max-width: 1200px; margin: 0 auto; padding: 32px 24px 48px; }}
    header {{ margin-bottom: 28px; }}
    header h1 {{ margin: 0 0 4px; font-size: 1.75rem; font-weight: 700; letter-spacing: -0.02em; }}
    header .subtitle {{ color: var(--muted); font-size: 0.95rem; }}
    header .repo-path {{
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 0.8rem; color: var(--muted);
      background: var(--bg); padding: 2px 8px; border-radius: 4px; display: inline-block;
    }}
    .metrics {{ display: flex; flex-wrap: wrap; gap: 10px; margin-top: 16px; }}
    .metric {{
      min-width: 120px; border: 1px solid var(--line); border-radius: 10px;
      background: var(--panel); padding: 14px 16px;
    }}
    .metric strong {{ display: block; font-size: 1.6rem; font-weight: 700; line-height: 1.1; }}
    .metric span {{ color: var(--muted); font-size: 0.82rem; }}
    .metric.overdue {{ border-color: var(--danger); background: var(--danger-soft); }}
    .metric.overdue strong {{ color: var(--danger); }}
    section {{ margin-top: 28px; }}
    section h2 {{
      font-size: 1.05rem; font-weight: 600; margin: 0 0 12px;
      display: flex; align-items: center; gap: 8px;
    }}
    section h2 .count-badge {{
      font-size: 0.78rem; font-weight: 500;
      background: var(--bg); color: var(--muted);
      padding: 2px 8px; border-radius: 999px;
    }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 14px; }}
    .card {{
      border: 1px solid var(--line); border-radius: 12px;
      background: var(--panel); padding: 18px;
      transition: box-shadow 0.15s, border-color 0.15s;
      text-decoration: none; color: inherit; display: block;
    }}
    .card:hover {{ box-shadow: 0 4px 12px rgba(0,0,0,0.1); border-color: var(--accent); text-decoration: none; }}
    .card h3 {{ margin: 0 0 4px; font-size: 1.1rem; font-weight: 600; }}
    .card .card-desc {{ color: var(--muted); font-size: 0.88rem; margin: 0 0 10px; line-height: 1.45; }}
    .card .card-meta {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }}
    .card .card-path {{
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 0.75rem; color: var(--muted); margin-top: 10px;
    }}
    .card .card-arrow {{ float: right; color: var(--muted); font-size: 1.2rem; transition: transform 0.15s; }}
    .card:hover .card-arrow {{ color: var(--accent); transform: translateX(3px); }}
    .card .card-stats {{
      display: flex; gap: 12px; margin-top: 12px; padding-top: 12px;
      border-top: 1px solid var(--line);
    }}
    .card .card-stat {{ font-size: 0.82rem; color: var(--muted); }}
    .card .card-stat strong {{ color: var(--ink); font-weight: 600; }}
    .pill {{
      display: inline-flex; align-items: center;
      padding: 3px 10px; border-radius: 999px;
      font-size: 0.78rem; font-weight: 500; white-space: nowrap;
      background: var(--accent-soft); color: var(--accent-ink);
    }}
    .pill.state-active {{ background: var(--success-soft); color: var(--success); }}
    .pill.state-completed {{ background: var(--muted); color: #fff; }}
    .pill.state-paused {{ background: var(--warning-soft); color: var(--warning); }}
    .pill.state-planning {{ background: var(--info-soft); color: var(--info); }}
    .pill.state-archived, .pill.state-cancelled {{ background: var(--bg); color: var(--muted); }}
    .progress-bar {{ height: 6px; background: var(--bg); border-radius: 3px; overflow: hidden; margin-top: 10px; }}
    .progress-bar .fill {{ height: 100%; background: var(--success); border-radius: 3px; transition: width 0.3s; }}
    .epic-list {{ margin-top: 8px; }}
    .epic-item {{
      display: flex; align-items: center; justify-content: space-between;
      padding: 8px 12px; border-radius: 8px; margin-bottom: 4px;
      transition: background 0.15s;
    }}
    .epic-item:hover {{ background: var(--accent-soft); text-decoration: none; }}
    .epic-item .epic-title {{ font-weight: 500; font-size: 0.92rem; }}
    .epic-item .epic-state {{ font-size: 0.75rem; color: var(--muted); }}
    .empty {{ border: 1px dashed var(--line); border-radius: 10px; padding: 28px; text-align: center; color: var(--muted); }}
    .breakdown {{ display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }}
    .breakdown-item {{
      font-size: 0.78rem; color: var(--muted);
      padding: 3px 10px; border-radius: 999px;
      background: var(--panel); border: 1px solid var(--line);
    }}
    .breakdown-item.overdue {{ color: var(--danger); background: var(--danger-soft); border-color: var(--danger); }}
    @media (max-width: 640px) {{
      main {{ padding: 16px 14px 32px; }}
      .metric {{ min-width: 100px; padding: 10px 12px; }}
      .metric strong {{ font-size: 1.3rem; }}
      .grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <h1>Trailmind</h1>
      <p class="subtitle">{repo_name} — project dashboard index</p>
      <span class="repo-path">{repo_path}</span>
    </header>
{overview_link}
{project_cards}
{epic_links}
  </main>
</body>
</html>
"""


def _discover_dashboards(repo_root: Path) -> dict:
    """Discover all dashboard files in the repo."""
    projects = []
    all_epics = []

    projects_dir = repo_root / "projects"
    if not projects_dir.exists():
        return {"projects": projects, "epics": all_epics, "overview": (repo_root / "overview.html").exists()}

    for proj_dir in sorted(projects_dir.iterdir()):
        if not proj_dir.is_dir():
            continue
        proj_md = proj_dir / "PROJECT.md"
        if not proj_md.exists():
            continue

        # Parse project frontmatter
        proj_info = {"slug": proj_dir.name, "title": proj_dir.name, "goal": "", "state": "active",
                     "owners": [], "tags": [], "epics": [], "dashboard": (proj_dir / "dashboard.html").exists()}
        try:
            from trailmind.log import read_entity_user_facing
            fm, body = read_entity_user_facing(proj_md, label="project")
            proj_info["title"] = str(fm.get("title") or proj_dir.name)
            proj_info["goal"] = str(fm.get("goal") or "")
            proj_info["state"] = str(fm.get("state") or "active")
            proj_info["owners"] = [str(o) for o in (fm.get("owners") or [])]
            proj_info["tags"] = [str(t) for t in (fm.get("tags") or [])]
        except Exception:
            pass

        # Discover epics
        epics = []
        for epic_dir in sorted(proj_dir.iterdir()):
            if not epic_dir.is_dir():
                continue
            epic_md = epic_dir / "EPIC.md"
            if not epic_md.exists():
                continue

            epic_info = {"slug": epic_dir.name, "title": epic_dir.name, "goal": "",
                         "state": "active", "target": "", "task_count": 0, "issue_count": 0,
                         "milestone_count": 0, "spec_count": 0, "plan_count": 0,
                         "task_done_count": 0,
                         "dashboard": (epic_dir / "dashboard.html").exists(),
                         "relative_path": f"projects/{proj_dir.name}/{epic_dir.name}"}
            try:
                from trailmind.log import read_entity_user_facing
                fm, _body = read_entity_user_facing(epic_md, label="epic")
                epic_info["title"] = str(fm.get("title") or epic_dir.name)
                epic_info["goal"] = str(fm.get("goal") or "")
                epic_info["state"] = str(fm.get("state") or "active")
                epic_info["target"] = str(fm.get("target") or "")
            except Exception:
                pass

            # Count entities
            for label, count_key in [("tasks", "task_count"), ("issues", "issue_count"),
                                       ("milestones", "milestone_count")]:
                d = epic_dir / label
                if d.exists():
                    files = [f for f in d.iterdir() if f.is_file() and f.suffix == ".md"]
                    epic_info[count_key] = len(files)
                    if label == "tasks":
                        from trailmind.log import read_entity_user_facing
                        done = 0
                        for f in files:
                            try:
                                fm2, _ = read_entity_user_facing(f, label="task")
                                if str(fm2.get("status")) == "done":
                                    done += 1
                            except Exception:
                                pass
                        epic_info["task_done_count"] = done

            for label, count_key in [("specs", "spec_count"), ("plans", "plan_count")]:
                d = epic_dir / "docs" / label
                if d.exists():
                    epic_info[count_key] = len([f for f in d.iterdir() if f.is_file() and f.suffix == ".md"])

            epics.append(epic_info)
            all_epics.append(epic_info)

        proj_info["epics"] = epics
        proj_info["epic_count"] = len(epics)
        projects.append(proj_info)

    return {
        "projects": projects,
        "epics": all_epics,
        "overview": (repo_root / "overview.html").exists(),
    }


def _render_index(repo_root: Path) -> str:
    """Render the index page HTML."""
    data = _discover_dashboards(repo_root)

    # Overview link
    overview_link = ""
    if data["overview"]:
        overview_link = f"""
    <div class="metrics">
      <a href="overview.html" class="metric" style="text-decoration:none;color:inherit;">
        <strong>📊</strong><span>Overview Dashboard</span>
      </a>
    </div>"""

    # Project cards
    project_cards = ""
    if data["projects"]:
        cards_html = []
        for proj in data["projects"]:
            epics_html = ""
            if proj["epics"]:
                epic_items = []
                for epic in proj["epics"]:
                    done = epic["task_done_count"]
                    total = epic["task_count"]
                    pct = int(done / total * 100) if total > 0 else 0
                    link = f"{epic['relative_path']}/dashboard.html" if epic["dashboard"] else "#"
                    epic_items.append(f"""
            <a href="{link}" class="epic-item">
              <span class="epic-title">{epic['title']}</span>
              <span class="epic-state">{epic['state']}</span>
            </a>""")
                if epic_items:
                    epics_html = f'<div class="epic-list">{"".join(epic_items)}</div>'

            proj_link = f"projects/{proj['slug']}/dashboard.html" if proj["dashboard"] else "#"
            cards_html.append(f"""
        <a href="{proj_link}" class="card">
          <span class="card-arrow">→</span>
          <h3>{proj['title']}</h3>
          <p class="card-desc">{proj['goal']}</p>
          <div class="card-meta">
            <span class="pill">{proj['slug']}</span>
            <span class="pill state-{proj['state']}">{proj['state']}</span>
            <span class="pill">{proj['epic_count']} epics</span>
          </div>
          {epics_html}
        </a>""")

        project_cards = f"""
    <section>
      <h2>Projects <span class="count-badge">{len(data['projects'])}</span></h2>
      <div class="grid">
        {"".join(cards_html)}
      </div>
    </section>"""
    else:
        project_cards = """
    <section class="empty">
      <h2>No projects found</h2>
      <p>Run <code>trailmind status --overview</code> to generate dashboards.</p>
    </section>"""

    # All epics quick links
    epic_links = ""
    if len(data["epics"]) > 3:
        links = []
        for e in sorted(data["epics"], key=lambda x: x["state"] != "active"):
            link = f"{e['relative_path']}/dashboard.html" if e["dashboard"] else "#"
            links.append(f'<a href="{link}" class="epic-item">'
                         f'<span class="epic-title">{e["title"]}</span>'
                         f'<span class="epic-state">{e["state"]}</span></a>')
        epic_links = f"""
    <section>
      <h2>All Epics <span class="count-badge">{len(data['epics'])}</span></h2>
      <div class="epic-list">
        {"".join(links)}
      </div>
    </section>"""

    return INDEX_HTML.format(
        repo_name=repo_root.name,
        repo_path=str(repo_root),
        overview_link=overview_link,
        project_cards=project_cards,
        epic_links=epic_links,
    )


class TrailmindHTTPRequestHandler(SimpleHTTPRequestHandler):
    """Custom handler that serves a generated index page."""

    repo_root: Path = Path.cwd()

    def do_GET(self) -> None:  # noqa: N802
        parsed_path = unquote(self.path.split("?")[0].split("#")[0])

        # Serve the index page for root or /index.html
        if parsed_path in ("/", "/index.html"):
            try:
                content = _render_index(self.repo_root)
                encoded = content.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
                return
            except Exception as e:
                self.send_error(500, f"Failed to render index: {e}")
                return

        # Fall back to default file serving
        super().do_GET()

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        """Suppress default logging for cleaner output."""
        pass


def serve_repo(repo_root: Path, *, host: str, port: int) -> None:
    handler = partial(TrailmindHTTPRequestHandler, directory=str(repo_root))
    handler.func_defaults = None
    # Set repo_root on the handler class
    TrailmindHTTPRequestHandler.repo_root = repo_root
    server = ThreadingHTTPServer((host, port), handler)
    url = f"http://{host}:{server.server_port}/"
    print(f"Trailmind dashboard server running at {url}")
    print(f"  Serving: {repo_root}")
    print(f"  Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
    finally:
        server.server_close()
