# Browser access to an offline container

Keep the application/model container on `--network none`. On its Docker host run:

```sh
python3 scripts/offline_api_bridge.py <existing-application-container>
```

This stdlib bridge binds only `127.0.0.1:18000`. Each connection uses `docker exec
-i` to relay raw bytes to the fixed application destination `127.0.0.1:8000`
inside that existing container. It does not expose model port 8001, change Docker
networking, parse HTTP, rewrite headers, buffer entire bodies, or log credentials
or case content. Authentication and upload limits remain enforced by the API.
Sixteen simultaneous connections and a 120-second idle timeout bound the relay.

From the reviewer's authorized local machine, use the established SSH connection
and dedicated trust/key settings, adding:

```sh
ssh -N -L 127.0.0.1:8040:127.0.0.1:18000 <existing-authorized-host-alias>
```

The human can open `http://127.0.0.1:8040`. The application must already serve its
static UI and API on container port 8000; the bridge performs no deployment or
authentication changes. Enter the service key in the page, never a URL. Stop the
host bridge and tunnel after review. Private footage must not be inspected by
remote screenshot/browser tools. Synthetic relay checks establish transport
mechanics only; real offline-host execution must be recorded separately.
