"""Shared styling, small HTML components and Altair charts for the dashboard."""

import altair as alt
import pandas as pd
import streamlit as st

LEVELS = ["Critical", "At Risk", "Healthy"]
LEVEL_COLORS = {"Critical": "#dc2626", "At Risk": "#f59e0b", "Healthy": "#16a34a"}
LEVEL_ICONS = {"Critical": "🔴", "At Risk": "🟠", "Healthy": "🟢"}
UP_COLOR, DOWN_COLOR = "#e11d48", "#2563eb"
ACCENT = "#6366f1"
NEUTRAL = "#7c879f"  # mid-grey: readable on light and dark backgrounds
TRACK = "rgba(148, 163, 184, .30)"
LEVEL_SCALE = alt.Scale(domain=LEVELS, range=[LEVEL_COLORS[l] for l in LEVELS])
LABEL_AXIS = alt.Axis(labelOverlap=False, labelLimit=260)

# Colour tokens per theme. Streamlit's own widgets follow [theme.light] /
# [theme.dark] in .streamlit/config.toml; these keep the custom HTML in step.
PALETTES = {
    "light": {
        "card": "#ffffff", "border": "#e5e7eb", "ink": "#0f172a", "muted": "#64748b",
        "soft": "#f8fafc", "shadow": "rgba(15, 23, 42, .05)", "dot_off": "#cbd5e1",
        "crit_bg": "#fee2e2", "crit_fg": "#b91c1c", "risk_bg": "#fef3c7", "risk_fg": "#b45309",
        "ok_bg": "#dcfce7", "ok_fg": "#15803d", "info_bg": "#e0e7ff", "info_fg": "#3730a3",
        "muted_bg": "#f1f5f9", "muted_fg": "#475569",
        "v_crit": "#fef2f2", "v_crit_b": "#fecaca", "v_risk": "#fffbeb", "v_risk_b": "#fde68a",
        "v_ok": "#f0fdf4", "v_ok_b": "#bbf7d0", "track": "#e5e7eb",
    },
    "dark": {
        "card": "#151b2e", "border": "#263049", "ink": "#e2e8f0", "muted": "#94a3b8",
        "soft": "#111727", "shadow": "rgba(0, 0, 0, .35)", "dot_off": "#475569",
        "crit_bg": "rgba(239, 68, 68, .16)", "crit_fg": "#fca5a5",
        "risk_bg": "rgba(245, 158, 11, .16)", "risk_fg": "#fcd34d",
        "ok_bg": "rgba(34, 197, 94, .16)", "ok_fg": "#86efac",
        "info_bg": "rgba(129, 140, 248, .18)", "info_fg": "#c7d2fe",
        "muted_bg": "rgba(148, 163, 184, .14)", "muted_fg": "#cbd5e1",
        "v_crit": "rgba(239, 68, 68, .10)", "v_crit_b": "rgba(239, 68, 68, .35)",
        "v_risk": "rgba(245, 158, 11, .10)", "v_risk_b": "rgba(245, 158, 11, .35)",
        "v_ok": "rgba(34, 197, 94, .10)", "v_ok_b": "rgba(34, 197, 94, .35)",
        "track": "#2a3350",
    },
}

