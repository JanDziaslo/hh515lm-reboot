[Polska wersja](README.md)

# hh515lm-reboot

The [`router_restart.py`](router_restart.py) script restarts the router through its local web API. It establishes an encrypted session with the web interface, logs in with the user's credentials, and sends a restart command.

The script has been tested on the TCL 5G CPE HH515LM. On every run, it reads the protocol parameters, API path, header names, and technical username from the JavaScript bundle of the current firmware. Other models may use an incompatible API, and a significant change to the firmware's JavaScript structure may require the parser to be updated.

## Requirements and installation

- Linux,
- Python 3,
- the `cryptography` and `python-dotenv` libraries.

Install the dependencies from [`requirements.txt`](requirements.txt):

```sh
python3 -m pip install -r requirements.txt
```

## Usage

> **Note:** restarting temporarily disconnects the network and all devices using the router.

First, safely test the API connection and encryption without logging in or restarting:

```sh
python3 router_restart.py --url http://ROUTER_ADDRESS --probe
```

Interactive restart (the password will be read without being displayed):

```sh
python3 router_restart.py --url http://ROUTER_ADDRESS
```

Without the `--monitor` option, the script retains its existing behavior: it immediately performs a single manual router restart. In monitoring mode, the script process remains running, but a single `ping` command is executed only at the configured intervals:

```sh
python3 router_restart.py \
  --url http://ROUTER_ADDRESS \
  --monitor \
  --ping-target 8.8.8.8 \
  --check-interval 60 \
  --failure-threshold 3 \
  --ping-timeout 3 \
  --restart-cooldown 120
```

By default, the script checks `8.8.8.8` every `60` seconds, treats `3` consecutive failures as the restart threshold, waits up to `3` seconds for a single ping, and applies a `120`-second cooldown after a restart. A successful ping resets the failure counter. When the threshold is reached, the script logs in to the router and calls `SetDeviceReboot`, then waits for the cooldown before resuming checks. Do not set the failure threshold too low, because brief packet loss could then cause unnecessary restarts.

The password is not stored in the code. The script reads it from a secure prompt or, for automated operation, from the `TCL_ROUTER_PASSWORD` environment variable. Do not enter the password in the command or store it in the repository. To run the script manually without leaving the password in your shell history:

```sh
read -rsp 'Router password: ' TCL_ROUTER_PASSWORD; echo
export TCL_ROUTER_PASSWORD
python3 router_restart.py --url http://ROUTER_ADDRESS
unset TCL_ROUTER_PASSWORD
```

The address can also be provided through an environment variable; the technical username will be detected from the firmware, and the script will prompt for the password:

```sh
export TCL_ROUTER_URL=http://ROUTER_ADDRESS
python3 router_restart.py
unset TCL_ROUTER_URL
```

The script automatically loads variables from the `.env` file in the current directory. To get started, copy the template and fill in your own values:

```sh
cp .env.example .env
```

The [`.env.example`](.env.example) file contains example values only and does not contain real credentials. The `.env` file is ignored by Git; do not commit it or the router password. You can specify another file with the `--env-file PATH` option:

```sh
python3 router_restart.py --env-file /path/to/router.env
```

Variables already set in the environment take precedence over values from the `.env` file, while CLI arguments override their corresponding environment values.

Example automation with a secret mounted outside the repository (for example, by a secret manager used by a service or container):

```sh
TCL_ROUTER_URL=http://ROUTER_ADDRESS \
  TCL_ROUTER_PASSWORD="$(cat /run/secrets/tcl_router_password)" \
  python3 /opt/hh515lm-reboot/router_restart.py
```

Available options:

- `--env-file` — path to a `.env` file; by default, the script loads `.env` from the current directory,
- `--url` — required router address; alternatively, the `TCL_ROUTER_URL` environment variable,
- `--user` — optional override for the technical username detected from the firmware; alternatively, the `TCL_ROUTER_USER` environment variable,
- `--timeout` — timeout in seconds (default: `10`),
- `--restart` — performs a single restart; this is an explicit equivalent of the default manual mode,
- `--probe` — checks API availability and encryption using `GetDeviceSt`, without logging in or restarting,
- `--monitor` — keeps the process running and periodically checks the connection instead of restarting the router immediately,
- `--ping-target` — address checked with ping (default: `8.8.8.8`); alternatively, the `TCL_PING_TARGET` environment variable,
- `--check-interval` — interval between checks in seconds (default: `60`); alternatively, the `TCL_CHECK_INTERVAL` environment variable,
- `--failure-threshold` — number of consecutive failures before a restart (default: `3`); alternatively, the `TCL_FAILURE_THRESHOLD` environment variable,
- `--ping-timeout` — timeout for a single ping in seconds (default: `3`); alternatively, the `TCL_PING_TIMEOUT` environment variable,
- `--restart-cooldown` — cooldown after a restart in seconds (default: `120`); alternatively, the `TCL_RESTART_COOLDOWN` environment variable.

## Docker

Copy [`.env.example`](.env.example) to `.env` and fill in the router address, password, and monitoring settings:

```sh
cp .env.example .env
```

> **Note:** the `.env` file contains the router password. Do not commit it or pass it into the image; the [`.dockerignore`](.dockerignore) configuration excludes it from the build context.

Build the image and start continuous monitoring in the background:

```sh
docker compose up --build -d
```

View the service logs:

```sh
docker compose logs -f hh515lm-reboot
```

Stop and remove the service:

```sh
docker compose down
```

You can perform a single manual router restart in a separate temporary container:

```sh
docker compose run --rm hh515lm-reboot --restart
```

Safely probe the API and encryption without logging in or restarting:

```sh
docker compose run --rm hh515lm-reboot --probe
```

The [`compose.yaml`](compose.yaml) file uses `network_mode: host` so that the container has direct access to the router on the LAN. This setup is intended primarily for Docker Engine on Linux. Docker Desktop requires host networking support to be available and enabled.

The container runs as a non-root user, with a read-only filesystem and `no-new-privileges` enabled. All capabilities are dropped, and only `NET_RAW` is then added because it is required by the `ping` command used for monitoring.

## Security

On every run, the script downloads the router web interface page, finds the `app*.js` bundle referenced by it, and then reads the API path, protocol header names, verification header value, and technical username from that bundle, as well as reconstructing the username encoding key. These are not user passwords or secrets that provide access to the router.

Resources are downloaded only from the same host as the router web interface and are subject to size limits. If the firmware's JavaScript layout is not supported, the script exits with an error instead of using fallback values. A significant change to the firmware's JavaScript structure may require the parser to be updated.

To restart the router, the script calls only `SetDeviceReboot`. It neither implements nor calls `SetDeviceReset`: this operation, which is absent from the script, restores factory settings rather than performing a normal restart.

## License

The project is available under the MIT License — see the [`LICENSE`](LICENSE) file.

## Disclaimer

This is an unofficial project and is neither affiliated with nor supported by TCL.
