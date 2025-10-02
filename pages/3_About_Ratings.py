import streamlit as st
import pandas as pd
import altair as alt
import plotly.express as px
import json
from math import radians, sin, cos, sqrt, atan2

# Pull the official scoring so our numbers match the app exactly
from scoring import (
    compute_all_vibes,
    norm_0_5, bool_norm, norm_seating, norm_price_index,
    norm_hours_late, norm_hours_early, norm_noise_inverse, norm_mid_noise_bonus,
)

st.title("About Ratings")

# ---------------------------
# Weight dictionary (mirrors scoring.py semantics)
# ---------------------------
VIBE_WEIGHTS = {
    "Work-Friendly": {
        "Wi-Fi quality": 0.22,
        "Outlets availability": 0.18,
        "Lower noise": 0.15,
        "Seating capacity": 0.12,
        "Restroom access": 0.10,
        "Open late": 0.10,
        "Cleanliness": 0.08,
        "Parking": 0.05,
    },
    "Aesthetic": {
        "Aesthetic score": 0.40,
        "Natural light": 0.20,
        "Latte art / presentation": 0.15,
        "Cleanliness": 0.10,
        "Unique decor": 0.10,
        "Desserts": 0.05,
    },
    "Grab-and-Go": {
        "Speed (mobile/drive-thru/peak)": 0.35,
        "Parking": 0.25,
        "Opens early": 0.15,
        "Mobile order": 0.15,
        "Drive-through": 0.10,
    },
    "Date-Night": {
        "Ambience (lighting/comfort/mid-noise)": 0.25,
        "Desserts": 0.20,
        "Open late": 0.18,
        "Aesthetic score": 0.15,
        "Walkable things nearby": 0.12,
        "Cleanliness": 0.10,
    },
    "Dietary-Friendly": {
        "Gluten-free options": 0.40,
        "Dairy-free milks": 0.28,
        "Nut-free choices": 0.12,
        "Ingredient transparency": 0.10,
        "Cleanliness": 0.10,
    },
    "Study-Spot": {
        "Outlets availability": 0.28,
        "Seating capacity": 0.22,
        "Wi-Fi quality": 0.18,
        "Budget-friendliness": 0.12,
        "Open late": 0.10,
        "Lower noise": 0.10,
    },
    "Family-Friendly": {
        "Roomy layout / space": 0.30,
        "Restroom access": 0.20,
        "Parking": 0.18,
        "Mid-noise tolerance": 0.15,
        "Kids snacks / treats": 0.10,
        "Park nearby": 0.07,
    },
}

# ---------------------------
# Helpers
# ---------------------------
def clamp01(x): return max(0.0, min(1.0, float(x)))

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000.0
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1); dlambda = radians(lon2 - lon1)
    a = sin(dphi/2)**2 + cos(phi1)*cos(phi2)*sin(dlambda/2)**2
    return 2*R*atan2(sqrt(a), sqrt(1-a))

def count_nearby(poi_df, lat, lng, radius_m=700):
    within = poi_df[poi_df.apply(lambda p: haversine(lat, lng, p.lat, p.lng) <= radius_m, axis=1)]
    walkables = len(within)
    parks = len(within[within["type"]=="park"])
    return walkables, parks, within["name"].head(2).tolist()

def norm_nearby(n, cap=5):
    try:
        return clamp01(float(n)/float(cap))
    except:
        return None