CSS = """
<style>
:root {%(guess)s}
:root[data-pm-theme="light"] {%(light)s}
:root[data-pm-theme="dark"] {%(dark)s}
.block-container {padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1280px;}
h1, h2, h3 {letter-spacing: -0.01em;}

/* Hero banner (same gradient in both themes) */
.hero {
  background: linear-gradient(120deg, #1e1b4b 0%%, #3730a3 55%%, #4f46e5 100%%);
  color: #fff; border-radius: 18px; padding: 1.5rem 1.8rem; margin-bottom: 1.4rem;
  box-shadow: 0 10px 30px -12px rgba(49, 46, 129, .55);
}
.hero h1 {color: #fff; font-size: 1.75rem; margin: 0 0 .3rem 0; padding: 0;}
.hero p {color: #c7d2fe; margin: 0; font-size: .98rem;}
.hero .eyebrow {text-transform: uppercase; letter-spacing: .12em; font-size: .72rem;
  color: #a5b4fc; font-weight: 600; margin-bottom: .35rem;}

/* Metric tiles */
[data-testid="stMetric"] {
  background: var(--pm-card); border: 1px solid var(--pm-border); border-radius: 14px;
  padding: .85rem 1rem; box-shadow: 0 1px 2px var(--pm-shadow);
}
[data-testid="stMetricLabel"] p {color: var(--pm-muted); font-weight: 500; font-size: .82rem;}
[data-testid="stMetricValue"] {font-size: 1.55rem; font-weight: 650; color: var(--pm-ink);}

/* Pills */
.pill {display: inline-block; padding: .22rem .7rem; border-radius: 999px;
  font-weight: 600; font-size: .82rem; line-height: 1.3;}
.pill-Critical {background: var(--pm-crit_bg); color: var(--pm-crit_fg);}
.pill-AtRisk  {background: var(--pm-risk_bg); color: var(--pm-risk_fg);}
.pill-Healthy {background: var(--pm-ok_bg); color: var(--pm-ok_fg);}
.pill-info    {background: var(--pm-info_bg); color: var(--pm-info_fg);}
.pill-muted   {background: var(--pm-muted_bg); color: var(--pm-muted_fg);}

/* Service chips on the overview */
.chips {display: flex; flex-wrap: wrap; gap: .55rem; margin: .2rem 0 .4rem 0;}
.chip {background: var(--pm-card); border: 1px solid var(--pm-border); border-radius: 12px;
  padding: .55rem .8rem; font-size: .85rem; min-width: 150px; flex: 1 1 150px;}
.chip b {display: block; color: var(--pm-ink); font-size: .9rem;}
.chip span {color: var(--pm-muted); font-size: .78rem;}
.dot {display: inline-block; width: .55rem; height: .55rem; border-radius: 50%%;
  margin-right: .35rem; vertical-align: middle;}
.dot-on {background: #22c55e;} .dot-off {background: var(--pm-dot_off);}
.dot-warn {background: #f59e0b;}

/* Result panel */
.verdict {border-radius: 14px; padding: 1rem 1.2rem; border: 1px solid;}
.verdict-Critical {background: var(--pm-v_crit); border-color: var(--pm-v_crit_b);}
.verdict-AtRisk  {background: var(--pm-v_risk); border-color: var(--pm-v_risk_b);}
.verdict-Healthy {background: var(--pm-v_ok); border-color: var(--pm-v_ok_b);}
.verdict .big {font-size: 2.3rem; font-weight: 700; color: var(--pm-ink); line-height: 1.1;}
.verdict .sub {color: var(--pm-muted); font-size: .88rem;}

/* Sidebar */
[data-testid="stSidebar"] {border-right: 1px solid var(--pm-border);}
.side-status {border-radius: 12px; padding: .6rem .75rem; background: var(--pm-soft);
  border: 1px solid var(--pm-border); font-size: .85rem; margin-top: .3rem;}
.side-status small {color: var(--pm-muted); display: block; margin-top: .15rem;
  word-break: break-all;}

/* Tabs */
.stTabs [data-baseweb="tab-list"] {gap: .3rem;}
.stTabs [data-baseweb="tab"] {padding: .4rem .9rem; border-radius: 10px 10px 0 0;}
</style>
"""


# Streamlit switches its theme in the browser without rerunning the script, so
# a server-side choice of palette would go stale. This watches the app's
# background brightness and tags <html> with data-pm-theme; the CSS above
# swaps every --pm-* token from that attribute instantly.
THEME_WATCHER = """
<script>
if (!window.__pmThemeWatcher) {
  window.__pmThemeWatcher = true;
  const sync = () => {
    const app = document.querySelector('.stApp');
    if (!app) return;
    const [r, g, b] = getComputedStyle(app).backgroundColor.match(/\d+/g).map(Number);
    const mode = (0.299 * r + 0.587 * g + 0.114 * b) < 128 ? 'dark' : 'light';
    if (document.documentElement.dataset.pmTheme !== mode)
      document.documentElement.dataset.pmTheme = mode;
  };
  sync();
  new MutationObserver(sync).observe(document.head, {childList: true, subtree: true});
  setInterval(sync, 1000);
}
</script>
"""


