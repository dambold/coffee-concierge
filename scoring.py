from __future__ import annotations
from dataclasses import dataclass
from typing import Tuple, List
import math
def _nz(v, d=None):
    if v is None: return d
    try:
        if isinstance(v,float) and math.isnan(v): return d
    except: pass
    return v
def clamp(x, lo=0.0, hi=1.0): return max(lo,min(hi,x))
def norm_0_5(x):
    x=_nz(x); 
    return None if x is None else clamp(float(x)/5.0)
def bool_norm(x):
    x=_nz(x); 
    return None if x is None else (1.0 if bool(x) else 0.0)
def norm_seating(c): c=_nz(c); return None if c is None else clamp(float(c)/40.0)
def norm_price_index(pi): pi=_nz(pi); return None if pi is None else clamp(1.0-((float(pi)-1.0)/3.0))
def norm_hours_late(h):
    if not isinstance(h,dict) or not h: return None
    t=l=0.0
    for v in h.values():
        if not isinstance(v,list) or len(v)!=2: continue
        o,c=v; 
        if o is None or c is None: continue
        span=(c-o) if c>=o else (24-o+c); t+=max(span,0)
        if c>19: l+=max(c-max(o,19),0)
    return None if t<=0 else clamp(l/t)
def norm_hours_early(h):
    if not isinstance(h,dict) or not h: return None
    t=e=0.0
    for v in h.values():
        if not isinstance(v,list) or len(v)!=2: continue
        o,c=v; 
        if o is None or c is None: continue
        span=(c-o) if c>=o else (24-o+c); t+=max(span,0)
        if o<7.5: e+=min(7.5-o, span) if c>o else min(7.5-o, 24-o+c)
    return None if t<=0 else clamp(e/t)
def norm_noise_inverse(n): n=norm_0_5(n); return None if n is None else clamp(1.0-n)
def norm_mid_noise_bonus(n): n=norm_0_5(n); return None if n is None else clamp(1.0-abs(n-0.5)*2.0)
def norm_df_milks(c): c=_nz(c); return None if c is None else clamp(float(c)/3.0)
def combine(parts: List[Tuple[float,float]]):
    pres=[(v,w) for v,w in parts if v is not None and w>0]; tw=sum(w for _,w in parts if w>0)
    if tw<=0 or not pres: return (0.0,0.0)
    num=sum(v*w for v,w in pres); den=sum(w for _,w in pres); cov=clamp(den/tw); 
    return (clamp(num/den), cov)
@dataclass
class VibeResult:
    score: float; coverage: float; confidence: str; drivers: List[str]
def _conf(c): return "High" if c>=0.8 else ("Medium" if c>=0.5 else "Low")
def work_friendly(r):
    wifi=norm_0_5(r.get("wifi_score")) or 0.6
    outlets=norm_0_5(r.get("outlets_score")) or 0.5
    noise_inv=norm_noise_inverse(r.get("noise_score")) or 0.5
    seating=norm_seating(r.get("seating_count")) or 0.4
    restroom=bool_norm(r.get("restroom_access")) or 0.5
    late=_nz(norm_hours_late(r.get("hours_json")),0.4)
    clean=norm_0_5(r.get("cleanliness_score")) or 0.6
    parking=norm_0_5(r.get("parking_score")) or 0.5
    s,c=combine([(wifi,0.22),(outlets,0.18),(noise_inv,0.15),(seating,0.12),(restroom,0.10),(late,0.10),(clean,0.08),(parking,0.05)]); s*=(0.9+0.1*c)
    d=[]; 
    if wifi>=0.7:d.append("reliable Wi‑Fi")
    if outlets>=0.6:d.append("many outlets")
    if noise_inv>=0.6:d.append("lower noise")
    if late>=0.5:d.append("open late")
    return VibeResult(round(100*s,1),c,_conf(c),d[:3])
def aesthetic(r):
    aest=norm_0_5(r.get("aesthetic_score")) or 0.5
    light=norm_0_5(r.get("natural_light_score", r.get("aesthetic_score"))) or 0.5
    latte=norm_0_5(r.get("latte_art_score")) or 0.4
    clean=norm_0_5(r.get("cleanliness_score")) or 0.6
    decor=norm_0_5(r.get("unique_decor_score", r.get("aesthetic_score"))) or 0.5
    dessert=norm_0_5(r.get("dessert_score")) or 0.5
    s,c=combine([(aest,0.40),(light,0.20),(latte,0.15),(clean,0.10),(decor,0.10),(dessert,0.05)]); s*=(0.9+0.1*c)
    d=[]; 
    if aest>=0.7:d.append("design-forward space")
    if light>=0.65:d.append("great natural light")
    if latte>=0.6:d.append("latte art")
    return VibeResult(round(100*s,1),c,_conf(c),d[:3])
def grab_and_go(r):
    parking=norm_0_5(r.get("parking_score")) or 0.5
    early=_nz(norm_hours_early(r.get("hours_json")),0.4)
    mobile=bool_norm(r.get("mobile_order")) or 0.0
    drive=bool_norm(r.get("has_drive_through")) or 0.0
    peak=clamp((_nz(r.get("peak_busy_penalty"),0.2)),0,1)
    speed=clamp(0.4+0.3*mobile+0.3*drive-0.2*peak)
    s,c=combine([(speed,0.35),(parking,0.25),(early,0.15),(mobile,0.15),(drive,0.10)]); s*=(0.9+0.1*c)
    d=[]; 
    if drive>=0.9:d.append("drive-through")
    if mobile>=0.9:d.append("mobile order")
    if early>=0.6:d.append("opens early")
    return VibeResult(round(100*s,1),c,_conf(c),d[:3])
