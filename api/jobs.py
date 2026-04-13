import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from celery import Celery
import redis

from api.config import settings

celery_app = Celery("molecopilot", broker=settings.redis_url)
celery_app.conf.result_backend = settings.redis_url

PROJECT_ROOT = Path(settings.data_root)

def _publish_and_buffer(r, job_id: str, event: str, payload: dict):
    """Publish to pub/sub AND buffer in Redis list (fixes SSE race condition)."""
    msg = json.dumps({"event": event, "payload": payload})
    r.rpush(f"job:{job_id}:events", msg)
    r.expire(f"job:{job_id}:events", 3600)  # expire after 1 hour
    r.publish(f"job:{job_id}", msg)

@celery_app.task
def run_dock_job(job_id: str, params: dict):
    """Run the 7-step docking pipeline as a background job."""
    from api.db import update_job, save_protein, save_compound, save_docking_run
    r = redis.from_url(settings.redis_url)
    update_job(job_id, status="running")

    try:
        # Step 1: Fetch protein
        _publish_and_buffer(r, job_id, "progress", {"step": "Fetching protein...", "step_num": 1})
        from core.fetch_pdb import fetch_protein, get_protein_info
        prot = fetch_protein(params["pdb_id"])
        pdb_path = prot["file_path"]

        # Step 2: Detect binding site
        _publish_and_buffer(r, job_id, "progress", {"step": "Detecting binding site...", "step_num": 2})
        from core.prep_protein import detect_binding_site
        binding_site = detect_binding_site(pdb_path)
        center = (binding_site["center_x"], binding_site["center_y"], binding_site["center_z"])
        box_size = (binding_site["size_x"], binding_site["size_y"], binding_site["size_z"])

        # Step 3: Prepare protein
        _publish_and_buffer(r, job_id, "progress", {"step": "Preparing protein...", "step_num": 3})
        from core.prep_protein import prepare_protein
        prep_result = prepare_protein(pdb_path)
        protein_pdbqt = prep_result["pdbqt_path"]

        # Step 4: Resolve compound
        _publish_and_buffer(r, job_id, "progress", {"step": "Resolving compound...", "step_num": 4})
        from core.utils import validate_smiles
        from core.fetch_compounds import search_pubchem, smiles_to_sdf
        compound_input = params.get("compound_input", "")
        compound_cid = None
        iupac_name = None
        compound_formula = None
        if validate_smiles(compound_input):
            smiles = compound_input
            compound_name = compound_input[:30]
        else:
            search_results = search_pubchem(compound_input, max_results=1)
            if not search_results:
                raise ValueError(f"Compound not found: {compound_input}")
            smiles = search_results[0]["smiles"]
            compound_name = search_results[0].get("name", compound_input)
            compound_cid = search_results[0].get("cid")
            iupac_name = search_results[0].get("iupac_name")
            compound_formula = search_results[0].get("formula")

        # Step 5: Prepare ligand
        _publish_and_buffer(r, job_id, "progress", {"step": "Preparing ligand...", "step_num": 5})
        sdf_result = smiles_to_sdf(smiles, compound_name)
        from core.prep_ligand import prepare_ligand
        lig_result = prepare_ligand(sdf_result["sdf_path"])
        ligand_pdbqt = lig_result["pdbqt_path"]

        # Step 6: Dock
        _publish_and_buffer(r, job_id, "progress", {"step": "Running AutoDock Vina...", "step_num": 6})
        from core.dock_vina import dock
        exhaustiveness = params.get("exhaustiveness", 32)
        dock_result = dock(
            protein_pdbqt=protein_pdbqt,
            ligand_pdbqt=ligand_pdbqt,
            center=center,
            box_size=box_size,
            exhaustiveness=exhaustiveness,
        )

        # Step 7: ADMET
        _publish_and_buffer(r, job_id, "progress", {"step": "Running ADMET analysis...", "step_num": 7})
        from core.admet_check import full_admet
        admet_result = full_admet(smiles)

        # Step 8: Enrichment (best-effort, never blocks result)
        _publish_and_buffer(r, job_id, "progress", {"step": "Enriching with external databases...", "step_num": 8})

        admetlab_data = None
        uniprot_data = None
        target_summary = None

        protein_info = get_protein_info(params["pdb_id"])

        def _enrich_admetlab():
            try:
                from core.admet_check import admetlab_profile
                return admetlab_profile(smiles)
            except Exception:
                return None

        def _enrich_protein_context():
            _uniprot = None
            _target = None
            try:
                accession = protein_info.get("uniprot_accession")
                if accession:
                    from core.literature import get_uniprot_info, get_target_summary
                    _uniprot = get_uniprot_info(uniprot_id=accession)
                    _target = get_target_summary(accession)
            except Exception:
                pass
            return _uniprot, _target

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                future_admet = executor.submit(_enrich_admetlab)
                future_protein = executor.submit(_enrich_protein_context)

                try:
                    admetlab_data = future_admet.result(timeout=60)
                except Exception:
                    pass

                try:
                    uniprot_data, target_summary = future_protein.result(timeout=60)
                except Exception:
                    pass
        except Exception:
            pass

        # Save to Supabase
        user_id = params.get("user_id")
        protein_id = save_protein(
            created_by=user_id, pdb_id=params["pdb_id"],
            title=protein_info.get("title"), organism=protein_info.get("organism"),
            resolution=protein_info.get("resolution"), method=protein_info.get("method"),
            pdb_path=pdb_path, pdbqt_path=protein_pdbqt, binding_site=binding_site,
        )["id"]
        compound_id = save_compound(
            created_by=user_id, name=compound_name, smiles=smiles,
            cid=str(compound_cid) if compound_cid else None,
            admet=admet_result, drug_likeness_score=admet_result.get("drug_likeness_score"),
        )["id"]
        run = save_docking_run(
            user_id=user_id, protein_id=protein_id, compound_id=compound_id,
            best_energy=dock_result["best_energy"], all_energies=dock_result["all_energies"],
            exhaustiveness=exhaustiveness, center=center, size=box_size,
            output_path=dock_result["output_path"],
        )

        result_data = {
            "run_id": run["id"],
            "best_energy": dock_result["best_energy"],
            "all_energies": dock_result.get("all_energies", []),
            "all_poses": dock_result.get("all_poses", []),
            "n_poses": dock_result["n_poses"],
            "compound": compound_name,
            "protein": params["pdb_id"],
            "smiles": smiles,
            "compound_cid": compound_cid,
            "iupac_name": iupac_name,
            "formula": compound_formula,
            "output_path": dock_result.get("output_path"),
            "receptor_path": dock_result.get("receptor"),
            "ligand_path": dock_result.get("ligand"),
            "protein_info": protein_info,
            "binding_site": binding_site,
            "admet": admet_result,
            "drug_likeness_score": admet_result.get("drug_likeness_score"),
            "sa_score": admet_result.get("sa_score"),
            "sa_assessment": admet_result.get("synthetic_assessment"),
            "uniprot": uniprot_data,
            "target_summary": target_summary,
            "admetlab": admetlab_data,
        }
        update_job(job_id, status="complete", result=result_data)
        _publish_and_buffer(r, job_id, "complete", result_data)

    except Exception as e:
        update_job(job_id, status="failed", error=str(e))
        _publish_and_buffer(r, job_id, "error", {"error": str(e)})


