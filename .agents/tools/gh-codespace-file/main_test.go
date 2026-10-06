package main

import (
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/cli/cli/v2/pkg/iostreams"
	"github.com/stretchr/testify/require"
	"golang.org/x/sys/unix"
)

const synthetic = "ghp_SYNTHETIC_NOT_A_REAL_CREDENTIAL_12345"

type roundTripFunc func(*http.Request) (*http.Response, error)

func (fn roundTripFunc) RoundTrip(r *http.Request) (*http.Response, error) { return fn(r) }

func fixture(t *testing.T, content string, mode os.FileMode) string {
	t.Helper()
	path := filepath.Join(t.TempDir(), "carrier")
	require.NoError(t, os.WriteFile(path, []byte(content), mode))
	// Test the requested mode independently of the operator's restrictive umask.
	require.NoError(t, os.Chmod(path, mode))
	return path
}

func TestCarrierModesAndSymlink(t *testing.T) {
	for _, mode := range []os.FileMode{0400, 0600} {
		path := fixture(t, synthetic+"\n", mode)
		got, err := readCarrier(path)
		require.NoError(t, err, "mode %o", mode)
		require.Equal(t, synthetic, got)
		pointer := filepath.Join(t.TempDir(), "runtime-pointer")
		require.NoError(t, os.Symlink(path, pointer))
		got, err = readCarrier(pointer)
		require.NoError(t, err)
		require.Equal(t, synthetic, got)
	}
}

func TestCarrierRejectsUnsafeInputs(t *testing.T) {
	for name, path := range map[string]string{
		"relative":  "carrier",
		"missing":   filepath.Join(t.TempDir(), "missing"),
		"directory": t.TempDir(),
		"public":    fixture(t, synthetic, 0644),
		"short":     fixture(t, "short", 0600),
		"multiple":  fixture(t, synthetic+"\n"+synthetic, 0600),
		"oversize":  fixture(t, strings.Repeat("a", 8193), 0600),
	} {
		t.Run(name, func(t *testing.T) {
			got, err := readCarrier(path)
			require.Error(t, err)
			require.Empty(t, got)
		})
	}
	path := fixture(t, synthetic, 0600)
	require.NoError(t, os.Link(path, filepath.Join(t.TempDir(), "extra-link")))
	_, err := readCarrier(path)
	require.Error(t, err)
	fifo := filepath.Join(t.TempDir(), "fifo")
	require.NoError(t, unix.Mkfifo(fifo, 0600))
	_, err = readCarrier(fifo)
	require.Error(t, err)
}

func TestTransportBoundary(t *testing.T) {
	called := false
	transport := &carrierTransport{token: synthetic, codespace: "quiet-woodshed-123", allowStart: true, base: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		called = true
		if r.Header.Get("Authorization") != "Bearer "+synthetic {
			t.Fatal("missing in-memory API authentication")
		}
		return &http.Response{StatusCode: 200, Body: io.NopCloser(strings.NewReader("{}")), Header: make(http.Header), Request: r}, nil
	})}
	for _, spec := range []struct{ method, url string }{
		{"GET", "https://api.github.com/user"},
		{"GET", "https://api.github.com/user/codespaces/quiet-woodshed-123?internal=true&refresh=true"},
		{"POST", "https://api.github.com/user/codespaces/quiet-woodshed-123/start"},
	} {
		request, err := http.NewRequest(spec.method, spec.url, nil)
		require.NoError(t, err)
		called = false
		response, err := transport.RoundTrip(request)
		require.NoError(t, err)
		require.True(t, called)
		response.Body.Close()
		if request.Header.Get("Authorization") != "" {
			t.Fatal("original request was mutated")
		}
	}
	for _, spec := range []struct{ method, url string }{
		{"GET", "http://api.github.com/user"},
		{"GET", "https://api.github.com:443/user"},
		{"GET", "https://api.github.com.evil.example/user"},
		{"GET", "https://api.github.com@evil.example/user"},
		{"GET", "https://evil.example/user"},
		{"GET", "https://api.github.com/user/codespaces/another-123"},
		{"GET", "https://api.github.com/user/codespaces"},
		{"DELETE", "https://api.github.com/user/codespaces/quiet-woodshed-123"},
		{"POST", "https://api.github.com/repos/DSA-Woodshed/dsa-study-packet/issues"},
	} {
		request, err := http.NewRequest(spec.method, spec.url, nil)
		require.NoError(t, err)
		called = false
		_, err = transport.RoundTrip(request)
		require.Error(t, err)
		require.False(t, called)
	}
}

