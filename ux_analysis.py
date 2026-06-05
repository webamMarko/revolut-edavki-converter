"""UX Analysis script for WealthEagle using Playwright."""

import asyncio
import json
import os
from pathlib import Path
from datetime import datetime

async def analyze_ux():
    """Run comprehensive UX analysis."""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("Installing Playwright...")
        os.system("pip install -q playwright")
        from playwright.async_api import async_playwright
        os.system("playwright install chromium")

    async with async_playwright() as p:
        browser = await p.chromium.launch()

        # Test configurations
        viewports = {
            "mobile": {"width": 375, "height": 667},
            "tablet": {"width": 768, "height": 1024},
            "desktop": {"width": 1440, "height": 900},
        }

        findings = {
            "timestamp": datetime.now().isoformat(),
            "application": "WealthEagle",
            "analysis": {
                "viewports": {},
                "accessibility": {
                    "issues": [],
                    "warnings": [],
                    "score": 0
                },
                "workflows_tested": [],
                "ux_issues": []
            }
        }

        # Create screenshots directory
        screenshots_dir = Path("ux-audit/output/screenshots")
        screenshots_dir.mkdir(parents=True, exist_ok=True)

        for viewport_name, viewport in viewports.items():
            print(f"\n📱 Analyzing {viewport_name} ({viewport['width']}x{viewport['height']})...")

            context = await browser.new_context(viewport=viewport)
            page = await context.new_page()

            # Set user agent for consistent rendering
            await page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"})

            try:
                # Navigate to homepage
                await page.goto("http://localhost:8080", wait_until="networkidle")

                # Wait for content to load
                await page.wait_for_timeout(1000)

                # Capture screenshots
                screenshot_path = screenshots_dir / f"01_homepage_{viewport_name}.png"
                await page.screenshot(path=str(screenshot_path))
                print(f"  ✓ Captured: {screenshot_path}")

                # Analyze page structure
                page_title = await page.title()
                main_elements = await page.locator("main, .container, .page").count()
                buttons = await page.locator("button, [role='button']").count()
                links = await page.locator("a").count()
                inputs = await page.locator("input, textarea, select").count()

                findings["analysis"]["viewports"][viewport_name] = {
                    "page_title": page_title,
                    "main_elements": main_elements,
                    "buttons": buttons,
                    "links": links,
                    "inputs": inputs,
                    "screenshots": [str(screenshot_path)]
                }

                # Check for common UX issues
                ux_checks = await check_ux_issues(page, viewport_name)
                findings["analysis"]["ux_issues"].extend(ux_checks)

                # Check accessibility
                a11y_issues = await check_accessibility(page, viewport_name)
                findings["analysis"]["accessibility"]["issues"].extend(a11y_issues)

                # Test main workflows
                workflows = await test_workflows(page, context, viewport_name, screenshots_dir)
                findings["analysis"]["workflows_tested"].extend(workflows)

            except Exception as e:
                print(f"  ✗ Error during analysis: {e}")
                findings["analysis"]["ux_issues"].append({
                    "viewport": viewport_name,
                    "type": "error",
                    "description": str(e)
                })
            finally:
                await context.close()

        await browser.close()

        # Save findings
        output_file = Path("ux-audit/output/ux_analysis_findings.json")
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w") as f:
            json.dump(findings, f, indent=2)

        print(f"\n✅ Analysis complete. Findings saved to {output_file}")
        return findings


async def check_ux_issues(page, viewport_name):
    """Check for common UX issues."""
    issues = []

    # Check viewport scaling
    try:
        viewport_meta = await page.locator('meta[name="viewport"]').get_attribute("content")
        if not viewport_meta:
            issues.append({
                "viewport": viewport_name,
                "type": "missing_viewport_meta",
                "severity": "high",
                "description": "Missing viewport meta tag - mobile responsiveness may be broken",
                "element": "meta[name='viewport']"
            })
    except Exception:
        pass

    # Check for keyboard accessibility
    try:
        # Try tab navigation
        focusable = await page.locator("button, a, input, [tabindex]").count()
        if focusable == 0:
            issues.append({
                "viewport": viewport_name,
                "type": "no_focusable_elements",
                "severity": "high",
                "description": "No focusable elements found - page may not be keyboard accessible",
            })
    except Exception:
        pass

    # Check color contrast
    try:
        # Look for small text that might have contrast issues
        low_contrast = await page.locator("body").evaluate("""() => {
            const elements = document.querySelectorAll('body *');
            let count = 0;
            for (let el of elements) {
                const style = window.getComputedStyle(el);
                const color = style.color;
                const bgColor = style.backgroundColor;
                // Simple heuristic - light text on light bg or vice versa
                if (color === bgColor) count++;
            }
            return count;
        }""")
        if low_contrast > 0:
            issues.append({
                "viewport": viewport_name,
                "type": "potential_low_contrast",
                "severity": "medium",
                "description": f"Found {low_contrast} elements with potentially low contrast",
            })
    except Exception:
        pass

    # Check for proper heading hierarchy
    try:
        headings = await page.locator("h1, h2, h3, h4, h5, h6").count()
        h1_count = await page.locator("h1").count()

        if h1_count == 0 and headings > 0:
            issues.append({
                "viewport": viewport_name,
                "type": "missing_h1",
                "severity": "medium",
                "description": "Page missing H1 heading - may affect accessibility",
            })
    except Exception:
        pass

    # Check button text
    try:
        buttons_no_text = await page.locator("button:not(:has-text())").count()
        if buttons_no_text > 0:
            issues.append({
                "viewport": viewport_name,
                "type": "buttons_missing_text",
                "severity": "high",
                "description": f"Found {buttons_no_text} buttons without visible text",
            })
    except Exception:
        pass

    return issues