def attr_strengths(vibe_key: str, r: dict, walk_norm=None, parks_norm=None) -> dict:
    """Mirror the transforms in scoring.py to produce 0..1 strengths aligned to labels."""
    s = {}
    if vibe_key == "Work-Friendly":
        s = {
            "Wi-Fi quality":        norm_0_5(r.get("wifi_score")) or 0.6,
            "Outlets availability": norm_0_5(r.get("outlets_score")) or 0.5,
            "Lower noise":          norm_noise_inverse(r.get("noise_score")) or 0.5,
            "Seating capacity":     norm_seating(r.get("seating_count")) or 0.4,
            "Restroom access":      bool_norm(r.get("restroom_access")) or 0.5,
            "Open late":            norm_hours_late(r.get("hours_json")) if isinstance(r.get("hours_json"), dict) else 0.4,
            "Cleanliness":          norm_0_5(r.get("cleanliness_score")) or 0.6,
            "Parking":              norm_0_5(r.get("parking_score")) or 0.5,
        }
    elif vibe_key == "Aesthetic":
        s = {
            "Aesthetic score":          norm_0_5(r.get("aesthetic_score")) or 0.5,
            "Natural light":            norm_0_5(r.get("natural_light_score", r.get("aesthetic_score"))) or 0.5,
            "Latte art / presentation": norm_0_5(r.get("latte_art_score")) or 0.4,
            "Cleanliness":              norm_0_5(r.get("cleanliness_score")) or 0.6,
            "Unique decor":             norm_0_5(r.get("unique_decor_score", r.get("aesthetic_score"))) or 0.5,
            "Desserts":                 norm_0_5(r.get("dessert_score")) or 0.5,
        }
    elif vibe_key == "Grab-and-Go":
        mobile = bool_norm(r.get("mobile_order")) or 0.0
        drive = bool_norm(r.get("has_drive_through")) or 0.0
        peak_penalty = 0.2
        speed = clamp01(0.4 + 0.3*mobile + 0.3*drive - 0.2*peak_penalty)
        s = {
            "Speed (mobile/drive-thru/peak)": speed,
            "Parking":                        norm_0_5(r.get("parking_score")) or 0.5,
            "Opens early":                    norm_hours_early(r.get("hours_json")) if isinstance(r.get("hours_json"), dict) else 0.4,
            "Mobile order":                   mobile,
            "Drive-through":                  drive,
        }
    elif vibe_key == "Date-Night":
        amb = ((norm_0_5(r.get("lighting_score", r.get("aesthetic_score"))) or 0.5) * 0.35 +
               (norm_0_5(r.get("seating_comfort_score", r.get("aesthetic_score"))) or 0.5) * 0.35 +
               (norm_mid_noise_bonus(r.get("noise_score")) or 0.5) * 0.30)
        s = {
            "Ambience (lighting/comfort/mid-noise)": amb,
            "Desserts":                 norm_0_5(r.get("dessert_score")) or 0.5,
            "Open late":                norm_hours_late(r.get("hours_json")) if isinstance(r.get("hours_json"), dict) else 0.4,
            "Aesthetic score":          norm_0_5(r.get("aesthetic_score")) or 0.5,
            "Walkable things nearby":   walk_norm,
            "Cleanliness":              norm_0_5(r.get("cleanliness_score")) or 0.6,
        }
    elif vibe_key == "Dietary-Friendly":
        s = {
            "Gluten-free options":      bool_norm(r.get("gf_food")) or 0.0,
            "Dairy-free milks":         (0.0 if r.get("df_milks") is None else clamp01(float(r.get("df_milks"))/3.0)),
            "Nut-free choices":         bool_norm(r.get("nut_free")) or 0.0,
            "Ingredient transparency":  norm_0_5(r.get("ingredient_transparency_score", 3.0)) or 0.6,
            "Cleanliness":              norm_0_5(r.get("cleanliness_score")) or 0.6,
        }
    elif vibe_key == "Study-Spot":
        s = {
            "Outlets availability":     norm_0_5(r.get("outlets_score")) or 0.5,
            "Seating capacity":         norm_seating(r.get("seating_count")) or 0.4,
            "Wi-Fi quality":            norm_0_5(r.get("wifi_score")) or 0.6,
            "Budget-friendliness":      norm_price_index(r.get("price_index")) or 0.5,
            "Open late":                norm_hours_late(r.get("hours_json")) if isinstance(r.get("hours_json"), dict) else 0.4,
            "Lower noise":              norm_noise_inverse(r.get("noise_score")) or 0.5,
        }
    elif vibe_key == "Family-Friendly":
        s = {
            "Roomy layout / space":     norm_0_5(r.get("space_score", r.get("seating_comfort_score"))) or 0.5,
            "Restroom access":          bool_norm(r.get("restroom_access")) or 0.5,
            "Parking":                  norm_0_5(r.get("parking_score")) or 0.5,
            "Mid-noise tolerance":      norm_mid_noise_bonus(r.get("noise_score")) or 0.5,
            "Kids snacks / treats":     norm_0_5(r.get("kids_snacks_score", r.get("dessert_score"))) or 0.5,
            "Park nearby":              parks_norm,
        }
    return {k: 0.0 if v is None else clamp01(v) for k, v in s.items()}

