"""JSON API endpoints: analytics, notes, goals, shares, preferences."""

import json
import os
from urllib.parse import parse_qs, urlparse

from .auth import get_session, get_session_token
from .portfolio import portfolio_conn, _DEMO_VIEW
from .templates import page_env, FOUC_SCRIPT, COMMON_JS, html_response, json_response

APP_BASE_URL = os.environ.get("APP_BASE_URL", "http://localhost:8080")


# ------------------------------------------------------------------
# Analytics API (lazy-load per-class)
# ------------------------------------------------------------------

def api_get_analytics(handler, scope: str):
    """GET /api/analytics/<scope> — per-class analytics JSON."""
    valid_scopes = ("stock", "cfd", "crypto", "savings")
    if scope not in valid_scopes:
        json_response(handler, {"error": f"Invalid scope. Must be one of: {', '.join(valid_scopes)}"}, status=400)
        return
    session = get_session(handler)
    conn = portfolio_conn(session, get_session_token(handler))
    from ..prices_db import get_prices_conn_or_none
    prices_conn = get_prices_conn_or_none()
    try:
        from ..analytics import compute_analytics
        from ..analytics_cache import compute_data_hash, get_cached, put_cache
        data_hash = compute_data_hash(conn, prices_conn)
        cached = get_cached(conn, scope, data_hash)
        if cached is not None:
            ac_analytics = cached
        else:
            ac_analytics = compute_analytics(conn, scope=scope, prices_conn=prices_conn)
            put_cache(conn, scope, data_hash, ac_analytics)

        ac_daily = ac_analytics.daily_series
        result = {
            "dates": [str(d) for d in ac_daily.index],
            "value_eur": [round(float(v), 2) for v in ac_daily["value_eur"]],
            "invested_eur": [round(float(v), 2) for v in ac_daily["invested_eur"]],
            "dividends_eur": [round(float(v), 2) for v in ac_daily["dividends_eur"]],
            "realized_gain_eur": [round(float(v), 2) for v in ac_daily["realized_gain_eur"]],
            "perf_index": [round(float(v), 2) for v in ac_daily["perf_index"]] if "perf_index" in ac_daily.columns else [],
            "summary": {
                "portfolio_value_eur": round(ac_analytics.portfolio_value_eur, 2),
                "total_invested_eur": round(ac_analytics.total_invested_eur, 2),
                "absolute_gain_eur": round(ac_analytics.absolute_gain_eur, 2),
                "total_return_pct": round(ac_analytics.total_return_pct, 2),
                "cagr_pct": round(ac_analytics.cagr_pct, 2) if ac_analytics.cagr_pct else None,
                "twr_pct": round(ac_analytics.twr_pct, 2) if ac_analytics.twr_pct else None,
                "max_drawdown_pct": round(ac_analytics.max_drawdown_pct, 2),
                "max_drawdown_peak_date": ac_analytics.max_drawdown_peak_date,
                "max_drawdown_trough_date": ac_analytics.max_drawdown_trough_date,
                "risk_metrics": ac_analytics.risk_metrics,
            },
            "gains": {
                "realized_eur": round(ac_analytics.total_realized_gain_eur, 2),
                "unrealized_eur": round(ac_analytics.total_unrealized_gain_eur, 2),
                "dividends_eur": round(ac_analytics.total_dividends_eur, 2),
                "fees_eur": round(ac_analytics.total_fees_eur, 2),
            },
            "positions": sorted(
                [
                    {
                        "ticker": p.ticker,
                        "quantity": round(p.quantity, 4),
                        "cost_basis_eur": round(p.cost_basis_eur, 2),
                        "avg_cost_eur": round(p.cost_basis_eur / p.quantity, 4) if p.quantity else 0,
                        "market_value_eur": round(p.market_value_eur, 2),
                        "unrealized_gain_eur": round(p.unrealized_gain_eur, 2),
                        "unrealized_gain_pct": round(p.unrealized_gain_pct, 2),
                        "weight_pct": round(p.weight_pct, 2),
                        "realized_gain_eur": round(p.realized_gain_eur, 2),
                    }
                    for p in ac_analytics.positions
                ],
                key=lambda x: x["market_value_eur"],
                reverse=True,
            ),
            "closed_positions": sorted(
                [
                    {
                        "ticker": p.ticker,
                        "total_cost_eur": round(p.total_cost_eur, 2),
                        "total_proceeds_eur": round(p.total_proceeds_eur, 2),
                        "realized_gain_eur": round(p.realized_gain_eur, 2),
                        "realized_gain_pct": round(p.realized_gain_pct, 2),
                    }
                    for p in ac_analytics.closed_positions
                ],
                key=lambda x: abs(x["realized_gain_eur"]),
                reverse=True,
            ),
            "position_lots": {
                ticker: [
                    {"qty": round(qty, 4), "cost_eur": round(cost, 4), "date": date}
                    for qty, cost, date in lots
                ]
                for ticker, lots in ac_analytics.position_lots.items()
            },
        }
        json_response(handler, result)
    except ValueError as e:
        json_response(handler, {"error": str(e)}, status=400)
    except Exception as e:
        json_response(handler, {"error": f"Analytics computation failed: {e}"}, status=500)
    finally:
        if prices_conn:
            prices_conn.close()
        conn.close()


