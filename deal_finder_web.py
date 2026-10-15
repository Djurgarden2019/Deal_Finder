#!/usr/bin/env python3
"""
Deal Finder Web – Blocket + Tradera + eBay
Kör med: streamlit run deal_finder_web.py
"""

import streamlit as st
import httpx
import subprocess
import json
from datetime import datetime
from typing import Optional

st.set_page_config(page_title="Deal Finder", page_icon="🔥", layout="wide")

BLOCKET_API = "https://blocket-api.se/v1/search"

LOCATIONS = {
    "Hela Sverige": None,
    "Stockholm": "STOCKHOLM",
    "Göteborg": "GOTEBORG",
    "Malmö": "MALMO",
    "Uppsala": "UPPSALA",
    "Linköping": "LINKOPING",
    "Örebro": "OREBRO",
    "Västerås": "VASTERAS",
    "Helsingborg": "HELSINGBORG",
    "Lund": "LUND",
}

PRESETS = {
    "Massivt trä / möbler": ["soffa", "byrå", "matbord", "sideboard", "fåtölj"],
    "Verktyg": ["makita", "dewalt", "milwaukee", "bosch"],
    "Elektronik": ["iphone", "macbook", "ps5", "xbox"],
    "Datorer": ["macbook", "laptop", "imac", "dell", "lenovo", "hp dator"],
    "Mobiltelefoner": ["iphone", "samsung", "pixel", "oneplus", "xiaomi"],
    "Klockor": ["rolex", "omega", "seiko", "tissot", "armbandsur", "klocka"],
    "Smycken": ["guld", "silver", "diamant", "ring", "halsband", "örhängen"],
    "Antikviteter": ["antik", "vintage", "gammal", "silverbestick", "porslin", "tavla"],
    "Bilar": ["volvo", "bmw", "audi", "volkswagen", "mercedes"],
    "MC / Motorcyklar": ["yamaha", "honda", "kawasaki", "harley", "mc"],
    "Mopeder": ["moped", "vespa", "puch", "derbi"],
    "LP-skivor": ["lp", "vinyl", "skiva", "album"],
    "Motorsågar": ["motorsåg", "stihl", "husqvarna", "jonsered"],
    "Båtar": ["båt", "segelbåt", "motorbåt", "jolle"],
    "Kläder": ["kläder", "jacka", "jeans", "tröja", "kappa"],
    "Skor": ["skor", "sneakers", "boots", "nike", "adidas"],
    "Jackor": ["jacka", "dunjacka", "läderjacka", "parkas"],
    "Träningsutrustning": ["löpband", "hantlar", "roddmaskin"],
    "Barnutrustning": ["barnvagn", "barnsäng"],
    "Kontorsstolar": ["herman miller", "kontorsstol"],
    "Småapparater": ["kitchenaid", "dyson"],
}

URGENCY_KEYWORDS = ["flyttar", "måste bort", "gratis", "bortskänkes", "bra skick", "akut"]


def get_price(item: dict) -> int:
    p = item.get("price")
    if isinstance(p, dict):
        return p.get("amount", 0) or 0
    if isinstance(p, (int, float)):
        return int(p)
    return 0


