"""
MoleCopilot — Literature & Database Search

Four tabs for searching PubMed, ChEMBL known actives, UniProt
protein metadata, and AI-powered research via Perplexity Sonar Pro.
All searches are persisted to the database for later review.
ChEMBL results include a "Dock this" button that saves the compound
to the database and pre-fills the Dock page.
"""

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
import pandas as pd

from components.database import (
    save_compound,
    get_compound_by_smiles,
    save_literature_search,
    get_literature_searches,
    get_all_literature_tags,
    update_literature_search,
    delete_literature_search,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_tags(query: str) -> list[str]:
    """Extract meaningful tags from a search query."""
    stop_words = {
        "the", "and", "for", "with", "from", "that", "this", "are", "was",
        "were", "been", "being", "have", "has", "had", "does", "did", "will",
        "would", "could", "should", "may", "might", "can", "about", "into",
        "through", "during", "before", "after", "above", "below", "between",
        "not", "but", "what", "which", "who", "how", "new", "recent", "latest",
    }
    words = re.sub(r'[^\w\s-]', '', query.lower()).split()
    tags = [w for w in words if w not in stop_words and len(w) >= 3]
    seen = set()
    unique = []
    for t in tags:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique[:5]


def _load_cached_search(search):
    """Load a saved search's cached results into the appropriate session_state key."""
    source = search["source_type"]
    results = search.get("results_json")

    if source == "perplexity":
        st.session_state["perplexity_result"] = results
    elif source == "chembl":
        st.session_state["chembl_result"] = results
    elif source == "uniprot":
        st.session_state["uniprot_result"] = results
    elif source == "pubmed":
        st.session_state["pubmed_result"] = results


def _refresh_search(search_record):
    """Re-run a saved search and update its DB record."""
    source = search_record["source_type"]
    query = search_record["query"]

    if source == "perplexity":
        from core.literature import search_perplexity
        tf = search_record.get("timeframe") or "all_time"
        new_results = search_perplexity(query, timeframe=tf)
    elif source == "pubmed":
        from core.literature import search_pubmed
        new_results = search_pubmed(query, max_results=10)
    elif source == "chembl":
        from core.literature import get_known_actives
        new_results = get_known_actives(target_name=query)
    elif source == "uniprot":
        from core.literature import get_uniprot_info
        new_results = get_uniprot_info(protein_name=query)
    else:
        return

    update_literature_search(search_record["id"], results=new_results)
    _load_cached_search({**search_record, "results_json": new_results})


# ---------------------------------------------------------------------------
# Page header
# ---------------------------------------------------------------------------

st.title("Literature & Database Search")
st.caption("Search PubMed, ChEMBL, UniProt, and AI-powered research from one place")


# ---------------------------------------------------------------------------
# Saved Searches Section (above tabs)
# ---------------------------------------------------------------------------

saved_searches = get_literature_searches(limit=50)
all_tags = get_all_literature_tags()

if saved_searches:
    with st.expander(f"Saved Searches ({len(saved_searches)})", expanded=False):
        col_filter1, col_filter2 = st.columns(2)
        with col_filter1:
            filter_sources = st.multiselect(
                "Source",
                ["pubmed", "chembl", "uniprot", "perplexity"],
                default=[],
                key="filter_src",
            )
        with col_filter2:
            filter_tags = st.multiselect(
                "Tags", all_tags, default=[], key="filter_tags"
            )

        filtered = saved_searches
        if filter_sources:
            filtered = [s for s in filtered if s["source_type"] in filter_sources]
        if filter_tags:
            filtered = [
                s for s in filtered
                if any(t in (s.get("tags_json") or []) for t in filter_tags)
            ]

        source_badge = {
            "pubmed": "PubMed",
            "chembl": "ChEMBL",
            "uniprot": "UniProt",
            "perplexity": "AI Research",
        }

        for search in filtered:
            col1, col2, col3, col4 = st.columns([4, 1, 1, 1])
            with col1:
                badge = source_badge.get(search["source_type"], "")
                query_preview = search["query"][:60]
                if len(search["query"]) > 60:
                    query_preview += "..."
                st.markdown(
                    f"**{badge}** | {query_preview} | "
                    f"{search['result_count']} results | "
                    f"{search['created_at'][:10]}"
                )
                tags = search.get("tags_json") or []
                if tags:
                    st.caption(" ".join(f"`{t}`" for t in tags))
            with col2:
                if st.button("View", key=f"view_{search['id']}"):
                    _load_cached_search(search)
                    st.rerun()
            with col3:
                if st.button("Refresh", key=f"refresh_{search['id']}"):
                    with st.spinner("Refreshing..."):
                        try:
                            _refresh_search(search)
                        except Exception as exc:
                            st.error(f"Refresh failed: {exc}")
                    st.rerun()
            with col4:
                if st.button("Delete", key=f"del_{search['id']}"):
                    delete_literature_search(search["id"])
                    st.rerun()


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_pubmed, tab_chembl, tab_uniprot, tab_perplexity = st.tabs(
    ["PubMed", "ChEMBL", "UniProt", "AI Research"]
)


# ---------------------------------------------------------------------------
# PubMed
# ---------------------------------------------------------------------------

with tab_pubmed:
    st.subheader("PubMed Literature Search")

    pubmed_query = st.text_input(
        "Search query",
        placeholder='e.g. "aromatase inhibitor docking"',
        key="pubmed_query",
    )
    pubmed_max = st.slider(
        "Max results", min_value=5, max_value=50, value=10, key="pubmed_max"
    )

    if st.button("Search PubMed", key="pubmed_search_btn"):
        if not pubmed_query.strip():
            st.warning("Please enter a search query.")
        else:
            with st.spinner("Searching PubMed..."):
                try:
                    from core.literature import search_pubmed

                    articles = search_pubmed(
                        pubmed_query.strip(), max_results=pubmed_max
                    )
                except Exception as exc:
                    st.error(f"PubMed search failed: {exc}")
                    articles = []

            if articles:
                st.session_state["pubmed_result"] = articles
                st.success(f"Found {len(articles)} article(s)")

                try:
                    save_literature_search(
                        query=pubmed_query.strip(),
                        source_type="pubmed",
                        results=articles,
                        tags=_generate_tags(pubmed_query),
                    )
                except Exception:
                    pass
            else:
                st.info("No results found. Try broadening your search.")

    # Display results (from fresh search or loaded from saved)
    pubmed_articles = st.session_state.get("pubmed_result")
    if pubmed_articles:
        table_data = []
        for art in pubmed_articles:
            authors_str = ", ".join(art.get("authors", [])[:3])
            if len(art.get("authors", [])) > 3:
                authors_str += " et al."
            table_data.append(
                {
                    "PMID": art.get("pmid", ""),
                    "Title": art.get("title", ""),
                    "Authors": authors_str,
                    "Journal": art.get("journal", ""),
                    "Year": art.get("year", ""),
                }
            )

        df = pd.DataFrame(table_data)
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Title": st.column_config.TextColumn(width="large"),
            },
        )

        for art in pubmed_articles:
            abstract = art.get("abstract", "").strip()
            doi = art.get("doi", "")
            pmid = art.get("pmid", "")
            title = art.get("title", "Untitled")

            header = f"PMID {pmid}: {title[:80]}"
            if len(title) > 80:
                header += "..."

            with st.expander(header):
                if abstract:
                    st.markdown(abstract)
                else:
                    st.info("No abstract available.")
                if doi:
                    st.markdown(
                        f"[View on publisher](https://doi.org/{doi})"
                    )
                st.markdown(
                    f"[View on PubMed](https://pubmed.ncbi.nlm.nih.gov/{pmid}/)"
                )


