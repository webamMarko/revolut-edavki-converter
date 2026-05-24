#!/usr/bin/env python3
"""
UX Audit Pipeline

Automated UX review + accessibility audit using Playwright, axe-core, and Claude.
Run: python ux-audit/audit.py [--config ux-audit/config.yaml] [--skip-claude]
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml
from playwright.sync_api import sync_playwright

SCRIPT_DIR = Path(__file__).resolve().parent
AXE_SOURCE_URL = "https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js"
IMPACT_ORDER = {"minor": 0, "moderate": 1, "serious": 2, "critical": 3}


def load_config(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def download_axe_source() -> str:
    """Download axe-core JS source, cached locally."""
    cache_path = SCRIPT_DIR / ".axe-core.min.js"
    if cache_path.exists() and cache_path.stat().st_size > 10000:
        return cache_path.read_text()

    import urllib.request
    print("  Downloading axe-core...")
    resp = urllib.request.urlopen(AXE_SOURCE_URL, timeout=30)
    js = resp.read().decode()
    cache_path.write_text(js)
    return js


def login(page, base_url: str, user_cfg: dict):
    """Log in via the web form."""
    page.goto(f"{base_url}/login")
    page.fill('input[name="username"]', user_cfg["username"])
    page.fill('input[name="password"]', user_cfg["password"])
    page.click('button[type="submit"]')
    page.wait_for_url(f"{base_url}/", timeout=8000)


def collect_page_data(page) -> dict:
    """Extract structured page metadata from the current page."""
    return page.evaluate("""() => {
        const headings = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].map(h => ({
            level: parseInt(h.tagName[1]),
            text: h.textContent.trim().substring(0, 120)
        }));
        const links = [...document.querySelectorAll('a[href]')].map(a => ({
            text: (a.textContent || '').trim().substring(0, 80),
            href: a.getAttribute('href')
        })).slice(0, 50);
        const buttons = [...document.querySelectorAll('button, input[type="submit"]')].map(b => ({
            text: (b.textContent || b.value || '').trim().substring(0, 80),
            type: b.type || 'button'
        }));
        const forms = [...document.querySelectorAll('form')].map(f => ({
            action: f.action,
            inputs: [...f.querySelectorAll('input,select,textarea')].map(i => ({
                name: i.name, type: i.type, label: i.labels?.[0]?.textContent?.trim()
            }))
        }));
        const images = [...document.querySelectorAll('img')].map(img => ({
            src: img.src,
            alt: img.alt,
            hasAlt: img.hasAttribute('alt')
        }));
        return {
            title: document.title,
            url: location.href,
            lang: document.documentElement.lang,
            headings, links, buttons, forms, images,
            metaViewport: document.querySelector('meta[name="viewport"]')?.content || null,
        };
    }""")


def run_axe(page, axe_source: str, config: dict) -> dict:
    """Inject axe-core and run accessibility checks."""
    page.evaluate(axe_source)

    skip_rules = config.get("accessibility", {}).get("skip_rules", [])
    standard = config.get("accessibility", {}).get("standard", "wcag2aa")

    rules_config = {}
    for rule_id in skip_rules:
        rules_config[rule_id] = {"enabled": False}

    result = page.evaluate("""([standard, rulesConfig]) => {
        return new Promise((resolve) => {
            axe.run(document, {
                runOnly: { type: 'tag', values: [standard, 'best-practice'] },
                rules: rulesConfig
            }).then(resolve);
        });
    }""", [standard, rules_config])

    violations = []
    for v in result.get("violations", []):
        violations.append({
            "id": v["id"],
            "impact": v["impact"],
            "description": v["description"],
            "help": v["help"],
            "helpUrl": v["helpUrl"],
            "nodes_count": len(v.get("nodes", [])),
            "nodes_sample": [
                {
                    "html": n.get("html", "")[:200],
                    "target": n.get("target", []),
                    "failureSummary": n.get("failureSummary", "")[:200],
                }
                for n in v.get("nodes", [])[:3]
            ],
        })

    return {
        "violations": violations,
        "passes_count": len(result.get("passes", [])),
        "violations_count": len(violations),
        "incomplete_count": len(result.get("incomplete", [])),
    }


def run_claude_review(page_results: list, output_dir: Path, skip: bool = False) -> dict:
    """Use Claude CLI to perform heuristic UX review on collected data."""
    if skip:
        return {"skipped": True, "pages": {}}

    review_input = []
    screenshot_paths = []
    for pr in page_results:
        entry = {
            "page_name": pr["name"],
            "url": pr["page_data"]["url"],
            "title": pr["page_data"]["title"],
            "headings": pr["page_data"]["headings"],
            "buttons_count": len(pr["page_data"]["buttons"]),
            "forms_count": len(pr["page_data"]["forms"]),
            "links_count": len(pr["page_data"]["links"]),
            "images_without_alt": sum(1 for img in pr["page_data"]["images"] if not img["hasAlt"]),
            "axe_violations": pr["axe_results"]["violations_count"],
            "axe_top_issues": [
                f"{v['impact']}: {v['description']}" for v in pr["axe_results"]["violations"][:5]
            ],
            "viewport": pr["viewport"],
        }
        review_input.append(entry)
        if pr.get("screenshot_path"):
            screenshot_paths.append(pr["screenshot_path"])

    prompt = f"""You are a UX expert reviewing a web application. Analyze the following page data and screenshots.

