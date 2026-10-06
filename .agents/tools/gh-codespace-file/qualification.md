# File-only Codespaces helper source and qualification

Authority: user-authorized DSA convergence and personal tooling preservation;
R-HOOK-CONVERGENCE-20261004 / R-N12 / R-N13. The adapter belongs only on the
personal contribution fork's orphan overlay or a locally excluded worktree.
Never merge it into either organization product.

The upstream implementation is official `cli/cli` v2.101.0 at commit
`0cf1092493af067646fc5f3db9421c6a6ec9c938`, using its `go1.27.1` toolchain.
No tracked upstream source was edited. Only the added command adapter changes
transport custody and exposed commands. The included MIT license is retained
from the upstream source. This local adaptation is not an upstream endorsement
or an unsolicited CLI contribution.

Final source SHA256:
`0b4ed055b015a69732817ca3af76e8e6ba863efe8e15934e2e7bcc7f0468f21f`.
Final tests SHA256:
`93f53331dcd4f494661402cc9ef72902eefac3614ae3d893a678e81535d0a4de`.
The original qualified tests were
`8125eccb755b912bda15f705f9e4308abb1ba0a15564c8aecf7983c4f710381e`;
the copied fixture now explicitly sets its requested synthetic file mode so
unsafe-mode checks remain meaningful under a restrictive operator umask.

Two separately built Linux/amd64 executables were qualified locally:

- Earlier SSH/logs-only binary:
  `e5ef65f8d6a8ff4f198e40b974f3e56c61244d47cd7d2297c90a17aaf957ccd4`.
  It remains a historical local operator artifact and is not rebuilt from the
  final source in this overlay.
- Final separate SSH/logs/rebuild binary:
  `3868199f17f6957d9fe302143783aef23c5889ed996c06b021d3ed2009b4dd35`.
  This overlay preserves that final source and reproduced this exact binary
  through a clean public-source bootstrap on Linux/amd64. The bootstrap retains
  and verifies the upstream tag as well as its exact commit, preserving Go's
  module build metadata. Rebuilding on a different platform
  or with different build metadata may produce a different binary digest;
  the bootstrap records the result instead of asserting unobserved parity.

Observed affected-package checks passed: ordinary Go tests, race tests, Go
format/fix, build, and executable help. Fixtures use synthetic carriers and
mocked HTTP. They exercise unsafe file/mode/link/FIFO inputs, exact HTTPS host
and resource routing, refused auth/repository/global commands, debug/config
restrictions, logs refusing automatic start, rebuild ID/name/owner binding,
cross-session refusal, and start refusal before identity verification. The
external tunnel transport never receives the operator carrier. Whole-CLI tests
and lint were not run; the upstream implementation is unchanged.

The operator carrier was not read by the implementing agent. No real hosted
resource, SSH identity, credential value, provider beforeimage, browser cookie,
or private operations receipt is included in this overlay. Real Codespaces
commands and lifecycle/product acceptance are recorded separately by the
resource owner. A successful asynchronous rebuild RPC does not prove subsequent
container readiness, persistence, editor attachment, or product behavior.

The included bootstrap fetches official public source at the exact commit,
copies the unchanged Go adapter, repeats the affected synthetic/race checks,
and writes a local build receipt. It refuses existing build directories and
does not run the helper with a carrier. It does not replace or update existing
operator binaries while a live SSH session is using them.
Shell syntax and ShellCheck passed; missing arguments, relative output paths,
and existing output-directory refusals were exercised. Runtime Go source is
byte-identical to the qualified adapter; no private provider/resource/host
pointers are present in this tool copy.

Native GitHub Codespaces web/desktop editor attachment requires normal GitHub
browser/extension sign-in. The upstream command opens a URL; its published
RPC services provide SSH, Jupyter, activity, and rebuild, with no VSCode server
bootstrap surface. This adapter does not convert its file-only operator
credential into browser cookies or editor auth. Optional desktop Remote-SSH
may connect to its ordinary localhost SSH listener with the operator's SSH key;
that is distinct from native Codespaces web-editor acceptance.

Primary sources: [CLI authentication environment](https://cli.github.com/manual/gh_help_environment),
[stdin login persistence](https://cli.github.com/manual/gh_auth_login),
[upstream Codespaces code command](https://github.com/cli/cli/blob/0cf1092493af067646fc5f3db9421c6a6ec9c938/pkg/cmd/codespace/code.go),
[published upstream RPC interface](https://github.com/cli/cli/blob/0cf1092493af067646fc5f3db9421c6a6ec9c938/internal/codespaces/rpc/invoker.go),
[Codespaces VSCode sign-in](https://docs.github.com/en/codespaces/developing-in-a-codespace/using-github-codespaces-in-visual-studio-code),
and [supported VSCode Remote-SSH](https://code.visualstudio.com/docs/remote/ssh).
