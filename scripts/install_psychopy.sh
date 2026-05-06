#!/usr/bin/env bash
# Install PsychoPy 2024.2.5 in the active uv venv.
#
# PsychoPy 2024.2.x has two issues that break naive `uv pip install`:
#
#   1. It declares a transitive on `pypi-search>=1.2.1` which has never been
#      published to PyPI under that name (https://pypi.org/pypi/pypi-search
#      returns 404). PsychoPy uses it for its IDE "Search PyPI" menu — not
#      needed for running experiments.
#
#   2. `wxPython>=4.1.1` is only published to PyPI as a source distribution
#      on Linux. Building from source requires GTK / OpenGL / wx-widgets
#      development headers and takes ~30+ minutes on most machines. The
#      wxPython project hosts prebuilt manylinux-style wheels at
#      `extras.wxpython.org` for common Ubuntu/Fedora versions.
#
# This script works around both problems by:
#   1. Installing the prebuilt wxPython wheel from extras.wxpython.org for
#      the detected Ubuntu/Mint version + Python version.
#   2. Installing PsychoPy itself with `--no-deps`, then installing every
#      other declared dependency individually (skipping pypi-search).
#
# Run from the gradcpt package root with the uv venv activated or available
# at .venv/. Environment overrides:
#   PSYCHOPY_VERSION    Default: 2024.2.5
#   WXPYTHON_VERSION    Default: 4.2.2
#   WXPYTHON_DISTRO     Default: detected from /etc/os-release
#                       (e.g. ubuntu-22.04 / ubuntu-24.04 / fedora-40)

set -euo pipefail

PSYCHOPY_VERSION=${PSYCHOPY_VERSION:-2024.2.5}
WXPYTHON_VERSION=${WXPYTHON_VERSION:-4.2.2}

# ---------------------------------------------------------------------------
# Detect the wxPython prebuilt-wheel distro tag.
# ---------------------------------------------------------------------------
detect_wxpython_distro() {
    if [ -n "${WXPYTHON_DISTRO:-}" ]; then
        echo "$WXPYTHON_DISTRO"
        return
    fi
    if [ -r /etc/os-release ]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        case "$ID" in
            ubuntu)
                echo "ubuntu-$VERSION_ID"
                return
                ;;
            linuxmint)
                # Linux Mint uses the underlying Ubuntu base
                case "$VERSION_ID" in
                    22*) echo "ubuntu-24.04"; return ;;
                    21*) echo "ubuntu-22.04"; return ;;
                esac
                ;;
            debian)
                # Debian doesn't have prebuilts; fall through and let the
                # Ubuntu wheel work (often does, ABI-compatible).
                echo "ubuntu-22.04"
                return
                ;;
            fedora)
                echo "fedora-$VERSION_ID"
                return
                ;;
        esac
    fi
    echo "ubuntu-22.04"  # safe fallback
}

WXPYTHON_DISTRO=$(detect_wxpython_distro)
WXPYTHON_INDEX="https://extras.wxpython.org/wxPython4/extras/linux/gtk3/${WXPYTHON_DISTRO}/"

echo "==> wxPython prebuilt index: $WXPYTHON_INDEX"
echo "==> Installing wxPython==$WXPYTHON_VERSION (this is a ~143 MiB download)"
uv pip install -f "$WXPYTHON_INDEX" "wxPython==$WXPYTHON_VERSION"

echo "==> Installing PsychoPy==$PSYCHOPY_VERSION (without deps)"
uv pip install --no-deps "psychopy==$PSYCHOPY_VERSION"

echo "==> Fetching PsychoPy's declared deps (excluding pypi-search and wxPython)"
DEPS_FILE=$(mktemp)
trap 'rm -f "$DEPS_FILE"' EXIT
.venv/bin/python - <<EOF > "$DEPS_FILE"
import json, urllib.request
url = "https://pypi.org/pypi/psychopy/${PSYCHOPY_VERSION}/json"
data = json.loads(urllib.request.urlopen(url).read())
for r in data["info"].get("requires_dist", []) or []:
    if "extra ==" in r:
        continue
    bare = r.split(";")[0].split(">")[0].split("=")[0].split("<")[0].split("!")[0].strip()
    if bare in ("pypi-search", "wxPython"):
        continue
    print(r)
EOF
echo "==> $(wc -l < "$DEPS_FILE") deps to install"

echo "==> Installing PsychoPy deps in bulk"
uv pip install -r "$DEPS_FILE"

echo "==> Verifying import"
.venv/bin/python -c "import psychopy; print('PsychoPy', psychopy.__version__, 'OK')"

echo
echo "Done. You can now run: uv run gradcpt run --subject pilot01"
