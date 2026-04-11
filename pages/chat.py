"""
MoleCopilot — Claude Code Chatbot with Rich Output

Sends user prompts to the Claude Code CLI (claude -p) and displays responses.
After each call, diffs the DB to detect new docking runs, compounds, and proteins,
then renders inline visualizations (charts, ADMET tables, images).
Chat history is persisted in SQLite.
"""

import streamlit as st
import subprocess
import json
import re
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

PROJECT_ROOT = Path(__file__).parent.parent

st.title("MoleCopilot Chat")
st.caption("Powered by Claude Code — full pipeline access with inline results")

from components.database import (
    get_chat_history, save_chat_message,
    get_db_snapshot, get_new_records_since,
    get_connection,
)

# ---------------------------------------------------------------------------
# Initialize chat history from DB
# ---------------------------------------------------------------------------

if "messages" not in st.session_state:
    try:
        history = get_chat_history(limit=50)
        st.session_state.messages = [
            {"role": m["role"], "content": m["content"], "artifacts": None}
            for m in history
        ]
    except Exception:
        st.session_state.messages = []


# ---------------------------------------------------------------------------
# Helpers: extract file paths and render rich output
# ---------------------------------------------------------------------------

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg"}
_FILE_PATTERN = re.compile(r'(?:/[\w./-]+\.(?:png|jpg|jpeg|gif|svg|pdb|pdbqt|sdf|csv|docx|pdf|xlsx))')


def _extract_file_paths(text: str) -> list[str]:
    """Find absolute file paths in response text."""
    paths = _FILE_PATTERN.findall(text)
    return [p for p in paths if Path(p).exists()]


def _render_artifacts(artifacts: dict):
    """Render rich output panel for new DB records and files."""
    if not artifacts:
        return

    new_runs = artifacts.get("docking_runs", [])
    new_compounds = artifacts.get("compounds", [])
    new_proteins = artifacts.get("proteins", [])
    image_paths = artifacts.get("images", [])

    has_content = new_runs or new_compounds or image_paths

    if not has_content:
        return

    st.divider()

    # ── New docking runs ───────────────────────────────────────────────
    if new_runs:
        st.markdown("**New Docking Results**")
        cols = st.columns(min(len(new_runs), 4))
        for i, run in enumerate(new_runs):
            col = cols[i % len(cols)]
            energy = run.get("best_energy")
            compound = run.get("compound_name", "Unknown")
            protein = run.get("protein_pdb_id", "?")

            if energy is not None and energy < -9.0:
                quality = "Excellent"
            elif energy is not None and energy < -8.0:
                quality = "Strong"
            elif energy is not None and energy < -7.0:
                quality = "Moderate"
            else:
                quality = "Weak"

            col.metric(
                f"{compound} vs {protein}",
                f"{energy:.1f} kcal/mol" if energy else "N/A",
                help=quality,
            )

        # Energy bar chart if multiple runs
        if len(new_runs) > 1:
            try:
                from components.charts import energy_bar_chart
                fig = energy_bar_chart(new_runs)
                st.plotly_chart(fig, use_container_width=True)
            except Exception:
                pass

        # Action buttons
        btn_cols = st.columns(3)
        if btn_cols[0].button("View in 3D", key="chat_3d"):
            st.switch_page("pages/viewer_3d.py")
        if btn_cols[1].button("Full Results", key="chat_results"):
            st.switch_page("pages/results.py")
        if btn_cols[2].button("Export Report", key="chat_export"):
            st.switch_page("pages/results.py")

    # ── New ADMET results ──────────────────────────────────────────────
    admet_compounds = [c for c in new_compounds if c.get("admet_json")]
    if admet_compounds:
        st.markdown("**ADMET Results**")
        for compound in admet_compounds:
            admet = compound["admet_json"]
            if not isinstance(admet, dict):
                continue
            name = compound.get("name") or compound.get("smiles", "Unknown")[:30]

            with st.expander(f"{name} — Score: {compound.get('drug_likeness_score', 'N/A')}", expanded=len(admet_compounds) == 1):
                acol1, acol2 = st.columns([1, 1])

                with acol1:
                    # Lipinski table
                    lip = admet.get("lipinski", {})
                    if lip:
                        import pandas as pd
                        st.markdown("**Lipinski Rule of 5**")
                        st.dataframe(pd.DataFrame({
                            "Property": ["MW", "LogP", "HBD", "HBA"],
                            "Value": [lip.get("mw", "?"), lip.get("logp", "?"),
                                      lip.get("hbd", "?"), lip.get("hba", "?")],
                            "Limit": ["≤500", "≤5", "≤5", "≤10"],
                        }), hide_index=True, use_container_width=True)

                with acol2:
                    try:
                        from components.charts import admet_radar
                        fig = admet_radar(admet, compound_name=name)
                        st.plotly_chart(fig, use_container_width=True)
                    except Exception:
                        pass

    # ── Images ─────────────────────────────────────────────────────────
    if image_paths:
        st.markdown("**Generated Images**")
        img_cols = st.columns(min(len(image_paths), 3))
        for i, img_path in enumerate(image_paths):
            col = img_cols[i % len(img_cols)]
            col.image(img_path, caption=Path(img_path).name)


