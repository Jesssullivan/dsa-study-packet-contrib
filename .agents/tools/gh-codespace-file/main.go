// Local operator adapter for cli/cli v2.101.0. It is deliberately not an auth
// command or a replacement GitHub CLI: only upstream SSH/logs/rebuild are exposed.
package main

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"sync/atomic"
	"time"

	"github.com/cli/cli/v2/internal/gh"
	"github.com/cli/cli/v2/pkg/cmd/codespace"
	"github.com/cli/cli/v2/pkg/cmdutil"
	"github.com/cli/cli/v2/pkg/iostreams"
	"github.com/spf13/cobra"
	"golang.org/x/sys/unix"
)

var carrierValue = regexp.MustCompile(`^[A-Za-z0-9_]+$`)
var codespaceName = regexp.MustCompile(`^[a-zA-Z0-9][a-zA-Z0-9-]+$`)
var githubLogin = regexp.MustCompile(`^[a-zA-Z0-9][a-zA-Z0-9-]{0,38}$`)

// Runtime sops-nix pointers may be symlinks. Resolve the pointer, open its final
// leaf without following another symlink, then validate the opened descriptor.
// The carrier never becomes an environment variable, argv value, or config file.
func readCarrier(path string) (string, error) {
	if !filepath.IsAbs(path) {
		return "", errors.New("token carrier must be an absolute file path")
	}
	resolved, err := filepath.EvalSymlinks(path)
	if err != nil {
		return "", errors.New("cannot resolve token carrier")
	}
	fd, err := unix.Open(resolved, unix.O_RDONLY|unix.O_NONBLOCK|unix.O_NOFOLLOW|unix.O_CLOEXEC, 0)
	if err != nil {
		return "", errors.New("cannot open token carrier")
	}
	f := os.NewFile(uintptr(fd), resolved)
	defer f.Close()
	var st unix.Stat_t
	if err := unix.Fstat(fd, &st); err != nil {
		return "", errors.New("cannot inspect token carrier")
	}
	if st.Mode&unix.S_IFMT != unix.S_IFREG || st.Uid != uint32(os.Geteuid()) || st.Nlink != 1 || (st.Mode&07777 != 0400 && st.Mode&07777 != 0600) {
		return "", errors.New("token carrier must be an owned regular single-link 0400/0600 file")
	}
	b, err := io.ReadAll(io.LimitReader(f, 8193))
	if err != nil {
		return "", errors.New("cannot read token carrier")
	}
	defer func() {
		for i := range b {
			b[i] = 0
		}
	}()
	token := strings.TrimSpace(string(b))
	if len(b) > 8192 || len(token) < 20 || !carrierValue.MatchString(token) {
		return "", errors.New("token carrier contains an invalid token format")
	}
	return token, nil
}

type carrierTransport struct {
	base             http.RoundTripper
	token            string
	codespace        string
	allowStart       bool
	ownedID          int64
	ownedOwner       string
	identityVerified atomic.Bool
}

func (t *carrierTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	// Exact host, HTTPS, no userinfo, and only this selected Codespace's read/start
	// routes. No redirect, repository, auth, org, or deletion APIs are exposed.
	path := "/user/codespaces/" + t.codespace
	allowed := req.Method == http.MethodGet && (req.URL.Path == path || req.URL.Path == "/user")
	allowed = allowed || (t.allowStart && req.Method == http.MethodPost && req.URL.Path == path+"/start")
	if req.URL.Scheme != "https" || req.URL.Host != "api.github.com" || req.URL.User != nil || !allowed || t.token == "" || !codespaceName.MatchString(t.codespace) {
		return nil, errors.New("refused request outside the selected Codespace GitHub API boundary")
	}
	if t.ownedID > 0 && req.Method == http.MethodPost && !t.identityVerified.Load() {
		return nil, errors.New("refused Codespace start before owned resource identity verification")
	}
	selectedRead := req.Method == http.MethodGet && req.URL.Path == path
	if t.ownedID > 0 && selectedRead {
		t.identityVerified.Store(false)
	}
	clone := req.Clone(req.Context())
	clone.Header = req.Header.Clone()
	clone.Header.Set("Authorization", "Bearer "+t.token)
	clone.Header.Set("User-Agent", "gh-codespace-file/cli-v2.101.0")
	clone.Header.Set("X-GitHub-Api-Version", "2022-11-28")
	response, err := t.base.RoundTrip(clone)
	if err != nil || response == nil || t.ownedID == 0 || !selectedRead || response.StatusCode != http.StatusOK {
		return response, err
	}
	// Upstream's selected-resource GET returns the tunnel credentials consumed by
	// RebuildContainer. Bind that response to the operator's exact owned ID/name/
	// owner before upstream can deserialize and use any connection information.
	data, err := io.ReadAll(io.LimitReader(response.Body, 4*1024*1024+1))
	response.Body.Close()
	if err != nil || len(data) > 4*1024*1024 {
		return nil, errors.New("cannot inspect selected Codespace identity")
	}
	var identity struct {
		ID    int64  `json:"id"`
		Name  string `json:"name"`
		Owner struct {
			Login string `json:"login"`
		} `json:"owner"`
	}
	if json.Unmarshal(data, &identity) != nil || identity.ID != t.ownedID || identity.Name != t.codespace || !githubLogin.MatchString(t.ownedOwner) || !strings.EqualFold(identity.Owner.Login, t.ownedOwner) {
		return nil, errors.New("refused selected Codespace identity outside the owned session")
	}
	t.identityVerified.Store(true)
	response.Body = io.NopCloser(bytes.NewReader(data))
	return response, nil
}