def theme() -> str:
    """'light' or 'dark': the theme the viewer picked (or their system's)."""
    try:
        return "dark" if st.context.theme.type == "dark" else "light"
    except AttributeError:  # older Streamlit without st.context.theme
        return "light"


def _tokens(name: str) -> str:
    return " ".join(f"--pm-{k}: {v};" for k, v in PALETTES[name].items())


def inject_css() -> None:
    st.markdown(CSS % {"guess": _tokens(theme()), "light": _tokens("light"),
                       "dark": _tokens("dark")}, unsafe_allow_html=True)
    st.html(THEME_WATCHER, unsafe_allow_javascript=True)


def hero(title: str, subtitle: str, eyebrow: str = "Predictive Maintenance") -> None:
    st.markdown(f'<div class="hero"><div class="eyebrow">{eyebrow}</div>'
                f'<h1>{title}</h1><p>{subtitle}</p></div>', unsafe_allow_html=True)


def pill(text: str, kind: str) -> str:
    return f'<span class="pill pill-{kind.replace(" ", "")}">{text}</span>'


def risk_pill(level: str) -> str:
    return pill(f"{LEVEL_ICONS[level]} {level}", level)


def chips(items: list[tuple[str, str, str]]) -> None:
    """items: (name, description, state) with state in on/off/warn."""
    html = "".join(f'<div class="chip"><b><span class="dot dot-{state}"></span>{name}</b>'
                   f'<span>{desc}</span></div>' for name, desc, state in items)
    st.markdown(f'<div class="chips">{html}</div>', unsafe_allow_html=True)


