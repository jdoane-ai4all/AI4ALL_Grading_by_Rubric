"""Download study inputs from Google Drive DIRECTLY into the container (not through chat).

Auth: a read-only Google service account. Put its JSON key in the environment
variable GOOGLE_SERVICE_ACCOUNT_JSON (an environment secret, never committed),
and share the Drive folder and workbook with the service account's email as Viewer.

What it fetches:
  * Data tab, columns A:AI ONLY, via the Sheets API (AJ:AK and the other tabs,
    which hold student names, are never requested) -> data/private/data_tab.csv
  * For each project row: the PDF (col T), text (col U) and ZIP (col W) by Drive file ID
    -> data/artifacts/<project_id>/, plus extraction.json unpacked from the ZIP
  * data/artifacts/manifest.csv, ready for `cli score`

Usage:  python scripts/fetch_drive.py --prep-folder <ID> --sheet <ID>
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import zipfile
from pathlib import Path

import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account

SCOPES = ["https://www.googleapis.com/auth/drive.readonly",
          "https://www.googleapis.com/auth/spreadsheets.readonly"]
API = "https://www.googleapis.com/drive/v3"


def session() -> requests.Session:
    info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    creds.refresh(Request())
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {creds.token}"
    return s


def list_children(s, folder_id):
    out, token = [], None
    while True:
        r = s.get(f"{API}/files", params={"q": f"'{folder_id}' in parents and trashed=false",
                                          "fields": "nextPageToken, files(id,name,mimeType,size)",
                                          "pageSize": 1000, "pageToken": token,
                                          "supportsAllDrives": True, "includeItemsFromAllDrives": True})
        r.raise_for_status()
        d = r.json()
        out += d["files"]
        token = d.get("nextPageToken")
        if not token:
            return out


def download(s, file_id, dest: Path):
    dest.parent.mkdir(parents=True, exist_ok=True)
    with s.get(f"{API}/files/{file_id}", params={"alt": "media", "supportsAllDrives": True}, stream=True) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)


def fetch_data_tab(s, sheet_id, out: Path):
    r = s.get(f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}/values/Data!A:AI",
              params={"valueRenderOption": "FORMATTED_VALUE"})
    r.raise_for_status()
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(r.json().get("values", []))
    print("Data tab rows:", len(r.json().get("values", [])))


ID_RE = re.compile(r"(?:/d/|/folders/|[?&]id=)([A-Za-z0-9_-]{20,})")


def _cell_link(cell: dict) -> str:
    """Hyperlink from a grid cell: explicit link, rich-text run link, HYPERLINK() formula, or URL text."""
    if cell.get("hyperlink"):
        return cell["hyperlink"]
    for run in cell.get("textFormatRuns", []) or []:
        uri = run.get("format", {}).get("link", {}).get("uri")
        if uri:
            return uri
    ev = cell.get("userEnteredValue", {})
    return ev.get("formulaValue") or ev.get("stringValue") or ""


def data_tab_links(s, sheet_id) -> list[dict]:
    """project_id (A) plus Drive file IDs for PDF (T), text (U) and ZIP (W). Columns AJ:AK never requested."""
    fields = "sheets.data.rowData.values(hyperlink,textFormatRuns,userEnteredValue)"
    out = {}
    for col, key in [("A", "project_id"), ("T", "pdf"), ("U", "text"), ("W", "zip")]:
        r = s.get(f"https://sheets.googleapis.com/v4/spreadsheets/{sheet_id}",
                  params={"ranges": f"Data!{col}2:{col}", "fields": fields})
        r.raise_for_status()
        rows = r.json()["sheets"][0]["data"][0].get("rowData", [])
        for i, row in enumerate(rows):
            cell = (row.get("values") or [{}])[0]
            d = out.setdefault(i, {})
            if key == "project_id":
                ev = cell.get("userEnteredValue", {})
                d[key] = str(ev.get("stringValue") or ev.get("numberValue") or "").strip()
            else:
                m = ID_RE.search(_cell_link(cell))
                d[key] = m.group(1) if m else ""
    return [d for d in out.values() if d.get("project_id")]


def fetch_artifacts(s, sheet_id, root: Path):
    rows = []
    for d in data_tab_links(s, sheet_id):
        pid = d["project_id"]
        pdir = root / pid
        rec = {"project_id": pid, "pdf_path": "", "text_path": "", "extraction_json": ""}
        if d["pdf"]:
            if not (pdir / "presentation.pdf").exists():
                download(s, d["pdf"], pdir / "presentation.pdf")
            rec["pdf_path"] = f"{pid}/presentation.pdf"
        if d["text"]:
            if not (pdir / "presentation.txt").exists():
                download(s, d["text"], pdir / "presentation.txt")
            rec["text_path"] = f"{pid}/presentation.txt"
        if d["zip"]:
            z = pdir / "ml-package.zip"
            if not z.exists():
                download(s, d["zip"], z)
            with zipfile.ZipFile(z) as zf:
                for n in zf.namelist():
                    if Path(n).name == "extraction.json" and ".." not in n and not n.startswith("/"):
                        (pdir / "extraction.json").write_bytes(zf.read(n))
                        rec["extraction_json"] = f"{pid}/extraction.json"
        missing = [k for k in ("pdf", "text", "zip") if not d[k]]
        if missing:
            print(pid, "missing link(s):", missing)
        rows.append(rec)
    with open(root / "manifest.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    print(len(rows), "projects ->", root / "manifest.csv")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--prep-folder", default="1KZ_bsSSYwRnaBBRVwaxBBo25i9ulf8eW")
    ap.add_argument("--sheet", default="13DZH9fANSqJDfODavq8pIBX_jxCmNMsFHcNcLZNoJ8E")
    a = ap.parse_args()
    s = session()
    fetch_data_tab(s, a.sheet, Path("data/private/data_tab.csv"))
    fetch_artifacts(s, a.sheet, Path("data/artifacts"))