# ------------------------------------------------------------------
# Dividend summary
# ------------------------------------------------------------------

def handle_dividend_summary(handler):
    """GET /api/dividend-summary?year=<year> — dividend tax summary."""
    session = get_session(handler)
    if not session:
        json_response(handler, {"error": "Unauthorized"}, status=401)
        return
    from ..doh_div_generator import build_dividend_entries, compute_dividend_tax_summary

    qs = parse_qs(urlparse(handler.path).query)
    year = int(qs.get("year", [str(__import__("datetime").datetime.now().year)])[0])

    conn = portfolio_conn(session, get_session_token(handler))
    try:
        entries = build_dividend_entries(conn, year)
        summary = compute_dividend_tax_summary(entries, year)
        json_response(handler, {
            "year": year,
            "total_gross_eur": summary.total_gross_eur,
            "total_withholding_eur": summary.total_withholding_eur,
            "total_net_received_eur": summary.total_net_received_eur,
            "si_tax_liability": summary.si_tax_liability,
            "total_credit_eur": summary.total_credit_eur,
            "net_tax_owed_si": summary.net_tax_owed_si,
            "total_reclaimable_eur": summary.total_reclaimable_eur,
            "entry_count": len(entries),
            "by_country": {
                k: {
                    "country_name": v["country_name"],
                    "gross_eur": round(v["gross_eur"], 2),
                    "withholding_eur": round(v["withholding_eur"], 2),
                    "credit_eur": round(v["credit_eur"], 2),
                    "reclaimable_eur": round(v["reclaimable_eur"], 2),
                    "treaty_rate": v["treaty_rate"],
                    "count": v["count"],
                } for k, v in summary.by_country.items()
            },
        })
    except Exception as e:
        json_response(handler, {"error": str(e)}, status=500)
    finally:
        conn.close()


# ------------------------------------------------------------------
# Notes API
# ------------------------------------------------------------------

def notes_conn_or_403(handler):
    """Return (session, conn) if user is premium/admin, else send 403 and return (None, None)."""
    session = get_session(handler)
    if not session or session["role"] not in ("premium", "admin"):
        json_response(handler, {"error": "forbidden"}, 403)
        return None, None
    conn = portfolio_conn(session, get_session_token(handler))
    return session, conn


def api_list_notes(handler):
    """GET /api/notes — list investment notes."""
    session = get_session(handler)
    conn = portfolio_conn(session, get_session_token(handler))
    try:
        from ..notes import query_notes_for_report
        notes = query_notes_for_report(conn)
        json_response(handler, notes)
    finally:
        conn.close()


