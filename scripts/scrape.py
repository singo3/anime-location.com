#!/usr/bin/env python3
"""
Anime Tourism 88 公式サイト（WordPress REST API）→ Google Maps で
聖地（作品タイトル＋都道府県）の緯度経度を解決し、
data/places.json へまとめて書き出すワンショットスクリプト。

● 必要パッケージ
   pip install requests python-dotenv googlemaps python-slugify tqdm

● .env 例
   GOOGLE_MAPS_KEY=AIzaSyXXXXXXXXXXXXXXXXXXXXXXXX

● 実行
   python scripts/scrape.py
"""

from __future__ import annotations
import json, os, time, requests, googlemaps
from pathlib import Path
from dotenv import load_dotenv
from slugify import slugify
from tqdm import tqdm

# ----------------------------------------------------------------------
# 0) 環境変数 & 定数
# ----------------------------------------------------------------------
load_dotenv()                                           # .env を読む
GMAPS_KEY  = os.getenv("GOOGLE_MAPS_KEY")               # 必須！
if not GMAPS_KEY:
    raise SystemExit("❌  .env に GOOGLE_MAPS_KEY がありません")

gmaps      = googlemaps.Client(key=GMAPS_KEY)
API_BASE   = "https://animetourism88.com/wp-json/wp/v2/places"
HEADERS    = {"User-Agent": "Mozilla/5.0 (Anime-Location Scraper)"}
OUTFILE    = Path("data/places.json")

# ----------------------------------------------------------------------
# 1) 低レベル util
# ----------------------------------------------------------------------
def fetch_all_places(per_page: int = 100) -> list[dict]:
    """
    1ページ目でヘッダ X-WP-TotalPages を読んで、
    必要なページだけループする安全版。
    """
    out: list[dict] = []

    # --- 1ページ目 ---
    url  = f"{API_BASE}?per_page={per_page}&page=1&_embed=1"
    resp = requests.get(url, headers=HEADERS, timeout=15)
    resp.raise_for_status()

    total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
    out.extend(resp.json())

    # --- 2ページ目以降 ---
    for page in range(2, total_pages + 1):
        url  = f"{API_BASE}?per_page={per_page}&page={page}&_embed=1"
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        out.extend(resp.json())

    return out

def term(row: dict, taxonomy: str) -> str:
    """row から taxonomy=area / places_cat などを取り出す"""
    for grp in row.get("_embedded", {}).get("wp:term", []):
        for t in grp:
            if t["taxonomy"] == taxonomy:
                return t["name"]
    return ""

def geocode_best_guess(work: str, pref: str) -> tuple[float | None, float | None]:
    """作品タイトル＋都道府県で検索し最初の結果を採用（失敗で None, None）"""
    if not pref:
        return None, None
    query = f"{work} {pref} Japan"
    try:
        res = gmaps.geocode(query, language="en")
        if not res:
            return None, None
        loc = res[0]["geometry"]["location"]
        return round(loc["lat"], 6), round(loc["lng"], 6)
    except Exception:
        return None, None

# ----------------------------------------------------------------------
# 2) メイン
# ----------------------------------------------------------------------
def main() -> None:
    print("🚚  Fetching place posts ...")
    rows = fetch_all_places()
    print(f"   → {len(rows)} records")

    records: list[dict] = []
    skipped = 0

    for r in tqdm(rows, desc="Geocoding"):
        work = r["title"]["rendered"]
        # 県名は area が最優先。無ければ places_cat（地方ブロック）が入ることが多い
        pref = term(r, "area") or term(r, "places_cat")
        lat, lng = geocode_best_guess(work, pref)
        if lat is None:
            skipped += 1
            continue

        records.append({
            "slug":  slugify(work),
            "title": work,
            "pref":  pref,
            "lat":   lat,
            "lng":   lng,
            "url":   r["link"]
        })

    # JSON 出力
    OUTFILE.parent.mkdir(exist_ok=True)
    OUTFILE.write_text(json.dumps(records, indent=2, ensure_ascii=False))
    print(f"✅  wrote {len(records)} spots → {OUTFILE}")


# ----------------------------------------------------------------------
if __name__ == "__main__":
    main()
