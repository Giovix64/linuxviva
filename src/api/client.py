import re
import httpx
import threading
from datetime import datetime, timedelta
from typing import Optional

BASE_URL = "https://web.spaggiari.eu/rest/v1"
_BASE_HEADERS = {
    "User-Agent": "CVVS/std/4.2.3 Android/10",
    "Z-Dev-Apikey": "Tg1NWEwNGIgIC0K",
    "Content-Type": "application/json",
}


class ClassevivaError(Exception):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class ClassevivaClient:
    def __init__(self):
        self._token: Optional[str] = None
        self._student_id: Optional[str] = None
        self._user_info: dict = {}
        self._lock = threading.Lock()

    def login(self, uid: str, password: str) -> dict:
        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{BASE_URL}/auth/login",
                headers=_BASE_HEADERS,
                json={"ident": None, "pass": password, "uid": uid},
            )
        if resp.status_code == 422:
            raise ClassevivaError("Credenziali errate", 422)
        if resp.status_code != 200:
            try:
                detail = resp.json()
            except Exception:
                detail = resp.text[:200]
            raise ClassevivaError(
                f"Errore di autenticazione (HTTP {resp.status_code}): {detail}",
                resp.status_code,
            )

        data = resp.json()

        # Response can be {"token": {...}, "ident": "S1234567", ...}
        # or LoginResultChoices when multiple accounts exist
        if "choices" in data or data.get("requestedAction"):
            raise ClassevivaError(
                "Account multipli rilevati: accedi dal sito web e seleziona il profilo prima", 0
            )

        raw_token = data.get("token", "")
        if isinstance(raw_token, dict):
            self._token = raw_token.get("token", "")
        else:
            self._token = str(raw_token)

        ident = data.get("ident", "")
        self._student_id = re.sub(r"[A-Za-z]+", "", ident)

        self._user_info = {
            "firstName": data.get("firstName", ""),
            "lastName": data.get("lastName", ""),
            "studentId": self._student_id,
        }
        return self._user_info

    # ------------------------------------------------------------------
    def _headers(self) -> dict:
        h = _BASE_HEADERS.copy()
        if self._token:
            h["Z-Auth-Token"] = self._token
        return h

    def _get_bytes(self, path: str) -> tuple[bytes, str]:
        """Returns (content_bytes, suggested_filename). Follows redirects."""
        if not self._student_id:
            raise ClassevivaError("Non autenticato")
        url = f"{BASE_URL}{path}"
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            resp = client.get(url, headers=self._headers())
        if resp.status_code == 401:
            raise ClassevivaError("Sessione scaduta", 401)
        if resp.status_code != 200:
            raise ClassevivaError(
                f"Errore download (HTTP {resp.status_code}) — {url}\n{resp.text[:200]}",
                resp.status_code,
            )
        cd = resp.headers.get("content-disposition", "")
        filename = ""
        for part in cd.split(";"):
            part = part.strip()
            if part.lower().startswith("filename="):
                filename = part[9:].strip().strip('"').strip("'")
        return resp.content, filename

    def download_noticeboard_attachment(
        self, evt_code: str, pub_id: int, attach_num: int, fallback_name: str = "allegato"
    ) -> tuple[bytes, str]:
        # POST to read endpoint — also marks the notice as read
        path = f"/students/{self._student_id}/noticeboard/read/{evt_code}/{pub_id}/{attach_num}"
        data, name = self._post_bytes(path)
        return data, name or fallback_name

    def download_didactics_file(
        self, content_id: int, fallback_name: str = "file"
    ) -> tuple[bytes, str]:
        path = f"/students/{self._student_id}/didactics/item/{content_id}"
        data, name = self._get_bytes(path)
        return data, name or fallback_name

    def _post(self, path: str, body: dict | None = None) -> dict:
        if not self._student_id:
            raise ClassevivaError("Non autenticato")
        h = self._headers()
        with httpx.Client(timeout=30) as client:
            if body is not None:
                resp = client.post(f"{BASE_URL}{path}", headers=h, json=body)
            else:
                # No body — drop Content-Type to avoid InvalidPayload
                h = {k: v for k, v in h.items() if k.lower() != "content-type"}
                resp = client.post(f"{BASE_URL}{path}", headers=h)
        if resp.status_code == 401:
            raise ClassevivaError("Sessione scaduta", 401)
        if resp.status_code != 200:
            raise ClassevivaError(
                f"Errore dal server (HTTP {resp.status_code}): {resp.text[:200]}",
                resp.status_code,
            )
        return resp.json()

    def _post_bytes(self, path: str) -> tuple[bytes, str]:
        if not self._student_id:
            raise ClassevivaError("Non autenticato")
        h = {k: v for k, v in self._headers().items() if k.lower() != "content-type"}
        with httpx.Client(timeout=60, follow_redirects=True) as client:
            resp = client.post(f"{BASE_URL}{path}", headers=h)
        if resp.status_code == 401:
            raise ClassevivaError("Sessione scaduta", 401)
        if resp.status_code != 200:
            raise ClassevivaError(
                f"Errore download (HTTP {resp.status_code}): {resp.text[:200]}",
                resp.status_code,
            )
        cd = resp.headers.get("content-disposition", "")
        filename = ""
        for part in cd.split(";"):
            part = part.strip()
            if part.lower().startswith("filename="):
                filename = part[9:].strip().strip('"').strip("'")
        return resp.content, filename

    def get_documents(self) -> list:
        data = self._post(f"/students/{self._student_id}/documents")
        result = []
        for doc in data.get("documents") or []:
            if doc.get("hash"):
                result.append({
                    "type": "download",
                    "desc": doc.get("desc") or "Pagella",
                    "hash": doc["hash"],
                    "sessione": doc.get("sessione"),
                })
        for report in data.get("schoolReports") or []:
            url = report.get("viewLink") or report.get("confirmLink")
            if url:
                result.append({
                    "type": "link",
                    "desc": report.get("desc") or "Report",
                    "url": url,
                    "sessione": report.get("sessione"),
                })
        return result

    def download_document(self, doc_hash: str, fallback_name: str = "pagella.pdf") -> tuple[bytes, str]:
        data, name = self._post_bytes(f"/students/{self._student_id}/documents/read/{doc_hash}")
        return data, name or fallback_name

    def _get(self, path: str) -> dict:
        if not self._student_id:
            raise ClassevivaError("Non autenticato")
        with httpx.Client(timeout=30) as client:
            resp = client.get(f"{BASE_URL}{path}", headers=self._headers())
        if resp.status_code == 401:
            raise ClassevivaError("Sessione scaduta, effettua nuovamente il login", 401)
        if resp.status_code != 200:
            raise ClassevivaError(
                f"Errore dal server (HTTP {resp.status_code}): {resp.text[:200]}", resp.status_code
            )
        return resp.json()

    # ------------------------------------------------------------------
    def get_grades(self) -> list:
        data = self._get(f"/students/{self._student_id}/grades")
        return data.get("grades", [])

    def get_absences(self) -> list:
        data = self._get(f"/students/{self._student_id}/absences/details")
        events = data.get("events") or data.get("absences") or []
        # Write raw codes to /tmp for debugging if counters appear wrong
        try:
            import json as _json
            with open("/tmp/classeviva_absences_debug.json", "w") as _f:
                _json.dump(events[:10], _f, indent=2)
        except Exception:
            pass
        return events

    def get_agenda(self, days_back: int = 7, days_forward: int = 30) -> list:
        start = (datetime.now() - timedelta(days=days_back)).strftime("%Y%m%d")
        end = (datetime.now() + timedelta(days=days_forward)).strftime("%Y%m%d")
        data = self._get(f"/students/{self._student_id}/agenda/all/{start}/{end}")
        return data.get("agenda", [])

    def get_noticeboard(self) -> list:
        data = self._get(f"/students/{self._student_id}/noticeboard")
        return data.get("items", [])

    def get_didactics(self) -> list:
        data = self._get(f"/students/{self._student_id}/didactics")
        return data.get("didacticts", data.get("didactics", []))

    def get_periods(self) -> list:
        data = self._get(f"/students/{self._student_id}/periods")
        return data.get("periods", [])

    # ------------------------------------------------------------------
    def is_authenticated(self) -> bool:
        return bool(self._token and self._student_id)

    def logout(self):
        with self._lock:
            self._token = None
            self._student_id = None
            self._user_info = {}

    @property
    def user_info(self) -> dict:
        return dict(self._user_info)

    @property
    def token(self) -> str:
        return self._token or ""
