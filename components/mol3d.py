import py3Dmol
from pathlib import Path


def render_complex(
    protein_pdb: str,
    ligand_pdb: str = None,
    interactions: dict = None,
    show_surface: bool = False,
    show_hbonds: bool = True,
    style: str = "cartoon",
) -> py3Dmol.view:
    """Build a py3Dmol view of a protein-ligand complex.

    Parameters
    ----------
    protein_pdb : str
        Path to the protein PDB file.
    ligand_pdb : str, optional
        Path to the ligand PDB/SDF file.
    interactions : dict, optional
        PLIP interaction data with 'hydrogen_bonds' list.
        Each H-bond entry may contain 'donor_coords' and 'acceptor_coords'
        as [x, y, z] lists.
    show_surface : bool
        Whether to render a translucent VDW surface on the protein.
    show_hbonds : bool
        Whether to draw hydrogen bonds as dashed yellow cylinders
        (requires coordinate data in interactions).
    style : str
        Protein style: "cartoon", "stick", "sphere", "line".

    Returns
    -------
    py3Dmol.view
    """
    view = py3Dmol.view(width=800, height=600)

    # Add protein
    with open(protein_pdb) as f:
        view.addModel(f.read(), "pdb")
    view.setStyle({"model": 0}, {style: {"color": "spectrum"}})

    # Add ligand if provided
    if ligand_pdb and Path(ligand_pdb).exists():
        ligand_path = Path(ligand_pdb)
        fmt = ligand_path.suffix.lstrip(".").lower()
        if fmt == "pdbqt":
            fmt = "pdb"
        elif fmt not in ("pdb", "sdf", "mol2", "xyz"):
            fmt = "pdb"

        with open(ligand_pdb) as f:
            view.addModel(f.read(), fmt)
        view.setStyle(
            {"model": 1},
            {"stick": {"colorscheme": "greenCarbon", "radius": 0.2}},
        )

    # Surface
    if show_surface:
        view.addSurface(
            py3Dmol.VDW,
            {"opacity": 0.5, "color": "white"},
            {"model": 0},
        )

    # H-bonds as dashed yellow cylinders
    if show_hbonds and interactions:
        for hb in interactions.get("hydrogen_bonds", []):
            donor = hb.get("donor_coords")
            acceptor = hb.get("acceptor_coords")
            if donor and acceptor and len(donor) == 3 and len(acceptor) == 3:
                view.addCylinder(
                    {
                        "start": {"x": donor[0], "y": donor[1], "z": donor[2]},
                        "end": {
                            "x": acceptor[0],
                            "y": acceptor[1],
                            "z": acceptor[2],
                        },
                        "color": "yellow",
                        "radius": 0.07,
                        "dashed": True,
                        "dashLength": 0.25,
                        "gapLength": 0.15,
                    }
                )

    view.zoomTo()
    return view


def render_protein(pdb_path: str, style: str = "cartoon") -> py3Dmol.view:
    """Render just a protein structure.

    Parameters
    ----------
    pdb_path : str
        Path to the PDB file.
    style : str
        Visualization style: "cartoon", "stick", "sphere", "line".

    Returns
    -------
    py3Dmol.view
    """
    view = py3Dmol.view(width=800, height=600)
    with open(pdb_path) as f:
        view.addModel(f.read(), "pdb")
    view.setStyle({style: {"color": "spectrum"}})
    view.zoomTo()
    return view