func TestCommandSurfaceDoesNotReadCarrier(t *testing.T) {
	for _, args := range [][]string{
		{"auth", "token"},
		{"create"},
		{"ssh"},
		{"logs"},
		{"rebuild"},
		{"rebuild", "-c", "quiet-woodshed-123"},
		{"rebuild", "-c", "quiet-woodshed-123", "--expected-codespace-id", "2025"},
		{"rebuild", "-c", "quiet-woodshed-123", "--expected-owner", "Jesssullivan"},
		{"rebuild", "-c", "quiet-woodshed-123", "--expected-codespace-id", "-1", "--expected-owner", "Jesssullivan"},
		{"rebuild", "-c", "quiet-woodshed-123", "--debug"},
		{"logs", "-c", "quiet-woodshed-123", "--debug"},
		{"logs", "-c", "quiet-woodshed-123", "--debug-file", "anything"},
		{"logs", "-c", "quiet-woodshed-123", "--config"},
		{"ssh", "-c", "quiet-woodshed-123", "--debug"},
		{"ssh", "-c", "quiet-woodshed-123", "--debug-file", "anything"},
		{"ssh", "-c", "quiet-woodshed-123", "--config"},
		{"ssh", "-c", "quiet-woodshed-123", "--stdio"},
	} {
		ios, _, _, _ := iostreams.Test()
		transport := &carrierTransport{base: roundTripFunc(func(*http.Request) (*http.Response, error) { t.Fatal("network reached"); return nil, nil })}
		cmd := newCommand(transport, ios)
		cmd.SetArgs(args)
		require.Error(t, cmd.Execute(), "restricted command: %v", args)
		if transport.token != "" {
			t.Fatal("restricted command loaded a token")
		}
	}
}

func TestRebuildOwnedSessionBinding(t *testing.T) {
	for _, scenario := range []struct {
		label    string
		body     string
		accepted bool
	}{
		{"owned-session", `{"id":2025,"name":"quiet-woodshed-123","owner":{"login":"Jesssullivan"},"state":"Rebuilding"}`, true},
		{"other-session-id", `{"id":2026,"name":"quiet-woodshed-123","owner":{"login":"Jesssullivan"},"state":"Rebuilding"}`, false},
		{"other-session-name", `{"id":2025,"name":"other-woodshed-456","owner":{"login":"Jesssullivan"},"state":"Rebuilding"}`, false},
		{"other-owner", `{"id":2025,"name":"quiet-woodshed-123","owner":{"login":"someone-else"},"state":"Rebuilding"}`, false},
		{"missing-id", `{"name":"quiet-woodshed-123","owner":{"login":"Jesssullivan"},"state":"Rebuilding"}`, false},
	} {
		t.Run(scenario.label, func(t *testing.T) {
			ios, _, stdout, stderr := iostreams.Test()
			calls := 0
			transport := &carrierTransport{base: roundTripFunc(func(r *http.Request) (*http.Response, error) {
				calls++
				require.Equal(t, "GET", r.Method)
				require.Equal(t, "/user/codespaces/quiet-woodshed-123", r.URL.Path)
				return &http.Response{StatusCode: 200, Body: io.NopCloser(strings.NewReader(scenario.body)), Header: make(http.Header), Request: r}, nil
			})}
			cmd := newCommand(transport, ios)
			cmd.SetArgs([]string{"--token-file", fixture(t, synthetic, 0400), "rebuild", "--codespace", "quiet-woodshed-123", "--expected-codespace-id", "2025", "--expected-owner", "Jesssullivan"})
			err := cmd.Execute()
			if scenario.accepted {
				require.NoError(t, err)
				require.Equal(t, "quiet-woodshed-123 is already rebuilding\n", stdout.String())
				require.True(t, transport.identityVerified.Load())
			} else {
				require.ErrorContains(t, err, "outside the owned session")
				require.Empty(t, stdout.String())
				require.False(t, transport.identityVerified.Load())
			}
			require.Empty(t, stderr.String())
			require.Equal(t, 1, calls, "only the selected-resource GET reached the underlying transport")
		})
	}
}

