# Coffee Concierge ☕🗺️

Find the right coffee shop for your vibe, with nearby parks/bookstores/landmarks, live business info, and photos.

## Demo
- Local: `python -m streamlit run app.py`
- (Cloud link here after deployment)

## What it shows
- Vibe scoring + narrative
- Google Places enrichment (address/phone/website + photos)
- Nearby POIs with walk/drive ETA + map
- Mapbox or OSM basemap (fallback)

## Tech
- Streamlit, Pandas, PyDeck
- Google Places API (server-side)
- Caching + session-state navigation

## Setup
```bash
pip install -r requirements.txt
# Put your key in .env (not committed)
# GOOGLE_MAPS_API_KEY=YOUR_KEY
python -m streamlit run app.py
