from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import ssl
import time
from pathlib import Path
from urllib.parse import urlsplit

import requests
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager


def _md5(value: str | bytes) -> str:
    data = value.encode() if isinstance(value, str) else value
    return hashlib.md5(data).hexdigest()


def _rewrap_pem(pem: str) -> str:
    body = re.sub(
        r"\s+",
        "",
        pem.replace("-----BEGIN PUBLIC KEY-----", "").replace(
            "-----END PUBLIC KEY-----", ""
        ),
    )
    lines = "\n".join(body[index : index + 64] for index in range(0, len(body), 64))
    return f"-----BEGIN PUBLIC KEY-----\n{lines}\n-----END PUBLIC KEY-----\n"


def _rsa(public_key: str, value: str) -> str:
    key = serialization.load_pem_public_key(_rewrap_pem(public_key).encode())
    encrypted = key.encrypt(value.encode(), padding.PKCS1v15())
    return base64.b64encode(encrypted).decode()


def _normalize_fingerprint(value: str) -> str:
    normalized = re.sub(r"[^0-9a-fA-F]", "", value).lower()
    if len(normalized) != 64:
        raise ValueError("fingerprint must contain exactly 64 SHA-256 hex characters")
    return normalized


class _FingerprintAdapter(HTTPAdapter):
    def __init__(self, fingerprint: str):
        self.fingerprint = fingerprint
        super().__init__()

    def init_poolmanager(self, connections, maxsize, block=False, **kwargs):
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        self.poolmanager = PoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            assert_fingerprint=self.fingerprint,
            ssl_context=context,
            **kwargs,
        )


