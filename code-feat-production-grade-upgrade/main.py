#!/usr/bin/env python3
"""
Main entry point for the Streamlit application.
This script properly sets up the Python path to handle relative imports.
"""

import sys
import os
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Now we can import and run the app
if __name__ == "__main__":
    from src.app import main
    main()