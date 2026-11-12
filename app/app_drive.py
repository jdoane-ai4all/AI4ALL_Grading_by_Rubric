"""Optional Google Drive browser for the Streamlit app (free: uses a Google Cloud service account).

Setup: create a service account in a free Google Cloud project, enable the Drive API, share the
decks folder with the service account's email as Viewer, and put the JSON key in the app's secrets
as GOOGLE_SERVICE_ACCOUNT_JSON (a TOML multi-line string). Only folders shared with that account are visible.
"""
import json
import re

import requests
import streamlit as st

API = "https://www.googleapis.com/drive/v3"


@st.cache_resource(ttl=3000)
def _session(sa_json: str):
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account
    creds = service_account.Credentials.from_service_account_info(
        json.loads(sa_json), scopes=["https://www.googleapis.com/auth/drive.readonly"])
    creds.refresh(Request())
    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {creds.token}"
    return s


def _list(s, q):
    out, token = [], None
    while True:
        r = s.get(f"{API}/files", params={"q": q, "fields": "nextPageToken, files(id,name,mimeType,size)",
                                          "pageSize": 1000, "orderBy": "folder,name", "pageToken": token,
                                          "supportsAllDrives": True, "includeItemsFromAllDrives": True})
        r.raise_for_status()
        d = r.json()
        out += d.get("files", [])
        token = d.get("nextPageToken")
        if not token:
            return out


def drive_browser(sa_json: str):
    """Renders a folder browser; returns [(name, bytes, file_id)] for files the user adds."""
    s = _session(sa_json)
    st.session_state.setdefault("drive_path", [])  # list of (id, name)
    link = st.text_input("Folder link or ID", placeholder="https://drive.google.com/drive/folders/...")
    if link:
        m = re.search(r"folders/([A-Za-z0-9_-]{10,})", link) or re.match(r"^([A-Za-z0-9_-]{10,})$", link.strip())
        if m and (not st.session_state.drive_path or st.session_state.drive_path[-1][0] != m.group(1)):
            st.session_state.drive_path = [(m.group(1), "Linked folder")]
    path = st.session_state.drive_path
    parent = path[-1][0] if path else None
    q = (f"'{parent}' in parents" if parent else "sharedWithMe = true") + " and trashed = false"
    items = _list(s, q)
    if path:
        st.caption(" / ".join(n for _, n in path))
        if st.button("⬆ Up", width="stretch"):
            path.pop()
            st.rerun()
    for f in [i for i in items if i["mimeType"] == "application/vnd.google-apps.folder"]:
        if st.button(f"📁 {f['name']}", key=f"dir_{f['id']}", width="stretch"):
            path.append((f["id"], f["name"]))
            st.rerun()
    pdfs = [i for i in items if i["mimeType"] == "application/pdf"]
    if not pdfs:
        st.caption("No PDFs here.")
        return []
    names = [p["name"] for p in pdfs]
    all_on = st.checkbox(f"Select all {len(pdfs)} PDFs")
    chosen = st.multiselect("PDFs", names, default=names if all_on else [])
    if chosen and st.button(f"Add {len(chosen)} to queue", type="primary", width="stretch"):
        out = []
        bar = st.empty()
        for i, p in enumerate([p for p in pdfs if p["name"] in chosen]):
            r = s.get(f"{API}/files/{p['id']}", params={"alt": "media", "supportsAllDrives": True})
            r.raise_for_status()
            out.append((p["name"], r.content, p["id"]))
            bar.caption(f"Downloaded {i + 1} of {len(chosen)}")
        return out
    return []