async def check_accessibility(page, viewport_name):
    """Check accessibility using built-in browser APIs."""
    issues = []

    try:
        # Inject axe-core if available
        axe_result = await page.evaluate("""async () => {
            // Check for common accessibility issues without axe-core
            const issues = [];

            // Check images have alt text
            const images = document.querySelectorAll('img');
            for (let img of images) {
                if (!img.alt && !img.getAttribute('aria-label')) {
                    issues.push({
                        type: 'missing_alt_text',
                        element: img.src,
                        severity: 'high'
                    });
                }
            }

            // Check form labels
            const inputs = document.querySelectorAll('input, textarea, select');
            for (let input of inputs) {
                if (!input.id || !document.querySelector(`label[for="${input.id}"]`)) {
                    if (!input.getAttribute('aria-label')) {
                        issues.push({
                            type: 'missing_form_label',
                            element: input.name || input.id,
                            severity: 'medium'
                        });
                    }
                }
            }

            // Check links have descriptive text
            const links = document.querySelectorAll('a');
            for (let link of links) {
                if (!link.textContent.trim() && !link.getAttribute('aria-label')) {
                    issues.push({
                        type: 'non_descriptive_link',
                        element: link.href,
                        severity: 'medium'
                    });
                }
            }

            return issues;
        }""")

        for issue in axe_result:
            issues.append({
                "viewport": viewport_name,
                **issue
            })
    except Exception:
        pass

    return issues


async def test_workflows(page, context, viewport_name, screenshots_dir):
    """Test key user workflows."""
    workflows = []

    # Test 1: Home page visibility and CTA
    try:
        cta_button = await page.locator("button:has-text('Get'), button:has-text('Upload'), button:has-text('Start')").first
        if cta_button:
            cta_text = await cta_button.text_content()
            cta_visible = await cta_button.is_visible()
            workflows.append({
                "name": "CTA Button Visibility",
                "viewport": viewport_name,
                "status": "pass" if cta_visible else "fail",
                "details": {
                    "button_text": cta_text,
                    "visible": cta_visible
                }
            })
            print(f"  ✓ Found CTA: '{cta_text}'")
    except Exception as e:
        workflows.append({
            "name": "CTA Button Visibility",
            "viewport": viewport_name,
            "status": "fail",
            "error": str(e)
        })

    # Test 2: Navigation menu
    try:
        nav = await page.locator("nav, header, [role='navigation']").count()
        workflows.append({
            "name": "Navigation Menu Present",
            "viewport": viewport_name,
            "status": "pass" if nav > 0 else "fail",
            "details": {
                "navigation_elements": nav
            }
        })
    except Exception as e:
        workflows.append({
            "name": "Navigation Menu Present",
            "viewport": viewport_name,
            "status": "fail",
            "error": str(e)
        })

    # Test 3: Page load time
    try:
        start = asyncio.get_event_loop().time()
        await page.goto("http://localhost:8080", wait_until="networkidle")
        load_time = asyncio.get_event_loop().time() - start

        status = "pass" if load_time < 3 else "slow"
        workflows.append({
            "name": "Page Load Performance",
            "viewport": viewport_name,
            "status": status,
            "details": {
                "load_time_seconds": round(load_time, 2),
                "threshold": "< 3 seconds"
            }
        })
    except Exception:
        pass

    return workflows


async def main():
    """Main entry point."""
    try:
        findings = await analyze_ux()

        # Print summary
        print("\n" + "="*60)
        print("📊 UX ANALYSIS SUMMARY")
        print("="*60)
        print(f"Application: {findings['application']}")
        print(f"Analysis Date: {findings['timestamp']}")
        print("\nViewports Analyzed:")
        for vp_name, vp_data in findings["analysis"]["viewports"].items():
            print(f"  • {vp_name.capitalize()}: {vp_data['page_title']}")

        print(f"\nUX Issues Found: {len(findings['analysis']['ux_issues'])}")
        print(f"Accessibility Issues: {len(findings['analysis']['accessibility']['issues'])}")
        print(f"Workflows Tested: {len(findings['analysis']['workflows_tested'])}")

    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
