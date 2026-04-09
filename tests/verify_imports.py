#!/usr/bin/env python3
"""Verify all MoleCopilot dependencies are importable."""

deps = [
    ("vina", "AutoDock Vina"),
    ("meeko", "Meeko (ligand prep)"),
    ("rdkit", "RDKit (cheminformatics)"),
    ("Bio", "BioPython"),
    ("requests", "Requests"),
    ("matplotlib", "Matplotlib"),
    ("pandas", "Pandas"),
    ("numpy", "NumPy"),
    ("seaborn", "Seaborn"),
    ("PIL", "Pillow"),
    ("plip", "PLIP (interaction profiler)"),
    ("prolif", "ProLIF (interaction fingerprints)"),
    ("py3Dmol", "py3Dmol (3D viewer)"),
    ("pdbfixer", "PDBFixer"),
    ("openmm", "OpenMM"),
    ("mcp", "MCP SDK"),
    ("docx", "python-docx"),
    ("fpdf", "fpdf2"),
    ("openpyxl", "openpyxl"),
    ("chembl_webresource_client", "ChEMBL client"),
]

# OpenBabel import path detection
ob_imports = [
    ("openbabel.pybel", "Open Babel (openbabel.pybel)"),
    ("openbabel", "Open Babel (openbabel)"),
]

print("MoleCopilot Dependency Check")
print("=" * 50)
passed = 0
failed = 0
for module, name in deps:
    try:
        __import__(module)
        print(f"  ✓ {name}")
        passed += 1
    except ImportError as e:
        print(f"  ✗ {name} — {e}")
        failed += 1

# Try OpenBabel imports
ob_ok = False
for module, name in ob_imports:
    try:
        __import__(module)
        print(f"  ✓ {name}")
        passed += 1
        ob_ok = True
        break
    except ImportError:
        continue
if not ob_ok:
    print(f"  ✗ Open Babel — no working import found")
    failed += 1

print("=" * 50)
print(f"  {passed} passed, {failed} failed")
if failed > 0:
    print("  Fix failed imports before proceeding.")
else:
    print("  All dependencies ready!")
