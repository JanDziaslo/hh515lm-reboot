#!/usr/bin/env python3
"""Bezpieczny restart routera TCL 5G CPE HH515LM przez jego API WWW."""

from __future__ import annotations

import argparse
import base64
import getpass
import hashlib
import hmac
import http.client
from html.parser import HTMLParser
import json
import os
import re
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


ALPHABET = string.ascii_letters + string.digits
MAX_HTML_SIZE = 512 * 1024
MAX_SCRIPT_SIZE = 10 * 1024 * 1024


class ScriptSourceParser(HTMLParser):
    """Zbiera adresy skryptów z dokumentu panelu routera."""

    def __init__(self) -> None:
        super().__init__()
        self.sources: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag.lower() != "script":
            return
        source = dict(attrs).get("src")
        if source:
            self.sources.append(source)


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


def encode_username(username: str, username_key: str) -> str:
    """Koduje nazwę użytkownika algorytmem panelu TCL."""
    result: list[str] = []
    for index, character in enumerate(username):
        key_code = ord(username_key[index % len(username_key)])
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
        self.panel_url = f"{self.origin}{parsed_url.path or '/'}"
        self.api_path = ""
        self.timeout = timeout
        self.session_id = ""
        self.tmp_key = ""
        self.hmac_key = ""
        self.token = ""
        self.verification_key = ""
        self.verification_header = ""
        self.token_header = ""
        self.username_key = ""
        self.default_username = ""

    def _get_text(self, url: str, max_size: int) -> str:
        parsed_url = urllib.parse.urlsplit(url)
        if (
            parsed_url.scheme != self.scheme
            or parsed_url.hostname != self.host
            or parsed_url.port != self.port
        ):
            raise RouterError("Panel wskazał skrypt spoza adresu routera.")

        connection_class = (
            http.client.HTTPSConnection
            if self.scheme == "https"
            else http.client.HTTPConnection
        )
        connection = connection_class(self.host, self.port, timeout=self.timeout)
        target = urllib.parse.urlunsplit(
            ("", "", parsed_url.path or "/", parsed_url.query, "")
        )
        try:
            connection.request(
                "GET",
                target,
                headers={"User-Agent": "Mozilla/5.0 TCL-HH515LM-Restart-Script/1.0"},
            )
            response = connection.getresponse()
            content = response.read(max_size + 1)
            if response.status >= 400:
                raise RouterError(f"Panel routera zwrócił HTTP {response.status}.")
            if len(content) > max_size:
                raise RouterError("Plik panelu routera przekracza bezpieczny limit rozmiaru.")
            return content.decode("utf-8")
        except (OSError, TimeoutError, http.client.HTTPException, UnicodeDecodeError) as error:
            raise RouterError(f"Nie udało się pobrać {url}: {error}") from error
        finally:
            connection.close()

    def discover_protocol_constants(self) -> None:
        """Odczytuje stałe protokołu z pakietu JavaScript bieżącego firmware."""
        panel_html = self._get_text(self.panel_url, MAX_HTML_SIZE)
        parser = ScriptSourceParser()
        parser.feed(panel_html)
        app_sources = [
            source
            for source in parser.sources
            if re.search(r"(?:^|/)app(?:\.[^/?]+)?\.js(?:\?|$)", source)
        ]
        if not app_sources:
            raise RouterError("Nie znaleziono głównego skryptu JavaScript panelu routera.")

        script_url = urllib.parse.urljoin(self.panel_url, app_sources[-1])
        script = self._get_text(script_url, MAX_SCRIPT_SIZE)

        verification_match = re.search(
            r'(["\'])(_TclRequestVerificationKey)\1\s*,\s*'
            r'[A-Za-z_$][\w$]*=(["\'])([A-Za-z0-9_]{32,256})\3',
            script,
        )
        token_header_match = re.search(
            r'(["\'])(_TclRequestVerificationToken)\1', script
        )
        username_match = re.search(
            r'([A-Za-z_$][\w$]*)=\[\[([\d,\-]+)\],\[([\d,\-]+)\]\]'
            r'.{0,1500}?encryptKey:[A-Za-z_$][\w$]*\(\1\[1\]\)',
            script,
        )
        api_path_match = re.search(
            r'\.basePath=(["\'])(/[^"\']+)\1', script
        )
        default_username_match = re.search(
            r'\.userName,[A-Za-z_$][\w$]*=void 0===[A-Za-z_$][\w$]*\?'
            r'(["\'])([^"\']+)\1',
            script,
        )
        if not all(
            (
                verification_match,
                token_header_match,
                username_match,
                api_path_match,
                default_username_match,
            )
        ):
            raise RouterError(
                "Nie udało się odczytać stałych protokołu z tego firmware. "
                "Układ panelu WWW może być nieobsługiwany."
            )

        encoded_username_key = [int(value) for value in username_match.group(3).split(",")]
        first = encoded_username_key[0]
        username_key = chr(first) + "".join(
            chr(first - value) for value in encoded_username_key[1:]
        )
        if not username_key.isalnum() or len(username_key) < 16:
            raise RouterError("Odczytany klucz kodowania użytkownika jest nieprawidłowy.")

        api_path = api_path_match.group(2)
        if not api_path.startswith("/") or "?" in api_path or "#" in api_path:
            raise RouterError("Odczytana ścieżka API routera jest nieprawidłowa.")

        self.api_path = api_path
        self.verification_header = verification_match.group(2)
        self.verification_key = verification_match.group(4)
        self.token_header = token_header_match.group(2)
        self.username_key = username_key
        self.default_username = default_username_match.group(2)

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
            self.verification_header: self.verification_key,
        }
        if self.session_id:
            headers["sessionid"] = self.session_id
        if self.token:
            headers[self.token_header] = self.token

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
        self.discover_protocol_constants()
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

    def login(self, username: str | None, password: str) -> None:
        device_state = self.call("GetDeviceSt")
        salt = device_state.get("Salt")
        if not salt:
            raise RouterError("Router nie zwrócił soli wymaganej do logowania.")

        password_hash = hashlib.pbkdf2_hmac(
            "sha512", password.encode(), str(salt).encode(), 1024, dklen=64
        ).hex()
        result = self.call(
            "Login",
            {
                "UserName": encode_username(
                    username or self.default_username, self.username_key
                ),
                "Password": password_hash,
            },
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
    parser.add_argument(
        "--url",
        default=os.environ.get("TCL_ROUTER_URL"),
        help="Adres routera (lub zmienna TCL_ROUTER_URL)",
    )
    parser.add_argument(
        "--user",
        default=os.environ.get("TCL_ROUTER_USER"),
        help="Techniczna nazwa użytkownika; zwykle wykrywana z firmware",
    )
    parser.add_argument("--timeout", type=float, default=10.0, help="Timeout w sekundach")
    parser.add_argument(
        "--probe",
        action="store_true",
        help="Tylko sprawdź API i szyfrowanie; bez logowania i restartu",
    )
    args = parser.parse_args()
    if not args.url:
        parser.error("podaj --url albo ustaw zmienną TCL_ROUTER_URL")
    return args


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
