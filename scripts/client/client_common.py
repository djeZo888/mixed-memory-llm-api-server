"""Private runtime support shared by the bootstrap and installed launcher."""

import json
import os
from pathlib import Path
import platform
import re
import stat
import subprocess

VERSION = "1.18.31"
PROVIDER = "local"
KEY_ENV = "V0_LOCAL_API_KEY_JSON"


class ClientError(Exception):
    pass


def absolute_path(value):
    path = Path(value)
    if not path.is_absolute() or any(ord(c) < 32 for c in str(path)):
        raise ClientError("Use an absolute path without control characters")
    # Resolve system aliases such as macOS /var -> /private/var consistently.
    return path.resolve()


def private_dir(path, create=False):
    if path.is_symlink():
        raise ClientError("Private state must not be a symlink")
    if create and not path.exists():
        path.mkdir(mode=0o700)
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ClientError("Private state must be an owned directory with mode 0700")


def private_file(path):
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or info.st_mode & 0o077 or info.st_nlink != 1):
        raise ClientError("Expected an owned private regular file (0600, no hard links)")


def write_new(path, data, mode=0o600):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)


def json_bytes(value):
    return (json.dumps(value, indent=2, ensure_ascii=True) + "\n").encode()


def endpoint(value):
    endpoint_kind(value)
    return value


def endpoint_kind(value):
    # Match the original text before any URL parser can strip whitespace or
    # normalize an address alias. Keep the existing loopback spellings only.
    message = ("Require http(s)://<loopback-or-canonical-RFC1918-IPv4>:<port-1..65535>/v1 "
               "without credentials/query/fragment/whitespace")
    if type(value) is not str:
        raise ClientError(message)
    match = re.fullmatch(r"(?ai:https?)://(?P<host>(?ai:localhost)|\[::1\]|[0-9]+(?:\.[0-9]+){3})"
                         r":(?P<port>[0-9]+)/v1", value)
    if match is None:
        raise ClientError(message)
    # Zero-padded ports were already accepted; IPv4 octets must be canonical.
    port = match["port"].lstrip("0")
    if not port or len(port) > 5 or int(port) > 65535:
        raise ClientError(message)
    host = match["host"]
    if host.lower() in ("localhost", "127.0.0.1", "[::1]"):
        return "loopback"
    octets = host.split(".")
    if any(len(part) > 3 or (len(part) > 1 and part[0] == "0") or int(part) > 255 for part in octets):
        raise ClientError(message)
    a, b, _, _ = map(int, octets)
    # Explicit RFC1918 networks, never ipaddress.is_private's broader set.
    if a == 10 or (a == 172 and 16 <= b <= 31) or (a == 192 and b == 168):
        return "private"
    raise ClientError(message)


def validate_endpoint_auth(settings):
    if type(settings) is not dict:
        raise ClientError("Client settings must be an object")
    kind = endpoint_kind(settings.get("base_url"))
    auth = settings.get("auth")
    if type(auth) is not dict:
        raise ClientError("Client authentication must be a file/env reference or explicit loopback disabled mode")
    auth_kind = auth.get("kind")
    if auth_kind == "disabled" and set(auth) == {"kind"}:
        if kind != "loopback":
            raise ClientError("Private IPv4 endpoints require a protected API key file or environment reference")
        return
    if auth_kind not in ("file", "env") or set(auth) != {"kind", "reference"}:
        raise ClientError("Client authentication must contain only kind and reference")
    reference = auth["reference"]
    if type(reference) is not str or not reference:
        raise ClientError("Key reference must be a nonempty string, never a key value")
    if auth_kind == "env":
        key_env_name(reference)
    elif not Path(reference).is_absolute() or any(ord(c) < 32 or ord(c) == 127 for c in reference):
        raise ClientError("Key file reference must be absolute without control characters")


def model_id(value):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/+@-]{0,255}", value):
        raise ClientError("Model ID must be a literal API ID (letters, digits, . _ : / + @ -)")
    return value


def reasoning_effort(value):
    # Deliberately expose only the reviewed opt-ins, not every SDK string.
    if type(value) is not str or value not in ("none", "low"):
        raise ClientError("reasoning-effort must be the literal string none or low; omit it for the default")
    return value


def key_env_name(value):
    if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", value):
        raise ClientError("Key environment reference must be an uppercase variable name")
    if value in ("HOME", "PATH", "CODEX_HOME", KEY_ENV) or value.startswith(("OPENCODE_", "XDG_", "NPM_")):
        raise ClientError("Key environment reference conflicts with runtime controls")
    return value