# ---------------------------------------------------------------------------
# Display existing messages
# ---------------------------------------------------------------------------

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("artifacts"):
            _render_artifacts(msg["artifacts"])

# ---------------------------------------------------------------------------
# Chat input
# ---------------------------------------------------------------------------

if prompt := st.chat_input("Ask about docking, compounds, targets..."):
    # Add and display user message
    st.session_state.messages.append({"role": "user", "content": prompt, "artifacts": None})
    try:
        save_chat_message("user", prompt)
    except Exception:
        pass

    with st.chat_message("user"):
        st.markdown(prompt)

    # Snapshot DB state before the call
    try:
        snapshot_before = get_db_snapshot()
    except Exception:
        snapshot_before = None

    # Call Claude Code CLI with streaming output
    with st.chat_message("assistant"):
        # Build conversation context from recent messages
        recent = st.session_state.messages[-10:]
        if len(recent) > 1:
            context_lines = []
            for msg in recent[:-1]:
                role = "User" if msg["role"] == "user" else "Assistant"
                content = msg["content"][:500]
                context_lines.append(f"{role}: {content}")
            context = "\n".join(context_lines)
            full_prompt = (
                f"Previous conversation:\n{context}\n\n"
                f"User: {prompt}"
            )
        else:
            full_prompt = prompt

        placeholder = st.empty()
        response = ""
        proc = None

        try:
            proc = subprocess.Popen(
                ["claude", "-p", full_prompt,
                 "--output-format", "stream-json", "--verbose",
                 "--dangerously-skip-permissions"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                cwd=str(PROJECT_ROOT),
            )

            # Set a 30-minute watchdog
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

                    # Extract text from assistant content chunks
                    if etype == "assistant":
                        for block in event.get("message", {}).get("content", []):
                            if block.get("type") == "text":
                                accumulated.append(block["text"])
                                placeholder.markdown("".join(accumulated))

                    # Final result — use as the definitive response
                    elif etype == "result":
                        result_text = event.get("result", "")
                        if result_text:
                            accumulated = [result_text]
                            placeholder.markdown(result_text)
            finally:
                watchdog.cancel()

            proc.wait(timeout=10)
            response = "".join(accumulated)

            if proc.returncode != 0 and not response:
                response = "Claude returned an error. Try a simpler query."

        except subprocess.TimeoutExpired:
            if proc:
                proc.kill()
            partial = "".join(accumulated) if accumulated else ""
            response = partial + ("\n\n---\n*Request timed out (30 min limit). Partial response shown above.*" if partial else "Request timed out (30 min limit). Try a simpler query.")
        except FileNotFoundError:
            response = (
                "Claude Code CLI not found. "
                "Install: `npm install -g @anthropic-ai/claude-code`"
            )
        finally:
            if proc and proc.poll() is None:
                proc.kill()
                proc.wait()

        if response:
            placeholder.markdown(response)

        # ── Detect new DB records + images ─────────────────────────────
        artifacts = None
        try:
            if snapshot_before:
                new_records = get_new_records_since(snapshot_before)
                image_paths = [p for p in _extract_file_paths(response)
                               if Path(p).suffix.lower() in _IMAGE_EXTS]

                artifacts = {
                    "docking_runs": new_records.get("docking_runs", []),
                    "compounds": new_records.get("compounds", []),
                    "proteins": new_records.get("proteins", []),
                    "images": image_paths,
                }

                _render_artifacts(artifacts)
        except Exception:
            pass

    # Save assistant response
    st.session_state.messages.append({
        "role": "assistant",
        "content": response,
        "artifacts": artifacts,
    })
    try:
        save_chat_message("assistant", response)
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------

with st.sidebar:
    st.subheader("Chat Controls")

    if st.button("Clear Chat History", key="clear_chat"):
        st.session_state.messages = []
        try:
            conn = get_connection()
            try:
                conn.execute("DELETE FROM chat_history")
                conn.commit()
            finally:
                conn.close()
        except Exception:
            pass
        st.rerun()

    st.markdown("---")
    st.markdown("**Example prompts:**")
    st.caption("- Dock aspirin against aromatase (3S7S)")
    st.caption("- Is CC(=O)Oc1ccccc1C(=O)O drug-like?")
    st.caption("- Search PubMed for BACE1 marine natural products")
    st.caption("- Compare aspirin, ibuprofen, and naproxen")
    st.caption("- Draw the structure of thymoquinone")
    st.caption("- Screen top 5 aromatase inhibitors from ChEMBL")
