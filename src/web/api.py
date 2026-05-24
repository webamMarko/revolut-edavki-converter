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
    portfolio_id = session.get("active_portfolio_id", 1)  # Default to portfolio 1
    conn = portfolio_conn(session, get_session_token(handler))
    from ..prices_db import get_prices_conn_or_none
    prices_conn = get_prices_conn_or_none()
    try:
        from ..analytics import compute_analytics
        from ..analytics_cache import compute_data_hash, get_cached, put_cache
        data_hash = compute_data_hash(conn, prices_conn, portfolio_id=portfolio_id)
        cached = get_cached(conn, scope, data_hash, portfolio_id=portfolio_id)
        if cached is not None:
            ac_analytics = cached
        else:
            ac_analytics = compute_analytics(conn, scope=scope, prices_conn=prices_conn, portfolio_id=portfolio_id)
            put_cache(conn, scope, data_hash, ac_analytics, portfolio_id=portfolio_id)

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


# ------------------------------------------------------------------
# Portfolio API (multi-portfolio support)
# ------------------------------------------------------------------

def api_get_portfolios(handler):
    """GET /api/portfolios — list user's portfolios with active_portfolio_id."""
    session = get_session(handler)
    conn = portfolio_conn(session, get_session_token(handler))
    try:
        from .. import db
        portfolios = db.list_portfolios(conn)
        response = {
            "portfolios": portfolios,
            "active_portfolio_id": session.get("active_portfolio_id", 1) if session else 1,
            "max_portfolios": 5,
        }
        json_response(handler, response)
    except Exception as e:
        json_response(handler, {"error": str(e)}, status=500)
    finally:
        conn.close()


def api_create_portfolio(handler):
    """POST /api/portfolios — create a new portfolio."""
    session = get_session(handler)
    conn = portfolio_conn(session, get_session_token(handler))
    try:
        body = json.loads(handler.rfile.read(int(handler.headers.get("Content-Length", 0))).decode())
        name = body.get("name", "").strip()
        if not name:
            json_response(handler, {"error": "Portfolio name is required"}, status=400)
            return

        from .. import db
        try:
            portfolio = db.create_portfolio(conn, name)
            json_response(handler, portfolio, status=201)
        except ValueError as e:
            if "Maximum of 5 portfolios" in str(e):
                json_response(handler, {"error": str(e)}, status=409)
            else:
                json_response(handler, {"error": str(e)}, status=400)
    except Exception as e:
        json_response(handler, {"error": str(e)}, status=500)
    finally:
        conn.close()


def api_update_portfolio(handler, portfolio_id: int):
    """PUT /api/portfolios/{id} — rename a portfolio."""
    session = get_session(handler)
    conn = portfolio_conn(session, get_session_token(handler))
    try:
        body = json.loads(handler.rfile.read(int(handler.headers.get("Content-Length", 0))).decode())
        new_name = body.get("name", "").strip()
        if not new_name:
            json_response(handler, {"error": "Portfolio name is required"}, status=400)
            return

        from .. import db
        try:
            db.rename_portfolio(conn, portfolio_id, new_name)
            # Return the updated portfolio
            updated = conn.execute(
                "SELECT id, name, slug, is_default FROM portfolios WHERE id = ?",
                (portfolio_id,)
            ).fetchone()
            if updated:
                response = dict(updated)
                json_response(handler, response)
            else:
                json_response(handler, {"error": "Portfolio not found"}, status=404)
        except ValueError as e:
            json_response(handler, {"error": str(e)}, status=400)
    except Exception as e:
        json_response(handler, {"error": str(e)}, status=500)
    finally:
        conn.close()


def api_delete_portfolio(handler, portfolio_id: int):
    """DELETE /api/portfolios/{id} — delete a portfolio."""
    session = get_session(handler)
    conn = portfolio_conn(session, get_session_token(handler))
    try:
        from .. import db
        try:
            db.delete_portfolio(conn, portfolio_id)
            json_response(handler, {"deleted": True})
        except ValueError as e:
            if "Cannot delete default portfolio" in str(e):
                json_response(handler, {"error": str(e)}, status=400)
            else:
                json_response(handler, {"error": str(e)}, status=400)
    except Exception as e:
        json_response(handler, {"error": str(e)}, status=500)
    finally:
        conn.close()