For each page, provide:
1. A UX score (1-10, where 10 is excellent)
2. Top 3 UX issues found (severity: critical/major/minor)
3. Top 3 positive UX aspects
4. Specific actionable recommendations

Page data:
{json.dumps(review_input, indent=2)}

Respond ONLY with valid JSON in this exact format:
{{
  "overall_score": <number 1-10>,
  "pages": {{
    "<page_name>": {{
      "score": <number 1-10>,
      "issues": [
        {{"severity": "critical|major|minor", "description": "..."}}
      ],
      "positives": ["..."],
      "recommendations": ["..."]
    }}
  }},
  "summary": "One paragraph overall UX assessment"
}}"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(prompt)
        prompt_file = f.name

    try:
        cmd = ["claude", "--print", "--max-turns", "1"]
        for sp in screenshot_paths[:8]:
            cmd.extend(["--file", sp])

        result = subprocess.run(
            cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(SCRIPT_DIR.parent),
        )

        response = result.stdout.strip()
        json_start = response.find("{")
        json_end = response.rfind("}") + 1
        if json_start >= 0 and json_end > json_start:
            return json.loads(response[json_start:json_end])
        else:
            return {"error": "Could not parse Claude response", "raw": response[:500]}
    except subprocess.TimeoutExpired:
        return {"error": "Claude CLI timed out"}
    except FileNotFoundError:
        return {"error": "Claude CLI not found — install claude CLI or run with --skip-claude"}
    except Exception as e:
        return {"error": str(e)}
    finally:
        os.unlink(prompt_file)


