#!/usr/bin/env python3
"""Turn a Playwright journey run into journeys/index.html.

Journeys down the left, the recording of the selected one on the right, with
its screenshots as a filmstrip underneath. Reads what the json reporter wrote;
nothing here needs to know about the app being tested.

    PLAYWRIGHT_BASE_URL=http://localhost:5173 \
      npx playwright test -c playwright.journeys.config.ts
    python3 scripts/build_report.py

Descriptions are optional. Put a title -> sentence map in
journeys/descriptions.json and the order of that file becomes the order of the
report, which is how the walk-through gets its shape.
"""

from __future__ import annotations

import html
import json
import sys
from datetime import datetime
from pathlib import Path

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "journeys").resolve()
RESULTS = OUT / "results.json"
DESCRIPTIONS = OUT / "descriptions.json"

LABEL = {"passed": ("ok", "passed"), "failed": ("bad", "failed"),
         "timedOut": ("bad", "timed out"), "skipped": ("skip", "skipped"),
         "flaky": ("skip", "flaky")}


def specs(suite: dict) -> list[dict]:
    """Every spec in a suite, however deeply nested."""
    out = list(suite.get("specs", []))
    for child in suite.get("suites", []):
        out += specs(child)
    return out


def relative(path: str) -> str:
    """A path the HTML can use, or "" if it sits outside the report folder."""
    if not path:
        return ""
    try:
        return Path(path).resolve().relative_to(OUT).as_posix()
    except ValueError:
        return ""


def collect() -> list[dict]:
    report = json.loads(RESULTS.read_text())
    described: dict[str, str] = {}
    if DESCRIPTIONS.exists():
        described = json.loads(DESCRIPTIONS.read_text())

    # Label each journey with its project ("· desktop", "· phone") only when the
    # run had more than one. Playwright writes each project's run as its own spec.
    projects = {t.get("projectName", "") for suite in report.get("suites", [])
                for spec in specs(suite) for t in spec["tests"]}

    found = []
    for suite in report.get("suites", []):
        for spec in specs(suite):
            for test in spec["tests"]:  # one per project: desktop, phone
                result = test["results"][-1]  # the last try, after any retry
                attachments = result.get("attachments", [])
                video = next((a.get("path", "") for a in attachments if a["name"] == "video"), "")
                # Everything else that is an image: the stills a journey took with
                # shot(), plus Playwright's own end-of-test screenshot.
                stills = [
                    {"caption": a["name"], "src": relative(a.get("path", ""))}
                    for a in attachments
                    if a.get("contentType", "").startswith("image/")
                ]
                # What the page complained about: 4xx/5xx, failed requests,
                # console errors. A journey can pass with all of that behind it,
                # so the report shows it rather than leaving it in a trace file
                # nobody opens.
                noise = ""
                for a in attachments:
                    if a["name"] == "network and console":
                        body = a.get("body", "")
                        noise = (Path(a["path"]).read_text(errors="replace")
                                 if a.get("path") and Path(a["path"]).exists() else body)
                found.append({
                    "noise": noise,
                    "title": spec["title"] + (f" · {test.get('projectName')}" if len(projects) > 1 else ""),
                    "base": spec["title"],
                    "project": test.get("projectName", ""),
                    "why": described.get(spec["title"], ""),
                    "status": ("skipped" if test.get("status") == "skipped"
                               else "flaky" if test.get("status") == "flaky" else result["status"]),
                    "video": relative(video),
                    "stills": [s for s in stills if s["src"]],
                })

    order = list(described)
    # Description order first, then desktop before phone for the same journey.
    found.sort(key=lambda j: (order.index(j["base"]) if j["base"] in order else len(order),
                              j["project"] != "desktop"))
    return found


def strip(j: dict) -> str:
    if not j["stills"]:
        return ""
    cells = "".join(
        f'<figure><img src="{html.escape(s["src"])}" alt="{html.escape(s["caption"])}" loading="lazy">'
        f'<figcaption>{html.escape(s["caption"])}</figcaption></figure>'
        for s in j["stills"]
    )
    return f'<div class="strip">{cells}</div>'