def runtime_dir(prefix):
    return prefix / "xdg" / "config" / "opencode"


def native_package():
    system = platform.system()
    machine = platform.machine().lower()
    arch = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "x64", "amd64": "x64"}.get(machine)
    if system not in ("Darwin", "Linux") or arch is None:
        raise ClientError("Supported client targets: macOS and glibc Linux, arm64/x64")
    if system == "Linux":
        try:
            if not os.confstr("CS_GNU_LIBC_VERSION"):
                raise ValueError("glibc unavailable")
        except (ValueError, OSError):
            raise ClientError("This bootstrap supports glibc Linux; musl is not validated") from None
    suffix = "-baseline" if arch == "x64" else ""
    return "opencode-" + ("darwin" if system == "Darwin" else "linux") + "-" + arch + suffix


def binary_path(prefix):
    return runtime_dir(prefix) / "node_modules" / native_package() / "bin" / "opencode"


def isolated_env(prefix):
    # HOME is unchanged; OpenCode's own home discovery is redirected below.
    env = {key: os.environ[key] for key in ("HOME", "PATH", "TERM", "COLORTERM", "LANG", "LC_ALL") if key in os.environ}
    env.update({
        "XDG_CONFIG_HOME": str(prefix / "xdg" / "config"),
        "XDG_DATA_HOME": str(prefix / "xdg" / "data"),
        "XDG_CACHE_HOME": str(prefix / "xdg" / "cache"),
        "XDG_STATE_HOME": str(prefix / "xdg" / "state"),
        "TMPDIR": str(prefix / "tmp"), "TMP": str(prefix / "tmp"), "TEMP": str(prefix / "tmp"),
        "npm_config_cache": str(prefix / "npm" / "cache"),
        "npm_config_logs_dir": str(prefix / "npm" / "logs"),
        "npm_config_userconfig": str(prefix / "npm" / "userconfig"),
        "npm_config_globalconfig": str(prefix / "npm" / "globalconfig"),
        "npm_config_registry": "https://registry.npmjs.org/",
        "npm_config_audit": "false", "npm_config_fund": "false", "npm_config_ignore_scripts": "true",
        "npm_config_update_notifier": "false",
        "BUN_INSTALL_CACHE_DIR": str(prefix / "bun-cache"),
        "OPENCODE_CONFIG": str(prefix / "opencode.json"),
        "OPENCODE_CONFIG_DIR": str(runtime_dir(prefix)),
        "OPENCODE_TEST_HOME": str(prefix / "discovery-home"),
        "OPENCODE_TEST_MANAGED_CONFIG_DIR": str(prefix / "managed"),
        "OPENCODE_DISABLE_PROJECT_CONFIG": "1",
        "OPENCODE_DISABLE_AUTOUPDATE": "1", "OPENCODE_DISABLE_MODELS_FETCH": "1",
        "OPENCODE_MODELS_PATH": str(prefix / "models.json"),
        "OPENCODE_DISABLE_DEFAULT_PLUGINS": "1", "OPENCODE_DISABLE_EXTERNAL_SKILLS": "1",
        "OPENCODE_DISABLE_CLAUDE_CODE": "1", "OPENCODE_DISABLE_LSP_DOWNLOAD": "1",
        "OPENCODE_DISABLE_EMBEDDED_WEB_UI": "1", "OPENCODE_PURE": "1",
        "OPENCODE_DISABLE_FFF": "1", "OPENCODE_EXPERIMENTAL_DISABLE_FILEWATCHER": "1",
        "DO_NOT_TRACK": "1",
    })
    return env


def refuse_managed_preferences():
    if platform.system() == "Darwin":
        import pwd
        root = Path("/Library/Managed Preferences")
        for directory in (root, root / pwd.getpwuid(os.getuid()).pw_name):
            # Only test existence. Never read managed config or user auth stores.
            if (directory / "ai.opencode.managed.plist").exists():
                raise ClientError("OpenCode managed preferences exist; isolated launch cannot override them")


