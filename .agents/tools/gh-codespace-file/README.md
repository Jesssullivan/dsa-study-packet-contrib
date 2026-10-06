# Local file-only Codespaces SSH/logs/rebuild adapter

Operator-only code; do not publish it in either Woodshed product repository.
This is a narrow local executable built inside the official `cli/cli` source
tree. Its SSH, logs, rebuild, platform RPC, port forwarding, and tunnel implementation remain
upstream code. The adapter changes the API transport and exposed command surface.

Pinned source: `cli/cli` tag `v2.101.0`, commit
`0cf1092493af067646fc5f3db9421c6a6ec9c938`. Go follows the upstream `go.mod`
(`go1.27.1` toolchain). The upstream tag is a reproducibility pin, not evidence
that this local adapter has been endorsed by GitHub.

## Why an adapter is needed

The [supported gh environment](https://cli.github.com/manual/gh_help_environment)
has environment and stored-token authentication, with no `GH_TOKEN_FILE`
interface. [`gh auth login --with-token`](https://cli.github.com/manual/gh_auth_login)
reads standard input and then stores the credential, which does not satisfy the
documented file-only custody rule. The source's `SetActiveToken` is marked for
testing only. No auth/config/keyring commands are exposed by this adapter.

## Reproduce locally

Run the included bootstrap from this personal overlay. It anonymously fetches
the exact official CLI commit into a new output directory, copies only the
adapter, runs synthetic and race tests, and builds a separate executable. It
never opens an operator carrier or invokes a hosted command. Requirements: Git,
Go (upstream toolchain `go1.27.1`), a C compiler for race tests, and Python 3.
The output directory must not already exist.

```sh
.agents/tools/gh-codespace-file/bootstrap.sh /absolute/path/to/new-build-directory
```

Inside the resulting pinned official source tree, equivalent commands are:

```sh
go test ./cmd/gh-codespace-file
go build -trimpath -o ./bin/gh-codespace-file-rebuild ./cmd/gh-codespace-file
./bin/gh-codespace-file-rebuild --help
```

An authorized operator may run this form. The argument is a file **path**, never
its credential value. Substitute the actual explicitly chosen owned Codespace
name, and supply a normal SSH identity with `-i` if wanted:

```sh
./bin/gh-codespace-file-rebuild \
  --token-file /absolute/path/to/admitted-file-only-carrier \
  ssh --codespace CHOSEN-CODESPACE-NAME -- \
  -i /absolute/path/to/own-ssh-key -o IdentitiesOnly=yes -T bash -s
```

Identity options are OpenSSH arguments after `--`; there is no gh `--identity`
flag. For `bash -s`, send the desired commands on standard input. To run one
command directly, replace `bash -s` with that command.

Read the selected running Codespace's creation logs using the official upstream
log reader (`--follow` is optional):

```sh
./bin/gh-codespace-file-rebuild \
  --token-file /absolute/path/to/admitted-file-only-carrier \
  logs --codespace CHOSEN-CODESPACE-NAME
```

The logs command permits only GET API requests and refuses to start a stopped
Codespace. Upstream reads `/workspaces/.codespaces/.persistedshare/creation.log`
over its tunnel/RPC/SSH implementation and may start the internal SSH server.
It does not expose SSH identity arguments; ordinary SSH config/agent identity
selection applies. When an explicit identity is required, use the SSH form
above with `cat /workspaces/.codespaces/.persistedshare/creation.log` as the
remote command instead of `bash -s`.

Recreate the explicitly recorded owned Codespace through upstream's platform
tunnel/RPC implementation. The expected ID and owner must come from the owned
resource receipt; the returned name, ID, and owner are checked before upstream
can use connection metadata. Substitute the actual resource's numeric ID:

```sh
./bin/gh-codespace-file-rebuild \
  --token-file /absolute/path/to/admitted-file-only-carrier \
  rebuild --codespace CHOSEN-CODESPACE-NAME \
  --expected-codespace-id RECORDED-NUMERIC-ID --expected-owner Jesssullivan
```

An optional upstream `--full` also removes cached Docker images. Rebuild uses the
working directory's devcontainer and preserves workspace code and current
changes. It calls upstream `RebuildContainer` over the selected tunnel; the
adapter exposes no REST rebuild endpoint. It needs no SSH identity argument.

The operator's prior SSH receipt must verify the real workspace HEAD, source
fork, and desired owned session before rebuilding. The Codespaces API exposes a
branch ref, which does not prove the current worktree commit. The helper's ID/
name/owner binding therefore complements that receipt. A successful RPC response
means rebuilding was requested; post-recreation lifecycle, exact source, and
product smoke must be verified separately by the owned environment operator.

Do not invoke `cat`, token printing, shell substitution, `gh auth login`, or an
environment export to provide the carrier. Build on the target Unix platform (or cross-compile for it) before using its
operator-selected runtime pointer. Carrier registration and custody remain
outside this public personal overlay.

## Boundaries

- Only upstream `ssh`, `logs`, and `rebuild` remain. An explicit Codespace name
  is required. Rebuild additionally requires an exact owned ID and owner and
  refuses other-session metadata before upstream can use its connection.
- The runtime pointer may be a sops-nix symlink. Its resolved descriptor must be
  an owned regular file, single link, and mode `0400` or `0600`. FIFO and unsafe
  modes are rejected before reading. Contents are size/format checked without
  putting them in an error message.
- Authentication exists in this process's memory and cloned request headers.
  It is sent only over HTTPS to exact `api.github.com` for `GET /user`,
  `GET /user/codespaces/<selected-name>`, and
  `POST /user/codespaces/<selected-name>/start` for `ssh`/`rebuild` only. Rebuild
  permits startup only after its exact owned resource identity was verified.
  The `logs` command has no POST permission. GitHub API redirects are refused.
- The external tunnel HTTP client has no carrier transport or credential. It
  uses the short-lived tunnel credentials returned by upstream's Codespaces API.
- Ambient GitHub credentials, host/API endpoint overrides, and HTTP debug are
  removed from this process before any OpenSSH child. Stored gh auth is never
  loaded. SSH debug, debug files, OpenSSH configuration export, and stdio proxy
  mode are disabled by the adapter.
- Upstream SSH may create its ordinary SSH key pair under `~/.ssh` when no
  identity exists, authorize the public key remotely, and start a stopped selected
  Codespace. The file-only GitHub credential is not passed to those children.
- This is ordinary Go process memory; it makes no locked-memory or resistance to
  debugging/core-dump guarantee. No credential is intentionally persisted.

The [official SSH command](https://cli.github.com/manual/gh_codespace_ssh) requires
an SSH server installed inside the Codespace. This helper does not install it.
Synthetic local tests cannot establish hosted Codespaces acceptance. A successful
real command, source SHA/fork identity checks, product smoke, and cleanup must be
recorded separately by the authorized operator.

Source references: [authentication lookup](https://github.com/cli/cli/blob/v2.101.0/internal/config/config.go),
[Codespaces API separation](https://github.com/cli/cli/blob/v2.101.0/internal/codespaces/api/api.go),
[SSH command](https://github.com/cli/cli/blob/v2.101.0/pkg/cmd/codespace/ssh.go).
The log reader is [upstream logs](https://github.com/cli/cli/blob/v2.101.0/pkg/cmd/codespace/logs.go),
documented by [gh codespace logs](https://cli.github.com/manual/gh_codespace_logs).
Rebuild uses [upstream rebuild](https://github.com/cli/cli/blob/v2.101.0/pkg/cmd/codespace/rebuild.go),
documented by [gh codespace rebuild](https://cli.github.com/manual/gh_codespace_rebuild).