# ---------------------------------------------------------------------------
# ChEMBL — Known Actives
# ---------------------------------------------------------------------------

with tab_chembl:
    st.subheader("ChEMBL Known Actives")
    st.caption(
        "Search for known active compounds against a biological target. "
        "Results include IC50, Ki, and EC50 data."
    )

    chembl_target = st.text_input(
        "Target name",
        placeholder="e.g. Aromatase, BACE1, HIF-2alpha",
        key="chembl_target",
    )

    if st.button("Search ChEMBL", key="chembl_search_btn"):
        if not chembl_target.strip():
            st.warning("Please enter a target name.")
        else:
            with st.spinner(
                f"Querying ChEMBL for '{chembl_target.strip()}'... "
                "This may take a minute."
            ):
                try:
                    from core.literature import get_known_actives

                    result = get_known_actives(target_name=chembl_target.strip())
                except Exception as exc:
                    st.error(f"ChEMBL query failed: {exc}")
                    result = {"compounds": [], "message": str(exc)}

            st.session_state["chembl_result"] = result

            if result.get("compounds"):
                try:
                    save_literature_search(
                        query=chembl_target.strip(),
                        source_type="chembl",
                        results=result,
                        tags=_generate_tags(chembl_target),
                    )
                except Exception:
                    pass

    # Display results (persisted across reruns via session_state)
    chembl_result = st.session_state.get("chembl_result")
    if chembl_result:
        target_name = chembl_result.get("target", "")
        target_id = chembl_result.get("target_chembl_id", "")
        compounds = chembl_result.get("compounds", [])
        message = chembl_result.get("message", "")

        if target_name:
            st.markdown(f"**Target:** {target_name} (`{target_id}`)")
        if message:
            st.info(message)

        if compounds:
            table_data = []
            for cpd in compounds:
                val = cpd.get("activity_value")
                val_str = f"{val:.2f}" if isinstance(val, (int, float)) else str(val or "N/A")
                table_data.append(
                    {
                        "Name": cpd.get("name", "Unknown"),
                        "SMILES": cpd.get("smiles", ""),
                        "Type": cpd.get("activity_type", ""),
                        "Value": val_str,
                        "Units": cpd.get("activity_units", ""),
                    }
                )

            df = pd.DataFrame(table_data)
            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "SMILES": st.column_config.TextColumn(width="medium"),
                },
            )

            st.markdown("---")
            st.markdown("**Select a compound to dock:**")

            for i, cpd in enumerate(compounds):
                smiles = cpd.get("smiles", "")
                name = cpd.get("name", "Unknown")
                if not smiles:
                    continue

                col1, col2 = st.columns([3, 1])
                with col1:
                    st.text(f"{name} — {smiles[:60]}{'...' if len(smiles) > 60 else ''}")
                with col2:
                    if st.button("Dock this", key=f"dock_chembl_{i}"):
                        try:
                            existing = get_compound_by_smiles(smiles)
                            if not existing:
                                save_compound(name=name, smiles=smiles)
                        except Exception as exc:
                            st.error(f"Failed to save compound: {exc}")

                        st.session_state["dock_prefill_smiles"] = smiles
                        st.session_state["dock_prefill_name"] = name
                        st.success(
                            f"Saved '{name}' to database. "
                            "Switch to the Dock page to run docking."
                        )