func cleanEnvironment() {
	// Upstream/API endpoint overrides, HTTP debug, and credential variables must
	// not influence this helper or reach its OpenSSH child. Config/keyring are
	// never opened: Factory.Config below returns a deliberate standalone error.
	for _, key := range []string{"GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN", "GH_DEBUG", "GH_HOST", "GITHUB_API_URL", "GITHUB_SERVER_URL"} {
		_ = os.Unsetenv(key)
	}
}

func newCommand(transport *carrierTransport, ios *iostreams.IOStreams) *cobra.Command {
	client := &http.Client{
		Transport: transport,
		Timeout:   60 * time.Second,
		CheckRedirect: func(_ *http.Request, _ []*http.Request) error {
			return errors.New("GitHub API redirects are disabled")
		},
	}
	f := &cmdutil.Factory{
		IOStreams: ios,
		Config: func() (gh.Config, error) {
			return nil, errors.New("standalone github.com endpoint; stored auth is disabled")
		},
		HttpClient: func() (*http.Client, error) { return client, nil },
		ExternalHttpClient: func() (*http.Client, error) {
			// Upstream's tunnel protocol may use its own short-lived connection
			// credentials. This client has no reference to the carrier transport.
			return &http.Client{Transport: http.DefaultTransport}, nil
		},
	}
	cmd := codespace.NewCmdCodespace(f)
	cmd.Use = "gh-codespace-file"
	cmd.Short = "File-only operator authentication for pinned upstream Codespaces SSH/logs/rebuild"
	cmd.Aliases = nil
	cmd.GroupID = ""
	cmd.SilenceErrors = true
	cmd.SilenceUsage = true
	cmd.CompletionOptions.DisableDefaultCmd = true
	cmd.SetOut(ios.Out)
	cmd.SetErr(ios.ErrOut)
	var pointer string
	cmd.PersistentFlags().StringVar(&pointer, "token-file", "", "Absolute path to an owned 0400/0600 file-only carrier")
	for _, sub := range cmd.Commands() {
		if sub.Name() != "ssh" && sub.Name() != "logs" && sub.Name() != "rebuild" {
			cmd.RemoveCommand(sub)
			continue
		}
		prior := sub.PreRunE
		var expectedID int64
		var expectedOwner string
		if sub.Name() == "rebuild" {
			sub.Flags().Int64Var(&expectedID, "expected-codespace-id", 0, "Exact ID of the recorded owned Codespace")
			sub.Flags().StringVar(&expectedOwner, "expected-owner", "", "Recorded owner login of the selected Codespace")
		}
		sub.PreRunE = func(c *cobra.Command, args []string) error {
			for _, name := range []string{"debug", "debug-file", "config", "stdio"} {
				if c.Flags().Changed(name) {
					return fmt.Errorf("--%s is disabled by the file-only adapter", name)
				}
			}
			name, _ := c.Flags().GetString("codespace")
			if !codespaceName.MatchString(name) {
				return errors.New("an explicit valid --codespace name is required")
			}
			if c.Name() == "rebuild" && (expectedID <= 0 || !githubLogin.MatchString(expectedOwner)) {
				return errors.New("rebuild requires exact --expected-codespace-id and --expected-owner from the owned session receipt")
			}
			if prior != nil {
				if err := prior(c, args); err != nil {
					return err
				}
			}
			token, err := readCarrier(pointer)
			if err != nil {
				return err
			}
			transport.token = token
			transport.codespace = name
			transport.allowStart = c.Name() == "ssh" || c.Name() == "rebuild"
			transport.ownedID = expectedID
			transport.ownedOwner = expectedOwner
			transport.identityVerified.Store(false)
			return nil
		}
	}
	return cmd
}

func main() {
	cleanEnvironment()
	transport := &carrierTransport{base: http.DefaultTransport}
	cmd := newCommand(transport, iostreams.System())
	if err := cmd.Execute(); err != nil {
		message := err.Error()
		if transport.token != "" {
			message = strings.ReplaceAll(message, transport.token, "[redacted]")
		}
		fmt.Fprintln(os.Stderr, message)
		os.Exit(1)
	}
}
