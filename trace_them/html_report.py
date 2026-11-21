"""Self-contained Atlassian Design System HTML report renderer and opener."""

from __future__ import annotations

from datetime import datetime, timezone
import html
import json
import os
from pathlib import Path
import webbrowser
from urllib.parse import urlsplit

from trace_them.site_types import get_site_types

# Brand mark ("06. Orbital Footprint") + Iconify `lucide` (ISC license) SVGs retrieved via `iconify-cli get`.
ICONS: dict[str, str] = {
    "brand": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 100 100" fill="none" aria-hidden="true">'
        '<g stroke="currentColor" stroke-linecap="round">'
        '<path d="M 22 25 A 38 38 0 0 1 78 25" stroke-width="6.5"/>'
        '<path d="M 78 75 A 38 38 0 0 1 22 75" stroke-width="6.5"/>'
        '<path d="M 33 52 A 17 17 0 0 1 67 52" stroke-width="6"/>'
        '<path d="M 41 56 A 9 9 0 0 1 59 56" stroke-width="6"/>'
        '<path d="M 50 56 V 70" stroke-width="6"/></g>'
        '<g fill="currentColor">'
        '<circle cx="15" cy="50" r="6"/><circle cx="85" cy="50" r="6"/><circle cx="50" cy="28" r="5"/></g></svg>'
    ),
    "search": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" aria-hidden="true">'
        '<g fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2">'
        '<path d="m21 21l-4.34-4.34"/><circle cx="11" cy="11" r="8"/></g></svg>'
    ),
    "user": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" aria-hidden="true">'
        '<g fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2">'
        '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></g></svg>'
    ),
    "mail": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" aria-hidden="true">'
        '<g fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2">'
        '<path d="m22 7l-8.991 5.727a2 2 0 0 1-2.009 0L2 7"/><rect width="20" height="16" x="2" y="4" rx="2"/></g></svg>'
    ),
    "circle-check": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" aria-hidden="true">'
        '<g fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2">'
        '<circle cx="12" cy="12" r="10"/><path d="m16 9l-5.5 5.5L8 12"/></g></svg>'
    ),
    "circle-minus": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" aria-hidden="true">'
        '<g fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2">'
        '<circle cx="12" cy="12" r="10"/><path d="M8 12h8"/></g></svg>'
    ),
    "shield-alert": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" aria-hidden="true">'
        '<path fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" '
        'd="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 '
        '6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1zm-8-5v4m0 4h.01"/></svg>'
    ),
    "clock": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" aria-hidden="true">'
        '<g fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2">'
        '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/></g></svg>'
    ),
    "alert-circle": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" aria-hidden="true">'
        '<g fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2">'
        '<circle cx="12" cy="12" r="10"/><path d="M12 8v4m0 4h.01"/></g></svg>'
    ),
    "circle-help": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" aria-hidden="true">'
        '<g fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2">'
        '<circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3m.08 4h.01"/></g></svg>'
    ),
    "external-link": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" aria-hidden="true">'
        '<path fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" '
        'd="M15 3h6v6m-11 5L21 3m-3 10v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/></svg>'
    ),
    "chevron-down": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" aria-hidden="true">'
        '<path fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" '
        'd="m6 9l6 6l6-6"/></svg>'
    ),
    "download": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" aria-hidden="true">'
        '<g fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2">'
        '<path d="M12 15V3m9 12v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10l5 5l5-5"/></g></svg>'
    ),
    "copy": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" aria-hidden="true">'
        '<g fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2">'
        '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/>'
        '<path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></g></svg>'
    ),
    "info": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" aria-hidden="true">'
        '<g fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2">'
        '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4m0-4h.01"/></g></svg>'
    ),
    "alert-triangle": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" aria-hidden="true">'
        '<path fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" '
        'd="m21.73 18l-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3M12 9v4m0 4h.01"/></svg>'
    ),
    "ban": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" aria-hidden="true">'
        '<g fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2">'
        '<circle cx="12" cy="12" r="10"/><path d="M4.929 4.929L19.07 19.071"/></g></svg>'
    ),
    "file-text": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" aria-hidden="true">'
        '<g fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2">'
        '<path d="M6 22a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8a2.4 2.4 0 0 1 1.704.706l3.588 3.588A2.4 2.4 0 0 1 20 8v12a2 2 0 0 1-2 2z"/>'
        '<path d="M14 2v5a1 1 0 0 0 1 1h5M10 9H8m8 4H8m8 4H8"/></g></svg>'
    ),
    "check": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" aria-hidden="true">'
        '<path fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" '
        'd="M20 6L9 17l-5-5"/></svg>'
    ),
    "arrow-up": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" aria-hidden="true">'
        '<path fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" '
        'd="m5 12l7-7l7 7m-7 7V5"/></svg>'
    ),
    "arrow-down": (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" aria-hidden="true">'
        '<path fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2" '
        'd="M12 5v14m7-7l-7 7l-7-7"/></svg>'
    ),
}

_STATUS_APPEARANCE: dict[str, tuple[str, str, str]] = {
    "found": ("success", "circle-check", "Found"),
    "not_found": ("neutral", "circle-minus", "Not found"),
    "blocked": ("warning", "shield-alert", "Blocked"),
    "rate_limited": ("warning", "clock", "Rate limited"),
    "budget_exhausted": ("warning", "clock", "Budget exhausted"),
    "error": ("danger", "alert-circle", "Error"),
    "invalid": ("danger", "ban", "Invalid"),
    "cancelled": ("danger", "ban", "Cancelled"),
    "unknown": ("info", "circle-help", "Unknown"),
    "unsupported": ("info", "circle-help", "Unsupported"),
    "missing_config": ("info", "alert-triangle", "Missing config"),
}

