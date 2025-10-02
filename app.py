import os
import json
from math import radians, sin, cos, sqrt, atan2
from pathlib import Path

import pandas as pd
import streamlit as st

from scoring import compute_all_vibes, narrative_one_liner

# -----------------------------------------------------------------------------
# Page + theme polish
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Coffee Concierge", page_icon="☕", layout="wide")

# (Optional) secrets → env (so services/places.py can read the key)
if "GOOGLE_MAPS_API_KEY" in st.secrets and not os.getenv("GOOGLE_MAPS_API_KEY"):
    os.environ["GOOGLE_MAPS_API_KEY"] = st.secrets["GOOGLE_MAPS_API_KEY"]

# Optional Google Places enrichment (safe if file/module missing)
try:
    from services.places import get_place_details, get_primary_photo_bytes
    HAS_PLACES = True
except Exception:
    HAS_PLACES = False

# Global CSS
st.markdown("""
<style>
/* page padding + nicer headings */
.block-container { padding-top: 1.3rem; padding-bottom: 1.8rem; }
h1, h2, h3 { letter-spacing: 0.2px; }

/* card container */
.cc-card {
  border-radius: 16px;
  border: 1px solid rgba(20,20,33,0.06);
  background: #fff;
  box-shadow: 0 6px 20px rgba(20,20,33,0.06);
  padding: 14px 16px 14px 16px;
  margin-bottom: 14px;
}

/* header & pills */
.cc-headline { display:flex; align-items:center; gap:8px; font-weight:700; font-size:1.05rem; margin: 2px 0 6px 0; }
.cc-pill { display:inline-flex; align-items:center; gap:6px; background: linear-gradient(135deg, #6C5CE7, #9B5DE5);
           color:#fff; padding:4px 10px; border-radius:999px; font-size:0.85rem; }
.cc-muted { color:#5d6b82; }

/* image wrapper for rounded corners */
.cc-thumb img { border-radius: 12px !important; }

/* small chips for features */
.cc-chip { display:inline-flex; align-items:center; gap:6px; background:#F3F5F9; color:#334; border:1px solid #E6EAF2;
           padding:4px 8px; border-radius:999px; font-size:0.78rem; margin-right:6px; margin-bottom:6px; }

/* subtle divider */
.cc-divider { height:1px; background:#EEF1F6; margin: 8px 0 12px 0; }

/* sticky brand bar */
.cc-brand {
 position: sticky; top: 0; z-index: 10; margin:-1rem -1rem 1rem -1rem;
 background: linear-gradient(90deg, #6C5CE7 0%, #9B5DE5 100%);
 padding: 10px 18px; color: #fff; border-bottom: 1px solid rgba(255,255,255,0.25);
}
</style>
""", unsafe_allow_html=True)

# Brand bar
st.markdown("""
<div class="cc-brand">
  <div style="display:flex; align-items:center; gap:10px;">
    <span style="font-weight:700;">Coffee Concierge</span>
    <span style="opacity:0.95;">· find the right vibe</span>
  </div>
</div>
""", unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Data (absolute paths for Streamlit Cloud)
# -----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

shops_path = DATA_DIR / "shops_example.csv"
poi_path   = DATA_DIR / "poi_example.csv"

if not shops_path.exists():
    st.error(f"Missing data file: {shops_path}\n\nAdd it to your repo and redeploy.")
    st.stop()
if not poi_path.exists():
    st.error(f"Missing data file: {poi_path}\n\nAdd it to your repo and redeploy.")
    st.stop()

shops = pd.read_csv(shops_path)
poi   = pd.read_csv(poi_path)

# -----------------------------------------------------------------------------
# Sidebar Filters (clean + compact)
# -----------------------------------------------------------------------------
with st.sidebar:
    st.header("Filters")
    with st.form("filters"):
        city = st.selectbox("City", sorted(shops["city"].unique()))
        vibe = st.selectbox(
            "Vibe",
            ["Work-Friendly", "Aesthetic", "Grab-and-Go", "Date-Night",
             "Dietary-Friendly", "Study-Spot", "Family-Friendly"]
        )
        gf = st.checkbox("Must have gluten-free options", value=False)
        wifi_min = st.slider("Min Wi-Fi score", 0.0, 5.0, 3.0, 0.5)
        debug_details = st.toggle("Debug mode", value=False)
        submitted = st.form_submit_button("Apply", use_container_width=True)
    st.caption("Pro tip: try **Date-Night** vs **Work-Friendly** to see different drivers.")

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def haversine(lat1, lon1, lat2, lon2):
    R = 6371000.0
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi/2)**2 + cos(phi1)*cos(phi2)*sin(dlambda/2)**2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))

def get_shop_details(row_dict: dict) -> dict:
    """
    CSV first; optionally enrich with Google Places if available.
    Returns at least: address, phone, website, google_url, place_id, photo_reference, source
    """
    details = {
        "address": row_dict.get("address"),
        "phone": row_dict.get("phone"),
        "website": row_dict.get("website"),
        "google_url": None,
        "place_id": row_dict.get("google_place_id"),
        "photo_reference": row_dict.get("photo_reference"),
        "source": "csv",
    }
    if HAS_PLACES and os.getenv("GOOGLE_MAPS_API_KEY") and (
        not details["address"] or not details["phone"] or not details["website"] or not details["photo_reference"]
    ):
        try:
            fetched = get_place_details(
                row_dict["name"], float(row_dict["lat"]), float(row_dict["lng"]), row_dict.get("city"),
            )
            if isinstance(fetched, dict):
                for k in ["address","phone","website","google_url","place_id","photo_reference"]:
                    if not details.get(k) and fetched.get(k):
                        details[k] = fetched[k]
                if fetched.get("address") or fetched.get("website") or fetched.get("phone"):
                    details["source"] = "google"
        except Exception:
            pass
    if not details.get("google_url"):
        q = f"https://www.google.com/maps/search/?api=1&query={row_dict['name'].replace(' ', '+')}%2C+{row_dict.get('city','')}"
        details["google_url"] = q
    return details

