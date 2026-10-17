# Administrative API client

Use the released `forte_admin.client` module from the administrator source
package. It uses Python's standard library, verified TLS and the selected
versioned application routes. It does not define new analysis endpoints.

```python
from pathlib import Path
from forte_admin.client import APIClient, load_profile

profile = load_profile(Path("/private/connections/customer.json"))
client = APIClient(
    profile["endpoint"],
    Path(profile["key_file"]),
    api_version=profile["api_version"],
    gateway_credentials_file=profile.get("gateway_credentials_file"),
)
print("Processing destination:", profile["endpoint"])
accepted = client.upload(Path("/authorized/development/input.mov"))
result = client.wait(accepted["job_id"], timeout=300)
# Keep the complete result local. A done job can still have insufficient evidence.
assert result["status"] in {"done", "failed"}
```

Add the extracted archive's `tools/forte-admin` directory to `PYTHONPATH` when
importing the module directly. `connect` creates an owner-only connection profile
and binds both key and optional gateway credential files to the selected origin.
The optional gateway file is `username:password`, owner-only and outside Git:

```sh
forte-admin connect --endpoint https://review.example.internal:8443 \
  --key-file /private/credentials/service.key \
  --gateway-credentials-file /private/credentials/admin-gateway.txt \
  --profile /private/connections/admin.json
```

Credentials are read from files, never printed in output, encoded into URLs or
forwarded through redirects. A key file cannot be silently rebound to a different
origin. An expired/unavailable local endpoint does not cause hosted submission.
Private/internal certificate authorities are configured through the host trust
store or Python's `SSL_CERT_FILE`/`SSL_CERT_DIR`; verification is never disabled.

The full multipart body, including its envelope, must fit 256 MiB. Uploads use
field `file`, require MOV, and stream fixed-size chunks. The server still probes
actual media. `processing` is polled; `done` and `failed` remain distinct.
Unknown execution states are protocol errors. Additive result fields and unknown
assessment vocabulary are preserved unchanged in local saved output, with no
conversion to a clean verdict. POST requests are never retried automatically;
a timeout may mean the job was admitted at the same destination.

Transport tests use clearly labeled synthetic endpoints. They do not provide a
production fallback and are not detection or legal accuracy measurements.
