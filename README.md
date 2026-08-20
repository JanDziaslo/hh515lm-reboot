# hh515lm-reboot

Skrypt [`router_restart.py`](router_restart.py) restartuje router przez jego lokalne API WWW. Nawiązuje szyfrowaną sesję z panelem, loguje się danymi użytkownika i wysyła polecenie restartu.

Skrypt zweryfikowano na TCL 5G CPE HH515LM. Przy każdym uruchomieniu odczytuje parametry protokołu, ścieżkę API, nazwy nagłówków i techniczną nazwę użytkownika z pakietu JavaScript bieżącego firmware. Inne modele mogą używać niezgodnego API, a istotna zmiana struktury JavaScript firmware może wymagać aktualizacji parsera.

## Wymagania i instalacja

- Linux,
- Python 3,
- biblioteka `cryptography`.

Zainstaluj zależności z [`requirements.txt`](requirements.txt):

```sh
python3 -m pip install -r requirements.txt
```

## Użycie

> **Uwaga:** restart chwilowo rozłącza sieć i wszystkie urządzenia korzystające z routera.

Najpierw bezpiecznie sprawdź połączenie z API i szyfrowanie, bez logowania i restartu:

```sh
python3 router_restart.py --url http://ADRES_ROUTERA --probe
```

Restart interaktywny (hasło zostanie odczytane bez wyświetlania):

```sh
python3 router_restart.py --url http://ADRES_ROUTERA
```

Hasło nie jest zapisane w kodzie. Skrypt pobiera je z bezpiecznego promptu, a w pracy automatycznej ze zmiennej `TCL_ROUTER_PASSWORD`. Nie wpisuj hasła w poleceniu ani nie zapisuj go w repozytorium. Do ręcznego uruchomienia bez pozostawiania hasła w historii powłoki:

```sh
read -rsp 'Hasło routera: ' TCL_ROUTER_PASSWORD; echo
export TCL_ROUTER_PASSWORD
python3 router_restart.py --url http://ADRES_ROUTERA
unset TCL_ROUTER_PASSWORD
```

Adres można również przekazać przez zmienną środowiskową; techniczna nazwa użytkownika zostanie wykryta z firmware, a skrypt poprosi o hasło:

```sh
export TCL_ROUTER_URL=http://ADRES_ROUTERA
python3 router_restart.py
unset TCL_ROUTER_URL
```

Przykład automatyzacji z sekretem zamontowanym poza repozytorium (np. przez menedżer sekretów używany przez usługę lub kontener):

```sh
TCL_ROUTER_URL=http://ADRES_ROUTERA \
  TCL_ROUTER_PASSWORD="$(cat /run/secrets/tcl_router_password)" \
  python3 /opt/hh515lm-reboot/router_restart.py
```

Dostępne opcje:

- `--url` — wymagany adres routera; alternatywnie zmienna `TCL_ROUTER_URL`,
- `--user` — opcjonalne nadpisanie technicznej nazwy użytkownika wykrywanej z firmware; alternatywnie zmienna `TCL_ROUTER_USER`,
- `--timeout` — limit czasu w sekundach (domyślnie `10`),
- `--probe` — sprawdza dostępność API i szyfrowanie przez `GetDeviceSt`, bez logowania i restartu.

## Bezpieczeństwo

Przy każdym uruchomieniu skrypt pobiera stronę panelu routera, odnajduje wskazany przez nią pakiet `app*.js`, a następnie odczytuje z niego ścieżkę API, nazwy nagłówków protokołu, wartość nagłówka weryfikacyjnego i techniczną nazwę użytkownika oraz rekonstruuje klucz jej kodowania. Nie są to hasła użytkownika ani sekrety zapewniające dostęp do routera.

Zasoby są pobierane wyłącznie z tego samego hosta co panel routera i z limitami rozmiaru. Jeśli układ JavaScript firmware nie jest obsługiwany, skrypt kończy się błędem zamiast używać wartości zapasowych. Istotna zmiana struktury JavaScript firmware może wymagać aktualizacji parsera.

W celu restartu skrypt wywołuje wyłącznie `SetDeviceReboot`. Nie implementuje ani nie wywołuje `SetDeviceReset`: ta nieobecna w skrypcie operacja służy do przywracania ustawień fabrycznych, a nie do zwykłego restartu.

## Licencja

Projekt jest udostępniany na licencji MIT — zobacz plik [`LICENSE`](LICENSE).

## Zastrzeżenie

Projekt jest nieoficjalny i nie jest powiązany z TCL ani przez tę firmę wspierany.
