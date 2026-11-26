"""Membangun paket ZIP statis siap upload ke Netlify Drop dengan snapshot data tersinkron."""
import json
import shutil
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

ROOT_DIR = Path(__file__).resolve().parents[2]
DIST_DIR = ROOT_DIR / "netlify-dist"
DATA_DIR = DIST_DIR / "data"
DETAILS_DIR = DATA_DIR / "details"
ZIP_OUT = ROOT_DIR.parent / "football-analytics-hub-netlify.zip"
SOURCE_HTML = ROOT_DIR / "backend" / "app" / "static" / "index.html"


STATIC_FALLBACK_HELPER = """
    let STATIC_MODE = false;
    const urlParams = new URLSearchParams(location.search);
    if (urlParams.get("gsheet")) {
      localStorage.setItem("fah_gsheet_url", urlParams.get("gsheet"));
    }
    const GSHEET_URL = localStorage.getItem("fah_gsheet_url") || "__GSHEET_WEBAPP_URL__";

    async function fetchSheetOrLocal(key, localPath) {
      if (GSHEET_URL) {
        try {
          const r = await origFetch(`${GSHEET_URL}?key=${encodeURIComponent(key)}`);
          if (r.ok) {
            const txt = await r.text();
            if (txt && !txt.includes('"Key tidak ditemukan"')) {
              return new Response(txt, { status: 200, headers: { "Content-Type": "application/json" } });
            }
          }
        } catch {}
      }
      return origFetch(localPath);
    }

    const origFetch = window.fetch.bind(window);
    window.fetch = async function(input, init) {
      const url = typeof input === "string" ? input : input.url;
      if (!url.startsWith(API_BASE + "/") && !url.startsWith("/")) {
        return origFetch(input, init);
      }
      const path = url.replace(API_BASE, "");
      if (!STATIC_MODE) {
        try {
          const resp = await origFetch(input, init);
          if (resp.ok || resp.status < 400) return resp;
          if (resp.status === 404 && location.protocol !== "file:") {
            STATIC_MODE = true;
          } else {
            return resp;
          }
        } catch (err) {
          if (location.protocol !== "file:") STATIC_MODE = true;
          else throw err;
        }
      }
      // Static Netlify + Google Sheets Live Store Mode
      if (path.startsWith("/health")) {
        return fetchSheetOrLocal("health", "./data/health.json");
      }
      if (path.startsWith("/matches?")) {
        const q = new URLSearchParams(path.split("?")[1] || "");
        const r = await fetchSheetOrLocal("matches", "./data/matches.json");
        let list = await r.json();
        const lg = q.get("league");
        const df = q.get("date_from");
        if (lg) list = list.filter(m => m.league_code === lg);
        if (df) list = list.filter(m => m.match_date.slice(0, 10) === df);
        return new Response(JSON.stringify(list), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (path.startsWith("/matches/")) {
        const id = path.split("/")[2];
        return fetchSheetOrLocal(`detail_${id}`, `./data/details/${id}.json`);
      }
      if (path.startsWith("/predict/")) {
        const id = Number(path.split("/")[2]);
        const r = await fetchSheetOrLocal("matches", "./data/matches.json");
        const list = await r.json();
        const found = list.find(m => m.id === id);
        return new Response(JSON.stringify(found?.prediction || {}), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (path.startsWith("/standings")) {
        const q = new URLSearchParams(path.split("?")[1] || "");
        const lg = q.get("league") || "PL";
        return fetchSheetOrLocal(`standings_${lg}`, `./data/standings_${lg}.json`);
      }
      if (path.startsWith("/history/accuracy")) {
        return fetchSheetOrLocal("accuracy", "./data/accuracy.json");
      }
      if (path === "/simulator/calculate" && init?.method === "POST") {
        const body = JSON.parse(init.body || "{}");
        const legs = body.legs || [];
        let prob = 1.0, odds = 1.0;
        const hasOdds = legs.every(l => l.manual_odds && l.manual_odds > 1.0);
        const ids = legs.map(l => l.match_id).filter(Boolean);
        const hasCorr = ids.length !== new Set(ids).size;
        for (const l of legs) {
          prob *= l.probability;
          if (hasOdds) odds *= l.manual_odds;
        }
        const risk = prob >= 0.30 ? "rendah" : (prob >= 0.12 ? "sedang" : "tinggi");
        return new Response(JSON.stringify({
          leg_count: legs.length,
          combined_probability: Number(prob.toFixed(6)),
          combined_probability_pct: Number((prob * 100).toFixed(2)),
          combined_odds: hasOdds ? Number(odds.toFixed(3)) : null,
          expected_value: hasOdds ? Number(((prob * odds) - 1).toFixed(4)) : null,
          risk_level: risk,
          has_same_match_correlation: hasCorr,
          correlation_note: hasCorr
            ? "Terdeteksi beberapa pasar dari pertandingan yang sama! Asumsi independensi tidak berlaku penuh."
            : "Perhitungan menggunakan asumsi independensi antar-laga: P(A ∩ B) = P(A) × P(B).",
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (path === "/simulator/save" && init?.method === "POST") {
        const body = JSON.parse(init.body || "{}");
        const saved = JSON.parse(localStorage.getItem("fah_saved_sims") || "[]");
        const calcRes = await window.fetch("/simulator/calculate", { method: "POST", body: init.body });
        const metrics = await calcRes.json();
        saved.unshift({ id: Date.now(), title: body.title, legs: body.legs, ...metrics });
        localStorage.setItem("fah_saved_sims", JSON.stringify(saved.slice(0, 20)));
        return new Response(JSON.stringify(saved[0]), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (path === "/simulator/history") {
        const saved = JSON.parse(localStorage.getItem("fah_saved_sims") || "[]");
        return new Response(JSON.stringify(saved), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (path === "/ingest/sync") {
        return new Response(JSON.stringify({
          status: "failed",
          data_delayed: true,
          error: "Mode statis Netlify aktif (hubungkan backend Render untuk sinkronisasi live)",
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      return origFetch(input, init);
    };
"""


