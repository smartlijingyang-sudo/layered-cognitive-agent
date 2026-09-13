#!/usr/bin/env python3
"""Check if stop node executors are registered in the booted scope."""

import asyncio
import sys
from pathlib import Path

# Add the project root to the path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from lca.harness.profile.boot.boot import boot_profile
from lca.plugins.composer.runtime.runtime.capabilities import resolve_node_executor_bindings


async def main():
    profile_name = "profiles/web-standard.yaml"
    print(f"Booting profile: {profile_name}")
    
    try:
        scope = await boot_profile(profile_name)
        print("Profile booted successfully")
        
        # Resolve node executor bindings
        executors = resolve_node_executor_bindings(scope)
        
        print(f"\nFound {len(executors)} node executors:")
        for name in sorted(executors.keys()):
            print(f"  - {name}")
        
        # Check for stop executors
        stop_executors = [name for name in executors.keys() if 'stop' in name]
        print(f"\nStop-related executors ({len(stop_executors)}):")
        for name in stop_executors:
            print(f"  - {name}")
            
        if not stop_executors:
            print("\n❌ No stop executors found!")
            return 1
        else:
            print(f"\n✅ Found {len(stop_executors)} stop executors")
            return 0
            
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