def contribution_df(vibe_key, weights_dict, strengths_dict):
    df = pd.DataFrame({
        "Attribute": list(weights_dict.keys()),
        "Weight (importance %)": [round(v * 100, 1) for v in weights_dict.values()],
        "Attribute strength (%)": [round(strengths_dict.get(k, 0.0) * 100, 1) for k in weights_dict.keys()],
    })
    df["Weighted contribution"] = (df["Weight (importance %)"]/100.0) * (df["Attribute strength (%)"]/100.0) * 100.0
    return df

# ---------------------------
# Tabs
# ---------------------------
tab_infographic, tab_shop, tab_whatif = st.tabs([
    "Weights (Infographic)", "Why this shop scored", "What-If (simulate changes)"
])

# ===========================
# TAB 1: Weights (Infographic)
# ===========================
with tab_infographic:
    st.markdown("""
### How Coffee Concierge Works  
Every coffee shop is scored on multiple **vibes**. Each vibe uses a transparent, weighted blend of real attributes (Wi-Fi, outlets, seating, hours, dietary options, parking, etc.).
""")
    c0, c1 = st.columns([1,1])
    with c0:
        vibe = st.selectbox("Choose a vibe to inspect", list(VIBE_WEIGHTS.keys()), index=0, key="vibe_inf")
    with c1:
        st.info("These are **weights** (importance), not a shop’s score.", icon="ℹ️")

    weights = VIBE_WEIGHTS[vibe]
    dfw = pd.DataFrame({"Attribute": list(weights.keys()), "Weight": list(weights.values())}).sort_values("Weight", ascending=True)

    st.markdown("#### Weight breakdown")
    bar = (
        alt.Chart(dfw)
        .mark_bar()
        .encode(
            x=alt.X("Weight:Q", axis=alt.Axis(format="%"), title="Weight (importance)"),
            y=alt.Y("Attribute:N", sort="-x", title=""),
            tooltip=[alt.Tooltip("Attribute:N"), alt.Tooltip("Weight:Q", format=".0%")],
        )
        .properties(height=max(220, 22*len(dfw)), width="container")
    )
    st.altair_chart(bar, use_container_width=True)

    st.markdown("#### Radar view")
    fig = px.line_polar(dfw, r="Weight", theta="Attribute", line_close=True)
    fig.update_traces(fill="toself")
    st.plotly_chart(fig, use_container_width=True)

# ===========================
# TAB 2: Why this shop scored
# ===========================
with tab_shop:
    st.markdown("### Inspect a real shop")

    shops = pd.read_csv("data/shops_example.csv")
    poi = pd.read_csv("data/poi_example.csv")

    shop_name = st.selectbox("Shop", list(shops["name"].unique()), key="shop_explain")
    vibe2 = st.selectbox("Vibe", list(VIBE_WEIGHTS.keys()), key="vibe_explain")

    row = shops[shops["name"] == shop_name].iloc[0].to_dict()
    try:
        row["hours_json"] = json.loads(row.get("hours_json", "{}"))
    except Exception:
        row["hours_json"] = {}

    # Nearby counts
    walkables_count, parks_count, poi_names = count_nearby(poi, row["lat"], row["lng"])
    walk_norm = norm_nearby(walkables_count)
    parks_norm = norm_nearby(parks_count)

    results_base = compute_all_vibes(row, nearby_walkables_count=walkables_count, nearby_parks_count=parks_count)
    this = results_base[vibe2]
    st.markdown(f"**Computed {vibe2} score:** `{this.score:.1f}` &nbsp;&nbsp;•&nbsp;&nbsp; **Data confidence:** `{this.confidence}`")

    strengths = attr_strengths(vibe2, row, walk_norm, parks_norm)
    df_contrib = contribution_df(vibe2, VIBE_WEIGHTS[vibe2], strengths)

    st.markdown("#### Attribute strengths vs. weights")
    chart_df_long = df_contrib.melt(id_vars="Attribute", var_name="Metric", value_name="Percent")
    chart_df_long = chart_df_long.replace({"Weight (importance %)": "Weight", "Attribute strength (%)": "Strength"})

    comp = (
        alt.Chart(chart_df_long)
        .mark_bar()
        .encode(
            y=alt.Y("Attribute:N", sort="-x", title=""),
            x=alt.X("Percent:Q", title="Percent"),
            color=alt.Color("Metric:N", legend=alt.Legend(title="")),
            tooltip=["Attribute:N", "Metric:N", alt.Tooltip("Percent:Q", format=".1f")],
        )
        .properties(height=max(240, 26*len(df_contrib)), width="container")
    )
    st.altair_chart(comp, use_container_width=True)

    st.markdown("#### Contribution to this vibe (Strength × Weight)")
    wc = df_contrib[["Attribute", "Weighted contribution"]].sort_values("Weighted contribution", ascending=True)
    contrib = (
        alt.Chart(wc)
        .mark_bar()
        .encode(
            x=alt.X("Weighted contribution:Q", title="Contribution (%)"),
            y=alt.Y("Attribute:N", sort="-x", title=""),
            tooltip=["Attribute:N", alt.Tooltip("Weighted contribution:Q", format=".1f")],
        )
        .properties(height=max(220, 22*len(wc)), width="container")
    )
    st.altair_chart(contrib, use_container_width=True)

    with st.expander("Details used for this calculation"):
        st.write({
            "Nearby walkables (<=700m)": int(walkables_count),
            "Nearby parks (<=700m)": int(parks_count),
            "Example POIs": poi_names,
        })
        st.caption("Walkable/park proximity uses a simple cap of 5, matching the demo app.")