def render_shop_card(row, details, score, text, img_bytes=None):
    st.markdown('<div class="cc-card">', unsafe_allow_html=True)

    # Header row: name + score + thumb
    left, right = st.columns([3, 1])
    with left:
        st.markdown(f'<div class="cc-headline">☕ {row["name"]}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="cc-pill">{score:.1f} · vibe score</div>', unsafe_allow_html=True)
        st.markdown(f"<div class='cc-muted' style='margin-top:6px'>{text}</div>", unsafe_allow_html=True)
    with right:
        if img_bytes:
            st.markdown('<div class="cc-thumb">', unsafe_allow_html=True)
            st.image(img_bytes, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

    # Chips
    chips = []
    if row.get("wifi_score") is not None:
        chips.append(f"<span class='cc-chip'>📶 Wi-Fi {row['wifi_score']:.1f}</span>")
    if row.get("seating_score") is not None:
        chips.append(f"<span class='cc-chip'>💺 Seating {row['seating_score']:.1f}</span>")
    if row.get("gf_food") is True:
        chips.append("<span class='cc-chip'>🌾 Gluten-free</span>")
    if chips:
        st.markdown("".join(chips), unsafe_allow_html=True)

    st.markdown('<div class="cc-divider"></div>', unsafe_allow_html=True)

    # Details row
    c1, c2, c3, c4 = st.columns([2.2, 1.2, 1.2, 1.2])
    with c1:
        st.markdown("**Address**"); st.write(details.get("address") or "—")
    with c2:
        st.markdown("**Phone**"); st.write(details.get("phone") or "—")
    with c3:
        st.markdown("**Website**")
        if details.get("website"):
            try: st.link_button("Open site", details["website"])
            except Exception: st.markdown(f"[Open site]({details['website']})")
        else:
            st.write("—")
    with c4:
        st.markdown("**Maps**")
        try: st.link_button("Open in Maps", details["google_url"])
        except Exception: st.markdown(f"[Open in Maps]({details['google_url']})")

    st.markdown('<div class="cc-divider"></div>', unsafe_allow_html=True)

    # Actions
    a1, a2 = st.columns([1, 6])
    with a1:
        if st.button("View details & nearby →", key=f"btn_{row['name']}"):
            st.session_state["selected_shop"] = row
            st.session_state["selected_city"] = row.get("city")
            st.switch_page("pages/2_Nearby.py")
    with a2:
        st.page_link("pages/3_About_Ratings.py", label="How ratings work →")

    # Optional debug toggle via sidebar
    if debug_details:
        with st.expander(f"Debug for {row['name']}"):
            st.write(details)

    st.markdown('</div>', unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# Filtering
# -----------------------------------------------------------------------------
df = shops[shops["city"] == city].copy()
df = df[df["wifi_score"] >= wifi_min]
if gf:
    df = df[df.get("gf_food", False) == True]

if df.empty:
    st.warning("No shops match those filters. Loosen the Wi-Fi minimum or turn off gluten-free.")
    st.stop()

# -----------------------------------------------------------------------------
# Build cards (score + details)
# -----------------------------------------------------------------------------
cards = []
for _, shop in df.iterrows():
    row = shop.to_dict()

    # Nearby POIs (~700m walkable)
    within = poi[poi.apply(lambda p: haversine(row["lat"], row["lng"], p["lat"], p["lng"]) <= 700, axis=1)]
    walkables = len(within)
    parks = len(within[within["type"] == "park"])

    # Hours JSON parse (if present)
    try:
        row["hours_json"] = json.loads(row.get("hours_json", "{}"))
    except Exception:
        row["hours_json"] = {}

    vibes = compute_all_vibes(row, nearby_walkables_count=walkables, nearby_parks_count=parks)
    score = vibes[vibe].score

    top_text = narrative_one_liner(
        shop_name=row["name"],
        results=vibes,
        walk_time_min=int((within.head(1).shape[0] and 5) or 7),
        poi_names=within["name"].head(2).tolist(),
    )

    cards.append((score, row, top_text))

# Sort by score desc
cards.sort(key=lambda x: x[0], reverse=True)

# -----------------------------------------------------------------------------
# Render
# -----------------------------------------------------------------------------
for score, row, text in cards:
    details = get_shop_details(row)
    img_bytes = None
    if HAS_PLACES:
        img_bytes = get_primary_photo_bytes(
            place_id=details.get("place_id"),
            photo_reference=details.get("photo_reference"),
            maxwidth=512
        )
    render_shop_card(row, details, score, text, img_bytes)

# -----------------------------------------------------------------------------
# Developer: test Places API (handy on Cloud)
# -----------------------------------------------------------------------------
st.divider()
if st.button("Test Places API with current filters"):
    try:
        sample = df.iloc[0].to_dict()
        if HAS_PLACES:
            res = get_place_details(sample["name"], float(sample["lat"]), float(sample["lng"]), sample.get("city"))
            st.code(res if res else "None", language="json")
            if res and isinstance(res, dict) and "debug" in res:
                st.warning(res["debug"])
        else:
            st.info("services/places.py not found; skipping live enrichment test.")
    except Exception as e:
        st.error(f"Places test error: {e}")