# ---------------------------------------------------------------------------
# UniProt
# ---------------------------------------------------------------------------

with tab_uniprot:
    st.subheader("UniProt Protein Information")

    uniprot_mode = st.radio(
        "Search by",
        options=["Protein name", "UniProt ID"],
        horizontal=True,
        key="uniprot_mode",
    )

    if uniprot_mode == "UniProt ID":
        uniprot_input = st.text_input(
            "UniProt Accession",
            placeholder="e.g. P11511",
            key="uniprot_id_input",
        )
    else:
        uniprot_input = st.text_input(
            "Protein name",
            placeholder="e.g. Aromatase, BACE1",
            key="uniprot_name_input",
        )

    if st.button("Search UniProt", key="uniprot_search_btn"):
        if not uniprot_input.strip():
            st.warning("Please enter a protein name or UniProt ID.")
        else:
            with st.spinner("Querying UniProt..."):
                try:
                    from core.literature import get_uniprot_info

                    if uniprot_mode == "UniProt ID":
                        info = get_uniprot_info(uniprot_id=uniprot_input.strip())
                    else:
                        info = get_uniprot_info(protein_name=uniprot_input.strip())
                except Exception as exc:
                    st.error(f"UniProt query failed: {exc}")
                    info = None

            if info:
                st.session_state["uniprot_result"] = info

                if info.get("name") and not info["name"].startswith("Error"):
                    try:
                        save_literature_search(
                            query=uniprot_input.strip(),
                            source_type="uniprot",
                            results=info,
                            tags=_generate_tags(uniprot_input),
                        )
                    except Exception:
                        pass

    # Display result
    info = st.session_state.get("uniprot_result")
    if info:
        name = info.get("name", "Unknown")
        organism = info.get("organism", "")
        function = info.get("function", "")
        domains = info.get("domains", [])
        subcell = info.get("subcellular_location", "")
        diseases = info.get("disease_associations", [])
        pdb_ids = info.get("pdb_structures", [])
        seq_len = info.get("sequence_length", 0)

        st.markdown(f"### {name}")

        col1, col2, col3 = st.columns(3)
        col1.metric("Organism", organism or "N/A")
        col2.metric("Sequence Length", f"{seq_len:,}" if seq_len else "N/A")
        col3.metric("PDB Structures", len(pdb_ids))

        if function:
            st.markdown("**Function:**")
            st.markdown(function)

        if subcell:
            st.markdown(f"**Subcellular Location:** {subcell}")

        if domains:
            st.markdown("**Domains:**")
            for d in domains:
                st.markdown(f"- {d}")

        if diseases:
            with st.expander(f"Disease Associations ({len(diseases)})"):
                for d in diseases:
                    st.markdown(f"- {d}")

        if pdb_ids:
            with st.expander(f"PDB Structures ({len(pdb_ids)})"):
                cols = st.columns(min(6, len(pdb_ids)))
                for i, pdb_id in enumerate(pdb_ids):
                    with cols[i % len(cols)]:
                        st.markdown(
                            f"[{pdb_id}](https://www.rcsb.org/structure/{pdb_id})"
                        )


