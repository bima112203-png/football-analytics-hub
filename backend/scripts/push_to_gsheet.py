"""
Sinkronisasi data live dari sumber web -> simpan offline di SQLite & JSON lokal -> kirim ke Google Spreadsheet Apps Script.
"""
import json
from pathlib import Path

import httpx
from fastapi.testclient import TestClient

from app.config import settings
from app.database import SessionLocal
from app.main import app
from app.services.ingestion import sync_league_data

BACKUP_DIR = Path(__file__).resolve().parents[1] / "offline_backup"


def sync_and_push_to_gsheet() -> dict:
    db = SessionLocal()
    try:
        sync_res = sync_league_data(db, job_type="gsheet_sync", recalculate_predictions=True)
        print(f"[1/3] Sinkronisasi sumber web & simpan offline SQLite: {sync_res}")
    finally:
        db.close()

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    details_dir = BACKUP_DIR / "details"
    details_dir.mkdir(parents=True, exist_ok=True)

    payload_items: dict[str, object] = {}
    with TestClient(app) as client:
        health = client.get("/health").json()
        matches = client.get("/matches").json()
        accuracy = client.get("/history/accuracy").json()

        payload_items["health"] = health
        payload_items["matches"] = matches
        payload_items["accuracy"] = accuracy

        for lg in ["PL", "PD", "SA", "BL1"]:
            payload_items[f"standings_{lg}"] = client.get(f"/standings?league={lg}").json()

        for m in matches:
            detail = client.get(f"/matches/{m['id']}").json()
            payload_items[f"detail_{m['id']}"] = detail
            (details_dir / f"{m['id']}.json").write_text(json.dumps(detail, ensure_ascii=False), encoding="utf-8")

    # Simpan backup file offline di device ini
    for k, v in payload_items.items():
        if not k.startswith("detail_"):
            (BACKUP_DIR / f"{k}.json").write_text(json.dumps(v, ensure_ascii=False), encoding="utf-8")
    print(f"[2/3] Backup offline JSON tersimpan di: {BACKUP_DIR} ({len(payload_items)} dataset)")

    url = settings.GSHEET_WEBAPP_URL.strip()
    if not url:
        print("[3/3] GSHEET_WEBAPP_URL belum diisi di .env — data tersimpan offline, siap dikirim setelah URL diisi.")
        return {"offline_saved": len(payload_items), "gsheet_pushed": False}

    # Kirim bertahap (batch 10 key per POST agar cepat & aman dari timeout Apps Script)
    keys = list(payload_items.keys())
    pushed_total = 0
    with httpx.Client(timeout=30.0, follow_redirects=True) as hc:
        for i in range(0, len(keys), 10):
            batch = {k: payload_items[k] for k in keys[i : i + 10]}
            resp = hc.post(
                url,
                json={"secret": settings.GSHEET_SYNC_SECRET, "items": batch},
            )
            resp.raise_for_status()
            res_json = resp.json()
            if res_json.get("status") != "ok":
                raise RuntimeError(f"Apps Script error: {res_json}")
            pushed_total += res_json.get("updated_keys", len(batch))

    print(f"[3/3] Berhasil kirim {pushed_total} dataset ke Google Spreadsheet!")
    return {"offline_saved": len(payload_items), "gsheet_pushed": True, "pushed_keys": pushed_total}


if __name__ == "__main__":
    sync_and_push_to_gsheet()
