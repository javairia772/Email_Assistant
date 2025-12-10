#!/usr/bin/env python3
"""Run McpSummariesProvider.get_summaries once and print diagnostics.

Usage:
    Activate your venv and run:
        . ./venv/Scripts/Activate.ps1  (PowerShell)
        python scripts/run_mcp_debug.py
"""
import json
import traceback
import sys
import os
from pathlib import Path

# Ensure project root is on sys.path so local packages (providers, Gmail, Outlook) import correctly
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

try:
    from providers.mcp_summaries_provider import McpSummariesProvider
except Exception as exc:
    print("Failed to import project modules. Make sure your virtualenv is activated and dependencies are installed.")
    print("Activate venv (PowerShell): .\\venv\\Scripts\\Activate.ps1")
    print("Install requirements: pip install -r requirements.txt")
    print("Detailed error:")
    import traceback
    traceback.print_exc()
    raise


def run_once():
    provider = McpSummariesProvider()
    try:
        result = provider.get_summaries(limit=10, existing_cache=None)
        print("=== MCP Provider Result ===")
        print("Contacts returned:", len(result) if isinstance(result, list) else type(result))
        if isinstance(result, list):
            for i, c in enumerate(result[:10], start=1):
                print(f"{i}. {c.get('email')} (threads: {len(c.get('threads', []))})")
        else:
            print(json.dumps(result, indent=2))
    except Exception as e:
        print("MCP provider raised exception:")
        traceback.print_exc()


if __name__ == '__main__':
    run_once()
