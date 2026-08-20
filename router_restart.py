#!/usr/bin/env python3
"""Bezpieczny restart routera TCL 5G CPE HH515LM przez jego API WWW."""

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import hmac
import http.client
import json
import os
import secrets
import string
import sys
import time
import urllib.parse
from typing import Any

try:
    from cryptography.hazmat.primitives import hashes, padding, serialization
    from cryptography.hazmat.primitives.asymmetric import padding as asymmetric_padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
except ImportError as error:
    raise SystemExit(
        "Brakuje biblioteki 'cryptography'. Uruchom: "
        "python3 -m pip install -r requirements.txt"
    ) from error


API_PATH = "/jrd/webapi"
VERIFICATION_KEY = "KSDHSDFOGQ5WERYTUIQWERTYUISDFG1HJZXCVCXBN2GDSMNDHKVKFsVBNf"
USERNAME_KEY = "e5dl12XYVggihggafXWf0f2YSf2Xngd1"
ALPHABET = string.ascii_letters + string.digits


class RouterError(RuntimeError):
    """Błąd komunikacji z API routera lub odpowiedź odrzucona przez router."""


def compact_json(value: Any) -> str:
    """Koduje JSON tak samo jak JSON.stringify używany przez panel routera."""
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def encrypt_payload(plaintext: str, password: str) -> str:
    """Odtwarza format OpenSSL Salted__ używany przez firmware TCL."""
    salt = os.urandom(8)
    derived = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=48, salt=salt, iterations=50
    ).derive(password.encode())
    key, iv = derived[:32], derived[32:]

    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext.encode()) + padder.finalize()
    encryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).encryptor()
    ciphertext = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(b"Salted__" + salt + ciphertext).decode()


def decrypt_payload(encoded: str, password: str) -> str:
    raw = base64.b64decode(encoded, validate=True)
    if not raw.startswith(b"Salted__") or len(raw) < 32:
        raise RouterError("Router zwrócił odpowiedź w nieznanym formacie szyfrowania.")

    salt, ciphertext = raw[8:16], raw[16:]
    derived = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=48, salt=salt, iterations=50
    ).derive(password.encode())
    key, iv = derived[:32], derived[32:]
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    padded = decryptor.update(ciphertext) + decryptor.finalize()
    unpadder = padding.PKCS7(128).unpadder()
    return (unpadder.update(padded) + unpadder.finalize()).decode()


def encode_username(username: str) -> str:
    """Koduje nazwę użytkownika algorytmem panelu TCL."""
    result: list[str] = []
    for index, character in enumerate(username):
        key_code = ord(USERNAME_KEY[index % len(USERNAME_KEY)])
        char_code = ord(character)
        result.append(chr((key_code & 0xF0) | ((char_code & 0x0F) ^ (key_code & 0x0F))))
        result.append(chr((key_code & 0xF0) | ((char_code >> 4) ^ (key_code & 0x0F))))
    return "".join(result)


