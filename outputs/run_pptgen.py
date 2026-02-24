#!/usr/bin/env python3
"""
Install npm dependencies and generate the Election 2024 PPT
"""
import subprocess
import sys
import os

def run_command(cmd, description):
    """Run a command and return its success status"""
    print(f"\n{description}...")
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            cwd="/Users/admin/work/agent_loop/outputs"
        )
        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return result.returncode == 0
    except Exception as e:
        print(f"Error: {e}")
        return False

def main():
    os.chdir("/Users/admin/work/agent_loop/outputs")
    
    # Step 1: Install npm dependencies
    success = run_command("npm install", "Installing npm dependencies (pptxgenjs)")
    if not success:
        print("Failed to install npm dependencies")
        sys.exit(1)
    
    # Step 2: Generate the PPT
    success = run_command("node election_ppt.js", "Generating Election 2024 PPT")
    if not success:
        print("Failed to generate PPT")
        sys.exit(1)
    
    # Step 3: Verify the file exists
    print("\nVerifying generated file...")
    result = subprocess.run(
        "ls -lh /Users/admin/work/agent_loop/outputs/US_Election_2024.pptx",
        shell=True,
        capture_output=True,
        text=True
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    
    print("\nPPT generation complete!")
    print("File: /Users/admin/work/agent_loop/outputs/US_Election_2024.pptx")

if __name__ == "__main__":
    main()
