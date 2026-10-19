from pathlib import Path

import pandas
import pydantic
from dotenv import load_dotenv


def test_core_dependencies_import():
    assert pandas is not None
    assert pydantic is not None
    assert callable(load_dotenv)


def test_env_example_exists():
    repository_root = Path(__file__).resolve().parents[1]
    assert (repository_root / ".env.example").is_file()
