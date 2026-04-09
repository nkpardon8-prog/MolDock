import plotly.graph_objects as go
import plotly.express as px


# Shared dark layout defaults
_DARK_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#FAFAFA", family="sans-serif"),
    margin=dict(l=20, r=20, t=40, b=20),
)


def energy_bar_chart(runs: list[dict]) -> go.Figure:
    """Horizontal bar chart of binding energies for docking runs.

    Parameters
    ----------
    runs : list of dict
        Each dict must have 'compound_name' and 'best_energy' keys.

    Returns
    -------
    go.Figure
    """
    if not runs:
        fig = go.Figure()
        fig.update_layout(
            title="No docking runs to display",
            **_DARK_LAYOUT,
        )
        return fig

    # Filter out runs with missing energy, then sort (most negative first)
    valid_runs = [r for r in runs if r.get("best_energy") is not None]
    if not valid_runs:
        fig = go.Figure()
        fig.update_layout(title="No docking runs to display", **_DARK_LAYOUT)
        return fig

    sorted_runs = sorted(valid_runs, key=lambda r: r["best_energy"])

    names = [r.get("compound_name") or r.get("name") or "Unknown" for r in sorted_runs]
    energies = [r["best_energy"] for r in sorted_runs]

    # Color coding: green < -8, gold -8 to -7, red > -7
    colors = []
    for e in energies:
        if e < -8.0:
            colors.append("#00D4AA")  # strong binder — green/teal
        elif e <= -7.0:
            colors.append("#FFD700")  # moderate — gold
        else:
            colors.append("#FF4B4B")  # weak — red

    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            y=names,
            x=energies,
            orientation="h",
            marker=dict(color=colors, line=dict(width=0)),
            text=[f"{e:.1f}" for e in energies],
            textposition="outside",
            textfont=dict(color="#FAFAFA", size=11),
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Binding Energy: %{x:.2f} kcal/mol<extra></extra>"
            ),
        )
    )

    # Threshold line at -7.0 kcal/mol
    fig.add_vline(
        x=-7.0,
        line_dash="dash",
        line_color="#FFD700",
        line_width=1.5,
        annotation_text="-7.0 kcal/mol",
        annotation_position="top",
        annotation_font_color="#FFD700",
        annotation_font_size=10,
    )

    fig.update_layout(
        title=dict(
            text="Binding Energies (kcal/mol)",
            font=dict(size=16),
        ),
        xaxis=dict(
            title="Binding Energy (kcal/mol)",
            gridcolor="rgba(255,255,255,0.1)",
            zeroline=False,
        ),
        yaxis=dict(
            title="",
            autorange="reversed",
            gridcolor="rgba(255,255,255,0.1)",
        ),
        height=max(300, len(names) * 40 + 100),
        **_DARK_LAYOUT,
    )

    return fig