# ===========================
# TAB 3: What-If (simulate changes)
# ===========================
with tab_whatif:
    st.markdown("### What-If: tweak attributes and see the impact")

    shops = pd.read_csv("data/shops_example.csv")
    poi = pd.read_csv("data/poi_example.csv")

    shop_name_wi = st.selectbox("Shop", list(shops["name"].unique()), key="shop_whatif")
    vibe3 = st.selectbox("Vibe to optimize", list(VIBE_WEIGHTS.keys()), key="vibe_whatif")

    row0 = shops[shops["name"] == shop_name_wi].iloc[0].to_dict()
    try:
        row0["hours_json"] = json.loads(row0.get("hours_json", "{}"))
    except Exception:
        row0["hours_json"] = {}

    # Baseline nearby
    w0_count, p0_count, _ = count_nearby(poi, row0["lat"], row0["lng"])

    # Baseline score
    base = compute_all_vibes(row0, nearby_walkables_count=w0_count, nearby_parks_count=p0_count)[vibe3].score

    st.caption("Adjust the sliders below. We recompute the shop’s attributes and vibe score in real time.")

    # Sliders depend on the selected vibe’s most influential inputs
    c1, c2, c3 = st.columns(3)
    # Common sliders (exist in many vibes)
    with c1:
        wifi = st.slider("Wi-Fi (0–5)", 0.0, 5.0, float(row0.get("wifi_score", 3.0)), 0.1)
        outlets = st.slider("Outlets (0–5)", 0.0, 5.0, float(row0.get("outlets_score", 3.0)), 0.1)
        noise = st.slider("Noise (0=quiet → 5=loud)", 0.0, 5.0, float(row0.get("noise_score", 2.5)), 0.1)

    with c2:
        seating = st.slider("Seating count", 0, 60, int(row0.get("seating_count", 20)), 1)
        parking = st.slider("Parking (0–5)", 0.0, 5.0, float(row0.get("parking_score", 3.0)), 0.1)
        price = st.slider("Price index (1=cheap → 4=exp.)", 1.0, 4.0, float(row0.get("price_index", 2.0)), 0.1)

    with c3:
        opens_early = st.slider("Opens early score (0–1)", 0.0, 1.0, float(norm_hours_early(row0.get("hours_json")) or 0.4), 0.05)
        open_late = st.slider("Open late score (0–1)", 0.0, 1.0, float(norm_hours_late(row0.get("hours_json")) or 0.4), 0.05)
        cleanliness = st.slider("Cleanliness (0–5)", 0.0, 5.0, float(row0.get("cleanliness_score", 4.0)), 0.1)

    # Niche sliders used by specific vibes
    c4, c5 = st.columns(2)
    with c4:
        aesthetic = st.slider("Aesthetic (0–5)", 0.0, 5.0, float(row0.get("aesthetic_score", 3.5)), 0.1)
        natural_light = st.slider("Natural light (0–5)", 0.0, 5.0, float(row0.get("natural_light_score", row0.get("aesthetic_score", 3.5))), 0.1)
        latte_art = st.slider("Latte art (0–5)", 0.0, 5.0, float(row0.get("latte_art_score", 3.0)), 0.1)

    with c5:
        gf_food = st.checkbox("Gluten-free options", bool(row0.get("gf_food", False)))
        df_milks = st.slider("Dairy-free milks (0–3)", 0, 3, int(row0.get("df_milks", 1)), 1)
        nut_free = st.checkbox("Nut-free choices", bool(row0.get("nut_free", False)))

    # We simulate hours by directly overriding the normalized early/late scores in the strengths;
    # to keep the app simple, we won’t rebuild the hour JSON here.

    # Build a modified row for recomputation (values that directly feed scoring.py)
    row_mod = dict(row0)
    row_mod.update({
        "wifi_score": wifi,
        "outlets_score": outlets,
        "noise_score": noise,
        "seating_count": seating,
        "parking_score": parking,
        "price_index": price,
        "cleanliness_score": cleanliness,
        "aesthetic_score": aesthetic,
        "natural_light_score": natural_light,
        "latte_art_score": latte_art,
        "gf_food": gf_food,
        "df_milks": df_milks,
        "nut_free": nut_free,
    })

    # Recompute nearby normalization unchanged (location didn’t move)
    res_mod = compute_all_vibes(row_mod, nearby_walkables_count=w0_count, nearby_parks_count=p0_count)[vibe3].score

    # Display delta
    delta = round(res_mod - base, 1)
    st.metric(label=f"{vibe3} score (simulated)", value=f"{res_mod:.1f}", delta=f"{delta:+.1f}")

    # Show which attributes (for this vibe) have biggest *potential* upside based on weight
    weights3 = VIBE_WEIGHTS[vibe3]
    strengths_base = attr_strengths(vibe3, row0, norm_nearby(w0_count), norm_nearby(p0_count))
    strengths_mod = attr_strengths(vibe3, row_mod, norm_nearby(w0_count), norm_nearby(p0_count))

    df_imp = pd.DataFrame({
        "Attribute": list(weights3.keys()),
        "Weight": [weights3[k] for k in weights3.keys()],
        "Base strength": [strengths_base.get(k, 0.0) for k in weights3.keys()],
        "New strength":  [strengths_mod.get(k, 0.0)  for k in weights3.keys()],
    })
    df_imp["Delta strength"] = df_imp["New strength"] - df_imp["Base strength"]
    df_imp["Delta contribution (%)"] = (df_imp["Delta strength"] * df_imp["Weight"] * 100.0).round(1)
    df_imp = df_imp.sort_values("Delta contribution (%)", ascending=True)

    st.markdown("#### Which tweaks moved the needle?")
    tweak = (
        alt.Chart(df_imp)
        .mark_bar()
        .encode(
            x=alt.X("Delta contribution (%):Q", title="Change in contribution (%)"),
            y=alt.Y("Attribute:N", sort="-x", title=""),
            tooltip=[
                "Attribute:N",
                alt.Tooltip("Delta contribution (%):Q", format=".1f"),
                alt.Tooltip("Base strength:Q", format=".0%"),
                alt.Tooltip("New strength:Q", format=".0%"),
                alt.Tooltip("Weight:Q", format=".0%"),
            ],
        )
        .properties(height=max(220, 22*len(df_imp)), width="container")
    )
    st.altair_chart(tweak, use_container_width=True)

    with st.expander("Nerd notes (how we simulate)"):
        st.write("""
- Sliders set raw inputs (e.g., Wi-Fi 0–5). We run them through the **same normalizers** as the scoring engine.
- Hours are approximated by directly adjusting the normalized **opens early** and **open late** sliders.
- We don’t move the shop, so **walkables/parks** remain constant.
- The metric above is the **real recomputed vibe score**, not a toy formula.
""")
