#!/bin/bash
# Setup and generate Election 2024 PPT

cd /Users/admin/work/agent_loop/outputs

echo "Installing npm dependencies..."
npm install

echo "Generating PPT..."
node election_ppt.js

echo ""
echo "Done! Checking file..."
ls -lh US_Election_2024.pptx