class AaPanel:
    def __init__(
        self,
        base_url: str,
        entrance: str,
        credentials: tuple[str, str],
        fingerprint: str,
    ):
        username, password = credentials
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("aaPanel base URL must be an https URL with a hostname")
        if not username or not password:
            raise ValueError("aaPanel username and password are required")

        self.base = f"https://{parsed.netloc}".rstrip("/")
        self.entrance = "/" + entrance.strip("/")
        if self.entrance == "/":
            raise ValueError("the full aaPanel security entrance is required")
        self.host = parsed.hostname
        self.port = parsed.port or 443
        self._user = username
        self._pwd = password
        self.fingerprint = _normalize_fingerprint(fingerprint)
        self.session = self._new_session()
        self.apsess: str | None = None
        self.http_token: str | None = None

    @staticmethod
    def _split_login_url(url: str) -> tuple[str, str]:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("profile URL must be a full https aaPanel login URL")
        entrance = parsed.path.strip("/")
        if not entrance:
            raise ValueError("profile URL must include the aaPanel security entrance")
        return f"https://{parsed.netloc}", entrance

    @staticmethod
    def fetch_fingerprint(url: str, timeout: float = 10) -> str:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("URL must be https and include a hostname")
        pem = ssl.get_server_certificate(
            (parsed.hostname, parsed.port or 443), timeout=timeout
        )
        der = ssl.PEM_cert_to_DER_cert(pem)
        return hashlib.sha256(der).hexdigest()

    @classmethod
    def from_env(cls, prefix: str = "AAPANEL") -> "AaPanel":
        url = os.environ[f"{prefix}_URL"]
        base, entrance = cls._split_login_url(url)
        return cls(
            base,
            entrance,
            (os.environ[f"{prefix}_USER"], os.environ[f"{prefix}_PWD"]),
            os.environ[f"{prefix}_FINGERPRINT"],
        )

    @staticmethod
    def _password_from_env(env_name: object) -> str:
        if not isinstance(env_name, str) or not env_name:
            raise ValueError("password_env must name a non-empty environment variable")
        try:
            return os.environ[env_name]
        except KeyError as error:
            raise RuntimeError(f"required password environment variable is unset: {env_name}") from error

    @staticmethod
    def _password_from_file(file_name: str) -> str:
        password_path = Path(file_name).expanduser()
        if not password_path.is_absolute():
            raise ValueError("password_file must be an absolute path")
        if password_path.is_symlink() or not password_path.is_file():
            raise PermissionError("password_file must be a regular non-symlink file")
        mode = password_path.stat().st_mode & 0o777
        if mode & 0o077:
            raise PermissionError("password_file must have mode 0600")
        password = password_path.read_text(encoding="utf-8")
        if not password:
            raise ValueError("password_file is empty")
        return password

    @classmethod
    def _profile_password(cls, profile: dict, profile_path: Path) -> str:
        if "password_env" in profile:
            return cls._password_from_env(profile["password_env"])
        if "password_file" in profile:
            return cls._password_from_file(profile["password_file"])
        if "pwd" in profile:
            mode = profile_path.stat().st_mode & 0o777
            if mode & 0o077:
                raise PermissionError("profile containing pwd must have mode 0600")
            return profile["pwd"]
        raise ValueError("profile requires password_env, password_file, or pwd")

    @classmethod
    def from_config(cls, path: str | os.PathLike[str]) -> "AaPanel":
        profile_path = Path(path).expanduser()
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        base, entrance = cls._split_login_url(profile["url"])

        password = cls._profile_password(profile, profile_path)

        return cls(
            base,
            entrance,
            (profile["user"], password),
            profile["fingerprint"],
        )

    def _new_session(self) -> requests.Session:
        session = requests.Session()
        session.mount("https://", _FingerprintAdapter(self.fingerprint))
        session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )
        return session

    @staticmethod
    def _div_data(html: str, class_name: str) -> str | None:
        match = re.search(
            rf'class="{re.escape(class_name)}"[^>]*\bdata="([^"]*)"', html
        )
        return match.group(1) if match else None

    def login(self) -> "AaPanel":
        html = ""
        for _ in range(8):
            response = self.session.get(self.base + self.entrance, timeout=20)
            response.raise_for_status()
            html = response.text
            if "public_key" in html:
                break
            time.sleep(1.5)

        last_token = self._div_data(html, "last_token")
        apsess_token = self._div_data(html, "apsess_token")
        public_key = self._div_data(html, "public_key")
        if not last_token or not public_key:
            raise RuntimeError("security entrance did not return aaPanel login tokens")

        payload = {
            "username": _rsa(public_key, _md5(_md5(self._user + last_token))),
            "password": _rsa(public_key, _md5(_md5(self._pwd) + "_bt.cn")),
            "code": "",
        }
        response = self.session.post(
            self.base + "/login",
            data=payload,
            timeout=20,
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        response.raise_for_status()
        result = response.json()
        if not result.get("status"):
            raise RuntimeError(f"aaPanel login failed: {result.get('msg')}")

        self.apsess = "/apsess_" + apsess_token if apsess_token else ""
        landing = self.session.get(self.base + self.apsess + "/", timeout=20)
        landing.raise_for_status()
        token_match = re.search(
            r'request_token[^>]*token\s*[:=]\s*["\']?([A-Za-z0-9]+)',
            landing.text,
        )
        self.http_token = (
            token_match.group(1)
            if token_match
            else self._div_data(landing.text, "request_token")
        )
        return self

    def _api(self, action: str, data=None, files=None):
        if self.apsess is None:
            raise RuntimeError("call login() before using the aaPanel API")
        headers = {"X-Requested-With": "XMLHttpRequest"}
        if self.http_token:
            headers["X-Http-Token"] = self.http_token
        response = self.session.post(
            self.base + self.apsess + "/files?action=" + action,
            data=data or {},
            files=files,
            headers=headers,
            timeout=120,
        )
        response.raise_for_status()
        try:
            return response.json()
        except ValueError as error:
            raise RuntimeError(
                f"aaPanel action {action} returned non-JSON: {response.text[:200]}"
            ) from error

    def listdir(self, path: str):
        return self._api("GetDir", {"path": path})

    def get_file(self, path: str):
        return self._api("GetFileBody", {"path": path})

    def save_file(self, path: str, text: str):
        return self._api(
            "SaveFileBody", {"path": path, "data": text, "encoding": "utf-8"}
        )

    def delete(self, path: str):
        return self._api("DeleteFile", {"path": path})

    def unzip(self, source_file: str, destination: str):
        return self._api(
            "UnZip",
            {
                "sfile": source_file,
                "dfile": destination,
                "type": "zip",
                "coding": "UTF-8",
                "password": "",
            },
        )

    def upload(self, remote_dir: str, local_path: str, chunk=2 * 1024 * 1024):
        name = os.path.basename(local_path)
        size = os.path.getsize(local_path)
        if size == 0:
            raise ValueError("refusing an empty upload")
        last_result = None
        with open(local_path, "rb") as source:
            start = 0
            while start < size:
                content = source.read(chunk)
                last_result = self._api(
                    "upload",
                    data={
                        "f_path": remote_dir,
                        "f_name": name,
                        "f_size": str(size),
                        "f_start": str(start),
                    },
                    files={"blob": (name, content, "application/octet-stream")},
                )
                if isinstance(last_result, dict) and last_result.get("status") is False:
                    raise RuntimeError(f"aaPanel upload failed: {last_result}")
                start += len(content)
        return last_result

    def upload_unzip(
        self,
        remote_dir: str,
        local_zip: str,
        wait_for: str | None = None,
        timeout: float = 40,
    ):
        upload_result = self.upload(remote_dir, local_zip)
        remote_zip = remote_dir.rstrip("/") + "/" + os.path.basename(local_zip)
        unzip_result = self.unzip(remote_zip, remote_dir)
        if isinstance(unzip_result, dict) and unzip_result.get("status") is False:
            raise RuntimeError(f"aaPanel unzip failed: {unzip_result}")

        if wait_for:
            deadline = time.time() + timeout
            while time.time() < deadline:
                directory = remote_dir + "/" + os.path.dirname(wait_for)
                listing = self.listdir(directory)
                names = [
                    item.split(";")[0]
                    for item in listing.get("FILES", [])
                ] if isinstance(listing, dict) else []
                if os.path.basename(wait_for) in names:
                    break
                time.sleep(1.5)
            else:
                raise TimeoutError(f"uploaded archive did not produce expected path: {wait_for}")

        delete_result = self.delete(remote_zip)
        return {
            "upload": upload_result,
            "unzip": unzip_result,
            "delete_archive": delete_result,
        }
