# hh515lm-reboot

Skrypt [`router_restart.py`](router_restart.py) restartuje router przez jego lokalne API WWW. Nawiązuje szyfrowaną sesję z panelem, loguje się danymi użytkownika i wysyła polecenie restartu.

Skrypt zweryfikowano na TCL 5G CPE HH515LM. Przy każdym uruchomieniu odczytuje parametry protokołu, ścieżkę API, nazwy nagłówków i techniczną nazwę użytkownika z pakietu JavaScript bieżącego firmware. Inne modele mogą używać niezgodnego API, a istotna zmiana struktury JavaScript firmware może wymagać aktualizacji parsera.

## Wymagania i instalacja

- Linux,
- Python 3,
- biblioteki `cryptography` i `python-dotenv`.

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

Bez opcji `--monitor` skrypt zachowuje dotychczasowe działanie: od razu wykonuje pojedynczy, ręczny restart routera. W trybie monitorowania proces skryptu pozostaje uruchomiony, ale pojedyncza komenda `ping` jest wykonywana tylko w ustalonych odstępach:

```sh
python3 router_restart.py \
  --url http://ADRES_ROUTERA \
  --monitor \
  --ping-target 8.8.8.8 \
  --check-interval 60 \
  --failure-threshold 3 \
  --ping-timeout 3 \
  --restart-cooldown 120
```

Domyślnie skrypt odpytuje `8.8.8.8` co `60` sekund, uznaje `3` kolejne błędy za próg restartu, czeka na pojedynczy ping do `3` sekund i po restarcie stosuje cooldown `120` sekund. Udany ping zeruje licznik błędów. Po osiągnięciu progu skrypt loguje się do routera i wykonuje `SetDeviceReboot`, po czym przed wznowieniem kontroli odczekuje cooldown. Nie ustawiaj zbyt niskiego progu błędów, ponieważ krótkotrwała utrata pakietów może wtedy powodować niepotrzebne restarty.

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

Skrypt automatycznie ładuje zmienne z pliku `.env` w bieżącym katalogu. Aby rozpocząć, skopiuj szablon i uzupełnij własne wartości:

```sh
cp .env.example .env
```

Plik [`.env.example`](.env.example) zawiera wyłącznie przykładowe wartości i nie zawiera prawdziwych danych dostępowych. Plik `.env` jest ignorowany przez Git; nie commituj go ani hasła do routera. Inny plik można wskazać opcją `--env-file ŚCIEŻKA`:

```sh
python3 router_restart.py --env-file /ścieżka/do/router.env
```

Wartości zmiennych już ustawionych w środowisku mają pierwszeństwo przed wartościami z pliku `.env`, a argumenty CLI nadpisują odpowiadające im wartości ze środowiska.

Przykład automatyzacji z sekretem zamontowanym poza repozytorium (np. przez menedżer sekretów używany przez usługę lub kontener):

```sh
TCL_ROUTER_URL=http://ADRES_ROUTERA \
  TCL_ROUTER_PASSWORD="$(cat /run/secrets/tcl_router_password)" \
  python3 /opt/hh515lm-reboot/router_restart.py
```

Dostępne opcje:

- `--env-file` — ścieżka do pliku `.env`; domyślnie skrypt ładuje `.env` z bieżącego katalogu,
- `--url` — wymagany adres routera; alternatywnie zmienna `TCL_ROUTER_URL`,
- `--user` — opcjonalne nadpisanie technicznej nazwy użytkownika wykrywanej z firmware; alternatywnie zmienna `TCL_ROUTER_USER`,
- `--timeout` — limit czasu w sekundach (domyślnie `10`),
- `--restart` — wykonuje pojedynczy restart; jest jawnym odpowiednikiem domyślnego trybu ręcznego,
- `--probe` — sprawdza dostępność API i szyfrowanie przez `GetDeviceSt`, bez logowania i restartu,
- `--monitor` — utrzymuje proces i okresowo sprawdza połączenie zamiast od razu restartować router,
- `--ping-target` — adres sprawdzany przez ping (domyślnie `8.8.8.8`); alternatywnie zmienna `TCL_PING_TARGET`,
- `--check-interval` — odstęp między kontrolami w sekundach (domyślnie `60`); alternatywnie zmienna `TCL_CHECK_INTERVAL`,
- `--failure-threshold` — liczba kolejnych błędów przed restartem (domyślnie `3`); alternatywnie zmienna `TCL_FAILURE_THRESHOLD`,
- `--ping-timeout` — timeout pojedynczego pingu w sekundach (domyślnie `3`); alternatywnie zmienna `TCL_PING_TIMEOUT`,
- `--restart-cooldown` — cooldown po restarcie w sekundach (domyślnie `120`); alternatywnie zmienna `TCL_RESTART_COOLDOWN`.

## Docker

Skopiuj [`.env.example`](.env.example) do `.env` i uzupełnij wartości adresem routera, hasłem oraz ustawieniami monitorowania:

```sh
cp .env.example .env
```

> **Uwaga:** plik `.env` zawiera hasło do routera. Nie commituj go ani nie przekazuj do obrazu; konfiguracja [`.dockerignore`](.dockerignore) wyklucza go z kontekstu budowania.

Zbuduj obraz i uruchom ciągłe monitorowanie w tle:

```sh
docker compose up --build -d
```

Podgląd logów usługi:

```sh
docker compose logs -f hh515lm-reboot
```

Zatrzymanie i usunięcie usługi:

```sh
docker compose down
```

Ręczny, pojedynczy restart routera można wykonać osobnym, tymczasowym kontenerem:

```sh
docker compose run --rm hh515lm-reboot --restart
```

Bezpieczny probe API i szyfrowania, bez logowania i restartu:

```sh
docker compose run --rm hh515lm-reboot --probe
```

Plik [`compose.yaml`](compose.yaml) używa `network_mode: host`, aby kontener miał bezpośredni dostęp do routera w sieci LAN. Rozwiązanie jest przeznaczone przede wszystkim dla Docker Engine na Linuxie. W Docker Desktop wymaga obsługi i włączenia host networking.

Kontener działa jako użytkownik bez uprawnień roota, z systemem plików tylko do odczytu i ustawieniem `no-new-privileges`. Wszystkie capabilities są odbierane, a następnie dodawane jest wyłącznie `NET_RAW`, wymagane przez polecenie `ping` używane do monitorowania.

## Bezpieczeństwo

Przy każdym uruchomieniu skrypt pobiera stronę panelu routera, odnajduje wskazany przez nią pakiet `app*.js`, a następnie odczytuje z niego ścieżkę API, nazwy nagłówków protokołu, wartość nagłówka weryfikacyjnego i techniczną nazwę użytkownika oraz rekonstruuje klucz jej kodowania. Nie są to hasła użytkownika ani sekrety zapewniające dostęp do routera.

Zasoby są pobierane wyłącznie z tego samego hosta co panel routera i z limitami rozmiaru. Jeśli układ JavaScript firmware nie jest obsługiwany, skrypt kończy się błędem zamiast używać wartości zapasowych. Istotna zmiana struktury JavaScript firmware może wymagać aktualizacji parsera.

W celu restartu skrypt wywołuje wyłącznie `SetDeviceReboot`. Nie implementuje ani nie wywołuje `SetDeviceReset`: ta nieobecna w skrypcie operacja służy do przywracania ustawień fabrycznych, a nie do zwykłego restartu.

## Licencja

Projekt jest udostępniany na licencji MIT — zobacz plik [`LICENSE`](LICENSE).

## Zastrzeżenie

Projekt jest nieoficjalny i nie jest powiązany z TCL ani przez tę firmę wspierany.
