# tests/conftest.py
import sys
import os

# Get the project root directory (one level up from tests/)
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
source_dir = os.path.join(project_root, 'src')

# Add the source directory to sys.path
# This allows 'from src import my_module' to work
sys.path.insert(0, source_dir)