@celery_app.task
def run_chat_job(job_id: str, session_id: str, message: str):
    """Run Claude Code chat as a background job with streaming."""
    from api.db import update_job, save_chat_message
    r = redis.from_url(settings.redis_url)
    update_job(job_id, status="running")

    proc = None
    try:
        import threading
        proc = subprocess.Popen(
            ["claude", "-p", message, "--output-format", "stream-json",
             "--verbose", "--dangerously-skip-permissions"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            cwd=str(PROJECT_ROOT),
        )

        watchdog = threading.Timer(1800, lambda: proc.kill())
        watchdog.start()

        accumulated = []
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                etype = event.get("type", "")
                if etype == "assistant":
                    for block in event.get("message", {}).get("content", []):
                        if block.get("type") == "text":
                            accumulated.append(block["text"])
                            _publish_and_buffer(r, job_id, "progress", {"text": "".join(accumulated)})
                elif etype == "result":
                    result_text = event.get("result", "")
                    if result_text:
                        accumulated = [result_text]
        finally:
            watchdog.cancel()

        proc.wait(timeout=10)
        response = "".join(accumulated)

        save_chat_message(session_id, role="assistant", content=response)
        update_job(job_id, status="complete", result={"response": response})
        _publish_and_buffer(r, job_id, "complete", {"text": response})

    except Exception as e:
        update_job(job_id, status="failed", error=str(e))
        _publish_and_buffer(r, job_id, "error", {"error": str(e)})
    finally:
        if proc and proc.poll() is None:
            proc.kill()
            proc.wait()


@celery_app.task
def run_optimize_job(job_id: str, params: dict):
    """Run BioNeMo optimization as a background job."""
    from api.db import update_job
    r = redis.from_url(settings.redis_url)
    update_job(job_id, status="running")

    try:
        _publish_and_buffer(r, job_id, "progress", {"step": "Running molecular optimization..."})
        from core.bionemo import sample_analogs, optimize_molecules

        smiles = params["smiles"]
        if params.get("property_name"):
            result = optimize_molecules(
                smiles=smiles,
                property_name=params.get("property_name", "qed"),
                num_molecules=params.get("num_molecules", 10),
                min_similarity=params.get("min_similarity", 0.3),
            )
        else:
            result = sample_analogs(
                smiles=smiles,
                num_molecules=params.get("num_molecules", 10),
                scaled_radius=params.get("scaled_radius", 1.0),
            )

        update_job(job_id, status="complete", result=result)
        _publish_and_buffer(r, job_id, "complete", result)

    except Exception as e:
        update_job(job_id, status="failed", error=str(e))
        _publish_and_buffer(r, job_id, "error", {"error": str(e)})
