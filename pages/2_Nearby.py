# pages/2_Nearby.py
import os
import json
from math import radians, sin, cos, sqrt, atan2
from pathlib import Path

import pandas as pd
import streamlit as st
import pydeck as pdk

# Optional Google Places enrichment (details + photos)
try:
    from services.places import get_place_details, get_primary_photo_bytes
    HAS_PLACES = True
except Exception:
    HAS_PLACES = False

st.set_page_config(page_title="Nearby Points of Interest", page_icon="🗺️", layout="wide")

# Minimal CSS reuse
st.markdown("""
<style>
.cc-card { border-radius:16px; border:1px solid rgba(20,20,33,0.06); background:#fff;
           box-shadow:0 6px 20px rgba(20,20,33,0.06); padding:14px 16px; margin-bottom:14px; }
.cc-divider { height:1px; background:#EEF1F6; margin: 8px 0 12px 0; }
</style>
""", unsafe_allow_html=True)

# Absolute paths for data (Cloud-safe)
ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
shops_path = DATA_DIR / "shops_example.csv"
poi_path   = DATA_DIR / "poi_example.csv"

if not shops_path.exists() or not poi_path.exists():
    st.error("Data files not found. Ensure 'data/shops_example.csv' and 'data/poi_example.csv' exist in the repo.")
    st.stop()

shops = pd.read_csv(shops_path)
poi   = pd.read_csv(poi_path)

# Map helper (Mapbox if token; else OSM tiles)
def deck_with_basemap(layers, view_state, tooltip=None):
    token = st.secrets.get("MAPBOX_API_KEY") or os.getenv("MAPBOX_API_KEY", "")
    if token:
        pdk.settings.mapbox_api_key = token
        return pdk.Deck(layers=layers, initial_view_state=view_state,
                        map_style="mapbox://styles/mapbox/light-v9", tooltip=tooltip)
    base = pdk.Layer(
        "TileLayer", data=None, min_zoom=0, max_zoom=19, tile_size=256,
        url="https://a.tile.openstreetmap.org/{z}/{x}/{y}.png", pickable=False,
    )
    return pdk.Deck(layers=[base, *layers], initial_view_state=view_state,
                    map_provider=None, map_style=None, tooltip=tooltip)

# Dist/time helpers
def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1); dl = radians(lon2 - lon1)
    a = sin(dphi/2)**2 + cos(phi1)*cos(phi2)*sin(dl/2)**2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))

def fmt_meters(m): return f"{int(round(m))} m" if m < 1000 else f"{m/1000:.2f} km"
def eta_minutes_km(distance_km, speed_kmh): return None if speed_kmh <= 0 else (distance_km / speed_kmh) * 60.0
def fmt_min(m): return "—" if m is None else f"{int(round(m))} min"

def resolve_shop_details(row_dict: dict) -> dict:
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
            fetched = get_place_details(row_dict["name"], float(row_dict["lat"]), float(row_dict["lng"]), row_dict.get("city"))
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

# Resolve selected shop (prefer session; else fallback selector)
if "selected_shop" in st.session_state and isinstance(st.session_state["selected_shop"], dict):
    shop_row = st.session_state["selected_shop"]
else:
    st.info("No shop passed from the main page. Pick one to explore nearby points of interest.")
    city = st.selectbox("City", sorted(shops["city"].unique()))
    shop_name = st.selectbox("Coffee shop", shops[shops["city"] == city]["name"].unique())
    shop_row = shops[shops["name"] == shop_name].iloc[0].to_dict()

# Parse hours JSON if present (keeps other code happy)
try:
    shop_row["hours_json"] = json.loads(shop_row.get("hours_json", "{}"))
except Exception:
    shop_row["hours_json"] = {}

shop_name = shop_row["name"]
shop_lat = float(shop_row["lat"])
shop_lng = float(shop_row["lng"])

# Header + actions
st.title(f"Nearby for **{shop_name}**")
a1, a2, _ = st.columns([1.2, 1, 6])
with a1:
    st.page_link("app.py", label="← Back to main")
with a2:
    if "selected_shop" in st.session_state and st.button("Clear selection"):
        del st.session_state["selected_shop"]
        st.experimental_rerun()

# Shop details block (styled)
details = resolve_shop_details(shop_row)
st.markdown('<div class="cc-card">', unsafe_allow_html=True)
pcol, cA, cB, cC = st.columns([1.2, 2, 1, 1])
with pcol:
    img_bytes = None
    if HAS_PLACES:
        try:
            img_bytes = get_primary_photo_bytes(
                place_id=details.get("place_id"),
                photo_reference=details.get("photo_reference"),
                maxwidth=512
            )
        except Exception:
            img_bytes = None
    if img_bytes:
        st.image(img_bytes, use_container_width=True)
    else:
        st.markdown("🖼️ *(no photo)*")