def api_create_note(handler):
    """POST /api/notes — create investment note."""
    _, conn = notes_conn_or_403(handler)
    if conn is None:
        return
    try:
        data = json.loads(handler._read_body())
        from ..notes import add_note
        note_id = add_note(
            conn,
            title=str(data.get("title", "")).strip(),
            summary=str(data.get("summary", "")).strip(),
            body=str(data.get("body", "")),
            tickers=str(data.get("tickers", "")),
            conviction=data.get("conviction", "medium"),
            action=data.get("action", "watch"),
        )
        from ..notes import query_notes_for_report
        all_notes = query_notes_for_report(conn)
        note = next((n for n in all_notes if n["id"] == note_id), None)
        json_response(handler, note or {"id": note_id}, 201)
    except (json.JSONDecodeError, KeyError) as e:
        json_response(handler, {"error": str(e)}, 400)
    finally:
        conn.close()


def api_update_note(handler, note_id: int):
    """PUT /api/notes/<id> — update investment note."""
    _, conn = notes_conn_or_403(handler)
    if conn is None:
        return
    try:
        data = json.loads(handler._read_body())
        from ..notes import edit_note, query_notes_for_report
        edit_note(conn, note_id, **{k: data[k] for k in
            ("title", "summary", "body", "tickers", "conviction", "action")
            if k in data})
        all_notes = query_notes_for_report(conn)
        note = next((n for n in all_notes if n["id"] == note_id), None)
        if note is None:
            json_response(handler, {"error": "not found"}, 404)
        else:
            json_response(handler, note)
    except (json.JSONDecodeError, KeyError) as e:
        json_response(handler, {"error": str(e)}, 400)
    finally:
        conn.close()


def api_delete_note(handler, note_id: int):
    """DELETE /api/notes/<id> — delete investment note."""
    _, conn = notes_conn_or_403(handler)
    if conn is None:
        return
    try:
        from ..notes import delete_note
        ok = delete_note(conn, note_id)
        if ok:
            json_response(handler, {"deleted": note_id})
        else:
            json_response(handler, {"error": "not found"}, 404)
    finally:
        conn.close()


# ------------------------------------------------------------------
# Onboarding API
# ------------------------------------------------------------------

def api_onboarding_status(handler):
    """GET /api/onboarding-status — returns {completed, hasData, hasSynced}"""
    session = get_session(handler)
    if not session or session["role"] not in ("premium", "admin"):
        json_response(handler, {"error": "Login required."}, status=403)
        return

    from ..users import get_onboarding_status
    status = get_onboarding_status(session["user_id"])
    json_response(handler, status)


def api_onboarding_complete(handler):
    """POST /api/onboarding-complete — marks onboarding as completed"""
    session = get_session(handler)
    if not session or session["role"] not in ("premium", "admin"):
        json_response(handler, {"error": "Login required."}, status=403)
        return

    from ..users import set_onboarding_completed
    ok = set_onboarding_completed(session["user_id"])
    json_response(handler, {"ok": ok})


def api_demo_toggle(handler):
    """POST /api/demo-toggle — toggles demo view for premium/admin users"""
    session = get_session(handler)
    if not session or session["role"] not in ("premium", "admin"):
        json_response(handler, {"error": "Login required."}, status=403)
        return

    try:
        data = json.loads(handler._read_body())
        demo_enabled = bool(data.get("demo", False))

        # Get session token from cookie
        session_token = get_session_token(handler)
        if session_token:
            _DEMO_VIEW[session_token] = demo_enabled

        json_response(handler, {"ok": True, "demo": demo_enabled})
    except (json.JSONDecodeError, KeyError) as e:
        json_response(handler, {"error": str(e)}, 400)


# ------------------------------------------------------------------
# Goals API
# ------------------------------------------------------------------

def goals_conn_or_403(handler):
    """Return (session, conn) if user is premium/admin, else send 403."""
    session = get_session(handler)
    if not session or session["role"] not in ("premium", "admin"):
        json_response(handler, {"error": "Login required."}, status=403)
        return None, None
    return session, portfolio_conn(session, get_session_token(handler))


def api_list_goals(handler):
    """GET /api/goals — list investment goals."""
    session = get_session(handler)
    conn = portfolio_conn(session, get_session_token(handler))
    try:
        from ..goals import list_goals
        goals = list_goals(conn)
        json_response(handler, goals)
    finally:
        conn.close()


