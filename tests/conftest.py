"""
Test session configuration.

Sets a fake ANTHROPIC_API_KEY before any test module imports src.config.
This prevents _load_settings() from raising RuntimeError during tests —
the key is never used in unit/integration tests because all LLM calls
are mocked.
"""

import os

# Must run at module level (not inside a fixture) so it takes effect before
# the first import of src.config, which validates the key at module load time.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key-not-real")
