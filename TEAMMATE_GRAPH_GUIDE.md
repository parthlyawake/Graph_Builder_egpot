# Run the code graph on your own repository

This is a local, read-only demo. Source code stays on your computer; the browser talks to a Python server bound to `127.0.0.1`. Nothing is uploaded to the public Carmein demo.

## Start

From this repository's root, install dependencies once:

```powershell
python -m pip install -r requirements.txt
```

Then build and view a repository:

```powershell
python bench/team_demo.py --repo "C:\path\to\your\repo" --port 8767
```

Open `http://127.0.0.1:8767/`. The first build may take a while on a large codebase. Stop with `Ctrl+C`. To switch repositories, stop the server and rerun with a different `--repo` path.

If generated code makes the graph noisy, add a `.ckgignore` file in the target repo (one glob per line) or pass repeated `--exclude` flags, for example:

```powershell
python bench/team_demo.py --repo "C:\path\to\your\repo" --exclude "generated/*" --exclude "fixtures/*"
```

The graph shows all indexed nodes. Search for a file, interface, endpoint, or symbol; click it to inspect relationships; use the 1-hop or 2-hop view for a focused slice. Enter a bug/change description under “Retrieve affected code” to compare retrieval methods and inspect candidate files. These are candidates, not verified root causes.

## Interface and contract semantics

- TypeScript `interface` declarations are first-class `interface` nodes. Method/property signatures appear as child nodes joined by `DECLARES` edges.
- An explicit TypeScript `class ... implements Interface` or `interface ... extends Interface` creates an `IMPLEMENTS` or `EXTENDS` edge in the contract layer when the named interface resolves within the indexed repo. Structural compatibility is **not** guessed.
- A statically registered HTTP method/path creates an `http_endpoint` contract node. A handler points to it with `IMPLEMENTS`; a literal client call points to it with `CONSUMES`. The direct `HTTP_CALLS` edge is kept for dependency traversal.
- Python framework decorators, Express route registrations, Go `http.HandleFunc`, and Next-style `app/api/.../route.ts` exports are covered. Existing protobuf/gRPC service/RPC contract nodes remain supported.

Use the **Contracts** edge toggle in the viewer to see or hide these relationships. Search `POST /api/...` or an interface name to jump to the contract node.

## Important limits

Only statically visible route paths and literal client URLs are connected. Dynamic URL construction, aliases, framework rewrites, inferred TypeScript structural conformance, and undocumented runtime registrations remain unresolved. A missing edge means “not proven by this parser,” not “no dependency.” Rebuild after changing source files; the local viewer is a snapshot taken at startup.

The public Vercel demo is a prebuilt Carmein snapshot. The command above is the supported way to try another teammate's repository without deploying or sharing its source.