# ---------------------------------------------------------------------------
# AI Research (Perplexity Sonar Pro)
# ---------------------------------------------------------------------------

with tab_perplexity:
    st.subheader("AI Research Search")
    st.caption(
        "Search for research papers, discoveries, and findings "
        "using Perplexity Sonar Pro"
    )

    perplexity_query = st.text_input(
        "Research topic",
        placeholder='e.g. "marine depsipeptide cytotoxicity mechanisms"',
        key="perplexity_query",
    )

    col_pq1, col_pq2 = st.columns([3, 1])
    with col_pq2:
        timeframe = st.radio(
            "Timeframe",
            options=["All time", "Recent (last year)"],
            horizontal=True,
            key="perplexity_timeframe",
        )

    if st.button("Search", key="perplexity_search_btn"):
        if not perplexity_query.strip():
            st.warning("Please enter a research topic.")
        else:
            with st.spinner("Searching with Perplexity Sonar Pro..."):
                try:
                    from core.literature import search_perplexity

                    tf = "recent" if "Recent" in timeframe else "all_time"
                    pplx_result = search_perplexity(
                        perplexity_query.strip(), timeframe=tf
                    )
                except ValueError as exc:
                    st.error(str(exc))
                    pplx_result = None
                except Exception as exc:
                    st.error(f"Perplexity search failed: {exc}")
                    pplx_result = None

            if pplx_result:
                st.session_state["perplexity_result"] = pplx_result

                try:
                    save_literature_search(
                        query=perplexity_query.strip(),
                        source_type="perplexity",
                        results=pplx_result,
                        tags=_generate_tags(perplexity_query),
                        timeframe=tf,
                    )
                except Exception:
                    pass

    # Display result (persisted across reruns via session_state)
    pplx_display = st.session_state.get("perplexity_result")
    if pplx_display:
        st.markdown(pplx_display["summary"])

        search_results = pplx_display.get("search_results", [])
        citations = pplx_display.get("citations", [])

        if search_results:
            st.markdown("---")
            st.markdown("### Sources")
            for i, sr in enumerate(search_results, 1):
                title = sr.get("title", "Untitled")
                url = sr.get("url", "")
                date = sr.get("date", "")
                snippet = sr.get("snippet", "")

                with st.expander(f"[{i}] {title}"):
                    if date:
                        st.caption(f"Published: {date}")
                    if snippet:
                        st.markdown(snippet)
                    if url:
                        st.markdown(f"[Open source]({url})")
        elif citations:
            st.markdown("---")
            st.markdown("### Sources")
            for i, url in enumerate(citations, 1):
                st.markdown(f"[{i}] {url}")
