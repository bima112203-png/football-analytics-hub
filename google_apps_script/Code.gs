/**
 * Football Analytics Hub — Google Apps Script Backend Store
 * Tempelkan kode ini ke Extensions > Apps Script di Google Spreadsheet Anda:
 * https://docs.google.com/spreadsheets/d/1lY6--SxxwLF5aKftNACFGv0A67fbgnJipZ0TAO2aUxY
 *
 * Cara Setup:
 * 1. Buka Project Settings (ikon roda gigi) > Script Properties > Tambahkan:
 *    Property: SYNC_SECRET  |  Value: (samakan dengan GSHEET_SYNC_SECRET di .env laptop Anda)
 * 2. Klik Deploy > New deployment > Type: Web app
 *    - Execute as: Me
 *    - Who has access: Anyone
 * 3. Salin Web App URL (https://script.google.com/macros/s/.../exec) ke .env (GSHEET_WEBAPP_URL).
 */

const STORE_SHEET_NAME = "fah_store";
const CHUNK_SIZE = 45000; // Aman di bawah batas 50.000 karakter/sel Google Sheets

function getOrCreateStoreSheet() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = ss.getSheetByName(STORE_SHEET_NAME);
  if (!sheet) {
    sheet = ss.insertSheet(STORE_SHEET_NAME);
    sheet.getRange(1, 1, 1, 3).setValues([["key", "updated_at", "payload_chunks"]]);
    sheet.setFrozenRows(1);
  }
  return sheet;
}

function jsonResponse(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}

function doGet(e) {
  const params = (e && e.parameter) ? e.parameter : {};
  if (params.action === "ping") {
    return jsonResponse({ status: "ok", service: "fah-gsheet-backend", timestamp: new Date().toISOString() });
  }

  const key = params.key;
  if (!key) {
    return jsonResponse({ error: "Parameter 'key' wajib diisi" });
  }

  const sheet = getOrCreateStoreSheet();
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    return jsonResponse({ error: "Data belum tersedia", key: key });
  }

  const keys = sheet.getRange(2, 1, lastRow - 1, 1).getValues();
  for (let i = 0; i < keys.length; i++) {
    if (String(keys[i][0]) === String(key)) {
      const rowValues = sheet.getRange(i + 2, 3, 1, sheet.getLastColumn() - 2).getValues()[0];
      const rawJson = rowValues.filter(Boolean).join("");
      return ContentService
        .createTextOutput(rawJson || "{}")
        .setMimeType(ContentService.MimeType.JSON);
    }
  }

  return jsonResponse({ error: "Key tidak ditemukan", key: key });
}

function doPost(e) {
  try {
    const body = JSON.parse(e.postData.contents);
    const expectedSecret = PropertiesService.getScriptProperties().getProperty("SYNC_SECRET");
    if (expectedSecret && body.secret !== expectedSecret) {
      return jsonResponse({ status: "error", message: "Unauthorized: SYNC_SECRET tidak cocok" });
    }

    const items = body.items || {};
    const sheet = getOrCreateStoreSheet();
    const nowIso = new Date().toISOString();

    const lastRow = sheet.getLastRow();
    const existingKeys = {};
    if (lastRow >= 2) {
      const keyRows = sheet.getRange(2, 1, lastRow - 1, 1).getValues();
      for (let i = 0; i < keyRows.length; i++) {
        existingKeys[String(keyRows[i][0])] = i + 2;
      }
    }

    let updatedCount = 0;
    for (const [key, value] of Object.entries(items)) {
      const jsonStr = typeof value === "string" ? value : JSON.stringify(value);
      const chunks = [];
      for (let pos = 0; pos < jsonStr.length; pos += CHUNK_SIZE) {
        chunks.push(jsonStr.slice(pos, pos + CHUNK_SIZE));
      }
      if (chunks.length === 0) chunks.push("{}");

      const rowIdx = existingKeys[key] || (sheet.getLastRow() + 1);
      existingKeys[key] = rowIdx;

      // Bersihkan sisa chunk lama bila ada
      const maxCols = Math.max(sheet.getLastColumn(), 2 + chunks.length);
      if (maxCols > 2) {
        sheet.getRange(rowIdx, 3, 1, maxCols - 2).clearContent();
      }
      sheet.getRange(rowIdx, 1, 1, 2 + chunks.length).setValues([[key, nowIso, ...chunks]]);
      updatedCount++;
    }

    return jsonResponse({ status: "ok", updated_keys: updatedCount, updated_at: nowIso });
  } catch (err) {
    return jsonResponse({ status: "error", message: String(err) });
  }
}