def api_switch_portfolio(handler):
    """POST /api/switch-portfolio — set active portfolio in session."""
    from .. import users
    session = get_session(handler)
    token = get_session_token(handler)
    try:
        body = json.loads(handler.rfile.read(int(handler.headers.get("Content-Length", 0))).decode())
        portfolio_id = body.get("portfolio_id")
        if not portfolio_id or not isinstance(portfolio_id, int):
            json_response(handler, {"error": "portfolio_id must be an integer"}, status=400)
            return

        users_conn = users.get_users_db()
        try:
            users.set_active_portfolio(token, portfolio_id, users_conn)
            json_response(handler, {"active_portfolio_id": portfolio_id})
        finally:
            users_conn.close()
    except Exception as e:
        json_response(handler, {"error": str(e)}, status=500)


# ------------------------------------------------------------------
# Dashboard Layout API
# ------------------------------------------------------------------

# Widget registry: hardcoded map of widget ID → metadata
WIDGET_REGISTRY = {
    "quick-glance": {"label": "Quick Glance", "template": "sections/quick_glance.html.j2", "default_w": 4, "default_h": 2, "min_w": 3, "min_h": 2},
    "health-score": {"label": "Health Score", "template": "sections/health_score.html.j2", "default_w": 4, "default_h": 2, "min_w": 3, "min_h": 2},
    "summary": {"label": "Summary", "template": "sections/summary.html.j2", "default_w": 6, "default_h": 4, "min_w": 4, "min_h": 3},
    "charts": {"label": "Charts", "template": "sections/charts.html.j2", "default_w": 8, "default_h": 5, "min_w": 6, "min_h": 4},
    "positions": {"label": "Positions", "template": "sections/positions.html.j2", "default_w": 12, "default_h": 4, "min_w": 6, "min_h": 3},
    "dividends": {"label": "Dividends", "template": "sections/dividends.html.j2", "default_w": 6, "default_h": 4, "min_w": 4, "min_h": 3},
    "projections": {"label": "Projections", "template": "sections/projections.html.j2", "default_w": 6, "default_h": 4, "min_w": 4, "min_h": 3},
    "notes": {"label": "Notes", "template": "sections/notes.html.j2", "default_w": 6, "default_h": 3, "min_w": 4, "min_h": 2},
    "real-estate": {"label": "Real Estate", "template": "sections/real_estate.html.j2", "default_w": 6, "default_h": 4, "min_w": 4, "min_h": 3},
    "risk": {"label": "Risk", "template": "sections/risk.html.j2", "default_w": 6, "default_h": 4, "min_w": 4, "min_h": 3},
    "dca-strategy": {"label": "DCA Strategy", "template": "sections/dca_strategy.html.j2", "default_w": 6, "default_h": 4, "min_w": 4, "min_h": 3},
    "tax-summary": {"label": "Tax Summary", "template": "sections/tax.html.j2", "default_w": 8, "default_h": 5, "min_w": 6, "min_h": 4},
    "tax-calendar": {"label": "Tax Calendar", "template": "sections/year_end_calendar.html.j2", "default_w": 6, "default_h": 4, "min_w": 4, "min_h": 3},
    "smart-sell": {"label": "Smart Sell", "template": "sections/smart_sell.html.j2", "default_w": 6, "default_h": 4, "min_w": 4, "min_h": 3},
    "tax-wizard": {"label": "Tax Wizard", "template": "sections/tax_wizard.html.j2", "default_w": 6, "default_h": 4, "min_w": 4, "min_h": 3},
    "transactions": {"label": "History", "template": "sections/transactions.html.j2", "default_w": 12, "default_h": 4, "min_w": 6, "min_h": 3},
}

# Default layout for first-time users
DEFAULT_LAYOUT = {
    "widgets": [
        {"id": "quick-glance", "x": 0, "y": 0, "w": 4, "h": 2},
        {"id": "summary", "x": 4, "y": 0, "w": 4, "h": 4},
        {"id": "charts", "x": 0, "y": 2, "w": 8, "h": 4},
        {"id": "positions", "x": 0, "y": 6, "w": 12, "h": 4},
    ]
}


