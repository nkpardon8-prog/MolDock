#!/bin/bash
set -e
echo "=== MoleCopilot Environment Setup ==="
echo ""

# Check conda
if ! command -v conda &> /dev/null; then
    echo "ERROR: conda not found. Install Miniconda or Anaconda first."
    exit 1
fi

# Create conda env
echo "Creating conda environment (Python 3.12)..."
conda create -n molecopilot python=3.12 -y

# Install conda-forge packages
echo "Installing scientific packages from conda-forge..."
conda install -n molecopilot -c conda-forge \
    vina rdkit pdbfixer openmm openbabel prolif \
    numpy pandas matplotlib seaborn pillow -y

# Install pip packages
echo "Installing Python packages via pip..."
conda run -n molecopilot pip install \
    meeko plip mcp py3Dmol biopython requests \
    python-docx fpdf2 openpyxl chembl-webresource-client gemmi \
    streamlit stmol plotly

# Verify
echo ""
echo "Verifying imports..."
conda run -n molecopilot python "$(dirname "$0")/tests/verify_imports.py"

echo ""
echo "=== Setup complete! ==="
echo "MCP server: conda run -n molecopilot python $(dirname "$0")/mcp_server.py"
echo "Dashboard:  conda run -n molecopilot streamlit run $(dirname "$0")/app.py"