def admet_radar(admet_dict: dict, compound_name: str = "Compound") -> go.Figure:
    """Radar chart of ADMET / drug-likeness properties.

    Axes are normalized to 0-1 based on Lipinski/Veber thresholds:
        MW: 0-500, LogP: 0-5, HBD: 0-5, HBA: 0-10,
        RotBonds: 0-10, TPSA: 0-140

    Parameters
    ----------
    admet_dict : dict
        Keys can be any of: MW/molecular_weight, LogP/logp, HBD/hbd,
        HBA/hba, RotBonds/rotatable_bonds, TPSA/tpsa.
    compound_name : str
        Label for the compound trace.

    Returns
    -------
    go.Figure
    """
    # Axis definitions: (label, max_value, dict_keys_to_try)
    axes = [
        ("MW", 500, ["MW", "molecular_weight", "mol_weight"]),
        ("LogP", 5, ["LogP", "logp", "log_p"]),
        ("HBD", 5, ["HBD", "hbd", "h_bond_donors"]),
        ("HBA", 10, ["HBA", "hba", "h_bond_acceptors"]),
        ("RotBonds", 10, ["RotBonds", "rotatable_bonds", "rot_bonds"]),
        ("TPSA", 140, ["TPSA", "tpsa"]),
    ]

    labels = []
    raw_values = []
    normalized_values = []
    max_values = []

    for label, max_val, keys in axes:
        value = None
        for k in keys:
            if k in admet_dict and admet_dict[k] is not None:
                try:
                    value = float(admet_dict[k])
                except (ValueError, TypeError):
                    continue
                break
        labels.append(label)
        max_values.append(max_val)
        if value is not None:
            raw_values.append(value)
            normalized_values.append(min(value / max_val, 1.5))  # cap at 1.5
        else:
            raw_values.append(None)
            normalized_values.append(0)

    # Close the polygon by repeating the first point
    labels_closed = labels + [labels[0]]
    norm_closed = normalized_values + [normalized_values[0]]

    # Ideal range: all properties at their threshold (normalized = 1.0)
    ideal_values = [1.0] * len(labels) + [1.0]

    fig = go.Figure()

    # Ideal range fill
    fig.add_trace(
        go.Scatterpolar(
            r=ideal_values,
            theta=labels_closed,
            fill="toself",
            fillcolor="rgba(0, 212, 170, 0.08)",
            line=dict(color="rgba(0, 212, 170, 0.3)", dash="dash", width=1),
            name="Ideal Limit",
            hoverinfo="skip",
        )
    )

    # Compound values
    hover_texts = []
    for i, label in enumerate(labels):
        if raw_values[i] is not None:
            hover_texts.append(
                f"{label}: {raw_values[i]:.1f} / {max_values[i]}"
            )
        else:
            hover_texts.append(f"{label}: N/A")
    hover_texts.append(hover_texts[0])  # close

    fig.add_trace(
        go.Scatterpolar(
            r=norm_closed,
            theta=labels_closed,
            fill="toself",
            fillcolor="rgba(0, 212, 170, 0.25)",
            line=dict(color="#00D4AA", width=2),
            marker=dict(size=6, color="#00D4AA"),
            name=compound_name,
            text=hover_texts,
            hoverinfo="text",
        )
    )

    fig.update_layout(
        title=dict(
            text=f"Drug-Likeness Profile: {compound_name}",
            font=dict(size=14),
        ),
        polar=dict(
            bgcolor="rgba(0,0,0,0)",
            radialaxis=dict(
                visible=True,
                range=[0, 1.2],
                tickvals=[0.25, 0.5, 0.75, 1.0],
                ticktext=["25%", "50%", "75%", "100%"],
                gridcolor="rgba(255,255,255,0.1)",
                linecolor="rgba(255,255,255,0.1)",
                tickfont=dict(size=9, color="#AAAAAA"),
            ),
            angularaxis=dict(
                gridcolor="rgba(255,255,255,0.15)",
                linecolor="rgba(255,255,255,0.15)",
                tickfont=dict(size=11, color="#FAFAFA"),
            ),
        ),
        showlegend=True,
        legend=dict(
            font=dict(size=10, color="#FAFAFA"),
            bgcolor="rgba(0,0,0,0)",
        ),
        height=450,
        **_DARK_LAYOUT,
    )

    return fig


def energy_histogram(runs: list[dict]) -> go.Figure:
    """Histogram of binding energy distribution from docking runs.

    Parameters
    ----------
    runs : list of dict
        Each dict should have 'best_energy' or 'binding_energy'.

    Returns
    -------
    go.Figure
    """
    energies = []
    for r in runs:
        e = r.get("best_energy") or r.get("binding_energy")
        if e is not None:
            energies.append(float(e))

    if not energies:
        fig = go.Figure()
        fig.update_layout(
            title="No energy data to display",
            **_DARK_LAYOUT,
        )
        return fig

    fig = go.Figure()

    fig.add_trace(
        go.Histogram(
            x=energies,
            nbinsx=min(30, max(5, len(energies) // 3)),
            marker=dict(color="#00D4AA", line=dict(color="#FAFAFA", width=0.5)),
            opacity=0.85,
            hovertemplate="Energy: %{x:.1f} kcal/mol<br>Count: %{y}<extra></extra>",
        )
    )

    # Threshold line at -7.0
    fig.add_vline(
        x=-7.0,
        line_dash="dash",
        line_color="#FF4B4B",
        line_width=1.5,
        annotation_text="-7.0 kcal/mol",
        annotation_position="top",
        annotation_font_color="#FF4B4B",
        annotation_font_size=10,
    )

    fig.update_layout(
        title=dict(
            text="Binding Energy Distribution",
            font=dict(size=16),
        ),
        xaxis=dict(
            title="Binding Energy (kcal/mol)",
            gridcolor="rgba(255,255,255,0.1)",
        ),
        yaxis=dict(
            title="Count",
            gridcolor="rgba(255,255,255,0.1)",
        ),
        height=400,
        **_DARK_LAYOUT,
    )

    return fig