func TestOwnedStartRequiresIdentityAndKeepsExactTarget(t *testing.T) {
	calls := 0
	transport := &carrierTransport{token: synthetic, codespace: "quiet-woodshed-123", allowStart: true, ownedID: 2025, ownedOwner: "Jesssullivan", base: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		calls++
		body := `{"id":2025,"name":"quiet-woodshed-123","owner":{"login":"Jesssullivan"},"state":"Shutdown"}`
		return &http.Response{StatusCode: 200, Body: io.NopCloser(strings.NewReader(body)), Header: make(http.Header), Request: r}, nil
	})}
	request, err := http.NewRequest("POST", "https://api.github.com/user/codespaces/quiet-woodshed-123/start", nil)
	require.NoError(t, err)
	_, err = transport.RoundTrip(request)
	require.ErrorContains(t, err, "before owned resource identity verification")
	require.Zero(t, calls)
	request, err = http.NewRequest("GET", "https://api.github.com/user/codespaces/quiet-woodshed-123", nil)
	require.NoError(t, err)
	response, err := transport.RoundTrip(request)
	require.NoError(t, err)
	response.Body.Close()
	require.True(t, transport.identityVerified.Load())
	request, err = http.NewRequest("POST", "https://api.github.com/user/codespaces/quiet-woodshed-123/start", nil)
	require.NoError(t, err)
	response, err = transport.RoundTrip(request)
	require.NoError(t, err)
	response.Body.Close()
	for _, target := range []string{
		"https://api.github.com/user/codespaces/other-woodshed-456/start",
		"https://api.github.com/user/codespaces/quiet-woodshed-123/rebuild",
		"https://api.github.com/orgs/DSA-Woodshed/codespaces/quiet-woodshed-123/start",
	} {
		request, err = http.NewRequest("POST", target, nil)
		require.NoError(t, err)
		_, err = transport.RoundTrip(request)
		require.ErrorContains(t, err, "outside the selected Codespace GitHub API boundary")
	}
	require.Equal(t, 2, calls)
}

func TestLogsAPIBoundaryRefusesAutomaticStart(t *testing.T) {
	ios, _, _, _ := iostreams.Test()
	calls := 0
	transport := &carrierTransport{base: roundTripFunc(func(r *http.Request) (*http.Response, error) {
		calls++
		require.Equal(t, "GET", r.Method)
		require.Equal(t, "/user/codespaces/quiet-woodshed-123", r.URL.Path)
		require.Equal(t, "Bearer "+synthetic, r.Header.Get("Authorization"))
		return &http.Response{StatusCode: 200, Body: io.NopCloser(strings.NewReader(`{"name":"quiet-woodshed-123","state":"Shutdown"}`)), Header: make(http.Header), Request: r}, nil
	})}
	cmd := newCommand(transport, ios)
	cmd.SetArgs([]string{"--token-file", fixture(t, synthetic, 0400), "logs", "--codespace", "quiet-woodshed-123"})
	err := cmd.Execute()
	require.ErrorContains(t, err, "refused request outside the selected Codespace GitHub API boundary")
	require.False(t, transport.allowStart)
	require.Equal(t, 1, calls, "only selected-resource GET may reach the underlying transport")
}

func TestAmbientAuthAndEndpointOverridesAreRemoved(t *testing.T) {
	for _, name := range []string{"GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN", "GH_DEBUG", "GH_HOST", "GITHUB_API_URL", "GITHUB_SERVER_URL"} {
		t.Setenv(name, "synthetic-value")
	}
	cleanEnvironment()
	for _, name := range []string{"GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN", "GH_DEBUG", "GH_HOST", "GITHUB_API_URL", "GITHUB_SERVER_URL"} {
		if _, set := os.LookupEnv(name); set {
			t.Fatalf("ambient variable survives: %s", name)
		}
	}
}