with cA:
    st.subheader(shop_name)
    st.write(details["address"] or "—")
with cB:
    st.markdown("**Phone**")
    st.write(details["phone"] or "—")
with cC:
    st.markdown("**Links**")
    if details["website"]:
        try: st.link_button("Website", details["website"])
        except Exception: st.markdown(f"[Website]({details['website']})")
    try: st.link_button("Google Maps", details["google_url"])
    except Exception: st.markdown(f"[Google Maps]({details['google_url']})")
st.markdown('</div>', unsafe_allow_html=True)

# Nearby controls
c0, c1, c2, c3 = st.columns([1.4, 1, 1, 1.2])
with c0: radius_m = st.slider("Search radius (m)", 200, 3000, 700, 50)
with c1: walk_kmh = st.slider("Walk speed (km/h)", 3.0, 6.0, 5.0, 0.5)
with c2: drive_kmh = st.slider("Drive speed (km/h)", 15.0, 55.0, 30.0, 5.0)
with c3: limit_lines = st.slider("Lines on map", 3, 20, 10, 1)

# Compute POIs in range
poi_calc = poi.copy()
poi_calc["distance_m"] = poi_calc.apply(
    lambda r: haversine_m(shop_lat, shop_lng, float(r["lat"]), float(r["lng"])), axis=1
)
within = poi_calc[poi_calc["distance_m"] <= radius_m].copy()
within["distance_km"] = within["distance_m"] / 1000.0
within["walk_min"] = within["distance_km"].apply(lambda d: eta_minutes_km(d, walk_kmh))
within["drive_min"] = within["distance_km"].apply(lambda d: eta_minutes_km(d, drive_kmh))
within["Distance"] = within["distance_m"].apply(fmt_meters)
within["Walk"] = within["walk_min"].apply(fmt_min)
within["Drive"] = within["drive_min"].apply(fmt_min)

# Summary + table
m0, m1, m2, m3 = st.columns(4)
m0.metric("POIs in range", f"{len(within)}")
m1.metric("Parks", f"{(within['type']=='park').sum()}")
m2.metric("Bookstores", f"{(within['type']=='bookstore').sum()}")
m3.metric("Landmarks", f"{(within['type']=='landmark').sum()}")
st.caption("Distances are straight-line (Haversine). Times use your selected speeds.")

st.subheader("Nearby places")
show_cols = ["name", "type", "Distance", "Walk", "Drive", "tags"]
st.dataframe(within.sort_values("distance_m")[show_cols].reset_index(drop=True), use_container_width=True)

# Map
st.subheader("Map")
poi_points = within[["lat", "lng", "name", "type", "Distance"]].rename(columns={"lng": "lon"})
shop_df = pd.DataFrame([{"lat": shop_lat, "lon": shop_lng, "name": shop_name, "type": "coffee"}])

topN = within.nsmallest(limit_lines, "distance_m")[["lat", "lng", "name", "Distance"]].rename(columns={"lng": "lon"})
lines_df = pd.DataFrame([
    {"from_lat": shop_lat, "from_lon": shop_lng, "to_lat": float(r["lat"]), "to_lon": float(r["lon"]),
     "name": r["name"], "distance": r["Distance"]}
    for _, r in topN.iterrows()
])

layers = [
    pdk.Layer("ScatterplotLayer", data=poi_points, get_position='[lon, lat]', get_radius=30, pickable=True,
              get_fill_color=[
                  "type == 'park' ? 34 : (type == 'bookstore' ? 0 : 200)",
                  "type == 'park' ? 139 : (type == 'bookstore' ? 122 : 30)",
                  "type == 'park' ? 34 : (type == 'bookstore' ? 204 : 200)",
                  180
              ]),
    pdk.Layer("ScatterplotLayer", data=shop_df, get_position='[lon, lat]', get_radius=60, pickable=True,
              get_fill_color=[220, 20, 60, 220]),
    pdk.Layer("LineLayer", data=lines_df, get_source_position='[from_lon, from_lat]',
              get_target_position='[to_lon, to_lat]', get_width=2, get_color=[70,130,180,200], pickable=True),
]
tooltip = {"html": "<b>{name}</b><br/>{distance}", "style": {"backgroundColor": "white", "color": "black"}}
view_state = pdk.ViewState(latitude=shop_lat, longitude=shop_lng, zoom=14, bearing=0, pitch=35)
deck = deck_with_basemap(layers, view_state, tooltip)
st.pydeck_chart(deck)

# Download itinerary
st.subheader("Export itinerary")
dl_cols = ["name", "type", "lat", "lng", "Distance", "Walk", "Drive", "tags"]
csv = within.sort_values("distance_m")[dl_cols].to_csv(index=False).encode("utf-8")
st.download_button(
    "Download itinerary (.csv)",
    csv,
    file_name=f"itinerary_{shop_row.get('shop_id', 'shop')}.csv",
    mime="text/csv",
)