_ASSOCIATION_APPEARANCE: dict[str, tuple[str, str]] = {
    "source_reported": ("discovery", "Source reported"),
    "unverified": ("neutral", "Unverified"),
}


def _esc(value: object) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def _safe_http_url(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = urlsplit(value.strip())
    except ValueError:
        return None
    if parsed.scheme.lower() in ("http", "https") and parsed.hostname:
        return value.strip()
    return None


def _safe_embedded_json(data: object) -> str:
    raw = json.dumps(data, indent=2, ensure_ascii=False)
    return (
        raw.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _icon(name: str, extra_class: str = "") -> str:
    cls = f"ads-icon {extra_class}".strip()
    return f'<span class="{cls}">{ICONS.get(name, ICONS["info"])}</span>'


def _status_lozenge(status: str) -> str:
    appearance, icon_name, label = _STATUS_APPEARANCE.get(
        status, ("info", "circle-help", status or "Unknown")
    )
    return (
        f'<span class="ads-lozenge ads-lozenge--{appearance}">'
        f'{_icon(icon_name)}<span>{_esc(label)}</span></span>'
    )


def _association_lozenge(association: str) -> str:
    appearance, label = _ASSOCIATION_APPEARANCE.get(
        association, ("neutral", association or "Unverified")
    )
    return f'<span class="ads-lozenge ads-lozenge--{appearance}"><span>{_esc(label)}</span></span>'


def _render_evidence_list(items: list[dict], heading: str) -> str:
    if not items:
        return ""
    rows = []
    for item in items:
        source = item.get("source", "")
        safe_url = _safe_http_url(source)
        if safe_url:
            source_html = (
                f'<a class="ads-link ads-mono" href="{_esc(safe_url)}" '
                f'target="_blank" rel="noopener noreferrer">{_esc(safe_url)}</a>'
            )
        else:
            source_html = f'<span class="ads-mono">{_esc(source)}</span>'
        rows.append(
            "<li>"
            f'<div class="evidence-top"><span class="ads-tag">{_esc(item.get("kind", ""))}</span>'
            f'<span class="evidence-time ads-mono">{_esc(item.get("observed_at", ""))}</span></div>'
            f'<div class="evidence-detail">{_esc(item.get("detail", ""))}</div>'
            f'<div class="evidence-source">Source: {source_html}</div>'
            "</li>"
        )
    return (
        f'<div class="evidence-group"><h4>{_esc(heading)}</h4>'
        f'<ul class="evidence-list">{"".join(rows)}</ul></div>'
    )


def _format_input_value(value: object) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return "" if value is None else str(value)


def render_html(report: dict) -> str:
    """Render a canonical Trace Them report into a self-contained Atlassian-styled HTML page."""
    input_info = report.get("input", {})
    input_type = str(input_info.get("type", "username"))
    input_display = _format_input_value(input_info.get("value"))
    tool_info = report.get("tool", {})
    tool_name = str(tool_info.get("name", "Trace Them"))
    tool_version = str(tool_info.get("version", ""))
    observed_at = str(report.get("observed_at", ""))
    schema_version = str(report.get("schema_version", "1.0"))
    manifest = report.get("manifest", {}) or {}
    selected_sites = manifest.get("selected_sites", []) or []
    skipped_sites = manifest.get("skipped", {}) or {}
    budget = report.get("request_budget")
    summary = report.get("summary", {}) or {}
    findings = report.get("findings", []) or []
    resolutions = report.get("resolutions", []) or []
    candidates = report.get("candidates", []) or []
    warnings = report.get("warnings", []) or []

    found_count = int(summary.get("found", 0))
    not_found_count = int(summary.get("not_found", 0))
    attention_count = sum(
        int(summary.get(key, 0))
        for key in ("blocked", "rate_limited", "error", "invalid", "budget_exhausted", "cancelled")
    )
    unknown_count = sum(
        int(summary.get(key, 0)) for key in ("unknown", "unsupported", "missing_config")
    )

    if isinstance(budget, dict):
        budget_text = f"{budget.get('used', 0)} / {budget.get('limit', 0)} used ({budget.get('remaining', 0)} left)"
    else:
        budget_text = "Not reported"

    input_icon = _icon("mail" if input_type == "email" else "user")

    warnings_html = "".join(
        f'<div class="ads-section-message ads-section-message--warning" role="alert">'
        f'<div class="ads-section-icon">{_icon("alert-triangle")}</div>'
        f'<div class="ads-section-content"><strong>Warning</strong><p>{_esc(item)}</p></div>'
        f"</div>"
        for item in warnings
    )

    # Filter chips based on statuses present in findings
    status_counts: dict[str, int] = {}
    origins_set: set[str] = set()
    for item in findings:
        st = str(item.get("status", "unknown"))
        status_counts[st] = status_counts.get(st, 0) + 1
        origins_set.add(str(item.get("origin", "input")))

    filter_chips = [
        f'<button type="button" class="ads-chip is-active" data-status-filter="all">'
        f'All <span class="ads-chip-count">{len(findings)}</span></button>'
    ]
    ordered_statuses = list(_STATUS_APPEARANCE.keys()) + [
        key for key in sorted(status_counts) if key not in _STATUS_APPEARANCE
    ]
    for st in ordered_statuses:
        count = status_counts.get(st, 0)
        if count == 0:
            continue
        _, _, label = _STATUS_APPEARANCE.get(st, ("info", "circle-help", st))
        filter_chips.append(
            f'<button type="button" class="ads-chip" data-status-filter="{_esc(st)}">'
            f'{_esc(label)} <span class="ads-chip-count">{count}</span></button>'
        )

    origin_options = ['<option value="all">All origins</option>'] + [
        f'<option value="{_esc(origin)}">{_esc(origin)}</option>'
        for origin in sorted(origins_set)
    ]

    finding_rows_html = []
    for idx, item in enumerate(findings):
        platform = str(item.get("platform", ""))
        username = str(item.get("username", ""))
        profile_url = str(item.get("profile_url", ""))
        status = str(item.get("status", "unknown"))
        reason = str(item.get("reason", ""))
        association = str(item.get("association", "unverified"))
        origin = str(item.get("origin", "input"))
        http_status = item.get("http_status")
        query_time = item.get("query_time")
        ev = item.get("evidence", []) or []
        assoc_ev = item.get("association_evidence", []) or []
        identifier = item.get("identifier")

        safe_url = _safe_http_url(profile_url)
        if safe_url:
            url_html = (
                f'<a class="ads-link ads-mono" href="{_esc(safe_url)}" '
                f'target="_blank" rel="noopener noreferrer">{_esc(safe_url)}{_icon("external-link")}</a>'
            )
        else:
            url_html = f'<span class="ads-mono">{_esc(profile_url or "—")}</span>'

        http_text = str(http_status) if http_status is not None else "—"
        time_text = f"{float(query_time) * 1000:.0f} ms" if isinstance(query_time, (int, float)) else "—"
        site_types = get_site_types(platform)
        search_blob = " ".join([platform, username, profile_url, status, association, origin, reason]).lower()

        details_parts = [
            f'<div class="detail-reason"><strong>Observation reason:</strong> {_esc(reason)}</div>'
        ]
        if identifier:
            details_parts.append(
                f'<div class="detail-meta"><strong>Identifier:</strong> '
                f'<span class="ads-mono">{_esc(identifier)}</span></div>'
            )
        details_parts.append(_render_evidence_list(ev, f"Observation evidence ({len(ev)})"))
        details_parts.append(
            _render_evidence_list(assoc_ev, f"Association evidence ({len(assoc_ev)})")
        )

        finding_rows_html.append(
            f'<tr class="finding-row" data-idx="{idx}" data-status="{_esc(status)}" '
            f'data-association="{_esc(association)}" data-origin="{_esc(origin)}" '
            f'data-site-types="{_esc(" ".join(site_types))}" '
            f'data-search="{_esc(search_blob)}">'
            f'<td><button type="button" class="ads-icon-btn row-toggle" aria-expanded="false" '
            f'aria-label="Toggle evidence details" data-target="detail-{idx}">'
            f'{_icon("chevron-down")}</button></td>'
            f'<td class="cell-platform"><strong>{_esc(platform)}</strong></td>'
            f'<td class="ads-mono">{_esc(username)}</td>'
            f'<td>{_status_lozenge(status)}</td>'
            f'<td>{_association_lozenge(association)}</td>'
            f'<td><span class="ads-tag">{_esc(origin)}</span></td>'
            f'<td class="ads-mono cell-num">{_esc(http_text)}</td>'
            f'<td class="ads-mono cell-num">{_esc(time_text)}</td>'
            f'<td class="cell-url">{url_html}</td>'
            f"</tr>"
            f'<tr class="detail-row" id="detail-{idx}" hidden>'
            f'<td colspan="9"><div class="detail-box">{"".join(details_parts)}</div></td>'
            f"</tr>"
        )

    findings_body = (
        "".join(finding_rows_html)
        if finding_rows_html
        else '<tr><td colspan="9" class="empty-state">No profile findings were recorded for this run.</td></tr>'
    )

    resolutions_html = ""
    if resolutions:
        res_cards = []
        for res in resolutions:
            ev_html = _render_evidence_list(res.get("evidence", []) or [], "Provider evidence")
            res_cards.append(
                '<div class="ads-card sub-card">'
                f'<div class="sub-card-head"><strong>{_esc(res.get("provider", ""))}</strong>'
                f'{_status_lozenge(str(res.get("status", "unknown")))}</div>'
                f'<p class="sub-card-reason">{_esc(res.get("reason", ""))}</p>'
                f"{ev_html}</div>"
            )
        resolutions_html = (
            '<section class="ads-section">'
            f'<h2 class="ads-section-title">{_icon("mail")} Email Resolutions ({len(resolutions)})</h2>'
            f'<div class="sub-grid">{"".join(res_cards)}</div></section>'
        )

    candidates_html = ""
    if candidates:
        cand_rows = []
        for cand in candidates:
            ev_list = cand.get("evidence", []) or []
            ev_summary = "; ".join(str(item.get("detail", "")) for item in ev_list) or "—"
            cand_rows.append(
                "<tr>"
                f'<td class="ads-mono"><strong>{_esc(cand.get("username", ""))}</strong></td>'
                f'<td><span class="ads-tag">{_esc(cand.get("origin", ""))}</span></td>'
                f'<td>{_esc(cand.get("platform") or "—")}</td>'
                f'<td>{_esc(ev_summary)}</td>'
                "</tr>"
            )
        candidates_html = (
            '<section class="ads-section">'
            f'<h2 class="ads-section-title">{_icon("user")} Candidate Handles ({len(candidates)})</h2>'
            '<div class="ads-card table-wrap"><table class="ads-table">'
            "<thead><tr><th>Username</th><th>Origin</th><th>Source Platform</th><th>Basis</th></tr></thead>"
            f'<tbody>{"".join(cand_rows)}</tbody></table></div></section>'
        )

    skipped_html = ""
    if skipped_sites:
        skip_rows = "".join(
            f'<tr><td><strong>{_esc(name)}</strong></td><td>{_esc(reason)}</td></tr>'
            for name, reason in sorted(skipped_sites.items(), key=lambda kv: kv[0].casefold())
        )
        skipped_html = (
            '<section class="ads-section">'
            '<details class="ads-details">'
            f'<summary class="ads-details-summary">{_icon("chevron-down")}'
            f'<span>Policy &amp; NSFW Skipped Targets ({len(skipped_sites)})</span></summary>'
            '<div class="table-wrap"><table class="ads-table">'
            "<thead><tr><th>Target</th><th>Skip Reason</th></tr></thead>"
            f"<tbody>{skip_rows}</tbody></table></div></details></section>"
        )

    from trace_them.reporting import safe_filename

    embedded_json = _safe_embedded_json(report)
    download_filename = f"trace-them-{safe_filename(input_display or 'report')}.json"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:;">
<title>{_esc(tool_name)} Report — {_esc(input_display)}</title>
<style>
  :root {{
    --ds-surface: #FFFFFF;
    --ds-surface-sunken: #F7F8F9;
    --ds-surface-hovered: #F1F2F4;
    --ds-text: #172B4D;
    --ds-text-subtle: #44546F;
    --ds-text-subtlest: #626F86;
    --ds-border: rgba(9, 30, 66, 0.14);
    --ds-border-bold: #8590A2;
    --ds-border-focused: #388BFF;
    --ds-brand-bold: #0C66E4;
    --ds-brand-bold-hover: #0055CC;
    --ds-selected-bg: #E9F2FF;
    --ds-selected-text: #0C66E4;
    --ds-shadow-card: 0 1px 1px rgba(9, 30, 66, 0.25), 0 0 1px rgba(9, 30, 66, 0.31);
    --ds-radius-sm: 3px;
    --ds-radius-md: 4px;
    --ds-radius-lg: 8px;
    --ds-font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", "Roboto", "Oxygen", "Ubuntu", "Fira Sans", "Droid Sans", "Helvetica Neue", sans-serif;
    --ds-font-mono: "SFMono-Regular", "Consolas", "Liberation Mono", "Menlo", monospace;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    background: var(--ds-surface-sunken);
    color: var(--ds-text);
    font-family: var(--ds-font-sans);
    font-size: 14px;
    line-height: 1.45;
    -webkit-font-smoothing: antialiased;
  }}
  .ads-icon {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 16px;
    height: 16px;
    flex-shrink: 0;
    vertical-align: middle;
  }}
  .ads-icon svg {{ width: 100%; height: 100%; }}
  .ads-mono {{ font-family: var(--ds-font-mono); font-size: 12.5px; }}
  .ads-topbar {{
    position: sticky;
    top: 0;
    z-index: 20;
    height: 56px;
    background: var(--ds-surface);
    border-bottom: 1px solid var(--ds-border);
    padding: 0 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
  }}
  .ads-brand {{
    display: flex;
    align-items: center;
    gap: 10px;
    font-weight: 600;
    font-size: 15px;
    color: var(--ds-text);
  }}
  .ads-brand-mark {{
    width: 28px;
    height: 28px;
    border-radius: 6px;
    background: var(--ds-brand-bold);
    color: #FFFFFF;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }}
  .ads-brand-mark .ads-icon {{ width: 18px; height: 18px; }}
  .ads-version-badge {{
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.02em;
    padding: 2px 6px;
    border-radius: var(--ds-radius-sm);
    background: var(--ds-selected-bg);
    color: var(--ds-selected-text);
  }}
  .ads-actions {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
  .ads-btn {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: 32px;
    padding: 0 12px;
    border-radius: var(--ds-radius-sm);
    border: 1px solid var(--ds-border);
    background: var(--ds-surface);
    color: var(--ds-text);
    font-family: inherit;
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    transition: background-color 0.12s ease;
  }}
  .ads-btn:hover {{ background: var(--ds-surface-hovered); }}
  .ads-btn:focus-visible, .ads-input:focus-visible, .ads-select:focus-visible, .ads-chip:focus-visible {{
    outline: 2px solid var(--ds-border-focused);
    outline-offset: 2px;
  }}
  .ads-btn--primary {{
    background: var(--ds-brand-bold);
    border-color: var(--ds-brand-bold);
    color: #FFFFFF;
  }}
  .ads-btn--primary:hover {{ background: var(--ds-brand-bold-hover); }}
  .ads-container {{
    max-width: 1320px;
    margin: 0 auto;
    padding: 24px;
  }}
  .ads-breadcrumb {{
    font-size: 12px;
    color: var(--ds-text-subtlest);
    margin-bottom: 6px;
  }}
  .ads-page-header {{
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    align-items: flex-end;
    gap: 16px;
    margin-bottom: 20px;
  }}
  .ads-page-title {{
    margin: 0;
    font-size: 24px;
    font-weight: 600;
    letter-spacing: -0.01em;
    display: flex;
    align-items: center;
    gap: 10px;
    word-break: break-word;
  }}
  .ads-meta-row {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px 16px;
    margin-top: 8px;
    color: var(--ds-text-subtle);
    font-size: 12.5px;
  }}
  .ads-meta-item {{ display: inline-flex; align-items: center; gap: 5px; }}
  .ads-section-message {{
    display: flex;
    gap: 12px;
    padding: 12px 16px;
    border-radius: var(--ds-radius-md);
    margin-bottom: 12px;
    border: 1px solid transparent;
  }}
  .ads-section-message--info {{
    background: #E9F2FF;
    border-color: #CCE0FF;
    color: var(--ds-text);
  }}
  .ads-section-message--info .ads-section-icon {{ color: #0055CC; }}
  .ads-section-message--warning {{
    background: #FFF7D6;
    border-color: #F8E6A0;
    color: var(--ds-text);
  }}
  .ads-section-message--warning .ads-section-icon {{ color: #A54800; }}
  .ads-section-icon {{ padding-top: 2px; }}
  .ads-section-content p {{ margin: 2px 0 0; color: var(--ds-text-subtle); font-size: 13px; }}
  .ads-kpi-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
    gap: 12px;
    margin: 18px 0 22px;
  }}
  .ads-card {{
    background: var(--ds-surface);
    border-radius: var(--ds-radius-lg);
    box-shadow: var(--ds-shadow-card);
  }}
  .ads-kpi {{
    padding: 14px 16px;
  }}
  .ads-kpi-label {{
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: var(--ds-text-subtlest);
  }}
  .ads-kpi-value {{
    margin-top: 6px;
    font-size: 24px;
    font-weight: 600;
    color: var(--ds-text);
  }}
  .ads-kpi-value--success {{ color: #216E4E; }}
  .ads-kpi-value--warning {{ color: #974F0C; }}
  .ads-kpi-value--info {{ color: #0055CC; }}
  .ads-kpi-sub {{
    margin-top: 2px;
    font-size: 12px;
    color: var(--ds-text-subtlest);
  }}
  .ads-section {{ margin-top: 24px; }}
  .ads-section-title {{
    margin: 0 0 12px;
    font-size: 16px;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  .ads-toolbar {{
    padding: 14px 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    border-bottom: 1px solid var(--ds-border);
  }}
  .ads-toolbar-row {{
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px;
  }}
  .ads-search-box {{
    position: relative;
    flex: 1 1 240px;
    max-width: 420px;
  }}
  .ads-search-box .ads-icon {{
    position: absolute;
    left: 10px;
    top: 50%;
    transform: translateY(-50%);
    color: var(--ds-text-subtlest);
    pointer-events: none;
  }}
  .ads-input, .ads-select {{
    height: 34px;
    border: 1px solid var(--ds-border-bold);
    border-radius: var(--ds-radius-sm);
    background: var(--ds-surface);
    color: var(--ds-text);
    font-family: inherit;
    font-size: 13px;
    padding: 0 10px;
  }}
  .ads-search-box .ads-input {{ width: 100%; padding-left: 32px; }}
  .ads-chips {{ display: flex; flex-wrap: wrap; gap: 6px; }}
  .ads-chip {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    height: 28px;
    padding: 0 10px;
    border-radius: var(--ds-radius-sm);
    border: 1px solid var(--ds-border);
    background: var(--ds-surface-sunken);
    color: var(--ds-text-subtle);
    font-family: inherit;
    font-size: 12.5px;
    font-weight: 500;
    cursor: pointer;
  }}
  .ads-chip:hover {{ background: var(--ds-surface-hovered); }}
  .ads-chip.is-active {{
    background: var(--ds-selected-bg);
    border-color: #85B8FF;
    color: var(--ds-selected-text);
    font-weight: 600;
  }}
  .ads-chip-count {{
    background: rgba(9, 30, 66, 0.08);
    padding: 0 5px;
    border-radius: 10px;
    font-size: 11px;
  }}
  .table-wrap {{ overflow-x: auto; }}
  .ads-table {{
    width: 100%;
    border-collapse: collapse;
    text-align: left;
  }}
  .ads-table th {{
    font-size: 12px;
    font-weight: 600;
    color: var(--ds-text-subtle);
    background: var(--ds-surface);
    border-bottom: 2px solid var(--ds-border);
    padding: 10px 12px;
    white-space: nowrap;
  }}
  .ads-table td {{
    padding: 10px 12px;
    border-bottom: 1px solid var(--ds-border);
    vertical-align: middle;
  }}
  .finding-row:hover {{ background: var(--ds-surface-hovered); }}
  .cell-num {{ text-align: right; white-space: nowrap; color: var(--ds-text-subtle); }}
  .cell-url {{ max-width: 340px; word-break: break-all; }}
  .ads-link {{
    color: var(--ds-brand-bold);
    text-decoration: none;
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }}
  .ads-link:hover {{ text-decoration: underline; }}
  .ads-lozenge {{
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 2px 6px;
    border-radius: var(--ds-radius-sm);
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.02em;
    white-space: nowrap;
    border: 1px solid transparent;
  }}
  .ads-lozenge .ads-icon {{ width: 13px; height: 13px; }}
  .ads-lozenge--success {{ background: #DCFFF1; color: #216E4E; border-color: #BAF3DB; }}
  .ads-lozenge--neutral {{ background: #F1F2F4; color: #44546F; border-color: #DCDFE4; }}
  .ads-lozenge--warning {{ background: #FFF7D6; color: #7F5F01; border-color: #F8E6A0; }}
  .ads-lozenge--danger {{ background: #FFECEB; color: #AE2E24; border-color: #FFD5D2; }}
  .ads-lozenge--info {{ background: #E9F2FF; color: #0055CC; border-color: #CCE0FF; }}
  .ads-lozenge--discovery {{ background: #F3F0FF; color: #5E4DB2; border-color: #DFD8FD; }}
  .ads-tag {{
    display: inline-block;
    padding: 2px 6px;
    border-radius: var(--ds-radius-sm);
    background: #F1F2F4;
    color: var(--ds-text-subtle);
    font-size: 12px;
    font-family: var(--ds-font-mono);
  }}
  .ads-icon-btn {{
    width: 28px;
    height: 28px;
    border-radius: var(--ds-radius-sm);
    border: 1px solid transparent;
    background: transparent;
    color: var(--ds-text-subtle);
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }}
  .ads-icon-btn:hover {{ background: var(--ds-surface-hovered); }}
  .ads-icon-btn[aria-expanded="true"] .ads-icon {{ transform: rotate(180deg); }}
  .detail-row td {{ background: var(--ds-surface-sunken); padding: 0; }}
  .detail-box {{ padding: 14px 18px; display: grid; gap: 10px; }}
  .detail-reason, .detail-meta {{ font-size: 13px; color: var(--ds-text); }}
  .evidence-group h4 {{
    margin: 0 0 6px;
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    color: var(--ds-text-subtlest);
  }}
  .evidence-list {{
    margin: 0;
    padding: 0;
    list-style: none;
    display: grid;
    gap: 8px;
  }}
  .evidence-list li {{
    background: var(--ds-surface);
    border: 1px solid var(--ds-border);
    border-radius: var(--ds-radius-md);
    padding: 10px 12px;
  }}
  .evidence-top {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    margin-bottom: 4px;
  }}
  .evidence-time {{ color: var(--ds-text-subtlest); }}
  .evidence-detail {{ font-size: 13px; color: var(--ds-text); }}
  .evidence-source {{ margin-top: 4px; font-size: 12px; color: var(--ds-text-subtle); word-break: break-all; }}
  .sub-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    gap: 12px;
  }}
  .sub-card {{ padding: 14px 16px; }}
  .sub-card-head {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
    margin-bottom: 6px;
  }}
  .sub-card-reason {{ margin: 0 0 10px; color: var(--ds-text-subtle); }}
  .ads-details {{
    background: var(--ds-surface);
    border-radius: var(--ds-radius-lg);
    box-shadow: var(--ds-shadow-card);
  }}
  .ads-details-summary {{
    padding: 12px 16px;
    cursor: pointer;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 8px;
    list-style: none;
  }}
  .ads-details[open] .ads-details-summary {{ border-bottom: 1px solid var(--ds-border); }}
  .empty-state {{
    text-align: center;
    padding: 28px 16px;
    color: var(--ds-text-subtlest);
  }}
  .ads-footer {{
    margin-top: 28px;
    padding-top: 16px;
    border-top: 1px solid var(--ds-border);
    color: var(--ds-text-subtlest);
    font-size: 12px;
    display: flex;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 8px;
  }}
  .ads-scroll-nav {{
    position: fixed;
    right: 20px;
    bottom: 20px;
    z-index: 30;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }}
  .ads-scroll-btn {{
    width: 36px;
    height: 36px;
    border-radius: var(--ds-radius-md);
    border: 1px solid var(--ds-border);
    background: var(--ds-surface);
    color: var(--ds-text);
    box-shadow: var(--ds-shadow-card);
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    transition: background-color 0.12s ease, color 0.12s ease;
  }}
  .ads-scroll-btn:hover {{
    background: var(--ds-selected-bg);
    color: var(--ds-selected-text);
  }}
  .ads-scroll-btn:focus-visible {{
    outline: 2px solid var(--ds-border-focused);
    outline-offset: 2px;
  }}
  @media (max-width: 720px) {{
    .ads-container {{ padding: 14px; }}
    .ads-topbar {{ padding: 0 14px; }}
    .ads-scroll-nav {{ right: 12px; bottom: 12px; }}
  }}
</style>
</head>
<body>
<header class="ads-topbar">
  <div class="ads-brand">
    <span class="ads-brand-mark">{_icon("brand")}</span>
    <span>{_esc(tool_name)}</span>
    <span class="ads-version-badge">Schema {_esc(schema_version)}</span>
  </div>
  <div class="ads-actions">
    <button type="button" class="ads-btn" id="copy-json-btn">{_icon("copy")}<span>Copy JSON</span></button>
    <button type="button" class="ads-btn ads-btn--primary" id="download-json-btn" data-download-name="{_esc(download_filename)}">{_icon("download")}<span>Download JSON</span></button>
  </div>
</header>

<main class="ads-container">
  <div class="ads-breadcrumb">Trace Them / Observation Report / {_esc(input_type)}</div>
  <div class="ads-page-header">
    <div>
      <h1 class="ads-page-title">{input_icon}<span>{_esc(input_display or "Observation Report")}</span></h1>
      <div class="ads-meta-row">
        <span class="ads-meta-item">{_icon("clock")} <span>Observed: <strong class="ads-mono">{_esc(observed_at)}</strong></span></span>
        <span class="ads-meta-item">{_icon("file-text")} <span>Budget: <strong class="ads-mono">{_esc(budget_text)}</strong></span></span>
        <span class="ads-meta-item"><span>Selected targets: <strong>{len(selected_sites)}</strong></span></span>
        <span class="ads-meta-item"><span>Tool: <strong>{_esc(tool_name)} {_esc(tool_version)}</strong></span></span>
      </div>
    </div>
  </div>

  <div class="ads-section-message ads-section-message--info">
    <div class="ads-section-icon">{_icon("info")}</div>
    <div class="ads-section-content">
      <strong>Evidence Scope</strong>
      <p>Account existence (<code>found</code>) and identity ownership (<code>association</code>) are distinct observations. An <code>unverified</code> match means a public profile responded at that handle and does not establish ownership across platforms.</p>
    </div>
  </div>

  {warnings_html}

  <section class="ads-kpi-grid" aria-label="Summary metrics">
    <div class="ads-card ads-kpi">
      <div class="ads-kpi-label">Total Findings</div>
      <div class="ads-kpi-value">{len(findings)}</div>
      <div class="ads-kpi-sub">Visible rows: <span id="visible-count">{len(findings)}</span></div>
    </div>
    <div class="ads-card ads-kpi">
      <div class="ads-kpi-label">Found</div>
      <div class="ads-kpi-value ads-kpi-value--success">{found_count}</div>
      <div class="ads-kpi-sub">Heuristic public profile hits</div>
    </div>
    <div class="ads-card ads-kpi">
      <div class="ads-kpi-label">Not Found</div>
      <div class="ads-kpi-value">{not_found_count}</div>
      <div class="ads-kpi-sub">Explicit absence signals</div>
    </div>
    <div class="ads-card ads-kpi">
      <div class="ads-kpi-label">Blocked / Failed</div>
      <div class="ads-kpi-value ads-kpi-value--warning">{attention_count}</div>
      <div class="ads-kpi-sub">Blocked, rate-limited, errors</div>
    </div>
    <div class="ads-card ads-kpi">
      <div class="ads-kpi-label">Unknown / Other</div>
      <div class="ads-kpi-value ads-kpi-value--info">{unknown_count}</div>
      <div class="ads-kpi-sub">Offline, ambiguous, unconfigured</div>
    </div>
  </section>

  <section class="ads-section">
    <h2 class="ads-section-title">Platform Findings</h2>
    <div class="ads-card">
      <div class="ads-toolbar">
        <div class="ads-toolbar-row">
          <div class="ads-search-box">
            {_icon("search")}
            <input type="search" id="search-input" class="ads-input" placeholder="Filter by platform, username, URL, or reason..." aria-label="Filter findings">
          </div>
          <select id="site-type-filter" class="ads-select" aria-label="Filter by site type">
            <option value="all">All Types</option>
            <option value="social">Social Media</option>
            <option value="programming">Programming</option>
            <option value="gaming">Gaming</option>
          </select>
          <select id="association-filter" class="ads-select" aria-label="Filter by association">
            <option value="all">All associations</option>
            <option value="source_reported">source_reported</option>
            <option value="unverified">unverified</option>
          </select>
          <select id="origin-filter" class="ads-select" aria-label="Filter by origin">
            {"".join(origin_options)}
          </select>
          <button type="button" class="ads-btn" id="toggle-all-btn">Expand all evidence</button>
        </div>
        <div class="ads-chips" role="group" aria-label="Filter by status">
          {"".join(filter_chips)}
        </div>
      </div>
      <div class="table-wrap">
        <table class="ads-table">
          <thead>
            <tr>
              <th style="width:36px"></th>
              <th>Platform</th>
              <th>Username</th>
              <th>Status</th>
              <th>Association</th>
              <th>Origin</th>
              <th class="cell-num">HTTP</th>
              <th class="cell-num">Time</th>
              <th>Profile URL</th>
            </tr>
          </thead>
          <tbody id="findings-tbody">
            {findings_body}
          </tbody>
        </table>
      </div>
      <div class="empty-state" id="no-filter-matches" hidden>No findings match the current filters.</div>
    </div>
  </section>

  {resolutions_html}
  {candidates_html}
  {skipped_html}

  <footer class="ads-footer">
    <span>Manifest source: <span class="ads-mono">{_esc(manifest.get("source") or "N/A")}</span></span>
    <span>Generated locally by {_esc(tool_name)} {_esc(tool_version)} — offline self-contained report</span>
  </footer>
</main>

<div class="ads-scroll-nav" role="navigation" aria-label="Page scroll controls">
  <button type="button" class="ads-scroll-btn" id="scroll-top-btn" title="Scroll to top" aria-label="Scroll to top">{_icon("arrow-up")}</button>
  <button type="button" class="ads-scroll-btn" id="scroll-bottom-btn" title="Scroll to bottom" aria-label="Scroll to bottom">{_icon("arrow-down")}</button>
</div>

<script type="application/json" id="trace-them-report-data">{embedded_json}</script>
<script>
(function () {{
  const dataEl = document.getElementById("trace-them-report-data");
  const rawJson = dataEl ? dataEl.textContent : "{{}}";
  const searchInput = document.getElementById("search-input");
  const siteTypeSelect = document.getElementById("site-type-filter");
  const assocSelect = document.getElementById("association-filter");
  const originSelect = document.getElementById("origin-filter");
  const chips = Array.from(document.querySelectorAll("[data-status-filter]"));
  const rows = Array.from(document.querySelectorAll("tr.finding-row"));
  const visibleEl = document.getElementById("visible-count");
  const emptyFilterEl = document.getElementById("no-filter-matches");
  const toggleAllBtn = document.getElementById("toggle-all-btn");
  let activeStatus = "all";
  let allExpanded = false;

  function applyFilters() {{
    const q = (searchInput ? searchInput.value : "").trim().toLowerCase();
    const siteType = siteTypeSelect ? siteTypeSelect.value : "all";
    const assoc = assocSelect ? assocSelect.value : "all";
    const origin = originSelect ? originSelect.value : "all";
    let visible = 0;

    rows.forEach((row) => {{
      const matchStatus = activeStatus === "all" || row.dataset.status === activeStatus;
      const rowTypes = (row.dataset.siteTypes || "").split(" ").filter(Boolean);
      const matchSiteType = siteType === "all" || rowTypes.includes(siteType);
      const matchAssoc = assoc === "all" || row.dataset.association === assoc;
      const matchOrigin = origin === "all" || row.dataset.origin === origin;
      const matchQuery = !q || (row.dataset.search || "").includes(q);
      const show = matchStatus && matchSiteType && matchAssoc && matchOrigin && matchQuery;
      row.hidden = !show;
      const detail = document.getElementById("detail-" + row.dataset.idx);
      if (!show && detail) {{
        detail.hidden = true;
        const btn = row.querySelector(".row-toggle");
        if (btn) btn.setAttribute("aria-expanded", "false");
      }}
      if (show) visible += 1;
    }});

    if (visibleEl) visibleEl.textContent = String(visible);
    if (emptyFilterEl) emptyFilterEl.hidden = !(rows.length > 0 && visible === 0);
  }}

  chips.forEach((chip) => {{
    chip.addEventListener("click", () => {{
      activeStatus = chip.dataset.statusFilter || "all";
      chips.forEach((c) => c.classList.toggle("is-active", c === chip));
      applyFilters();
    }});
  }});

  if (searchInput) searchInput.addEventListener("input", applyFilters);
  if (siteTypeSelect) siteTypeSelect.addEventListener("change", applyFilters);
  if (assocSelect) assocSelect.addEventListener("change", applyFilters);
  if (originSelect) originSelect.addEventListener("change", applyFilters);

  document.addEventListener("click", (event) => {{
    const btn = event.target.closest(".row-toggle");
    if (!btn) return;
    const detail = document.getElementById(btn.dataset.target);
    if (!detail) return;
    const expanded = btn.getAttribute("aria-expanded") === "true";
    btn.setAttribute("aria-expanded", expanded ? "false" : "true");
    detail.hidden = expanded;
  }});

  if (toggleAllBtn) {{
    toggleAllBtn.addEventListener("click", () => {{
      allExpanded = !allExpanded;
      rows.forEach((row) => {{
        if (row.hidden) return;
        const detail = document.getElementById("detail-" + row.dataset.idx);
        const btn = row.querySelector(".row-toggle");
        if (detail) detail.hidden = !allExpanded;
        if (btn) btn.setAttribute("aria-expanded", allExpanded ? "true" : "false");
      }});
      toggleAllBtn.textContent = allExpanded ? "Collapse all evidence" : "Expand all evidence";
    }});
  }}

  const copyBtn = document.getElementById("copy-json-btn");
  if (copyBtn) {{
    copyBtn.addEventListener("click", async () => {{
      const label = copyBtn.querySelector("span:last-child");
      try {{
        await navigator.clipboard.writeText(rawJson);
        if (label) label.textContent = "Copied";
        setTimeout(() => {{ if (label) label.textContent = "Copy JSON"; }}, 1800);
      }} catch (_err) {{
        if (label) label.textContent = "Copy failed";
      }}
    }});
  }}

  const dlBtn = document.getElementById("download-json-btn");
  if (dlBtn) {{
    dlBtn.addEventListener("click", () => {{
      const blob = new Blob([rawJson], {{ type: "application/json;charset=utf-8" }});
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = dlBtn.dataset.downloadName || "trace-them-report.json";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    }});
  }}

  const scrollTopBtn = document.getElementById("scroll-top-btn");
  if (scrollTopBtn) {{
    scrollTopBtn.addEventListener("click", () => {{
      window.scrollTo({{ top: 0, behavior: "instant" }});
    }});
  }}

  const scrollBottomBtn = document.getElementById("scroll-bottom-btn");
  if (scrollBottomBtn) {{
    scrollBottomBtn.addEventListener("click", () => {{
      window.scrollTo({{ top: document.documentElement.scrollHeight, behavior: "instant" }});
    }});
  }}
}})();
</script>
</body>
</html>
"""


def write_html(report: dict, output_dir: str | Path, *, stem: str | None = None) -> Path:
    """Write a timestamped HTML visualization report into output_dir and return its path."""
    from trace_them.reporting import _atomic_write, safe_filename

    directory = Path(output_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    base_stem = safe_filename(stem if stem is not None else report["input"]["value"])
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    path = directory / f"{timestamp}-{base_stem}.html"
    _atomic_write(path, render_html(report).encode("utf-8"))
    return path


def list_html_files(output_dir: str | Path) -> list[Path]:
    """List regular .html report files directly inside output_dir, newest first."""
    directory = Path(output_dir).expanduser().resolve()
    if not directory.is_dir():
        raise FileNotFoundError(f"HTML report folder does not exist: {directory}")
    html_files = [
        item for item in directory.iterdir()
        if item.is_file() and item.suffix.lower() == ".html"
    ]
    return sorted(html_files, key=lambda item: (item.stat().st_mtime_ns, item.name), reverse=True)


def find_latest_html(output_dir: str | Path) -> Path:
    """Return the newest .html report file inside output_dir."""
    directory = Path(output_dir).expanduser().resolve()
    html_files = list_html_files(directory)
    if not html_files:
        raise FileNotFoundError(f"No HTML report files found in {directory}")
    return html_files[0]


def delete_html_files(
    output_dir: str | Path,
    filenames: list[str] | None = None,
    *,
    delete_all: bool = False,
    dry_run: bool = False,
) -> list[Path]:
    """Delete one, multiple, or all .html files strictly inside output_dir."""
    directory = Path(output_dir).expanduser().resolve()
    if not directory.is_dir():
        raise FileNotFoundError(f"HTML report folder does not exist: {directory}")
    if delete_all:
        targets = list_html_files(directory)
    else:
        if not filenames:
            raise ValueError("Specify one or more HTML files to delete, or use delete_all=True")
        targets = []
        for raw in dict.fromkeys(filenames):
            if (
                not isinstance(raw, str)
                or not raw.strip()
                or any(ord(char) < 32 or ord(char) == 127 for char in raw)
            ):
                raise ValueError("HTML filename must be nonempty and contain no control characters")
            raw_path = Path(raw.strip()).expanduser()
            candidate = (
                raw_path.resolve()
                if raw_path.is_absolute() or len(raw_path.parts) > 1
                else (directory / raw_path).resolve()
            )
            if candidate.parent != directory:
                raise ValueError(f"Refusing to delete file outside configured HTML folder: {raw}")
            if candidate.suffix.lower() != ".html":
                raise ValueError(f"Only .html files can be deleted: {candidate.name}")
            if not candidate.is_file():
                raise FileNotFoundError(f"HTML report file not found: {candidate.name}")
            targets.append(candidate)
    if not dry_run:
        for target in targets:
            target.unlink()
    return targets


def open_html_file(path: Path) -> None:
    """Open a local HTML report in the system default browser."""
    target = Path(path).resolve()
    if not target.is_file():
        raise FileNotFoundError(f"HTML report file does not exist: {target}")
    opened = webbrowser.open(target.as_uri())
    if not opened and os.name == "nt":
        os.startfile(str(target))  # type: ignore[attr-defined]
        return
    if not opened:
        raise OSError(f"Unable to open browser for {target}")
