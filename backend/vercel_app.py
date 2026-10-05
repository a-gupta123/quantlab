"""Vercel entrypoint for the API service (see /vercel.json).

The API is not publicly routed on Vercel: only the Next.js service reaches it,
through a private service binding, and every route still requires the
API_INTERNAL_TOKEN bearer token.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from quantlab.api.main import create_app  # noqa: E402

app = create_app()
