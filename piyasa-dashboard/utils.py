def signal_color(value):
    if value is None:
        return "#6B7280"
    if value > 0:
        return "#10B981"
    if value < 0:
        return "#EF4444"
    return "#F59E0B"


def signal_icon(value):
    if value is None:
        return "⚪"
    if value > 0:
        return "🟢"
    if value < 0:
        return "🔴"
    return "🟡"


def signal_label(value):
    if value is None:
        return "Veri Yok"
    if value > 0:
        return "Pozitif"
    if value < 0:
        return "Negatif"
    return "Nötr"


def format_number(val, decimals=2):
    if val is None:
        return "N/A"
    try:
        if abs(val) >= 1_000_000:
            return f"{val/1_000_000:,.{decimals}f}M"
        if abs(val) >= 1_000:
            return f"{val:,.{decimals}f}"
        return f"{val:.{decimals}f}"
    except (TypeError, ValueError):
        return "N/A"


def pct_format(val):
    if val is None:
        return "N/A"
    return f"%{val:.2f}"


def score_bar_html(label, score, max_score, color=None):
    if color is None:
        color = signal_color(score)
    pct = min(max(abs(score) / max_score * 100, 5), 100) if max_score > 0 else 0
    sign = "+" if score > 0 else ""
    return f"""
    <div style="margin-bottom:8px;">
        <div style="display:flex; justify-content:space-between; font-size:13px; margin-bottom:2px;">
            <span style="color:#374151;">{label}</span>
            <span style="font-weight:700; color:{color};">{sign}{score:.1f}</span>
        </div>
        <div style="background:#E5E7EB; border-radius:4px; height:8px; overflow:hidden;">
            <div style="background:{color}; width:{pct:.0f}%; height:100%; border-radius:4px;"></div>
        </div>
    </div>
    """


def indicator_row_html(name, value, threshold, signal_val, points, description):
    color = signal_color(signal_val)
    icon = signal_icon(signal_val)
    pts_str = f"+{points}" if points > 0 else str(points)
    pts_color = signal_color(points)
    return f"""
    <tr style="border-bottom:1px solid #F3F4F6;">
        <td style="padding:8px 12px; font-size:13px;">{icon} {name}</td>
        <td style="padding:8px 12px; font-size:13px; font-weight:600;">{value}</td>
        <td style="padding:8px 12px; font-size:12px; color:#6B7280;">{threshold}</td>
        <td style="padding:8px 12px; font-size:13px; font-weight:700; color:{pts_color};">{pts_str}</td>
        <td style="padding:8px 12px; font-size:12px; color:#6B7280;">{description}</td>
    </tr>
    """


def sub_score_card_html(label, score, icon="📊"):
    color = signal_color(score)
    sign = "+" if score > 0 else ""
    return f"""
    <div style="flex:1; background:#F9FAFB; border:1px solid #E5E7EB; border-radius:10px; padding:14px; text-align:center; min-width:120px;">
        <div style="font-size:12px; color:#6B7280; margin-bottom:4px;">{icon} {label}</div>
        <div style="font-size:24px; font-weight:800; color:{color};">{sign}{score:.1f}</div>
    </div>
    """
