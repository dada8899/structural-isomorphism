# Private first-answer worker candidate

The worker is optional. Missing pins, a failed model preflight, or a missing worker socket keeps generic generation unavailable. This candidate does not select a model, enable a service, or change Main's database.

- Service identity: non-root `structural-answer` UID distinct from Main UID 981. Its primary group is `structural`, with no other supplementary groups. The service exposes `/run/structural-first-answer/worker.sock` (0660) to that group and checks the kernel peer UID is exactly 981. The inference socket is 0600. The gateway connects only to the verified inference child PID and UID.
- Service resources: one Python supervisor/gateway plus one llama-server child in the same systemd cgroup; four inference threads, one inference slot, context 4096, no context shift, no thinking, prompt cache disabled, no application output logs. The unit limits memory to 6 GiB without swap and restricts address families to Unix sockets.
- Filesystem: the service sees an isolated `/run`, `/var`, `/opt` and `/etc`. The unit binds only its own socket directory, its dedicated release tree, and public local account/loader metadata. It has no environment or credential file and must not use Main's Python or artifact paths via symlinks outside this tree. See [systemd execution environment directives](https://www.freedesktop.org/software/systemd/man/latest/systemd.exec).
- Recovery: the launcher waits for the verified child's local health response before listening to Main. An incomplete inference receipt closes both socket endpoints, retires the gateway, and terminates/reaps the child before returning failure. systemd supervises the entire cgroup and limits restart bursts. The old request is neither stored nor replayed by the worker.

The deployment tree is root-owned, with no group or other write access:

```text
/opt/structural-first-answer/
  release/                       reviewed code and launcher
    first-answer-artifact.sha256  SHA-256 of exact manifest bytes, then LF
  runtime/                       standalone Python 3.11+ with pinned dependencies
  artifacts/
    manifest.json                {"schema_version":1,"files":{"path":{"size":123,"sha256":"..."}}}
    bin/llama-server             fixed reviewed executable
    bin/lib*.so*                 only verified, physical runtime libraries
    model/model.gguf             one verified model
```

Manifest member names and sizes must match the actual tree. Bundled library aliases must be materialized as regular files during preparation; do not copy unverified symlinks into the release. The live worker reads and verifies the pin and every member before executing anything. The pin must be generated from the reviewed runtime and model; no default pin is included.

Before enabling: verify the actual unit in the target systemd version; test mount visibility, process UID/GID and actual Linux peer credentials; confirm Main can reach only the gateway; observe cgroup memory, CPU, and first answer latency with the selected immutable model; verify stop and unknown-result recovery, including no replay. A successful synthetic child test does not establish model quality or a deployed service.
