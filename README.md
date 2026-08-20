# hh515lm-reboot

Skrypt [`router_restart.py`](router_restart.py) restartuje router przez jego lokalne API WWW. Nawiązuje szyfrowaną sesję z panelem, loguje się danymi użytkownika i wysyła polecenie restartu.

Skrypt zweryfikowano na TCL 5G CPE HH515LM. Inne modele lub wersje firmware mogą używać niezgodnego API i nie działać.

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
python3 router_restart.py --probe
```

Restart interaktywny (hasło zostanie odczytane bez wyświetlania):

```sh
python3 router_restart.py
```

Hasło nie jest zapisane w kodzie. Skrypt pobiera je z bezpiecznego promptu, a w pracy automatycznej ze zmiennej `TCL_ROUTER_PASSWORD`. Nie wpisuj hasła w poleceniu ani nie zapisuj go w repozytorium. Do ręcznego uruchomienia bez pozostawiania hasła w historii powłoki:

```sh
read -rsp 'Hasło routera: ' TCL_ROUTER_PASSWORD; echo
export TCL_ROUTER_PASSWORD
python3 router_restart.py
unset TCL_ROUTER_PASSWORD
```

Przykład automatyzacji z sekretem zamontowanym poza repozytorium (np. przez menedżer sekretów używany przez usługę lub kontener):

```sh
TCL_ROUTER_PASSWORD="$(cat /run/secrets/tcl_router_password)" \
  python3 /opt/hh515lm-reboot/router_restart.py
```

Dostępne opcje:

- `--url` — adres routera (domyślnie `http://192.168.1.1`),
- `--user` — użytkownik panelu (domyślnie `admin`),
- `--timeout` — limit czasu w sekundach (domyślnie `10`),
- `--probe` — sprawdza dostępność API i szyfrowanie przez `GetDeviceSt`, bez logowania i restartu.

## Bezpieczeństwo

Stałe `VERIFICATION_KEY` i `USERNAME_KEY` pochodzą z publicznie dostępnych zasobów panelu WWW firmware i służą do odtworzenia jego protokołu. Nie są hasłem użytkownika ani sekretem zapewniającym dostęp do routera.

W celu restartu skrypt wywołuje wyłącznie `SetDeviceReboot`. Nie implementuje ani nie wywołuje `SetDeviceReset`: ta nieobecna w skrypcie operacja służy do przywracania ustawień fabrycznych, a nie do zwykłego restartu.

## Licencja

Projekt jest udostępniany na licencji MIT — zobacz plik [`LICENSE`](LICENSE).

## Zastrzeżenie

Projekt jest nieoficjalny i nie jest powiązany z TCL ani przez tę firmę wspierany.