def verdict(result: dict) -> None:
    level = result["risk_level"]
    cause = result["likely_cause"] if result["likely_cause"] != "-" else "No failure expected"
    st.markdown(
        f'<div class="verdict verdict-{level.replace(" ", "")}">'
        f'<div class="sub">Failure probability</div>'
        f'<div class="big">{result["failure_probability"]:.1%}</div>'
        f'<div style="margin:.45rem 0 .55rem 0">{risk_pill(level)} '
        f'{pill(cause, "muted")}</div>'
        f'<div class="sub">{result["recommendation"]}</div></div>',
        unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------
def gauge(probability: float, level: str):
    """Donut gauge filled to the failure probability."""
    df = pd.DataFrame({"part": ["value", "rest"],
                       "share": [max(probability, 0.004), 1 - max(probability, 0.004)]})
    base = alt.Chart(df).encode(
        theta=alt.Theta("share:Q", stack=True),
        color=alt.Color("part:N", legend=None,
                        scale=alt.Scale(domain=["value", "rest"],
                                        range=[LEVEL_COLORS[level], TRACK])),
        order=alt.Order("part:N", sort="descending"))
    ring = base.mark_arc(innerRadius=58, outerRadius=78, cornerRadius=4)
    label = alt.Chart(pd.DataFrame({"t": [f"{probability:.0%}"]})).mark_text(
        fontSize=24, fontWeight=700, color=NEUTRAL).encode(text="t:N")
    return (ring + label).properties(height=180, width=180)


def contribution_chart(contribs: list[dict], top: int = 8):
    df = pd.DataFrame(contribs).head(top)
    df["label"] = df.apply(lambda r: f"{r['feature']} = {r['value']:g}", axis=1)
    return (
        alt.Chart(df).mark_bar(cornerRadius=3).encode(
            x=alt.X("contribution:Q", title="Effect on failure risk (SHAP)"),
            y=alt.Y("label:N", sort=None, title=None, axis=LABEL_AXIS),
            color=alt.Color("effect:N", legend=alt.Legend(title=None, orient="bottom"),
                            scale=alt.Scale(domain=["Raises risk", "Lowers risk"],
                                            range=[UP_COLOR, DOWN_COLOR])),
            tooltip=["feature", "value", alt.Tooltip("contribution:Q", format=".4f"), "effect"],
        ).properties(height=32 * len(df) + 40)
    )


def modes_chart(mode_probs: dict):
    df = (pd.Series(mode_probs, name="probability").sort_values(ascending=False)
          .rename_axis("mode").reset_index())
    return alt.Chart(df).mark_bar(cornerRadius=3, color=ACCENT).encode(
        x=alt.X("probability:Q", axis=alt.Axis(format="%"), title="Probability"),
        y=alt.Y("mode:N", sort="-x", title=None, axis=LABEL_AXIS),
        tooltip=["mode", alt.Tooltip("probability:Q", format=".1%")],
    ).properties(height=210)


def whatif_chart(df: pd.DataFrame, feature: str, current: float, thresholds: dict):
    line = alt.Chart(df).mark_line(color=ACCENT, strokeWidth=3, point=True).encode(
        x=alt.X(f"{feature}:Q", title=feature, scale=alt.Scale(zero=False)),
        y=alt.Y("failure_probability:Q", title="Failure probability",
                axis=alt.Axis(format="%")),
        tooltip=[alt.Tooltip(f"{feature}:Q"),
                 alt.Tooltip("failure_probability:Q", format=".1%"), "risk_level"])
    rules = pd.DataFrame({"y": [thresholds["t_risk"], thresholds["t_critical"]],
                          "label": ["At Risk threshold", "Critical threshold"]})
    hlines = alt.Chart(rules).mark_rule(strokeDash=[5, 4]).encode(
        y="y:Q", color=alt.Color("label:N", legend=alt.Legend(title=None, orient="bottom"),
                                 scale=alt.Scale(domain=list(rules["label"]),
                                                 range=[LEVEL_COLORS["At Risk"],
                                                        LEVEL_COLORS["Critical"]])))
    now = alt.Chart(pd.DataFrame({"x": [current]})).mark_rule(
        color=NEUTRAL, strokeWidth=1.5).encode(x="x:Q")
    return (line + hlines + now).properties(height=300)


def level_donut(levels: pd.Series):
    counts = levels.value_counts().reindex(LEVELS, fill_value=0).rename_axis(
        "risk_level").reset_index(name="machines")
    return alt.Chart(counts).mark_arc(innerRadius=55, cornerRadius=3).encode(
        theta="machines:Q",
        color=alt.Color("risk_level:N", scale=LEVEL_SCALE,
                        legend=alt.Legend(title=None, orient="bottom")),
        tooltip=["risk_level", "machines"],
    ).properties(height=230)


def fleet_scatter(res: pd.DataFrame):
    return alt.Chart(res).mark_circle(size=70, opacity=.75).encode(
        x=alt.X("Tool wear [min]:Q"),
        y=alt.Y("Torque [Nm]:Q", scale=alt.Scale(zero=False)),
        color=alt.Color("risk_level:N", scale=LEVEL_SCALE,
                        legend=alt.Legend(title=None, orient="bottom")),
        tooltip=["machine_id", "risk_level", alt.Tooltip("failure_probability:Q", format=".1%"),
                 "likely_cause", "Tool wear [min]", "Torque [Nm]"],
    ).properties(height=260)


def history_timeline(df: pd.DataFrame):
    return alt.Chart(df).mark_bar().encode(
        x=alt.X("yearmonthdatehours(time):T", title=None),
        y=alt.Y("count():Q", title="Predictions"),
        color=alt.Color("risk_level:N", scale=LEVEL_SCALE,
                        legend=alt.Legend(title=None, orient="bottom")),
        tooltip=[alt.Tooltip("yearmonthdatehours(time):T", title="Hour"),
                 "risk_level", "count()"],
    ).properties(height=240)


def machine_trend(df: pd.DataFrame, thresholds: dict | None):
    line = alt.Chart(df).mark_line(point=True, color=ACCENT).encode(
        x=alt.X("time:T", title=None),
        y=alt.Y("failure_probability:Q", axis=alt.Axis(format="%"),
                title="Failure probability"),
        tooltip=["time:T", alt.Tooltip("failure_probability:Q", format=".1%"), "risk_level"])
    if not thresholds:
        return line.properties(height=240)
    rule = alt.Chart(pd.DataFrame({"y": [thresholds["t_critical"]]})).mark_rule(
        strokeDash=[5, 4], color=LEVEL_COLORS["Critical"]).encode(y="y:Q")
    return (line + rule).properties(height=240)