def generate_markdown_report(results: dict, output_path: Path):
    """Generate human-readable markdown report."""
    lines = [
        f"# UX Audit Report",
        f"",
        f"**Date:** {results['timestamp']}",
        f"**Base URL:** {results['base_url']}",
        f"**Pages audited:** {len(results['pages'])}",
        f"",
    ]

    # Summary
    total_violations = sum(p["axe_results"]["violations_count"] for p in results["pages"])
    critical_serious = sum(
        1 for p in results["pages"]
        for v in p["axe_results"]["violations"]
        if v["impact"] in ("critical", "serious")
    )
    lines.extend([
        f"## Summary",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total axe violations | {total_violations} |",
        f"| Critical + Serious | {critical_serious} |",
        f"| CI threshold result | {'PASS' if results['ci_pass'] else 'FAIL'} |",
    ])

    claude = results.get("claude_review", {})
    if claude.get("overall_score"):
        lines.append(f"| Claude UX score | {claude['overall_score']}/10 |")
    if claude.get("summary"):
        lines.extend(["", f"> {claude['summary']}", ""])

    lines.extend(["", "---", ""])

    # Per-page details
    for page in results["pages"]:
        lines.extend([
            f"## {page['name']} ({page['viewport']})",
            f"",
            f"**URL:** `{page['page_data']['url']}`",
            f"",
        ])

        # Accessibility
        axe = page["axe_results"]
        lines.append(f"### Accessibility ({axe['violations_count']} violations, {axe['passes_count']} passes)")
        lines.append("")
        if axe["violations"]:
            for v in axe["violations"]:
                icon = {"critical": "🔴", "serious": "🟠", "moderate": "🟡", "minor": "🔵"}.get(v["impact"], "⚪")
                lines.append(f"- {icon} **{v['impact'].upper()}** — {v['description']}")
                lines.append(f"  - {v['help']} ({v['nodes_count']} nodes)")
                for node in v.get("nodes_sample", [])[:1]:
                    lines.append(f"  - `{node['html'][:100]}`")
        else:
            lines.append("No violations found.")
        lines.append("")

        # Claude review for this page
        page_review = claude.get("pages", {}).get(page["name"], {})
        if page_review:
            lines.append(f"### UX Review (Score: {page_review.get('score', 'N/A')}/10)")
            lines.append("")
            if page_review.get("issues"):
                lines.append("**Issues:**")
                for issue in page_review["issues"]:
                    lines.append(f"- [{issue.get('severity', '?')}] {issue.get('description', '')}")
            if page_review.get("recommendations"):
                lines.append("")
                lines.append("**Recommendations:**")
                for rec in page_review["recommendations"]:
                    lines.append(f"- {rec}")
            lines.append("")

        if page.get("screenshot_path"):
            rel = os.path.relpath(page["screenshot_path"], output_path.parent)
            lines.append(f"**Screenshot:** ![{page['name']}]({rel})")
            lines.append("")

        lines.extend(["---", ""])

    # Threshold details
    lines.extend([
        "## CI Thresholds",
        "",
        f"| Check | Threshold | Actual | Result |",
        f"|-------|-----------|--------|--------|",
    ])
    for check in results.get("threshold_checks", []):
        status = "PASS" if check["pass"] else "FAIL"
        lines.append(f"| {check['name']} | {check['threshold']} | {check['actual']} | {status} |")

    output_path.write_text("\n".join(lines))


def check_thresholds(config: dict, page_results: list, claude_review: dict) -> tuple:
    """Check CI thresholds. Returns (pass: bool, checks: list)."""
    thresholds = config.get("thresholds", {})
    checks = []

    # Max violations
    max_violations = thresholds.get("max_violations", 5)
    critical_serious = sum(
        1 for p in page_results
        for v in p["axe_results"]["violations"]
        if v["impact"] in ("critical", "serious")
    )
    checks.append({
        "name": "Critical+Serious violations",
        "threshold": f"<= {max_violations}",
        "actual": critical_serious,
        "pass": critical_serious <= max_violations,
    })

    # Max impact level
    max_impact = thresholds.get("max_accessibility_impact", "serious")
    max_impact_val = IMPACT_ORDER.get(max_impact, 2)
    worst_found = max(
        (IMPACT_ORDER.get(v["impact"], 0) for p in page_results for v in p["axe_results"]["violations"]),
        default=-1,
    )
    worst_label = {v: k for k, v in IMPACT_ORDER.items()}.get(worst_found, "none")
    checks.append({
        "name": "Max impact level",
        "threshold": f"< {max_impact}",
        "actual": worst_label,
        "pass": worst_found < max_impact_val,
    })

    # UX score
    min_ux = thresholds.get("min_ux_score", 4)
    ux_score = claude_review.get("overall_score")
    if ux_score is not None:
        checks.append({
            "name": "Claude UX score",
            "threshold": f">= {min_ux}",
            "actual": ux_score,
            "pass": ux_score >= min_ux,
        })

    all_pass = all(c["pass"] for c in checks)
    return all_pass, checks


