#!/usr/bin/env python3
"""MoleCopilot end-to-end integration test."""
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

PASSED = 0
FAILED = 0
RESULTS = []

def run_step(name, func):
    global PASSED, FAILED
    print(f"\n{'='*60}")
    print(f"  Step: {name}")
    print(f"{'='*60}")
    try:
        result = func()
        PASSED += 1
        RESULTS.append((name, "PASS", ""))
        return result
    except Exception as e:
        FAILED += 1
        RESULTS.append((name, "FAIL", str(e)))
        print(f"  FAILED: {e}")
        traceback.print_exc()
        return None

if __name__ == "__main__":
    start = time.time()
    print("MoleCopilot Integration Test")
    print("=" * 60)

    # 1. Fetch protein
    def _fetch():
        from core.fetch_pdb import fetch_protein
        result = fetch_protein("3S7S")
        print(f"  Downloaded: {result['file_path']}")
        assert Path(result['file_path']).exists()
        return result
    prot = run_step("1. Fetch PDB 3S7S (human aromatase)", _fetch)

    # 2. Detect binding site
    def _detect():
        from core.prep_protein import detect_binding_site
        site = detect_binding_site(prot["file_path"])
        print(f"  Ligand found: {site['ligand_found']}, name: {site.get('ligand_resname', 'none')}")
        print(f"  Center: ({site['center_x']:.1f}, {site['center_y']:.1f}, {site['center_z']:.1f})")
        print(f"  Box: ({site['size_x']:.1f}, {site['size_y']:.1f}, {site['size_z']:.1f})")
        return site
    site = run_step("2. Detect binding site", _detect) if prot else None

    # 3. Prepare protein
    def _prep_prot():
        from core.prep_protein import prepare_protein
        result = prepare_protein(prot["file_path"])
        print(f"  Clean PDB: {result['clean_pdb']}")
        print(f"  PDBQT: {result['pdbqt_path']}")
        assert Path(result['pdbqt_path']).exists()
        return result
    prepped = run_step("3. Prepare protein", _prep_prot) if prot else None

    # 4. Fetch aspirin
    def _fetch_asp():
        from core.fetch_compounds import search_pubchem, fetch_compound_sdf
        results = search_pubchem("aspirin", max_results=1)
        print(f"  Found: {results[0].get('name', 'aspirin')} (CID: {results[0]['cid']})")
        sdf = fetch_compound_sdf(results[0]['cid'])
        print(f"  SDF: {sdf['sdf_path']}")
        return sdf, results[0].get('smiles', 'CC(=O)Oc1ccccc1C(=O)O')
    aspirin_data = run_step("4. Fetch aspirin from PubChem", _fetch_asp)
    sdf_path = aspirin_data[0]["sdf_path"] if aspirin_data else None
    aspirin_smiles = aspirin_data[1] if aspirin_data else "CC(=O)Oc1ccccc1C(=O)O"

    # 5. Prepare aspirin
    def _prep_asp():
        from core.prep_ligand import prepare_ligand
        result = prepare_ligand(sdf_path)
        print(f"  PDBQT: {result['pdbqt_path']}, Method: {result['method']}")
        assert Path(result['pdbqt_path']).exists()
        return result
    lig = run_step("5. Prepare aspirin for docking", _prep_asp) if sdf_path else None

    # 6. Dock
    def _dock():
        from core.dock_vina import dock
        center = (site["center_x"], site["center_y"], site["center_z"])
        box = (site["size_x"], site["size_y"], site["size_z"])
        result = dock(prepped["pdbqt_path"], lig["pdbqt_path"],
                      center=center, box_size=box, exhaustiveness=8, n_poses=5)
        print(f"  Best energy: {result['best_energy']:.1f} kcal/mol")
        print(f"  Poses: {len(result['all_energies'])}")
        return result
    dock_result = run_step("6. Dock aspirin vs aromatase (exh=8)", _dock) if (prepped and lig and site) else None

    # 7. ADMET aspirin
    def _admet_asp():
        from core.admet_check import full_admet
        r = full_admet(aspirin_smiles)
        print(f"  Score: {r['drug_likeness_score']:.2f} — {r['assessment']}")
        print(f"  Lipinski: {'PASS' if r['lipinski']['passes'] else 'FAIL'}, Veber: {'PASS' if r['veber']['passes'] else 'FAIL'}")
        return r
    admet_result = run_step("7. ADMET on aspirin", _admet_asp)

    # 8. ADMET thymoquinone
    def _admet_tq():
        from core.admet_check import full_admet
        r = full_admet("CC1=CC(=O)C(=CC1=O)C(C)C")
        print(f"  Thymoquinone: {r['drug_likeness_score']:.2f} — {r['assessment']}")
        print(f"  MW={r['mw']:.1f}, LogP={r['logp']:.2f}")
        return r
    run_step("8. ADMET on thymoquinone", _admet_tq)

    # 9. ADMET exemestane
    def _admet_ex():
        from core.admet_check import full_admet
        r = full_admet("CC12CCC3C(C1CCC2=O)CC(=C)C4=CC(=O)C=CC34C")
        print(f"  Exemestane: {r['drug_likeness_score']:.2f} — {r['assessment']}")
        return r
    run_step("9. ADMET on exemestane", _admet_ex)

    # 10. Generate report
    def _report():
        from core.analyze_results import generate_summary
        s = generate_summary(
            docking_results=[{**(dock_result or {}), "name": "aspirin"}],
            admet_results=[{**(admet_result or {}), "name": "aspirin"}],
            project_name="test_pipeline"
        )
        print(f"  Report: {s['report_path']}")
        print(f"  Length: {len(s['markdown'])} chars")
        return s
    run_step("10. Generate summary report", _report)

    # Summary
    elapsed = time.time() - start
    print(f"\n{'='*60}")
    print(f"  RESULTS: {PASSED} passed, {FAILED} failed")
    print(f"  Time: {elapsed:.1f}s")
    print(f"{'='*60}")
    for name, status, err in RESULTS:
        icon = "✓" if status == "PASS" else "✗"
        line = f"  {icon} {name}"
        if err:
            line += f" — {err[:80]}"
        print(line)