def build() -> Path:
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DETAILS_DIR.mkdir(parents=True, exist_ok=True)

    with TestClient(app) as client:
        health = client.get("/health").json()
        (DATA_DIR / "health.json").write_text(json.dumps(health, ensure_ascii=False), encoding="utf-8")

        matches = client.get("/matches").json()
        (DATA_DIR / "matches.json").write_text(json.dumps(matches, ensure_ascii=False), encoding="utf-8")

        for m in matches:
            detail = client.get(f"/matches/{m['id']}").json()
            (DETAILS_DIR / f"{m['id']}.json").write_text(json.dumps(detail, ensure_ascii=False), encoding="utf-8")

        for lg in ["PL", "PD", "SA", "BL1"]:
            st = client.get(f"/standings?league={lg}").json()
            (DATA_DIR / f"standings_{lg}.json").write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")

        acc = client.get("/history/accuracy").json()
        (DATA_DIR / "accuracy.json").write_text(json.dumps(acc, ensure_ascii=False), encoding="utf-8")

    html = SOURCE_HTML.read_text(encoding="utf-8")
    marker = 'const API_BASE = (location.protocol === "file:") ? "http://localhost:8000" : "";'
    assert marker in html, "Marker API_BASE tidak ditemukan di index.html"
    helper = STATIC_FALLBACK_HELPER.replace("__GSHEET_WEBAPP_URL__", settings.GSHEET_WEBAPP_URL.strip())
    html = html.replace(marker, marker + "\n" + helper, 1)
    # Jangan jalankan EventSource di mode statis Netlify (agar tidak ada console error 404 /events/stream)
    html = html.replace(
        "function connectSSE() {",
        "function connectSSE() {\n      if (STATIC_MODE || location.hostname.endsWith('netlify.app')) return;",
        1,
    )
    (DIST_DIR / "index.html").write_text(html, encoding="utf-8")

    if ZIP_OUT.exists():
        ZIP_OUT.unlink()
    with zipfile.ZipFile(ZIP_OUT, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in DIST_DIR.rglob("*"):
            if file_path.is_file():
                zf.write(file_path, arcname=file_path.relative_to(DIST_DIR))

    print(f"[ZIP] Berhasil dibuat: {ZIP_OUT} ({ZIP_OUT.stat().st_size} bytes)")
    print(f"[ZIP] Laga diekspor: {len(matches)}, Detail diekspor: {len(matches)}")
    return ZIP_OUT


if __name__ == "__main__":
    build()