def run_audit(config_path: Path, skip_claude: bool = False):
    config = load_config(config_path)
    base_url = config["base_url"]
    output_dir = SCRIPT_DIR / config.get("output_dir", "output")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    screenshots_dir = output_dir / f"screenshots-{timestamp}"
    screenshots_dir.mkdir(exist_ok=True)

    print(f"UX Audit Pipeline")
    print(f"  Base URL: {base_url}")
    print(f"  Output:   {output_dir}")
    print()

    axe_source = download_axe_source()
    page_results = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)

        auth_contexts = {}

        for page_cfg in config["pages"]:
            for vp_name, vp in config["viewports"].items():
                name = page_cfg["name"]
                auth_key = page_cfg.get("auth", "guest")
                ctx_key = f"{auth_key}_{vp_name}"

                print(f"  [{vp_name}] {name} ({page_cfg['path']})...", end=" ", flush=True)

                if ctx_key not in auth_contexts:
                    ctx = browser.new_context(
                        viewport=vp,
                        is_mobile=(vp_name == "mobile"),
                        has_touch=(vp_name == "mobile"),
                    )
                    if auth_key != "guest" and config["users"].get(auth_key):
                        p = ctx.new_page()
                        login(p, base_url, config["users"][auth_key])
                        p.close()
                    auth_contexts[ctx_key] = ctx

                page = auth_contexts[ctx_key].new_page()
                url = f"{base_url}{page_cfg['path']}"

                try:
                    page.goto(url, wait_until="networkidle", timeout=15000)
                    wait_sel = page_cfg.get("wait_for")
                    if wait_sel:
                        for sel in wait_sel.split(","):
                            try:
                                page.wait_for_selector(sel.strip(), timeout=3000)
                                break
                            except Exception:
                                continue

                    screenshot_name = f"{name.lower().replace(' ', '_')}_{vp_name}.png"
                    screenshot_path = str(screenshots_dir / screenshot_name)
                    page.screenshot(path=screenshot_path, full_page=True)

                    page_data = collect_page_data(page)
                    axe_results = run_axe(page, axe_source, config)

                    page_results.append({
                        "name": name,
                        "viewport": vp_name,
                        "page_data": page_data,
                        "axe_results": axe_results,
                        "screenshot_path": screenshot_path,
                    })

                    v_count = axe_results["violations_count"]
                    print(f"OK ({v_count} violations)")

                except Exception as e:
                    print(f"ERROR: {e}")
                    page_results.append({
                        "name": name,
                        "viewport": vp_name,
                        "page_data": {"url": url, "title": "", "headings": [], "links": [], "buttons": [], "forms": [], "images": [], "metaViewport": None, "lang": ""},
                        "axe_results": {"violations": [], "passes_count": 0, "violations_count": 0, "incomplete_count": 0},
                        "screenshot_path": None,
                        "error": str(e),
                    })
                finally:
                    page.close()

        for ctx in auth_contexts.values():
            ctx.close()
        browser.close()

    # Claude UX review
    print()
    if skip_claude:
        print("  Skipping Claude UX review (--skip-claude)")
        claude_review = {"skipped": True, "pages": {}}
    else:
        print("  Running Claude UX review...", end=" ", flush=True)
        claude_review = run_claude_review(page_results, output_dir, skip=skip_claude)
        if claude_review.get("error"):
            print(f"WARNING: {claude_review['error']}")
        else:
            score = claude_review.get("overall_score", "?")
            print(f"Done (score: {score}/10)")

    # Check thresholds
    ci_pass, threshold_checks = check_thresholds(config, page_results, claude_review)

    # Build final results
    results = {
        "timestamp": timestamp,
        "base_url": base_url,
        "pages": page_results,
        "claude_review": claude_review,
        "ci_pass": ci_pass,
        "threshold_checks": threshold_checks,
    }

    # Write JSON report
    json_path = output_dir / f"audit-{timestamp}.json"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2, default=str)

    # Write markdown report
    md_path = output_dir / f"audit-{timestamp}.md"
    generate_markdown_report(results, md_path)

    # Write latest symlink-style files
    (output_dir / "latest.json").write_text(json_path.name)
    (output_dir / "latest.md").write_text(md_path.name)

    print()
    print(f"  JSON report: {json_path}")
    print(f"  Markdown report: {md_path}")
    print(f"  Screenshots: {screenshots_dir}/")
    print()

    if ci_pass:
        print("  CI Result: PASS")
    else:
        print("  CI Result: FAIL")
        for c in threshold_checks:
            if not c["pass"]:
                print(f"    - {c['name']}: {c['actual']} (threshold: {c['threshold']})")

    return 0 if ci_pass else 1


def main():
    parser = argparse.ArgumentParser(description="Run UX audit pipeline")
    parser.add_argument(
        "--config",
        type=Path,
        default=SCRIPT_DIR / "config.yaml",
        help="Path to config.yaml",
    )
    parser.add_argument(
        "--skip-claude",
        action="store_true",
        help="Skip Claude UX review (accessibility only)",
    )
    args = parser.parse_args()

    sys.exit(run_audit(args.config, skip_claude=args.skip_claude))


if __name__ == "__main__":
    main()
