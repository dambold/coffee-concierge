import os
import json
from math import radians, sin, cos, sqrt, atan2

import pandas as pd
import streamlit as st

from scoring import compute_all_vibes, narrative_one_liner
# --- add near top of app.py (after imports) ---
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

shops_path = DATA_DIR / "shops_example.csv"
poi_path = DATA_DIR / "poi_example.csv"

if not shops_path.exists():
    import streamlit as st
    st.error(
        f"Missing data file: {shops_path}\n\n"
        "Fix: add 'data/shops_example.csv' to your GitHub repo (case-sensitive) "
        "and redeploy."
    )
    st.stop()

if not poi_path.exists():
    import streamlit as st
    st.error(
        f"Missing data file: {poi_path}\n\n"
        "Fix: add 'data/poi_example.csv' to your GitHub repo (case-sensitive) "
        "and redeploy."
    )
    st.stop()

# --- replace old reads ---
import pandas as pd
shops = pd.read_csv(shops_path)
poi = pd.read_csv(poi_path)

# -----------------------------------------------------------------------------
# Streamlit page config
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Coffee Concierge", page_icon="☕", layout="wide")
st.markdown("""
<style>
/* page padding + nicer headings */
.block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
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

/* section header inside card */
.cc-headline {
  display:flex; align-items:center; gap:8px;
  font-weight: 700; font-size: 1.1rem; margin: 2px 0 8px 0;
}

/* vibe score pill */
.cc-pill {
  display:inline-flex; align-items:center; gap:6px;
  background: linear-gradient(135deg, #6C5CE7, #9B5DE5);
  color:#fff; padding:4px 10px; border-radius:999px; font-size:0.85rem;
}

/* helper for muted text */
.cc-muted { color:#5d6b82; }

/* fine print link row */
.cc-links { display:flex; gap:12px; align-items:center; flex-wrap:wrap; }

/* image wrapper to enforce rounded corners */
.cc-thumb img { border-radius: 12px !important; }

/* button row spacing */
.cc-actions { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }

/* small chips for features */
.cc-chip {
  display:inline-flex; align-items:center; gap:6px;
  background:#F3F5F9; color:#334; border:1px solid #E6EAF2;
  padding:4px 8px; border-radius:999px; font-size:0.78rem; margin-right:6px; margin-bottom:6px;
}

/* subtle divider */
.cc-divider { height:1px; background: #EEF1F6; margin: 8px 0 12px 0; }
</style>
""", unsafe_allow_html=True)

# If a secret exists, surface it as an env var so services/places.py can see it.
if "GOOGLE_MAPS_API_KEY" in st.secrets and not os.getenv("GOOGLE_MAPS_API_KEY"):
    os.environ["GOOGLE_MAPS_API_KEY"] = st.secrets["GOOGLE_MAPS_API_KEY"]

# Optional Google Places enrichment (safe if file/module missing)
try:
    from services.places import (
        get_place_details,
        get_primary_photo_bytes,  # <-- photos
    )
    HAS_PLACES = True
except Exception:
    HAS_PLACES = False

st.title("Coffee Concierge")
st.caption("Find the right coffee shop for your vibe — then add a nearby park, bookstore, or landmark.")

# -----------------------------------------------------------------------------
# Data
# -----------------------------------------------------------------------------
shops = pd.read_csv("data/shops_example.csv")
poi = pd.read_csv("data/poi_example.csv")

# -----------------------------------------------------------------------------
# Controls
# -----------------------------------------------------------------------------
colA, colB, colC = st.columns([1, 1, 2])
with colA:
    city = st.selectbox("City", sorted(shops["city"].unique()))
with colB:
    vibe = st.selectbox(
        "Vibe",
        ["Work-Friendly", "Aesthetic", "Grab-and-Go", "Date-Night",
         "Dietary-Friendly", "Study-Spot", "Family-Friendly"],
    )
with colC:
    st.info("Tip: try **Date-Night** or **Work-Friendly** to see different drivers.", icon="💡")

col1, col2, col3 = st.columns([1, 1, 1])
with col1:
    gf = st.checkbox("Must have gluten-free options", value=False)
with col2:
    wifi_min = st.slider("Min Wi-Fi score (0–5)", 0.0, 5.0, 3.0, 0.5)
with col3:
    debug_details = st.toggle("Debug: show shop detail sources", value=False)

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def haversine(lat1, lon1, lat2, lon2):
    R = 6371000.0
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))

