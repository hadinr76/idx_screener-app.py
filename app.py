"""
Web Screener - AI Trader Indonesia
===================================

Aplikasi Flask BARU & TERPISAH untuk screening saham.

Kenapa terpisah dari web/app.py?
- Tidak menyentuh/mengubah route, template, atau cache file yang sudah
  ada di web/app.py, jadi tidak ada risiko merusak dashboard lama.
- Bisa dijalankan berdampingan (port berbeda) dengan web/app.py yang lama.
- Memakai ulang logika scoring yang sudah ada (scanner.DailyRecommendation),
  jadi hasil screening-nya kurang lebih sama dengan yang sudah ada -
  hanya dibungkus dengan penanganan error yang lebih rapi.

Cara menjalankan (dari root folder project, BUKAN dari dalam idx_screener/):
    python -m idx_screener.app

Lalu buka: http://127.0.0.1:5050
"""

import json
import logging
import sys
import time
from pathlib import Path

# Supaya bisa import modul-modul di root project (scanner/, data/, dst)
# walau app.py ini ada di sub-folder idx_screener/.
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from flask import Flask, render_template, redirect, url_for, request

from scanner.daily_recommendation import DailyRecommendation

logger = logging.getLogger("idx_screener")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = Flask(__name__)

# Cache file SENGAJA dibuat berbeda dari punya web/app.py
# (yang pakai data/web_cache/latest_screening.json), supaya kedua
# aplikasi tidak saling menimpa data satu sama lain.
CACHE_FILE = ROOT_DIR / "data" / "web_cache" / "latest_screening_v2.json"
CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)

# Status scan terakhir - dipakai untuk menampilkan pesan error di halaman
# kalau proses scan gagal, alih-alih bikin aplikasi crash / halaman putih.
last_scan_status = {
    "success": None,
    "message": None,
    "timestamp": None,
    "duration_seconds": None,
    "total_saham": None,
}


def _load_cached_results():
    """Ambil hasil scan terakhir dari file cache, kalau ada."""

    if not CACHE_FILE.exists():
        return []

    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("Gagal membaca cache %s: %s", CACHE_FILE, e)
        return []


def _save_cached_results(results):

    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)


@app.route("/")
def dashboard():

    results = _load_cached_results()

    query = request.args.get("q", "").strip().upper()
    sort_by = request.args.get("sort", "opportunity_score")

    if query:
        results = [
            r for r in results
            if query in str(r.get("kode", "")).upper()
        ]

    # Urutkan; kalau field sort_by tidak ada di data, fallback ke 0
    # supaya tidak melempar error dan bikin halaman gagal render.
    results = sorted(
        results,
        key=lambda r: r.get(sort_by, 0) or 0,
        reverse=True,
    )

    return render_template(
        "dashboard.html",
        results=results,
        query=query,
        sort_by=sort_by,
        status=last_scan_status,
    )


@app.route("/scan", methods=["POST", "GET"])
def scan():
    """
    Menjalankan proses screening.

    Dibungkus try/except supaya kalau proses gagal di tengah jalan
    (mis. yfinance bermasalah), aplikasi tidak crash - user tetap
    diarahkan kembali ke dashboard dengan pesan error yang jelas,
    dan hasil scan SEBELUMNYA (kalau ada) tetap tersedia/tidak hilang.
    """

    start_time = time.time()

    logger.info("Memulai proses screening...")

    try:
        engine = DailyRecommendation(
            period="1y",
            technical_limit=20,
        )

        results = engine.run()

        if not results:
            raise ValueError(
                "Screening selesai tapi tidak menghasilkan data sama sekali "
                "- kemungkinan sumber data (yfinance) sedang bermasalah."
            )

        results = sorted(
            results,
            key=lambda r: r.get("opportunity_score", 0) or 0,
            reverse=True,
        )

        _save_cached_results(results)

        elapsed = time.time() - start_time

        last_scan_status.update({
            "success": True,
            "message": f"Screening berhasil untuk {len(results)} saham.",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_seconds": round(elapsed, 2),
            "total_saham": len(results),
        })

        logger.info(
            "Screening selesai: %d saham, %.2f detik",
            len(results), elapsed,
        )

    except Exception as e:

        elapsed = time.time() - start_time

        logger.exception("Screening gagal: %s", e)

        last_scan_status.update({
            "success": False,
            "message": f"Screening gagal: {e}",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "duration_seconds": round(elapsed, 2),
            "total_saham": None,
        })

    return redirect(url_for("dashboard"))


if __name__ == "__main__":

    # Port SENGAJA dibuat beda (5050) dari web/app.py (5000), supaya
    # kedua aplikasi bisa jalan berbarengan tanpa rebutan port.
    app.run(
        host="127.0.0.1",
        port=5050,
        debug=False,
        use_reloader=False,
    )
