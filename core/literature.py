"""
MoleCopilot literature and biological-database queries.

Provides helpers to search PubMed, retrieve known active compounds
from ChEMBL, and fetch protein metadata from UniProt.  Every function
returns a plain JSON-serialisable dict/list so callers can embed the
results directly into reports or pipeline state.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from core.utils import setup_logging, REPORTS_DIR, RESULTS_DIR, ensure_dir, load_env

logger = setup_logging("literature")

# ---------------------------------------------------------------------------
# PubMed
# ---------------------------------------------------------------------------


def search_pubmed(query: str, max_results: int = 10) -> list[dict]:
    """Search PubMed via NCBI Entrez and return structured article records.

    Parameters
    ----------
    query : str
        Free-text PubMed search query (e.g. ``"aromatase inhibitor docking"``).
    max_results : int, optional
        Maximum number of articles to retrieve (default 10, capped at 200).

    Returns
    -------
    list[dict]
        Each dict contains the keys ``pmid``, ``title``, ``authors``,
        ``journal``, ``year``, ``abstract``, and ``doi``.
    """
    from Bio import Entrez

    Entrez.email = "molecopilot@users.noreply.github.com"
    env = load_env()
    if "NCBI_API_KEY" in env:
        Entrez.api_key = env["NCBI_API_KEY"]

    max_results = min(max_results, 200)
    logger.info("Searching PubMed: %r  (max %d)", query, max_results)

    # -- Step 1: ESearch for PMIDs ---------------------------------------------
    search_handle = Entrez.esearch(db="pubmed", term=query, retmax=max_results)
    search_record = Entrez.read(search_handle)
    search_handle.close()
    ids: list[str] = search_record.get("IdList", [])

    if not ids:
        logger.warning("PubMed returned 0 results for %r", query)
        return []

    logger.info("Found %d PubMed IDs, fetching details ...", len(ids))

    # -- Step 2: EFetch full XML records ---------------------------------------
    fetch_handle = Entrez.efetch(db="pubmed", id=ids, rettype="xml")
    records = Entrez.read(fetch_handle)
    fetch_handle.close()

    articles: list[dict] = []
    for pubmed_article in records.get("PubmedArticle", []):
        medline = pubmed_article.get("MedlineCitation", {})
        article_data = medline.get("Article", {})

        # PMID
        pmid = str(medline.get("PMID", ""))

        # Title
        title = str(article_data.get("ArticleTitle", ""))

        # Authors
        author_list_raw = article_data.get("AuthorList", [])
        authors: list[str] = []
        for author in author_list_raw:
            last = author.get("LastName", "")
            first = author.get("ForeName", "")
            if last:
                authors.append(f"{last} {first}".strip())

        # Journal
        journal_info = article_data.get("Journal", {})
        journal = str(journal_info.get("Title", ""))

        # Year — prefer ArticleDate, fall back to PubDate, then MedlineDate
        year = ""
        journal_issue = journal_info.get("JournalIssue", {})
        pub_date = journal_issue.get("PubDate", {})
        if "Year" in pub_date:
            year = str(pub_date["Year"])
        elif "MedlineDate" in pub_date:
            # MedlineDate often starts with the year, e.g. "2023 Jan-Feb"
            md = str(pub_date["MedlineDate"])
            match = re.match(r"(\d{4})", md)
            if match:
                year = match.group(1)

        # Abstract
        abstract_parts = article_data.get("Abstract", {}).get("AbstractText", [])
        abstract = " ".join(str(part) for part in abstract_parts)

        # DOI — scan ELocationID list
        doi = ""
        for eloc in article_data.get("ELocationID", []):
            if getattr(eloc, "attributes", {}).get("EIdType", "") == "doi":
                doi = str(eloc)
                break
        # Fallback: scan ArticleIdList in PubmedData
        if not doi:
            pubmed_data = pubmed_article.get("PubmedData", {})
            for aid in pubmed_data.get("ArticleIdList", []):
                if getattr(aid, "attributes", {}).get("IdType", "") == "doi":
                    doi = str(aid)
                    break

        articles.append({
            "pmid": pmid,
            "title": title,
            "authors": authors,
            "journal": journal,
            "year": year,
            "abstract": abstract,
            "doi": doi,
        })

    logger.info("Parsed %d articles from PubMed", len(articles))
    return articles


# ---------------------------------------------------------------------------
# ChEMBL — known actives
# ---------------------------------------------------------------------------


def get_known_actives(
    target_name: Optional[str] = None,
    uniprot_id: Optional[str] = None,
    chembl_id: Optional[str] = None,
) -> dict:
    """Retrieve known active compounds for a biological target from ChEMBL.

    At least one of *target_name*, *uniprot_id*, or *chembl_id* must be
    provided.  The function resolves the target's ChEMBL ID, then pulls
    IC50/Ki/EC50 activity records together with compound SMILES.

    Parameters
    ----------
    target_name : str, optional
        Human-readable target name to search (e.g. ``"Aromatase"``).
    uniprot_id : str, optional
        UniProt accession (e.g. ``"P11511"``).
    chembl_id : str, optional
        ChEMBL target ID (e.g. ``"CHEMBL1978"``).

    Returns
    -------
    dict
        Keys: ``target``, ``target_chembl_id``, ``compounds`` (list of
        dicts with ``name``, ``smiles``, ``activity_type``,
        ``activity_value``, ``activity_units``), and ``message``.
    """
    from chembl_webresource_client.new_client import new_client

    target_api = new_client.target
    activity_api = new_client.activity
    molecule_api = new_client.molecule

    result: dict = {
        "target": "",
        "target_chembl_id": "",
        "compounds": [],
        "message": "",
    }

    # -- Resolve target ChEMBL ID --------------------------------------------
    resolved_chembl_id: str = ""
    resolved_name: str = ""

    if chembl_id:
        resolved_chembl_id = chembl_id
        logger.info("Using provided ChEMBL ID: %s", chembl_id)
        # Fetch name for output
        targets = target_api.filter(target_chembl_id=chembl_id)
        targets_list = list(targets)
        if targets_list:
            resolved_name = targets_list[0].get("pref_name", chembl_id)
        else:
            resolved_name = chembl_id

    elif uniprot_id:
        logger.info("Searching ChEMBL target by UniProt: %s", uniprot_id)
        targets = target_api.get(
            target_components__accession=uniprot_id
        )
        targets_list = list(targets) if targets else []
        if not targets_list:
            result["message"] = f"No ChEMBL target found for UniProt {uniprot_id}"
            logger.warning(result["message"])
            return result
        resolved_chembl_id = targets_list[0]["target_chembl_id"]
        resolved_name = targets_list[0].get("pref_name", resolved_chembl_id)

    elif target_name:
        logger.info("Searching ChEMBL target by name: %r", target_name)
        targets = target_api.search(target_name)
        targets_list = list(targets) if targets else []
        if not targets_list:
            result["message"] = f"No ChEMBL target found matching '{target_name}'"
            logger.warning(result["message"])
            return result
        # Take the first SINGLE PROTEIN match, falling back to the first hit
        chosen = targets_list[0]
        for t in targets_list:
            if t.get("target_type") == "SINGLE PROTEIN":
                chosen = t
                break
        resolved_chembl_id = chosen["target_chembl_id"]
        resolved_name = chosen.get("pref_name", resolved_chembl_id)

    else:
        result["message"] = "Provide at least one of target_name, uniprot_id, or chembl_id."
        logger.error(result["message"])
        return result

    result["target"] = resolved_name
    result["target_chembl_id"] = resolved_chembl_id
    logger.info("Resolved target: %s (%s)", resolved_name, resolved_chembl_id)

    # -- Fetch activities (IC50, Ki, EC50) ------------------------------------
    activity_types = ["IC50", "Ki", "EC50"]
    logger.info("Fetching activities for %s ...", resolved_chembl_id)

    activities = activity_api.filter(
        target_chembl_id=resolved_chembl_id,
        standard_type__in=activity_types,
        standard_relation="=",
    ).only([
        "molecule_chembl_id",
        "canonical_smiles",
        "standard_type",
        "standard_value",
        "standard_units",
        "pchembl_value",
    ])

    seen_molecules: set[str] = set()
    compounds: list[dict] = []

    for act in activities:
        mol_id = act.get("molecule_chembl_id", "")
        if not mol_id or mol_id in seen_molecules:
            continue
        seen_molecules.add(mol_id)

        smiles = act.get("canonical_smiles", "")
        activity_type = act.get("standard_type", "")
        activity_value = act.get("standard_value")
        activity_units = act.get("standard_units", "")

        # Try to resolve a human-readable name for the molecule
        name = mol_id
        try:
            mol_record = molecule_api.get(mol_id)
            if mol_record:
                pref = mol_record.get("pref_name")
                if pref:
                    name = pref
        except Exception:
            pass  # keep mol_id as the name

        if activity_value is not None:
            try:
                activity_value = float(activity_value)
            except (TypeError, ValueError):
                pass

        compounds.append({
            "name": name,
            "smiles": smiles,
            "activity_type": activity_type,
            "activity_value": activity_value,
            "activity_units": activity_units,
        })

    result["compounds"] = compounds
    result["message"] = f"Retrieved {len(compounds)} unique compounds with IC50/Ki/EC50 data."
    logger.info(result["message"])
    return result


# ---------------------------------------------------------------------------
# UniProt
# ---------------------------------------------------------------------------


def get_uniprot_info(
    uniprot_id: Optional[str] = None,
    protein_name: Optional[str] = None,
) -> dict:
    """Fetch protein metadata from UniProt.

    Provide either *uniprot_id* (accession, e.g. ``"P11511"``) for a
    direct lookup, or *protein_name* for a free-text search (returns the
    top hit).

    Parameters
    ----------
    uniprot_id : str, optional
        UniProt accession.
    protein_name : str, optional
        Protein name or keyword to search.

    Returns
    -------
    dict
        Keys: ``name``, ``organism``, ``function``, ``domains`` (list),
        ``subcellular_location``, ``disease_associations`` (list),
        ``pdb_structures`` (list), ``sequence_length`` (int).
    """
    import requests

    base_url = "https://rest.uniprot.org/uniprotkb"

    result: dict = {
        "name": "",
        "organism": "",
        "function": "",
        "domains": [],
        "subcellular_location": "",
        "disease_associations": [],
        "pdb_structures": [],
        "sequence_length": 0,
    }

    # -- Fetch JSON record ----------------------------------------------------
    data: dict = {}

    if uniprot_id:
        url = f"{base_url}/{uniprot_id}?format=json"
        logger.info("Fetching UniProt entry: %s", uniprot_id)
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200:
            logger.error("UniProt returned HTTP %d for %s", resp.status_code, uniprot_id)
            result["name"] = f"Error: HTTP {resp.status_code}"
            return result
        data = resp.json()

    elif protein_name:
        url = f"{base_url}/search?query={requests.utils.quote(protein_name)}&format=json&size=1"
        logger.info("Searching UniProt for: %r", protein_name)
        resp = requests.get(url, timeout=30)
        if resp.status_code != 200:
            logger.error("UniProt search returned HTTP %d", resp.status_code)
            result["name"] = f"Error: HTTP {resp.status_code}"
            return result
        payload = resp.json()
        results_list = payload.get("results", [])
        if not results_list:
            logger.warning("UniProt returned 0 results for %r", protein_name)
            result["name"] = "No results found"
            return result
        data = results_list[0]

    else:
        logger.error("Provide either uniprot_id or protein_name")
        result["name"] = "Error: no identifier provided"
        return result

    # -- Parse common fields --------------------------------------------------

    # Protein name — prefer recommendedName, fall back to submittedName
    protein_desc = data.get("proteinDescription", {})
    rec_name = protein_desc.get("recommendedName", {})
    if rec_name:
        result["name"] = rec_name.get("fullName", {}).get("value", "")
    else:
        sub_names = protein_desc.get("submissionNames", [])
        if sub_names:
            result["name"] = sub_names[0].get("fullName", {}).get("value", "")

    # Organism
    organism_data = data.get("organism", {})
    result["organism"] = organism_data.get("scientificName", "")

    # Comments: function, subcellular location, disease
    for comment in data.get("comments", []):
        comment_type = comment.get("commentType", "")

        if comment_type == "FUNCTION":
            texts = comment.get("texts", [])
            if texts:
                result["function"] = texts[0].get("value", "")

        elif comment_type == "SUBCELLULAR LOCATION":
            locations = comment.get("subcellularLocations", [])
            loc_names: list[str] = []
            for loc in locations:
                loc_val = loc.get("location", {}).get("value", "")
                if loc_val:
                    loc_names.append(loc_val)
            result["subcellular_location"] = "; ".join(loc_names)

        elif comment_type == "DISEASE":
            disease = comment.get("disease", {})
            disease_name = disease.get("diseaseId", "")
            if disease_name:
                desc = disease.get("description", "")
                entry = disease_name
                if desc:
                    entry = f"{disease_name}: {desc}"
                result["disease_associations"].append(entry)

    # Features: domains
    for feature in data.get("features", []):
        if feature.get("type", "") == "Domain":
            desc = feature.get("description", "")
            if desc:
                result["domains"].append(desc)

    # Cross-references: PDB structures
    for xref in data.get("uniProtKBCrossReferences", []):
        if xref.get("database", "") == "PDB":
            pdb_id = xref.get("id", "")
            if pdb_id:
                result["pdb_structures"].append(pdb_id)

    # Sequence length
    sequence_data = data.get("sequence", {})
    result["sequence_length"] = sequence_data.get("length", 0)

    logger.info(
        "UniProt: %s | organism=%s | seq_len=%d | PDB=%d",
        result["name"],
        result["organism"],
        result["sequence_length"],
        len(result["pdb_structures"]),
    )
    return result


# ---------------------------------------------------------------------------
# Perplexity Sonar Pro
# ---------------------------------------------------------------------------


def search_perplexity(query: str, timeframe: str = "all_time") -> dict:
    """Search for research papers/findings via Perplexity Sonar Pro.

    Parameters
    ----------
    query : str
        Free-text research topic.
    timeframe : str
        ``"recent"`` (last year) or ``"all_time"`` (no filter).

    Returns
    -------
    dict
        Keys: ``summary`` (narrative with inline [1][2] refs),
        ``citations`` (URL list), ``search_results`` (rich objects),
        ``query``, ``timeframe``.
    """
    import requests as _requests

    env = load_env()
    api_key = env.get("PERPLEXITY_API_KEY")
    if not api_key:
        raise ValueError(
            "PERPLEXITY_API_KEY not set in .env \u2014 "
            "add your key to the .env file in the project root"
        )

    logger.info("Searching Perplexity: %r  (timeframe=%s)", query, timeframe)

    system_prompt = (
        "You are a scientific research assistant specializing in pharmacology, "
        "medicinal chemistry, and drug discovery. Search for research papers, "
        "discoveries, and findings on the given topic. For each finding, provide: "
        "the key discovery or result, the authors/group, the journal, and year. "
        "Cite your sources using numbered references [1], [2], etc. "
        "Focus on peer-reviewed publications and credible scientific sources. "
        "Return up to 10 distinct findings."
    )

    body: dict = {
        "model": "sonar-pro",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ],
        "search_mode": "academic",
        "search_domain_filter": [
            "pubmed.ncbi.nlm.nih.gov",
            "nature.com",
            "sciencedirect.com",
            "springer.com",
            "wiley.com",
            "acs.org",
            "rsc.org",
            "mdpi.com",
        ],
        "web_search_options": {"search_context_size": "high"},
        "return_related_questions": False,
    }

    if timeframe == "recent":
        body["search_recency_filter"] = "year"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    resp = _requests.post(
        "https://api.perplexity.ai/chat/completions",
        headers=headers,
        json=body,
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()

    result = {
        "summary": data["choices"][0]["message"]["content"],
        "citations": data.get("citations", []),
        "search_results": data.get("search_results", []),
        "query": query,
        "timeframe": timeframe,
    }

    logger.info(
        "Perplexity returned %d citations, %d search_results",
        len(result["citations"]),
        len(result["search_results"]),
    )
    return result


# ---------------------------------------------------------------------------
# Standalone demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json as _json

    print("=" * 70)
    print("MoleCopilot Literature Module — Standalone Demo")
    print("=" * 70)

    # -- PubMed search ---------------------------------------------------------
    print("\n--- PubMed Search: 'aromatase inhibitor docking' (max 3) ---\n")
    try:
        articles = search_pubmed("aromatase inhibitor docking", max_results=3)
        for i, art in enumerate(articles, 1):
            print(f"  [{i}] PMID {art['pmid']}")
            print(f"      Title  : {art['title'][:90]}...")
            print(f"      Authors: {', '.join(art['authors'][:3])}")
            print(f"      Journal: {art['journal']}  ({art['year']})")
            print(f"      DOI    : {art['doi']}")
            print()
    except Exception as exc:
        logger.error("PubMed demo failed: %s", exc)
        print(f"  [SKIPPED] PubMed search failed: {exc}")

    # -- UniProt lookup --------------------------------------------------------
    print("\n--- UniProt Info: P11511 (Aromatase) ---\n")
    try:
        info = get_uniprot_info(uniprot_id="P11511")
        print(f"  Name     : {info['name']}")
        print(f"  Organism : {info['organism']}")
        print(f"  Seq len  : {info['sequence_length']}")
        print(f"  Domains  : {info['domains'][:5]}")
        print(f"  PDB IDs  : {info['pdb_structures'][:5]}")
        print(f"  Function : {info['function'][:120]}...")
        print()
    except Exception as exc:
        logger.error("UniProt demo failed: %s", exc)
        print(f"  [SKIPPED] UniProt lookup failed: {exc}")

    # -- ChEMBL known actives --------------------------------------------------
    print("\n--- ChEMBL Known Actives: 'Aromatase' (by name) ---\n")
    try:
        actives = get_known_actives(target_name="Aromatase")
        print(f"  Target       : {actives['target']}")
        print(f"  ChEMBL ID    : {actives['target_chembl_id']}")
        print(f"  # Compounds  : {len(actives['compounds'])}")
        for cpd in actives["compounds"][:5]:
            val = cpd["activity_value"]
            print(
                f"    - {cpd['name'][:30]:30s}  {cpd['activity_type']:5s} "
                f"= {val} {cpd['activity_units']}"
            )
        print(f"  Message      : {actives['message']}")
    except Exception as exc:
        logger.error("ChEMBL demo failed: %s", exc)
        print(f"  [SKIPPED] ChEMBL query failed: {exc}")

    print("\n" + "=" * 70)
    print("Demo complete.")