def get_shop_details(row_dict: dict) -> dict:
    """
    Return details using CSV first, then optional Google enrichment:
      {address, phone, website, google_url, place_id, photo_reference, source}
    Always returns a usable google_url fallback (Maps search).
    """
    details = {
        "address": row_dict.get("address"),
        "phone": row_dict.get("phone"),
        "website": row_dict.get("website"),
        "google_url": None,
        "place_id": row_dict.get("google_place_id"),
        "photo_reference": row_dict.get("photo_reference"),  # allow prefilled CSV if you ever add it
        "source": "csv",
    }

    # Optional live enrichment if any of the basics are missing
    if HAS_PLACES and os.getenv("GOOGLE_MAPS_API_KEY") and (
        not details["address"] or not details["phone"] or not details["website"] or not details["photo_reference"]
    ):
        try:
            fetched = get_place_details(
                row_dict["name"],
                float(row_dict["lat"]),
                float(row_dict["lng"]),
                row_dict.get("city"),
            )
            if isinstance(fetched, dict) and ("address" in fetched or "debug" in fetched):
                for k in ["address", "phone", "website", "google_url", "place_id", "photo_reference"]:
                    if not details.get(k) and fetched.get(k):
                        details[k] = fetched.get(k)
                if fetched.get("address") or fetched.get("website") or fetched.get("phone"):
                    details["source"] = "google"
        except Exception:
            pass

    # Fallback Google Maps search URL if canonical url missing
    if not details.get("google_url"):
        q = f"https://www.google.com/maps/search/?api=1&query={row_dict['name'].replace(' ', '+')}%2C+{row_dict.get('city','')}"
        details["google_url"] = q

    return details

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
# Build cards (score + details + session-state handoff)
# -----------------------------------------------------------------------------
cards = []
for _, shop in df.iterrows():
    row = shop.to_dict()

    # Nearby POIs within ~700m (walkable)
    within = poi[poi.apply(lambda p: haversine(row["lat"], row["lng"], p["lat"], p["lng"]) <= 700, axis=1)]
    walkables = len(within)
    parks = len(within[within["type"] == "park"])

    # Parse hours JSON if present
    try:
        hours = json.loads(row.get("hours_json", "{}"))
    except Exception:
        hours = {}
    row["hours_json"] = hours

    # Score all vibes, pick selected vibe's score
    vibes = compute_all_vibes(row, nearby_walkables_count=walkables, nearby_parks_count=parks)
    score = vibes[vibe].score

    # One-liner narrative
    top_text = narrative_one_liner(
        shop_name=row["name"],
        results=vibes,
        walk_time_min=int((within.head(1).shape[0] and 5) or 7),
        poi_names=within["name"].head(2).tolist(),
    )

    # Save for sort + render later
    cards.append((score, row, top_text, within))

# Sort by selected vibe score
cards.sort(key=lambda x: x[0], reverse=True)

# -----------------------------------------------------------------------------
# Render cards (with photo thumbnails)
# -----------------------------------------------------------------------------
for score, row, text, within in cards:
    details = get_shop_details(row)

    with st.container(border=True):
        st.markdown(f"### {row['name']} — {vibe} score: **{score:.1f}**")
        st.markdown(text)

        # Photo + info columns
        img_col, info_col = st.columns([1, 3])

        # --- Photo thumbnail ---
        with img_col:
            img_bytes = None
            if HAS_PLACES:
                img_bytes = get_primary_photo_bytes(
                    place_id=details.get("place_id"),
                    photo_reference=details.get("photo_reference"),
                    maxwidth=512
                )
            if img_bytes:
                st.image(img_bytes, use_container_width=True)
            else:
                st.markdown("🖼️ *(no photo)*")

        # --- Details ---
        with info_col:
            c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
            with c1:
                st.markdown("**Address**")
                st.write(details["address"] or "—")
            with c2:
                st.markdown("**Phone**")
                st.write(details["phone"] or "—")
            with c3:
                st.markdown("**Website**")
                if details["website"]:
                    try:
                        st.link_button("Open site", details["website"])
                    except Exception:
                        st.markdown(f"[Open site]({details['website']})")
                else:
                    st.write("—")
            with c4:
                st.markdown("**Google Maps**")
                try:
                    st.link_button("Open in Maps", details["google_url"])
                except Exception:
                    st.markdown(f"[Open in Maps]({details['google_url']})")

            if debug_details:
                with st.expander(f"Debug for {row['name']}"):
                    st.write({
                        "source": details.get("source"),
                        "address": details.get("address"),
                        "phone": details.get("phone"),
                        "website": details.get("website"),
                        "google_url": details.get("google_url"),
                        "place_id": details.get("place_id"),
                        "photo_reference": details.get("photo_reference"),
                    })

            # Actions
            a1, a2 = st.columns([1, 6])
            with a1:
                if st.button("View details & nearby →", key=f"btn_{row['name']}"):
                    st.session_state["selected_shop"] = row
                    st.session_state["selected_city"] = city
                    st.switch_page("pages/2_Nearby.py")
            with a2:
                st.page_link("pages/3_About_Ratings.py", label="How ratings work →")

# -----------------------------------------------------------------------------
# Developer tool: Test Places API with current filters
# -----------------------------------------------------------------------------
st.divider()
if st.button("Test Places API with current filters"):
    try:
        sample = df.iloc[0].to_dict()
        if HAS_PLACES:
            res = get_place_details(
                sample["name"],
                float(sample["lat"]),
                float(sample["lng"]),
                sample.get("city"),
            )
            st.code(res if res else "None", language="json")
            if res and isinstance(res, dict) and "debug" in res:
                st.warning(res["debug"])
        else:
            st.info("services/places.py not found; skipping live enrichment test.")
    except Exception as e:
        st.error(f"Places test error: {e}")