def config_for(settings):
    validate_endpoint_auth(settings)
    model = settings["model"]
    model_config = {"name": model, "limit": {
        "context": settings["context_tokens"], "output": settings["output_tokens"]}}
    if "reasoning_effort" in settings:
        # OpenCode 1.18.31 -> bundled openai-compatible 2.0.41 -> top-level
        # reasoning_effort. Keep absence byte-for-byte compatible with V0.
        model_config["options"] = {"reasoningEffort": reasoning_effort(settings["reasoning_effort"])}
    options = {"baseURL": settings["base_url"]}
    if settings["auth"]["kind"] != "disabled":
        options["apiKey"] = "{env:" + KEY_ENV + "}"
    return {
        "$schema": "https://opencode.ai/config.json",
        "model": PROVIDER + "/" + model, "small_model": PROVIDER + "/" + model,
        "enabled_providers": [PROVIDER],
        "provider": {PROVIDER: {
            "npm": "@ai-sdk/openai-compatible", "name": "Local model API", "options": options,
            "models": {model: model_config},
        }},
        "autoupdate": False, "share": "disabled", "snapshot": False, "shell": "/bin/sh",
        "plugin": [], "mcp": {}, "lsp": False, "formatter": False,
        "permission": {"*": "deny", "read": "allow", "glob": "allow", "grep": "allow",
                       "edit": "ask", "bash": "ask", "external_directory": "deny"},
    }


def encode_key(raw):
    if not raw or len(raw) > 8192 or any(c < 33 or c > 126 for c in raw):
        raise ClientError("Key must be 1..8192 printable ASCII bytes without whitespace; file is never trimmed")
    # OpenCode interpolates env text before parsing JSON, then expands {file:...}.
    # Escape JSON AND opening braces so both passes preserve key bytes safely.
    return json.dumps(raw.decode("ascii"))[1:-1].replace("{", "\\u007b")


def load_key(auth):
    if auth["kind"] == "file":
        path = Path(auth["reference"])
        if path.is_symlink():
            raise ClientError("Key file must not be a symlink")
        private_dir(path.parent)
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_mode & 0o077 or info.st_nlink != 1):
                raise ClientError("Key must be an owned 0600 regular file without hard links")
            raw = stream.read(8193)
    else:
        value = os.environ.get(auth["reference"])
        if value is None:
            raise ClientError("Configured key environment variable is absent")
        try:
            raw = value.encode("ascii")
        except UnicodeEncodeError:
            raise ClientError("Key must be printable ASCII") from None
    return encode_key(raw)


def run_capture(args, cwd, env, timeout=60, include_stderr=False):
    result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        # Do not echo untrusted CLI diagnostics/config/prompt/credential values.
        raise ClientError("Child command failed (exit " + str(result.returncode) + "); output withheld")
    return result.stdout + (result.stderr if include_stderr else "")


def verify_install(prefix):
    private_dir(prefix)
    for name in ("bin", "xdg", "xdg/config", "xdg/data", "xdg/cache", "xdg/state", "xdg/config/opencode",
                 "npm", "npm/cache", "npm/logs", "tmp", "bun-cache"):
        private_dir(prefix / name)
    for name in ("bootstrap.json", "opencode.json", "models.json"):
        private_file(prefix / name)
    settings = json.loads((prefix / "bootstrap.json").read_text())
    validate_endpoint_auth(settings)
    if settings["version"] != VERSION:
        raise ClientError("Installed pin differs from launcher; use a new prefix for upgrades")
    actual = json.loads((prefix / "opencode.json").read_text())
    if json.loads((prefix / "models.json").read_text()) != {}:
        raise ClientError("Private model catalog must remain empty; model is supplied by local config")
    if actual != config_for(settings):
        raise ClientError("Generated configuration changed; use a new prefix to reconfigure")
    for name in ("opencode-ai", "@opencode-ai/plugin", native_package()):
        data = json.loads((runtime_dir(prefix) / "node_modules" / name / "package.json").read_text())
        if data["version"] != VERSION:
            raise ClientError("Installed dependency version differs from reviewed pin")
    # Refuse new config/discovery files before OpenCode can load them.
    for directory in (prefix / "managed", prefix / "discovery-home"):
        private_dir(directory)
        if any(directory.iterdir()):
            raise ClientError("Private discovery directories must remain empty")
    for name in ("config.json", "opencode.json", "opencode.jsonc", "config", "agent", "agents",
                 "command", "commands", "plugin", "plugins", "tool", "tools", "skill", "skills",
                 "tui.json", "tui.jsonc", "AGENTS.md", "CONTEXT.md"):
        if (runtime_dir(prefix) / name).exists():
            raise ClientError("Unexpected additional OpenCode configuration in private runtime")
    refuse_managed_preferences()
    return settings