def save_dashboard_layout(user_id: int, layout: dict, conn=None):
    """Save dashboard layout for a user. Returns True on success.
    
    Validates:
    - widgets is an array of 0-16 items
    - each widget id is in WIDGET_REGISTRY
    - x, y, w, h are non-negative integers
    - w ≤ 12, h ≤ 8
    - no duplicate widget IDs
    """
    from .. import users
    
    close = conn is None
    if conn is None:
        conn = users.get_users_db()
    
    try:
        widgets = layout.get("widgets", [])
        
        # Validate widget count
        if not isinstance(widgets, list):
            raise ValueError("widgets must be an array")
        if len(widgets) > 16:
            raise ValueError("Too many widgets (max 16)")
        
        # Validate each widget
        seen_ids = set()
        for widget in widgets:
            widget_id = widget.get("id")
            x = widget.get("x")
            y = widget.get("y")
            w = widget.get("w")
            h = widget.get("h")
            
            # Validate widget ID
            if widget_id not in WIDGET_REGISTRY:
                raise ValueError(f"Invalid widget ID: {widget_id}")
            
            # Check for duplicates
            if widget_id in seen_ids:
                raise ValueError(f"Duplicate widget ID: {widget_id}")
            seen_ids.add(widget_id)
            
            # Validate coordinates
            if not all(isinstance(v, int) and v >= 0 for v in [x, y, w, h]):
                raise ValueError("Invalid coordinates (must be non-negative integers)")
            
            # Validate bounds
            if w > 12:
                raise ValueError(f"Widget width {w} exceeds grid width (12)")
            if h > 8:
                raise ValueError(f"Widget height {h} exceeds max height (8)")
        
        # Save to database
        layout_json = json.dumps(layout)
        conn.execute(
            "UPDATE users SET dashboard_layout = ? WHERE id = ?",
            (layout_json, user_id)
        )
        conn.commit()
        
        return True
    
    finally:
        if close:
            conn.close()


def get_dashboard_layout(user_id: int, conn=None):
    """Get dashboard layout for a user. Returns saved layout or default.
    
    Returns dict with:
    - widgets: array of widget objects
    - isDefault: boolean indicating if this is the default layout
    """
    from .. import users
    
    close = conn is None
    if conn is None:
        conn = users.get_users_db()
    
    try:
        cursor = conn.execute(
            "SELECT dashboard_layout FROM users WHERE id = ?",
            (user_id,)
        )
        row = cursor.fetchone()
        
        if not row or not row[0]:
            # No saved layout, return default
            return {"widgets": DEFAULT_LAYOUT["widgets"], "isDefault": True}
        
        # Parse saved layout
        layout = json.loads(row[0])
        return {"widgets": layout.get("widgets", []), "isDefault": False}
    
    finally:
        if close:
            conn.close()


def api_save_dashboard_layout(handler):
    """PUT /api/dashboard-layout — save user's dashboard layout."""
    from .. import users
    
    session = get_session(handler)
    if not session:
        json_response(handler, {"error": "Unauthorized"}, status=401)
        return
    
    # Role gate: premium/admin only
    if session.get("role") not in ("premium", "admin", "cofounder"):
        json_response(handler, {"error": "Forbidden: premium/admin access required"}, status=403)
        return
    
    try:
        body = json.loads(handler.rfile.read(int(handler.headers.get("Content-Length", 0))).decode())
        user_id = session.get("user_id")
        
        users_conn = users.get_users_db()
        try:
            save_dashboard_layout(user_id, body, users_conn)
            json_response(handler, {"status": "ok"})
        finally:
            users_conn.close()
    
    except ValueError as e:
        json_response(handler, {"error": str(e)}, status=400)
    except Exception as e:
        json_response(handler, {"error": str(e)}, status=500)


def api_get_dashboard_layout(handler):
    """GET /api/dashboard-layout — get user's dashboard layout."""
    from .. import users
    
    session = get_session(handler)
    if not session:
        json_response(handler, {"error": "Unauthorized"}, status=401)
        return
    
    try:
        user_id = session.get("user_id")
        users_conn = users.get_users_db()
        try:
            layout = get_dashboard_layout(user_id, users_conn)
            json_response(handler, layout)
        finally:
            users_conn.close()
    
    except Exception as e:
        json_response(handler, {"error": str(e)}, status=500)