def date_night(r, walk=None):
    amb=combine([(norm_0_5(r.get("lighting_score", r.get("aesthetic_score"))),0.35),(norm_0_5(r.get("seating_comfort_score", r.get("aesthetic_score"))),0.35),(norm_mid_noise_bonus(r.get("noise_score")),0.30)])[0]
    dessert=norm_0_5(r.get("dessert_score")) or 0.5
    late=_nz(norm_hours_late(r.get("hours_json")),0.4)
    aest=norm_0_5(r.get("aesthetic_score")) or 0.5
    walk=_nz(walk, _nz(r.get("nearby_walkables_norm"), None))
    clean=norm_0_5(r.get("cleanliness_score")) or 0.6
    s,c=combine([(amb,0.25),(dessert,0.20),(late,0.18),(aest,0.15),(walk,0.12),(clean,0.10)]); s*=(0.9+0.1*c)
    d=[]; 
    if amb and amb>=0.65:d.append("cozy ambience")
    if dessert>=0.65:d.append("good desserts")
    if late>=0.6:d.append("open late")
    return VibeResult(round(100*s,1),c,_conf(c),d[:3])
def dietary_friendly(r):
    gf=bool_norm(r.get("gf_food")) or 0.0
    df=norm_df_milks(r.get("df_milks")) or 0.0
    nut=bool_norm(r.get("nut_free")) or 0.0
    label=norm_0_5(r.get("ingredient_transparency_score",3.0)) or 0.6
    clean=norm_0_5(r.get("cleanliness_score")) or 0.6
    s,c=combine([(gf,0.40),(df,0.28),(nut,0.12),(label,0.10),(clean,0.10)]); s*=(0.9+0.1*c)
    d=[]; 
    if gf>=0.9:d.append("gluten-free options")
    if df>=0.67:d.append("dairy-free milks")
    if nut>=0.9:d.append("nut-free choices")
    return VibeResult(round(100*s,1),c,_conf(c),d[:3])
def study_spot(r):
    outlets=norm_0_5(r.get("outlets_score")) or 0.5
    seating=norm_seating(r.get("seating_count")) or 0.4
    wifi=norm_0_5(r.get("wifi_score")) or 0.6
    price=norm_price_index(r.get("price_index")) or 0.5
    late=_nz(norm_hours_late(r.get("hours_json")),0.4)
    noise_inv=norm_noise_inverse(r.get("noise_score")) or 0.5
    s,c=combine([(outlets,0.28),(seating,0.22),(wifi,0.18),(price,0.12),(late,0.10),(noise_inv,0.10)]); s*=(0.9+0.1*c)
    d=[]; 
    if outlets>=0.6:d.append("outlets available")
    if seating>=0.6:d.append("ample seating")
    if price>=0.6:d.append("budget-friendly")
    return VibeResult(round(100*s,1),c,_conf(c),d[:3])
def family_friendly(r, parks=None):
    space=norm_0_5(r.get("space_score", r.get("seating_comfort_score"))) or 0.5
    restroom=bool_norm(r.get("restroom_access")) or 0.5
    parking=norm_0_5(r.get("parking_score")) or 0.5
    noise_tol=norm_mid_noise_bonus(r.get("noise_score")) or 0.5
    kids=norm_0_5(r.get("kids_snacks_score", r.get("dessert_score"))) or 0.5
    parks=_nz(parks, _nz(r.get("nearby_parks_norm"), None))
    s,c=combine([(space,0.30),(restroom,0.20),(parking,0.18),(noise_tol,0.15),(kids,0.10),(parks,0.07)]); s*=(0.9+0.1*c)
    d=[]; 
    if space>=0.6:d.append("roomy layout")
    if restroom>=0.9:d.append("restroom access")
    if parks and parks>=0.6:d.append("park nearby")
    return VibeResult(round(100*s,1),c,_conf(c),d[:3])
VIBE_FUNCS={"Work-Friendly":work_friendly,"Aesthetic":aesthetic,"Grab-and-Go":grab_and_go,"Date-Night":date_night,"Dietary-Friendly":dietary_friendly,"Study-Spot":study_spot,"Family-Friendly":family_friendly}
def compute_all_vibes(row, *, nearby_walkables_count=None, nearby_parks_count=None):
    def nn(n): return clamp(float(_nz(n,0))/5.0)
    walk = nn(nearby_walkables_count) if nearby_walkables_count is not None else None
    parks = nn(nearby_parks_count) if nearby_parks_count is not None else None
    return {"Work-Friendly":work_friendly(row),"Aesthetic":aesthetic(row),"Grab-and-Go":grab_and_go(row),"Date-Night":date_night(row, walk),"Dietary-Friendly":dietary_friendly(row),"Study-Spot":study_spot(row),"Family-Friendly":family_friendly(row, parks)}
def best_vibes(results, top_k=2): return sorted(results.items(), key=lambda kv: kv[1].score, reverse=True)[:top_k]
def narrative_one_liner(shop_name, results, *, walk_time_min=None, poi_names=None, late_days_str=None):
    vibe, vr = best_vibes(results,1)[0]
    drivers = ", ".join(vr.drivers) if vr.drivers else "solid fundamentals"
    bits=[f"**{shop_name}** is strong for **{vibe}** thanks to {drivers}."]
    if walk_time_min and poi_names: bits.append(f"It’s about a {walk_time_min}-min walk to {' and '.join(poi_names[:2])}." )
    if late_days_str and 'open late' not in (vr.drivers or []): bits.append(f"Open late {late_days_str}." )
    bits.append(f"Data confidence: {vr.confidence}." ); return " ".join(bits)