def noise(j: dict) -> str:
    if not j.get("noise"):
        return ""
    lines = j["noise"].strip().splitlines()
    return (f'<details class="noise"><summary>{len(lines)} network or console '
            f'problem{"" if len(lines) == 1 else "s"} during this journey</summary>'
            f'<pre>{html.escape(j["noise"])}</pre></details>')


def build() -> Path:
    items = collect()
    if not items:
        raise SystemExit(f"no journeys in {RESULTS} — did the suite run?")
    passed = sum(1 for j in items if j["status"] == "passed")

    panes = "\n".join(
        f'''<div class="pane" id="p{i}" {"" if i == 0 else "hidden"}>
          <h2>{html.escape(j["title"])}</h2>
          <p class="why">{html.escape(j["why"])}</p>
          {f'<video src="{html.escape(j["video"])}" controls autoplay muted loop playsinline preload="metadata"></video>'
           if j["video"] else '<p class="none">No recording for this journey.</p>'}
          {strip(j)}
          {noise(j)}
        </div>'''
        for i, j in enumerate(items)
    )
    rows = "\n".join(
        f'''<li><button class="j" data-pane="p{i}" {"data-selected" if i == 0 else ""}>
          <span class="n">{i + 1}</span>
          <span class="body"><span class="t">{html.escape(j["title"])}</span>
          <span class="w">{html.escape(j["why"])}</span></span>
          <span class="s {LABEL.get(j["status"], ("bad", j["status"]))[0]}">{LABEL.get(j["status"], ("bad", j["status"]))[1]}</span>
        </button></li>'''
        for i, j in enumerate(items)
    )

    out = OUT / "index.html"
    out.write_text(TEMPLATE.format(
        rows=rows, panes=panes, count=len(items), passed=passed,
        when=datetime.now().astimezone().strftime("%d %b %Y, %H:%M %Z"),
    ))
    return out


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>User journeys</title>
<style>
  :root {{
    --bg:#0e1012; --surface:#16191c; --surface-2:#1e2226; --border:#2a2f35;
    --text:#e6e9ec; --dim:#9aa4ae; --faint:#6b7580; --accent:#5b9dd9;
    --ok:#4ab08a; --bad:#d4645f; --skip:#8a8f96;
  }}
  :root:not([data-theme="dark"]) {{
    @media (prefers-color-scheme: light) {{
      --bg:#f6f8f9; --surface:#fff; --surface-2:#eef1f3; --border:#d9dfe4;
      --text:#10181f; --dim:#53616d; --faint:#8794a0;
    }}
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--text);
    font:15px/1.55 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; }}
  header {{ display:flex; align-items:baseline; gap:14px; flex-wrap:wrap;
    padding:18px 20px; border-bottom:1px solid var(--border); }}
  h1 {{ margin:0; font-size:17px; font-weight:600; }}
  .tally {{ margin-left:auto; font-size:13px; color:var(--dim); }}
  .tally b {{ color:var(--ok); }}
  /* The page never scrolls as a whole: the journey list scrolls on its own and the
     player stays put, so picking journey 14 does not drag the video off screen. */
  html, body {{ height:100%; }}
  body {{ display:flex; flex-direction:column; overflow:hidden; }}
  header, footer {{ flex:none; }}
  main {{ flex:1; min-height:0; display:grid; grid-template-columns:minmax(300px,420px) 1fr; }}
  aside {{ border-right:1px solid var(--border); overflow-y:auto; min-height:0; }}
  @media (max-width:820px) {{
    body {{ overflow:auto; height:auto; }}
    main {{ display:block; }}
    aside {{ border-right:0; overflow:visible; }}
  }}
  ul {{ list-style:none; margin:0; padding:8px; }}
  .j {{ display:flex; gap:12px; width:100%; text-align:left; cursor:pointer; background:none;
    border:1px solid transparent; border-radius:10px; padding:11px 12px; color:inherit;
    font:inherit; align-items:flex-start; }}
  .j:hover {{ background:var(--surface); }}
  .j[data-selected] {{ background:var(--surface-2); border-color:var(--border); }}
  .n {{ flex:none; width:22px; height:22px; border-radius:6px; background:var(--surface-2);
    color:var(--dim); font-size:12px; display:grid; place-items:center; margin-top:1px; }}
  .j[data-selected] .n {{ background:var(--accent); color:#fff; }}
  .body {{ min-width:0; flex:1; }}
  .t {{ display:block; font-weight:550; }}
  .w {{ display:block; color:var(--dim); font-size:13px; margin-top:3px; }}
  .s {{ flex:none; font-size:11px; letter-spacing:.04em; text-transform:uppercase; margin-top:3px; }}
  .s.ok {{ color:var(--ok); }} .s.bad {{ color:var(--bad); }} .s.skip {{ color:var(--skip); }}
  section {{ padding:20px 22px; min-width:0; min-height:0; overflow-y:auto; }}
  .pane h2 {{ margin:0 0 4px; font-size:16px; font-weight:600; }}
  .why {{ margin:0 0 16px; color:var(--dim); max-width:70ch; }}
  video {{ width:100%; max-width:1100px; max-height:calc(100dvh - 330px); object-fit:contain;
    border:1px solid var(--border); border-radius:12px; background:#000; display:block; }}
  .strip {{ display:flex; gap:10px; overflow-x:auto; padding:16px 0 4px; max-width:1100px; }}
  .strip figure {{ margin:0; flex:none; width:210px; }}
  .strip img {{ width:100%; border:1px solid var(--border); border-radius:8px; display:block;
    background:var(--surface-2); cursor:zoom-in; }}
  .strip figcaption {{ color:var(--faint); font-size:12px; margin-top:5px; }}
  .none {{ color:var(--faint); font-size:14px; }}
  .noise {{ margin-top:18px; max-width:1100px; border:1px solid var(--border);
    border-radius:10px; background:var(--surface); }}
  .noise summary {{ cursor:pointer; padding:10px 14px; color:var(--bad); font-size:13px; }}
  .noise pre {{ margin:0; padding:0 14px 14px; overflow-x:auto; color:var(--dim);
    font-size:12.5px; line-height:1.6; }}
  dialog {{ border:0; padding:0; background:transparent; max-width:96vw; max-height:96vh; }}
  dialog::backdrop {{ background:rgba(0,0,0,.8); }}
  dialog img {{ max-width:96vw; max-height:96vh; border-radius:10px; display:block; }}
  footer {{ padding:14px 20px; border-top:1px solid var(--border); color:var(--faint); font-size:12px; }}
</style>
</head>
<body>
<header>
  <h1>User journeys</h1>
  <span class="tally"><b>{passed}</b> of {count} passed &middot; {when}</span>
</header>
<main>
  <aside><ul>
{rows}
  </ul></aside>
  <section>
{panes}
  </section>
</main>
<footer>Each clip is a real browser driven against the running app. Click a journey to watch it; click a still to enlarge.</footer>
<dialog id="zoom"><img alt=""></dialog>
<script>
  const panes = [...document.querySelectorAll(".pane")];
  document.querySelectorAll(".j").forEach((b) => b.addEventListener("click", () => {{
    document.querySelectorAll(".j").forEach((o) => o.removeAttribute("data-selected"));
    b.setAttribute("data-selected", "");
    panes.forEach((p) => {{
      const on = p.id === b.dataset.pane;
      p.hidden = !on;
      const v = p.querySelector("video");
      if (v) on ? v.play().catch(() => {{}}) : v.pause();
    }});
  }}));
  const zoom = document.getElementById("zoom");
  document.addEventListener("click", (e) => {{
    if (e.target.matches(".strip img")) {{
      zoom.querySelector("img").src = e.target.src;
      zoom.showModal();
    }} else if (e.target === zoom) zoom.close();
  }});
</script>
</body>
</html>
"""

if __name__ == "__main__":
    print(build())