def api_get_goal(handler, goal_id: int):
    """GET /api/goals/<id> — get goal by ID."""
    session = get_session(handler)
    conn = portfolio_conn(session, get_session_token(handler))
    try:
        from ..goals import get_goal
        goal = get_goal(conn, goal_id)
        if goal is None:
            json_response(handler, {"error": "not found"}, 404)
        else:
            json_response(handler, goal)
    finally:
        conn.close()


def api_create_goal(handler):
    """POST /api/goals — create investment goal."""
    session, conn = goals_conn_or_403(handler)
    if conn is None:
        return
    try:
        data = json.loads(handler._read_body())
        name = str(data.get("name", "")).strip()
        target_amount = float(data.get("target_amount_eur", 0))
        target_date = str(data.get("target_date", "")).strip()
        if not name or target_amount <= 0 or not target_date:
            json_response(handler, {"error": "name, target_amount_eur, and target_date are required"}, 400)
            return
        from ..goals import create_goal, get_goal
        goal_id = create_goal(
            conn, name=name, target_amount_eur=target_amount,
            target_date=target_date,
            monthly_contribution=float(data.get("monthly_contribution", 0)),
            scope=str(data.get("scope", "all")),
            tickers=str(data.get("tickers", "")),
        )
        goal = get_goal(conn, goal_id)
        json_response(handler, goal, 201)
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        json_response(handler, {"error": str(e)}, 400)
    finally:
        conn.close()


def api_update_goal(handler, goal_id: int):
    """PUT /api/goals/<id> — update investment goal."""
    session, conn = goals_conn_or_403(handler)
    if conn is None:
        return
    try:
        data = json.loads(handler._read_body())
        from ..goals import update_goal, get_goal
        update_goal(conn, goal_id, **data)
        goal = get_goal(conn, goal_id)
        if goal is None:
            json_response(handler, {"error": "not found"}, 404)
        else:
            json_response(handler, goal)
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        json_response(handler, {"error": str(e)}, 400)
    finally:
        conn.close()


def api_delete_goal(handler, goal_id: int):
    """DELETE /api/goals/<id> — delete investment goal."""
    session, conn = goals_conn_or_403(handler)
    if conn is None:
        return
    try:
        from ..goals import delete_goal
        ok = delete_goal(conn, goal_id)
        if ok:
            json_response(handler, {"deleted": goal_id})
        else:
            json_response(handler, {"error": "not found"}, 404)
    finally:
        conn.close()


def api_goal_projection(handler, goal_id: int):
    """GET /api/goals/<id>/projection — goal projection."""
    session = get_session(handler)
    conn = portfolio_conn(session, get_session_token(handler))
    from ..prices_db import get_prices_conn_or_none
    prices_conn = get_prices_conn_or_none()
    try:
        from ..goals import compute_goal_projection
        projection = compute_goal_projection(conn, goal_id, prices_conn=prices_conn)
        if projection is None:
            json_response(handler, {"error": "goal not found"}, 404)
            return
        json_response(handler, {
            "goal_id": projection.goal_id,
            "current_value_eur": projection.current_value_eur,
            "target_amount_eur": projection.target_amount_eur,
            "progress_pct": projection.progress_pct,
            "months_remaining": projection.months_remaining,
            "required_monthly_eur": projection.required_monthly_eur,
            "probability_of_success": projection.probability_of_success,
            "percentile_10": projection.percentile_10,
            "percentile_50": projection.percentile_50,
            "percentile_90": projection.percentile_90,
        })
    except Exception as e:
        json_response(handler, {"error": f"Projection failed: {e}"}, 500)
    finally:
        if prices_conn:
            prices_conn.close()
        conn.close()


# ------------------------------------------------------------------
# Email preferences
# ------------------------------------------------------------------

def api_get_email_preferences(handler):
    """GET /api/email-preferences — get email report preferences."""
    session = get_session(handler)
    if not session or session["role"] not in ("premium", "admin"):
        json_response(handler, {"error": "Login required."}, status=403)
        return
    from ..email_reports import get_preferences
    prefs = get_preferences(session["user_id"])
    json_response(handler, {
        "weekly_enabled": prefs.weekly_enabled,
        "monthly_enabled": prefs.monthly_enabled,
        "alert_enabled": prefs.alert_enabled,
        "digest_enabled": prefs.digest_enabled,
        "scope": prefs.scope,
        "country": prefs.country,
    })