def calculate_deal_score(item: dict, all_items: list[dict]) -> float:
    score = 50.0
    price = get_price(item)
    title = (item.get("heading") or "").lower()
    if price == 0:
        score += 30
    elif price < 500:
        score += 15
    prices = [get_price(i) for i in all_items if get_price(i) > 0]
    if prices and price > 0:
        median = sorted(prices)[len(prices)//2]
        if median > 0 and price / median < 0.6:
            score += 20
    score += min(sum(1 for kw in URGENCY_KEYWORDS if kw in title) * 8, 20)
    return min(score, 100)


def search_blocket(query: str, min_price=None, max_price=None, location=None, limit=40) -> list[dict]:
    # Om minpris är satt högt → sortera på relevans/nyast istället för billigast
    sort = "RELEVANCE" if (min_price and min_price > 500) else "PRICE_ASC"
    params = {"query": query, "sort_order": sort}
    if location:
        params["locations"] = location
    try:
        resp = httpx.get(BLOCKET_API, params=params, timeout=15)
        resp.raise_for_status()
        docs = resp.json().get("docs", [])
        filtered = []
        for d in docs:
            d["_source"] = "Blocket"
            p = get_price(d)
            # Gratis-annonser inkluderas bara om minpris är 0 eller inte satt
            if min_price and min_price > 0 and p == 0:
                continue
            if (min_price is None or p >= min_price) and (max_price is None or p <= max_price):
                filtered.append(d)
        return filtered[:limit]
    except Exception as e:
        st.error(f"Blocket: {e}")
        return []


def search_tradera(query: str, min_price=None, max_price=None, limit=15) -> list[dict]:
    try:
        result = subprocess.run(["tradera", "search", query, "--page-size", "30", "--format", "json"],
                                capture_output=True, text=True, timeout=25)
        if result.returncode != 0:
            return []
        items = json.loads(result.stdout).get("items", [])
        out = []
        for it in items:
            try:
                price = int(float(str(it.get("price", 0)).replace(" ", "").replace("kr", "")))
            except Exception:
                price = 0
            if min_price and min_price > 0 and price == 0:
                continue
            if (min_price is None or price >= min_price) and (max_price is None or price <= max_price):
                url = it.get("url", "")
                if url and not url.startswith("http"):
                    url = "https://www.tradera.com" + url
                out.append({
                    "heading": it.get("title", ""),
                    "price": {"amount": price},
                    "location": {"name": "Tradera"},
                    "canonical_url": url,
                    "id": it.get("itemId"),
                    "_source": "Tradera",
                })
        return out[:limit]
    except Exception:
        return []


def search_ebay(query: str, limit=5) -> list[dict]:
    """eBay – öppnar sökresultat (priser i USD)."""
    search_url = f"https://www.ebay.com/sch/i.html?_nkw={query.replace(' ', '+')}&_sop=15"
    return [{
        "heading": f"Öppna sökresultat för '{query}' på eBay",
        "price": {"amount": 0},
        "location": {"name": "eBay (USD)"},
        "canonical_url": search_url,
        "id": f"ebay-{hash(query)}",
        "_source": "eBay",
    }]


# --- UI ---
st.title("🔥 Deal Finder")
st.caption("Blocket · Tradera · eBay")

free_query = st.text_input("Fritextsökning", placeholder="t.ex. soffa, makita, iphone...")

col1, col2 = st.columns(2)
with col1:
    preset = st.selectbox("Kategori", ["Ingen"] + list(PRESETS.keys()))
with col2:
    location_name = st.selectbox("Plats (Blocket)", list(LOCATIONS.keys()))
    location = LOCATIONS[location_name]

col_min, col_max = st.columns(2)
with col_min:
    min_price = st.slider("Minsta pris (kr)", 0, 5000, 0, step=50) or None
with col_max:
    max_price = st.slider("Maxpris (kr)", 0, 15000, 3000, step=100) or None

sources = st.multiselect("Källor", ["Blocket", "Tradera", "eBay"], default=["Blocket", "Tradera"])
sort_mode = st.radio("Sortera efter", ["Deal-score", "Maximal uppsida"], horizontal=True)

if st.button("🔍 Sök", type="primary", use_container_width=True):
    queries = [free_query.strip()] if free_query.strip() else PRESETS.get(preset, [])
    if not queries or queries == [""]:
        st.warning("Skriv ett sökord eller välj kategori.")
    else:
        all_results = []
        with st.spinner("Söker..."):
            for q in queries:
                if "Blocket" in sources:
                    all_results.extend(search_blocket(q, min_price, max_price, location))
                if "Tradera" in sources:
                    all_results.extend(search_tradera(q, min_price, max_price))
                if "eBay" in sources:
                    all_results.extend(search_ebay(q))

        if all_results:
            prices = [get_price(i) for i in all_results if get_price(i) > 0]
            median = sorted(prices)[len(prices)//2] if prices else 0

            for item in all_results:
                p = get_price(item)
                item["_profit"] = max(median - p, 0) if median and p > 0 else 0
                item["_score"] = calculate_deal_score(item, all_results)

            if sort_mode == "Maximal uppsida":
                sorted_items = sorted(all_results, key=lambda x: x["_profit"], reverse=True)
            else:
                sorted_items = sorted(all_results, key=lambda x: x["_score"], reverse=True)

            st.success(f"{len(sorted_items)} resultat")
            if median:
                st.info(f"Medianpris: {median:,} kr".replace(",", " "))

            for item in sorted_items[:40]:
                score = item.get("_score", 0)
                profit = item.get("_profit", 0)
                title = item.get("heading", "")
                price = get_price(item)
                price_str = "Gratis/bud" if price == 0 else f"{price:,} kr".replace(",", " ")
                source = item.get("_source", "")
                url = item.get("canonical_url", "")
                pot = f" · ~{profit:,} kr uppsida".replace(",", " ") if profit > 0 else ""

                emoji = "💰" if profit > 1000 else "🔥" if score >= 70 else ""
                with st.container(border=True):
                    c1, c2 = st.columns([5, 1])
                    with c1:
                        st.markdown(f"**{emoji} [{score:.0f}] [{source}] {title}**")
                        st.caption(f"{price_str}{pot}")
                    with c2:
                        if url:
                            st.link_button("Öppna", url)
        else:
            st.warning("Inga resultat.")

st.divider()
st.caption("Tips: Installera Tradera med `pip install tradera-cli`. eBay öppnar sökresultat i USD.")