class TclRouterApi:
    def __init__(self, base_url: str, timeout: float) -> None:
        parsed_url = urllib.parse.urlsplit(base_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
            raise RouterError("Adres routera musi zaczynać się od http:// lub https://.")
        self.scheme = parsed_url.scheme
        self.host = parsed_url.hostname
        self.port = parsed_url.port
        self.origin = f"{parsed_url.scheme}://{parsed_url.netloc}"
        self.api_path = parsed_url.path.rstrip("/") + API_PATH
        self.timeout = timeout
        self.session_id = ""
        self.tmp_key = ""
        self.hmac_key = ""
        self.token = ""

    def _post_raw(
        self, method: str, params: Any, *, encrypted: bool, hmac_value: str = ""
    ) -> Any:
        now = int(time.time() * 1000)
        body = {
            "_": now,
            "id": f"{secrets.randbelow(1000) / 10:.1f}",
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "hmac": hmac_value,
        }
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json",
            "Origin": self.origin,
            "Referer": f"{self.origin}/",
            "User-Agent": "Mozilla/5.0 TCL-HH515LM-Restart-Script/1.0",
            "_TclRequestVerificationKey": VERIFICATION_KEY,
        }
        if self.session_id:
            headers["sessionid"] = self.session_id
        if self.token:
            headers["_TclRequestVerificationToken"] = self.token

        connection_class = (
            http.client.HTTPSConnection
            if self.scheme == "https"
            else http.client.HTTPConnection
        )
        connection = connection_class(self.host, self.port, timeout=self.timeout)
        try:
            connection.request(
                "POST",
                f"{self.api_path}?name={urllib.parse.quote(method)}",
                body=compact_json(body).encode(),
                headers=headers,
            )
            response = connection.getresponse()
            response_body = response.read()
            if response.status >= 400:
                raise RouterError(f"HTTP {response.status} podczas wykonywania {method}.")
            payload = json.loads(response_body.decode())
        except (OSError, TimeoutError, http.client.HTTPException, json.JSONDecodeError) as error:
            raise RouterError(f"Nie udało się wykonać {method}: {error}") from error
        finally:
            connection.close()

        if "error" in payload:
            details = payload["error"]
            raise RouterError(
                f"Router odrzucił {method}: kod={details.get('code')}, "
                f"komunikat={details.get('message', 'brak')}"
            )
        if "result" not in payload:
            raise RouterError(f"Niepełna odpowiedź routera dla {method}.")

        result = payload["result"]
        if encrypted:
            try:
                return json.loads(decrypt_payload(result, self.tmp_key))
            except (ValueError, TypeError, json.JSONDecodeError) as error:
                raise RouterError(f"Nie udało się odszyfrować odpowiedzi {method}.") from error
        return result

    def establish_session(self) -> None:
        public_key_result = self._post_raw("GetPubKey", {}, encrypted=False)
        public_key_pem = public_key_result.get("publicKey", "").replace("\\n", "\n")
        if not public_key_pem:
            raise RouterError("Router nie zwrócił klucza publicznego.")

        self.tmp_key = "".join(secrets.choice(ALPHABET) for _ in range(128))
        self.hmac_key = "".join(secrets.choice(ALPHABET) for _ in range(32))
        key_data = compact_json({"TmpKey": self.tmp_key, "HmacKey": self.hmac_key})
        try:
            public_key = serialization.load_pem_public_key(public_key_pem.encode())
            encrypted_keys = public_key.encrypt(
                key_data.encode(), asymmetric_padding.PKCS1v15()
            )
        except (TypeError, ValueError) as error:
            raise RouterError("Nie udało się przygotować bezpiecznej sesji.") from error

        self.session_id = "webui"
        session_result = self._post_raw(
            "SetConfidentKey",
            base64.b64encode(encrypted_keys).decode(),
            encrypted=True,
        )
        self.session_id = session_result.get("SessionId", "")
        if not self.session_id:
            raise RouterError("Router nie utworzył sesji API.")

    def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        if not self.session_id or not self.tmp_key or not self.hmac_key:
            raise RouterError("Sesja API nie została zainicjalizowana.")

        data = dict(params or {})
        data["_"] = int(time.time() * 1000)
        plaintext = compact_json(data)
        signature = hmac.new(
            self.hmac_key.encode(), plaintext.encode(), hashlib.sha256
        ).hexdigest()
        encrypted = encrypt_payload(plaintext, self.tmp_key)
        return self._post_raw(method, encrypted, encrypted=True, hmac_value=signature)

    def login(self, username: str, password: str) -> None:
        device_state = self.call("GetDeviceSt")
        salt = device_state.get("Salt")
        if not salt:
            raise RouterError("Router nie zwrócił soli wymaganej do logowania.")

        password_hash = hashlib.pbkdf2_hmac(
            "sha512", password.encode(), str(salt).encode(), 1024, dklen=64
        ).hex()
        result = self.call(
            "Login",
            {"UserName": encode_username(username), "Password": password_hash},
        )
        self.token = result.get("token", "")
        if not self.token:
            raise RouterError("Logowanie nie zwróciło tokenu. Sprawdź hasło.")

    def restart(self) -> None:
        # Celowo nie ma tu obsługi SetDeviceReset (przywracania ustawień fabrycznych).
        self.call("SetDeviceReboot", {})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Restart routera TCL 5G CPE HH515LM przez lokalne API."
    )
    parser.add_argument("--url", default="http://192.168.1.1", help="Adres routera")
    parser.add_argument("--user", default="admin", help="Użytkownik panelu")
    parser.add_argument("--timeout", type=float, default=10.0, help="Timeout w sekundach")
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Tylko sprawdź API i szyfrowanie; bez logowania i restartu",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api = TclRouterApi(args.url, args.timeout)
    try:
        api.establish_session()
        if args.probe:
            api.call("GetDeviceSt")
            print("API routera odpowiada poprawnie. Nie wykonano restartu.")
            return 0

        password = os.environ.get("TCL_ROUTER_PASSWORD")
        if not password:
            if not sys.stdin.isatty():
                raise RouterError(
                    "Ustaw zmienną środowiskową TCL_ROUTER_PASSWORD dla pracy automatycznej."
                )
            password = getpass.getpass("Hasło panelu routera: ")

        api.login(args.user, password)
        api.restart()
        print("Polecenie restartu zostało przyjęte przez router.")
        return 0
    except RouterError as error:
        print(f"Błąd: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
