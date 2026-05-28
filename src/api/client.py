import re
import httpx
import threading
from datetime import datetime, timedelta
from typing import Optional

BASE_URL = "https://web.spaggiari.eu/rest/v1"
Z_DEV_APIKEY = "Tg1NWEwNGIgIC0K"
_BASE_HEADERS = {
    "User-Agent": "CVVS/std/4.2.3 Android/10",
    "Z-Dev-Apikey": Z_DEV_APIKEY,
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

    def _try_get_binary(self, path: str) -> tuple[bytes, str] | None:
        """GET a path and return (bytes, filename) if it looks like a real file, else None."""
        if not self._student_id:
            return None
        try:
            with httpx.Client(timeout=60, follow_redirects=True) as client:
                resp = client.get(f"{BASE_URL}{path}", headers=self._headers())
            if resp.status_code != 200:
                return None
            if resp.content[:4] == b"%PDF" or (
                resp.headers.get("content-disposition", "") and
                "json" not in resp.headers.get("content-type", "").lower()
            ):
                filename = self._parse_cd_filename(resp.headers.get("content-disposition", ""))
                return resp.content, filename
        except Exception:
            pass
        return None

    def _try_post_binary(self, path: str) -> tuple[bytes, str] | None:
        """POST to path (no body) and return (bytes, filename) if it looks like a file, else None."""
        if not self._student_id:
            return None
        try:
            h = {k: v for k, v in self._headers().items() if k.lower() != "content-type"}
            with httpx.Client(timeout=60, follow_redirects=True) as client:
                resp = client.post(f"{BASE_URL}{path}", headers=h)
            if resp.status_code != 200:
                return None
            if resp.content[:4] == b"%PDF":
                filename = self._parse_cd_filename(resp.headers.get("content-disposition", ""))
                return resp.content, filename
        except Exception:
            pass
        return None

    def join_noticeboard_notice(self, evt_code: str, pub_id: int) -> None:
        """Send read confirmation — required by the server before attachment download."""
        if not self._student_id:
            return
        h = {k: v for k, v in self._headers().items() if k.lower() != "content-type"}
        for join_path in [
            f"{BASE_URL}/students/{self._student_id}/noticeboard/read/{evt_code}/{pub_id}/join",
            f"{BASE_URL}/students/{self._student_id}/noticeboard/read/{evt_code}/{pub_id}/sign",
        ]:
            try:
                with httpx.Client(timeout=30) as client:
                    client.post(join_path, headers=h)
            except Exception:
                pass

    def download_noticeboard_attachment(
        self, evt_code: str, pub_id: int, attach_num: int,
        fallback_name: str = "allegato", need_join: bool = False,
    ) -> tuple[bytes, str]:
        if not self._student_id:
            raise ClassevivaError("Non autenticato")

        # Send read confirmation first (idempotent — safe to always call)
        self.join_noticeboard_notice(evt_code, pub_id)

        sid = self._student_id
        # Try every known endpoint variant for the attachment
        candidates = [
            f"/students/{sid}/noticeboard/read/{evt_code}/{pub_id}/{attach_num}",
            f"/students/{sid}/noticeboard/{evt_code}/{pub_id}/attach/{attach_num}",
            f"/students/{sid}/noticeboard/attach/{evt_code}/{pub_id}/{attach_num}",
        ]

        last_debug = b""
        for path in candidates:
            # Try POST first (original API), then GET
            for method in ("post", "get"):
                try:
                    h = {k: v for k, v in self._headers().items() if k.lower() != "content-type"}
                    with httpx.Client(timeout=60, follow_redirects=True) as client:
                        resp = getattr(client, method)(f"{BASE_URL}{path}", headers=h)
                    if resp.status_code == 401:
                        raise ClassevivaError("Sessione scaduta", 401)
                    if resp.status_code != 200:
                        continue
                    ct = resp.headers.get("content-type", "").lower()
                    # Valid binary file
                    if resp.content[:4] == b"%PDF":
                        filename = self._parse_cd_filename(resp.headers.get("content-disposition", ""))
                        return resp.content, filename or fallback_name
                    # Non-PDF binary (e.g. docx, zip)
                    if "json" not in ct and "html" not in ct and "text/" not in ct and len(resp.content) > 500:
                        filename = self._parse_cd_filename(resp.headers.get("content-disposition", ""))
                        return resp.content, filename or fallback_name
                    last_debug = resp.content[:2000]
                except ClassevivaError:
                    raise
                except Exception:
                    continue

        raise ClassevivaError(
            "Impossibile scaricare l'allegato: il server non ha restituito dati validi.\n"
            "Prova ad aprire questo avviso sul sito web Classeviva per sbloccare il download."
        )

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
        try:
            return resp.json()
        except Exception:
            return {}

    @staticmethod
    def _parse_cd_filename(cd: str) -> str:
        for part in cd.split(";"):
            part = part.strip()
            if part.lower().startswith("filename="):
                return part[9:].strip().strip('"').strip("'")
        return ""

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
        filename = self._parse_cd_filename(resp.headers.get("content-disposition", ""))
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
        return events

    def get_agenda(self, days_back: int = 7, days_forward: int = 30) -> list:
        start = (datetime.now() - timedelta(days=days_back)).strftime("%Y%m%d")
        end = (datetime.now() + timedelta(days=days_forward)).strftime("%Y%m%d")
        data = self._get(f"/students/{self._student_id}/agenda/all/{start}/{end}")
        return data.get("agenda", [])

    def get_noticeboard(self) -> list:
        data = self._get(f"/students/{self._student_id}/noticeboard")
        items = data.get("items", [])
        return items

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
