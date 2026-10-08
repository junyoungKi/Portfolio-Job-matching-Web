"""Author: Joonyoung Ki

Purpose: Pytest configuration that makes the repository root importable so
tests can ``import app...`` regardless of the invocation directory.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
