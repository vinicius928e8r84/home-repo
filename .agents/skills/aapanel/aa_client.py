"""Generic aaPanel (bt-panel) client — works against ANY aaPanel server.

Credentials are supplied by the caller (never hardcoded). Three sources:
    AaPanel(base_url, entrance, username, password)      # explicit
    AaPanel.from_env()                                    # AAPANEL_URL / _USER / _PWD
    AaPanel.from_config(path)                             # JSON {url,user,pwd}
where AAPANEL_URL / config "url" is the FULL login URL incl. entrance,
e.g. https://1.2.3.4:20923/7566289f

Gotchas baked in (learned the hard way):
  * The security entrance returns a FAKE nginx-404 to any request carrying
    X-Requested-With. Hit the entrance as a plain browser; that header is added
    ONLY on /login and /files API calls.
  * TLS via cert pinning (assert_fingerprint), never verify=False.
  * Login tokens are data= attrs on <div class="last_token|apsess_token|public_key">.
  * username = rsa(md5(md5(user+last_token))); password = rsa(md5(md5(pwd)+'_bt.cn')).
  * NEVER call system?action=RestartServer — it reboots the whole VPS.
"""
import os, re, ssl, json, time, base64, hashlib
import requests
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding


def _md5(s):
    return hashlib.md5(s.encode() if isinstance(s, str) else s).hexdigest()


def _rewrap_pem(pem):
    body = re.sub(r"\s+", "", pem.replace("-----BEGIN PUBLIC KEY-----", "")
                  .replace("-----END PUBLIC KEY-----", ""))
    lines = "\n".join(body[i:i + 64] for i in range(0, len(body), 64))
    return f"-----BEGIN PUBLIC KEY-----\n{lines}\n-----END PUBLIC KEY-----\n"


def _rsa(pub_pem, data):
    key = serialization.load_pem_public_key(_rewrap_pem(pub_pem).encode())
    return base64.b64encode(key.encrypt(data.encode(), padding.PKCS1v15())).decode()


class AaPanel:
    def __init__(self, base_url, entrance, username, password):
        self.base = base_url.rstrip("/")
        self.entrance = "/" + entrance.strip("/")
        self.host = self.base.split("://")[1].split(":")[0]
        self.port = int(self.base.split(":")[2].split("/")[0])
        self._user, self._pwd = username, password
        self.fp = self._fingerprint()
        self.s = self._session()
        self.apsess = None
        self.htoken = None

    # ---- constructors ----
    @staticmethod
    def _split(url):
        base = "https://" + url.split("://")[1].split("/")[0]
        entrance = url.split("://")[1][len(base.split("://")[1]):]
        return base, entrance

    @classmethod
    def from_env(cls):
        base, ent = cls._split(os.environ["AAPANEL_URL"])
        return cls(base, ent, os.environ["AAPANEL_USER"], os.environ["AAPANEL_PWD"])

    @classmethod
    def from_config(cls, path):
        c = json.load(open(path, encoding="utf-8"))
        base, ent = cls._split(c["url"])
        return cls(base, ent, c["user"], c["pwd"])

    # ---- transport ----
    def _fingerprint(self):
        der = ssl.PEM_cert_to_DER_cert(ssl.get_server_certificate((self.host, self.port)))
        return hashlib.sha256(der).hexdigest()

    def _session(self):
        fp = self.fp

        class FP(HTTPAdapter):
            def init_poolmanager(self, c, m, block=False, **kw):
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                self.poolmanager = PoolManager(num_pools=c, maxsize=m, block=block,
                                               assert_fingerprint=fp, ssl_context=ctx, **kw)
        s = requests.Session()
        s.mount("https://", FP())
        s.headers.update({  # plain-browser: NO X-Requested-With (triggers fake 404)
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        })
        return s

    # ---- auth ----
    @staticmethod
    def _divdata(html, cls):
        m = re.search(r'class="' + cls + r'"[^>]*\bdata="([^"]*)"', html)
        return m.group(1) if m else None

    def login(self):
        html = ""
        for _ in range(8):
            html = self.s.get(self.base + self.entrance, timeout=20).text
            if "public_key" in html:
                break
            time.sleep(1.5)
        last_token = self._divdata(html, "last_token")
        apsess_token = self._divdata(html, "apsess_token")
        pub = self._divdata(html, "public_key")
        if not (last_token and pub):
            raise RuntimeError("entrance did not yield login tokens (wrong URL/entrance?)")
        data = {"username": _rsa(pub, _md5(_md5(self._user + last_token))),
                "password": _rsa(pub, _md5(_md5(self._pwd) + "_bt.cn")), "code": ""}
        j = self.s.post(self.base + "/login", data=data, timeout=20,
                        headers={"X-Requested-With": "XMLHttpRequest"}).json()
        if not j.get("status"):
            raise RuntimeError("login failed: " + str(j.get("msg")))
        self.apsess = "/apsess_" + apsess_token if apsess_token else ""
        rr = self.s.get(self.base + self.apsess + "/", timeout=20).text
        t = re.search(r'request_token[^>]*token\s*[:=]\s*["\']?([A-Za-z0-9]+)', rr) \
            or self._divdata(rr, "request_token")
        self.htoken = t.group(1) if hasattr(t, "group") else t
        return self

    # ---- files API ----
    def _api(self, action, data=None, files=None):
        h = {"X-Requested-With": "XMLHttpRequest"}
        if self.htoken:
            h["X-Http-Token"] = self.htoken
        r = self.s.post(self.base + self.apsess + "/files?action=" + action,
                        data=data or {}, files=files, headers=h, timeout=120)
        try:
            return r.json()
        except Exception:
            return {"raw": r.text[:200], "code": r.status_code}

    def listdir(self, path):
        return self._api("GetDir", {"path": path})

    def get_file(self, path):
        return self._api("GetFileBody", {"path": path})

    def save_file(self, path, text):
        return self._api("SaveFileBody", {"path": path, "data": text, "encoding": "utf-8"})

    def delete(self, path):
        return self._api("DeleteFile", {"path": path})

    def unzip(self, sfile, dfile):
        return self._api("UnZip", {"sfile": sfile, "dfile": dfile, "type": "zip",
                                   "coding": "UTF-8", "password": ""})

    def upload(self, remote_dir, local_path, chunk=2 * 1024 * 1024):
        name, size, last = os.path.basename(local_path), os.path.getsize(local_path), None
        with open(local_path, "rb") as f:
            start = 0
            while True:
                buf = f.read(chunk)
                if not buf and start:
                    break
                last = self._api("upload",
                                 data={"f_path": remote_dir, "f_name": name,
                                       "f_size": str(size), "f_start": str(start)},
                                 files={"blob": (name, buf, "application/octet-stream")})
                start += len(buf)
                if start >= size:
                    break
        return last

    def upload_unzip(self, remote_dir, local_zip, wait_for=None, timeout=40):
        """Upload a zip and extract into remote_dir; poll listdir for wait_for; rm zip."""
        self.upload(remote_dir, local_zip)
        remote_zip = remote_dir.rstrip("/") + "/" + os.path.basename(local_zip)
        self.unzip(remote_zip, remote_dir)
        if wait_for:
            deadline = time.time() + timeout
            while time.time() < deadline:
                d = self.listdir(remote_dir + "/" + os.path.dirname(wait_for))
                names = [x.split(";")[0] for x in d.get("FILES", [])] if isinstance(d, dict) else []
                if os.path.basename(wait_for) in names:
                    break
                time.sleep(1.5)
        return self.delete(remote_zip)