def api_save_email_preferences(handler):
    """POST /api/email-preferences — save email report preferences."""
    session = get_session(handler)
    if not session or session["role"] not in ("premium", "admin"):
        json_response(handler, {"error": "Login required."}, status=403)
        return
    body = handler._read_body()
    try:
        data = json.loads(body)
    except Exception:
        json_response(handler, {"error": "Invalid JSON."}, status=400)
        return
    from ..email_reports import save_preferences
    save_preferences(
        user_id=session["user_id"],
        weekly_enabled=bool(data.get("weekly_enabled", False)),
        monthly_enabled=bool(data.get("monthly_enabled", True)),
        alert_enabled=bool(data.get("alert_enabled", False)),
        digest_enabled=bool(data.get("digest_enabled", False)),
        scope=data.get("scope", "all"),
        country=data.get("country", "SI"),
    )
    json_response(handler, {"ok": True})


# ------------------------------------------------------------------
# eDavki filed-year tracking
# ------------------------------------------------------------------

def api_get_edavki_filed(handler):
    """GET /api/edavki-filed — get eDavki filed years."""
    session = get_session(handler)
    if not session or session["role"] not in ("premium", "admin"):
        json_response(handler, {"error": "Login required."}, status=403)
        return
    conn = portfolio_conn(session, get_session_token(handler))
    try:
        row = conn.execute(
            "SELECT value FROM metadata WHERE key = 'edavki_filed_years'"
        ).fetchone()
        filed_years = json.loads(row[0]) if row and row[0] else []
        json_response(handler, {"filed_years": filed_years})
    finally:
        conn.close()


def api_save_edavki_filed(handler):
    """POST /api/edavki-filed — save eDavki filed years."""
    session = get_session(handler)
    if not session or session["role"] not in ("premium", "admin"):
        json_response(handler, {"error": "Login required."}, status=403)
        return
    body = handler._read_body()
    try:
        data = json.loads(body)
    except Exception:
        json_response(handler, {"error": "Invalid JSON."}, status=400)
        return
    filed_years = data.get("filed_years")
    dismissed_until = data.get("dismissed_until")
    if filed_years is not None and not isinstance(filed_years, list):
        json_response(handler, {"error": "filed_years must be a list."}, status=400)
        return
    conn = portfolio_conn(session, get_session_token(handler))
    try:
        if filed_years is not None:
            conn.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES ('edavki_filed_years', ?)",
                (json.dumps(sorted(set(int(y) for y in filed_years))),)
            )
        if dismissed_until is not None:
            conn.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES ('edavki_widget_dismissed_until', ?)",
                (str(dismissed_until),)
            )
        conn.commit()
        from ..report_cache import invalidate_user_html
        try:
            invalidate_user_html(session["username"])
        except Exception:
            pass
        json_response(handler, {"ok": True})
    finally:
        conn.close()


# ------------------------------------------------------------------
# Portfolio sharing
# ------------------------------------------------------------------

def api_list_shares(handler):
    """GET /api/shares — list portfolio shares."""
    session = get_session(handler)
    if not session or session["role"] not in ("premium", "admin"):
        json_response(handler, {"error": "Login required."}, status=403)
        return
    from ..users import list_shares
    shares = list_shares(session["user_id"])
    json_response(handler, [{
        "id": s.id,
        "token": s.share_token,
        "label": s.label,
        "scope": s.scope,
        "percentage_only": s.percentage_only,
        "include_holdings": s.include_holdings,
        "created_at": s.created_at,
        "expires_at": s.expires_at,
        "access_count": s.access_count,
        "url": f"{APP_BASE_URL.rstrip('/')}/s/{s.share_token}",
    } for s in shares])


