"""Streamlit Community Cloud entrypoint for the single-key public demo."""

import os
import runpy
from pathlib import Path

# A separate entrypoint keeps the ordinary app local-first. Public hosting must
# always use isolated session history and the bounded evidence-only provider.
os.environ['BMQ_MODEL_PROVIDER'] = 'gemini'
os.environ['BMQ_PUBLIC_DEMO'] = 'true'
os.environ['BMQ_MODEL_HINTS'] = 'false'
os.environ['BMQ_GEMMA_ROUNDS'] = '1'
os.environ['BMQ_HUNT_ORDER'] = 'gemma,fuzz'
os.environ.setdefault('BMQ_MODEL', 'gemma-4-26b-a4b-it')
runpy.run_path(str(Path(__file__).with_name('app.py')), run_name='__main__')
