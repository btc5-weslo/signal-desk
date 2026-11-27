"""Backend unit tests opt into mock seeding. QA gates under ../qa/backend_gates
do not load this file, so they see the platform default use_mock_data=False.
"""
import os

# Must be set before app.main / get_settings is imported by test modules.
os.environ.setdefault("SIGNAL_USE_MOCK_DATA", "true")