def api_create_share(handler):
    """POST /api/shares — create portfolio share."""
    session = get_session(handler)
    if not session or session["role"] not in ("premium", "admin"):
        json_response(handler, {"error": "Login required."}, status=403)
        return
    body = handler._read_body()
    try:
        data = json.loads(body) if body else {}
    except Exception:
        data = {}
    from ..users import create_share
    share = create_share(
        user_id=session["user_id"],
        label=data.get("label"),
        scope=data.get("scope", "all"),
        percentage_only=data.get("percentage_only", True),
        include_holdings=data.get("include_holdings", False),
        expires_hours=data.get("expires_hours"),
    )
    json_response(handler, {
        "id": share.id,
        "token": share.share_token,
        "url": f"{APP_BASE_URL.rstrip('/')}/s/{share.share_token}",
    })


def api_delete_share(handler, share_id_str: str):
    """POST /api/shares/<id>/delete — delete portfolio share."""
    session = get_session(handler)
    if not session or session["role"] not in ("premium", "admin"):
        json_response(handler, {"error": "Login required."}, status=403)
        return
    try:
        share_id = int(share_id_str)
    except ValueError:
        json_response(handler, {"error": "Invalid share ID."}, status=400)
        return
    from ..users import delete_share
    deleted = delete_share(share_id, session["user_id"])
    json_response(handler, {"ok": deleted})


def serve_shared_portfolio(handler, token: str):
    """GET /s/<token> — view shared portfolio."""
    from ..users import get_share_by_token, get_user_by_id
    from ..analytics import compute_analytics
    from ..analytics_cache import compute_data_hash, get_cached, put_cache
    from ..html_report import generate_html_report, query_transactions
    from ..prices_db import get_prices_conn_or_none
    from .portfolio import user_db_path

    share = get_share_by_token(token)
    if not share:
        template = page_env.get_template("pages/shared_expired.html.j2")
        html = template.render(
            fouc_script=FOUC_SCRIPT,
            common_js=COMMON_JS,
            show_header=False,
            show_drop_import=False
        )
        html_response(handler, html, status=404)
        return

    user = get_user_by_id(share.user_id)
    if not user:
        template = page_env.get_template("pages/shared_expired.html.j2")
        html = template.render(
            fouc_script=FOUC_SCRIPT,
            common_js=COMMON_JS,
            show_header=False,
            show_drop_import=False
        )
        html_response(handler, html, status=404)
        return

    conn = None
    prices_conn = None
    try:
        from ..db import get_connection
        conn = get_connection(db_path=user_db_path(user.username))
        prices_conn = get_prices_conn_or_none()

        data_hash = compute_data_hash(conn, prices_conn)

        cached = get_cached(conn, share.scope, data_hash)
        if cached is not None:
            analytics = cached
        else:
            analytics = compute_analytics(conn, scope=share.scope, prices_conn=prices_conn)
            put_cache(conn, share.scope, data_hash, analytics)

        transactions = query_transactions(conn) if share.include_holdings else []

        html = generate_html_report(
            analytics, {}, transactions, per_class=None,
            available_classes=[],
            real_estate=None, fire_config=None,
            investment_notes=[], conn=conn,
            country="SI", prices_conn=prices_conn,
            shared_mode=True,
            percentage_only=share.percentage_only,
            include_holdings=share.include_holdings,
        )

        share_meta = json.dumps({
            "shared": True,
            "label": share.label,
            "percentage_only": share.percentage_only,
            "include_holdings": share.include_holdings,
            "scope": share.scope,
        })
        d_script_end = html.find(";</script>", html.find("<script>const D="))
        if d_script_end != -1:
            html = html[:d_script_end] + f";D.share={share_meta};D.user=null" + html[d_script_end:]

        handler.send_response(200)
        handler.send_header("Content-Type", "text/html; charset=utf-8")
        handler.send_header("Cache-Control", "public, max-age=300")
        handler.end_headers()
        handler.wfile.write(html.encode("utf-8"))
    except Exception as e:
        handler.send_response(500)
        handler.send_header("Content-Type", "text/plain")
        handler.end_headers()
        handler.wfile.write(f"Error loading shared portfolio: {e}".encode("utf-8"))
    finally:
        if prices_conn:
            prices_conn.close()
        if conn:
            conn.close()
