import os
import sys

# Import the application as the package it is: `import injecto.processing`, not
# `import processing`. The repo root goes on the path, not injecto/ itself -
# putting the package directory on sys.path is what made `git`, `logs` and
# `version` top-level module names and shadowed anything installed under those.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Injecto refuses to run without a service token unless auth is explicitly
# disabled (OP-260). The suite runs in that dev mode and tests that exercise
# auth set a token themselves. Pinned here, before injecto is imported, so the
# developer's shell cannot change it: an exported SERVICE_TOKEN used to fail
# every endpoint test with 401.
os.environ.pop("SERVICE_TOKEN", None)
os.environ["INJECTO_AUTH_DISABLED"] = "true"
