# =============================================================================
#
#   CRISIS — Coupled Regional Rainfall-Induced and Seismic Slope Instability
#            Simulations
#
#   Module  : back_analysis.py
#   Purpose : Back-analysis of mapped landslides to estimate shear strength
#             parameters (cohesion c and friction angle Phi) by finding the
#             modeled landslide that best matches each mapped landslide in
#             location, area, and volume.
#
#   Authors : Mirna Kassem
#             University of California, Berkeley
#             kassem_mirna@berkeley.edu
#
#             Prof. Dimitrios Zekkos
#             University of California, Berkeley
#             zekkos@berkeley.edu
#
#   Standalone / HPC usage
#   ----------------------
#       python back_analysis.py config_back_analysis_windows.json
#
#       from back_analysis import run_model
#       run_model(params)                # params is a plain dict; see crisis_params.py
#
#   This module has NO GUI dependencies and can be executed on HPC systems
#   by importing it directly or via the command-line entry point at the
#   bottom of this file.
#
#   Parallelism
#   -----------
#   Each mapped landslide is processed independently. The code uses Python's
#   ProcessPoolExecutor to run multiple landslides simultaneously, one per CPU
#   core, with true parallelism (each worker gets its own Python interpreter,
#   bypassing the GIL).
#
#   The number of parallel workers is controlled by the 'n_workers' parameter:
#
#     n_workers = null   → uses ALL available CPU cores on the machine
#                          (default; recommended for desktop / laptop use)
#     n_workers = N      → uses exactly N cores, capped at the number of
#                          landslides (no benefit in having more workers than
#                          tasks)
#
#   On HPC (e.g. SLURM), set n_workers to the number of cores allocated to
#   your job so the model does not exceed its allocation:
#       #SBATCH --cpus-per-task=16  →  set n_workers to 16
#
#   For debugging a crash in a worker, set n_workers = 1 to force serial
#   execution, which produces cleaner tracebacks.
#
# =============================================================================


# =============================================================================
# Standard-library and third-party imports
# =============================================================================

import os
import sys
import json
import math
import heapq
import re as _re
import threading
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from multiprocessing import Manager as _Manager

import numpy as np
import pandas as pd
import geopandas as gpd
import h5py
from shapely.geometry import box as _shapely_box
from shapely.ops import unary_union as _unary_union

# matplotlib is only needed for visualisation in the standalone __main__ block;
# importing it at module level forces Tk backend initialisation in every worker
# process, which causes hangs in ProcessPoolExecutor on Windows.
# It is therefore imported lazily inside `if __name__ == '__main__':`.


# =============================================================================
# Terminology
# =============================================================================
#
#  "Local Error"
#  Error computed between a mapped landslide and a modeled landslide for a
#  single (c, Phi) combination.  One (c, Phi) combination may produce multiple
#  modeled landslides; the local error is evaluated for each individually and
#  the minimum is retained.
#
#  "Global Error"
#  After the local-minimum landslide is identified for each (c, Phi) combination,
#  the global error compares all retained combinations.  The combination yielding
#  the smallest global error is selected as the back-calculated shear strength.
#
# =============================================================================


# =============================================================================
# Required inputs — reference guide
# =============================================================================
#
#  RASTER INPUTS  (all HDF5 files; dataset key = 'data')
#  ┌──────────────────────────────────────────────────────────────────────────┐
#  │ File name                      │ Description                              │
#  ├──────────────────────────────────────────────────────────────────────────┤
#  │ DEM.h5                         │ Digital Elevation Model (m), m×n         │
#  │ Pressure_head_T{t}Z{d+1}.h5    │ Pore pressure head (m), one per (t, d)   │
#  │ Theta_T{t}Z{d+1}.h5            │ Volumetric water content, one per (t, d) │
#  │                                │   (only if Strength_variation_with_theta)│
#  ├──────────────────────────────────────────────────────────────────────────┤
#  │ ID.xlsx                        │ Single-column list of mapped landslide   │
#  │                                │   IDs (no header)                        │
#  │ LD{ID}.xlsx                    │ One file per mapped landslide; row 1     │
#  │                                │   must be a header row (any text — read  │
#  │                                │   by column position, not by name — but  │
#  │                                │   row 1 is always skipped, so a missing  │
#  │                                │   header row causes the first data row   │
#  │                                │   to be misread as the header). Row 2    │
#  │                                │   contains the values, in order:         │
#  │                                │   Mapped Area (m^2),                     │
#  │                                │   Mapped Centroid X (m),                 │
#  │                                │   Mapped Centroid Y (m),                 │
#  │                                │   Mapped Volume (m^3)                    │
#  │                                │   Centroid X/Y can be extracted from     │
#  │                                │   GIS software using the same projected  │
#  │                                │   coordinate system as the rest of the   │
#  │                                │   model                                  │
#  └──────────────────────────────────────────────────────────────────────────┘
#
#  Slope, Flow Direction, Flow Accumulation, and the x/y coordinate vectors are
#  no longer separate file inputs — they are all auto-derived from DEM.h5,
#  Cell_size, xmin, and ymin:
#    Slope             via compute_slope_gradient8()            (TopoToolbox gradient8 equivalent)
#    Flow Direction    via compute_flow_direction_topotoolbox()  (TopoToolbox FLOWobj equivalent)
#    Flow Accumulation via compute_flow_accumulation_topotoolbox() (TopoToolbox flowacc equivalent)
#    x, y coordinates  via compute_coordinate_vectors()          (cell centers from the
#                                                                  lower-left corner)
#
#  SCALAR INPUTS
#  ┌──────────────────────────────────────────────────────────────────────────┐
#  │ Parameter                       │ Units │ Description                       │
#  ├──────────────────────────────────────────────────────────────────────────┤
#  │ Cell_size                       │ m     │ Grid cell resolution              │
#  │ Gamma_soil                      │ kN/m³ │ Unit weight of soil               │
#  │ z_min                           │ m     │ Shallowest depth layer centre     │
#  │ z_max                           │ m     │ Deepest depth layer centre        │
#  │ xmin, ymin                      │ m     │ Lower-left DEM cell center (required; used to derive the x/y coordinate vectors) │
#  │ R_search                        │ —     │ Search-radius scaling factor      │
#  │ C_single_min/max/increment      │ kPa   │ Cohesion range                    │
#  │ Phi_single_min/max/increment    │ °     │ Friction angle range              │
#  │ Theta_s                         │ —     │ Saturated volumetric water content│
#  │ Theta_r                         │ —     │ Residual volumetric water content │
#  │ Strength_variation_with_theta   │ —     │ 0 => Bishop coefficient χ=1; 1 => χ varies with saturation │
#  │ Coordinate_Reference_System     │ EPSG  │ CRS for shapefile export          │
#  └──────────────────────────────────────────────────────────────────────────┘
#
#  OUTPUTS
#  ┌──────────────────────────────────────────────────────────────────────────┐
#  │ File                                    │ Description                    					│
#  ├──────────────────────────────────────────────────────────────────────────┤
#  │ Predicted_landslides_time_{ID}.shp      │ Best-matching modeled polygon  					│
#  │ acceptable_combinations_for_LD_{ID}.xlsx│ All (c,Phi) combinations with min total error │
#  │ Back_Calculated_Landslides_Summary.xlsx │ One row per landslide: mean/SD of the         │
#  │                                          │ back-calculated strength parameters, plus an  │
#  │                                          │ Excluded_Landslides sheet for any landslide   │
#  │                                          │ with no positive-effective-stress solution    │
#  └──────────────────────────────────────────────────────────────────────────┘
#
# =============================================================================


# =============================================================================
# Function 1 — Upslope grid cells, method A (inflow-direction check)
# =============================================================================

def T_UpGrid1(FD_Mat, indID):
    """
    Find all upslope (inflow) cells for a target cell using the D8 convention.

    Checks every one of the 8 neighbours: a neighbour is upslope if its D8
    flow direction points back toward the target cell.

    Parameters
    ----------
    FD_Mat : ndarray (m × n)   Flow direction matrix.
    indID  : int                Linear index of the target cell.

    Returns
    -------
    UpGrid_Cells : ndarray      Linear indices of upslope cells (length ≤ 8).
    """
    # Get the grid dimensions and convert the linear index to row/col coordinates
    nrow, ncol = FD_Mat.shape
    T_row, T_col = np.unravel_index(indID, (nrow, ncol))

    # D8 direction codes (ArcGIS convention) mapped to (row offset, col offset)
    directions = {
        1:   (0,  1),   # E
        2:   (1,  1),   # SE
        4:   (1,  0),   # S
        8:   (1, -1),   # SW
        16:  (0, -1),   # W
        32:  (-1, -1),  # NW
        64:  (-1,  0),  # N
        128: (-1,  1),  # NE
    }
    # Opposite direction: a neighbour drains into the target if its D8 code
    # is the opposite of the direction used to reach it from the target
    opposite = {1: 16, 2: 32, 4: 64, 8: 128, 16: 1, 32: 2, 64: 4, 128: 8}

    # Check each of the 8 neighbours for inflow
    UpGrid_Cells = []
    for code, (dr, dc) in directions.items():
        r, c = T_row + dr, T_col + dc
        # Skip neighbours that lie outside the DEM boundary
        if r < 0 or r >= nrow or c < 0 or c >= ncol:
            continue
        # Accept the neighbour only if its flow direction points back to the target
        if FD_Mat[r, c] == opposite[code]:
            lin_idx = np.ravel_multi_index((r, c), (nrow, ncol))
            UpGrid_Cells.append(lin_idx)

    return np.array(UpGrid_Cells, dtype=int)


# =============================================================================
# Function 2 — Vectorised upslope-neighbor precomputation
# =============================================================================

def precompute_upgrid_all(FD_Mat):
    """
    Vectorised one-time precomputation of the upslope neighbors for every cell
    in FD_Mat simultaneously.

    For each cell, identifies the 3 neighboring cells on its upslope side based
    on the cell's own D8 flow direction.  Returns a (total_cells × 3) lookup
    table.  The -1 sentinel marks out-of-bounds slots.

    Usage inside the Breadth-First Search (BFS) expansion:
        up_raw = lookup[index]
        UpGrid_Cells = up_raw[up_raw >= 0]

    Called once per landslide before the (c, Phi, t) loops; eliminates all
    per-cell upslope lookups during BFS traversal.

    Returns
    -------
    lookup : ndarray (total_cells × 3), int64
    """
    nrow, ncol = FD_Mat.shape
    total = nrow * ncol

    # D8 neighbor offsets matching T_UpGrid's D8 table exactly:
    # D8[:, 0] = col offset,  D8[:, 1] = row offset
    D8_col = np.array([ 1,  1,  0, -1, -1, -1,  0,  1], dtype=np.int32)
    D8_row = np.array([ 0,  1,  1,  1,  0, -1, -1, -1], dtype=np.int32)

    # Maps each D8 flow-direction code to the 3 D8 table indices that are
    # upslope — exactly mirrors the if/elif slicing in T_UpGrid
    fd_to_d8 = {
        1:   [3, 4, 5],   # E  → [3:6]     = SW, W, NW
        2:   [4, 5, 6],   # SE → [4:7]     = W, NW, N
        4:   [5, 6, 7],   # S  → [5:8]     = NW, N, NE
        8:   [0, 6, 7],   # SW → [[0,6,7]] = E, N, NE
        16:  [0, 1, 7],   # W  → [[0,1,7]] = E, SE, NE
        32:  [0, 1, 2],   # NW → [0:3]     = E, SE, S
        64:  [1, 2, 3],   # N  → [1:4]     = SE, S, SW
        128: [2, 3, 4],   # NE → [2:5]     = S, SW, W
    }

    # Initialise the lookup table with -1 (invalid / out-of-bounds sentinel)
    lookup = np.full((total, 3), -1, dtype=np.int64)

    # Flatten the (row, col) grid into 1-D arrays of cell coordinates
    row_all, col_all = np.mgrid[0:nrow, 0:ncol]
    row_all  = row_all.ravel().astype(np.int32)
    col_all  = col_all.ravel().astype(np.int32)
    FD_flat  = FD_Mat.ravel()

    # Process one D8 direction code at a time using vectorised numpy operations
    for fd_code, d8_idxs in fd_to_d8.items():
        # Find all cells whose flow direction matches this code
        mask     = FD_flat == fd_code
        if not np.any(mask):
            continue
        r_src    = row_all[mask]
        c_src    = col_all[mask]
        # Flat linear indices of the source cells
        flat_src = r_src.astype(np.int64) * ncol + c_src.astype(np.int64)

        # For each of the 3 upslope neighbor positions, compute neighbor coords
        for pos, d8_i in enumerate(d8_idxs):
            r_n       = r_src + D8_row[d8_i]
            c_n       = c_src + D8_col[d8_i]
            # Keep only neighbors that lie within the DEM boundary
            in_bounds = (r_n >= 0) & (r_n < nrow) & (c_n >= 0) & (c_n < ncol)
            # Store flat neighbor index or -1 for out-of-bounds slots
            nbr       = np.where(in_bounds,
                                 r_n.astype(np.int64) * ncol + c_n.astype(np.int64),
                                 np.int64(-1))
            lookup[flat_src, pos] = nbr

    return lookup


# =============================================================================
# Function 3 — Breadth-First Search (BFS) + refinement for a single (triggering cell, depth) pair
# =============================================================================

def _bfs_single_cell(trig_cell, di, Depths_vector,
                     elev_flat, area_flat, slope_flat,
                     m, n, Cell_size, upgrid_lookup, x, y):
    """
    Run the pseudo-3D Breadth-First Search (BFS) and geometry refinement for
    one (triggering cell, depth index) pair and return the precomputed landslide
    properties.

    The modeled landslide SHAPE depends only on the triggering cell, the
    triggering depth, and the fixed terrain arrays — it is independent of the
    strength parameters (c, Phi) and the time step.  Precomputing this once per
    (cell, depth) combo and caching the result eliminates the BFS bottleneck
    from the inner (c, Phi, t) loop entirely, replacing thousands of BFS calls
    with a few hundred upfront computations.

    Returns
    -------
    dict  with keys {area, vol, cx, cy, trig_index, trig_slope, trig_row,
                     trig_col}, or None if the candidate is invalid / too small.
    """
    # Retrieve the failure depth for this depth index
    depth = float(Depths_vector[di])

    # Skip cells with no contributing area (sinks) or NaN elevation (no-data)
    if area_flat[trig_cell] <= 0 or np.isnan(elev_flat[trig_cell]):
        return None

    # Convert the flat linear index to (row, col) coordinates
    trig_row, trig_col = divmod(int(trig_cell), n)
    Elev_Trig  = float(elev_flat[trig_cell])
    Trig_Slope = float(slope_flat[trig_cell])
    # Failure plane elevation at the triggering cell
    Hf_Trig    = Elev_Trig - depth
    # Precompute tan(slope) for repeated use inside the BFS loop
    tan_ts     = math.tan(math.radians(Trig_Slope))

    # ── Breadth-First Search (BFS): grow the landslide body upslope ──────────
    LD_list = [int(trig_cell)]
    LD_set  = {int(trig_cell)}
    Count   = 0
    while Count < len(LD_list):
        idx    = LD_list[Count]
        # Retrieve precomputed upslope neighbors; drop the -1 out-of-bounds sentinel
        up_raw = upgrid_lookup[idx]
        up     = up_raw[up_raw >= 0]

        # Condition 1: upslope neighbors must have smaller contributing area
        if len(up):
            up = up[area_flat[up] <= area_flat[idx]]
        # Condition 2: upslope neighbors must be at or above the triggering elevation
        if len(up):
            up = up[elev_flat[up] >= Elev_Trig]
        # Condition 3: projected failure depth at each neighbor must be positive
        if len(up):
            ur, uc = np.unravel_index(up, (m, n))
            # Planimetric distance from triggering cell to each candidate neighbor
            dist   = np.sqrt((ur - trig_row)**2 + (uc - trig_col)**2) * Cell_size
            # Failure plane elevation projected outward from the triggering cell
            hf     = Hf_Trig + dist * tan_ts
            # Keep only cells where the surface is above the projected failure plane
            up     = up[elev_flat[up] - hf > 0]

        # Add surviving neighbors to the growing landslide body
        for cell in up.tolist():
            if cell not in LD_set:
                LD_set.add(cell)
                LD_list.append(cell)
        Count += 1

    # Reject degenerate landslides with 2 or fewer cells
    LD = np.array(LD_list, dtype=np.int64)
    if len(LD) <= 2:
        return None

    # ── Geometry refinement: refine the failure plane slope ───────────────────
    Surf  = elev_flat[LD]
    lr, lc = np.unravel_index(LD, (m, n))
    # Planimetric distance from the triggering cell to every landslide cell
    dist  = np.sqrt((lr - trig_row)**2 + (lc - trig_col)**2) * Cell_size
    # Find the highest elevation within the landslide body
    maxE  = float(np.max(Surf))
    minD  = float(np.min(dist[Surf == maxE]))
    # Avoid division by zero for degenerate geometries
    if minD == 0:
        return None
    # Compute refined mean slope from triggering cell to the highest point
    M_sl  = math.ceil(math.degrees(math.atan((maxE - Hf_Trig) / minD)))
    # Rate of slope change along the landslide body (slope gradient)
    dx_sl = (M_sl - Trig_Slope) / minD
    # Recompute failure plane depths using the refined slope profile
    Hf    = Hf_Trig + dist * np.tan(np.radians(Trig_Slope + dist * dx_sl))
    LD_Z  = Surf - Hf
    # Retain only cells where the refined failure depth is still positive
    keep  = LD_Z > 0
    LD    = LD[keep]
    LD_Z  = LD_Z[keep]
    # Final size check after refinement
    if len(LD) <= 2:
        return None

    # ── Compute landslide geometry metrics ────────────────────────────────────
    # Planar area = number of cells × cell area
    area = float(len(LD) * Cell_size ** 2)
    # Volume = sum of failure depths × cell area (prism volumes)
    vol  = float(np.sum(LD_Z) * Cell_size ** 2)

    # Compute centroid coordinates from the coordinate arrays
    lr2, lc2 = np.unravel_index(LD, (m, n))
    lx = x[lc2] if x.ndim == 1 else x[lr2, lc2]
    ly = y[lr2] if y.ndim == 1 else y[lr2, lc2]

    # Return all precomputed properties as a dictionary for O(1) lookup in the inner loop
    return {
        'area':       area,
        'vol':        vol,
        'cx':         float(np.mean(lx)),
        'cy':         float(np.mean(ly)),
        'trig_index': int(trig_cell),
        'trig_slope': Trig_Slope,
        'trig_row':   trig_row,
        'trig_col':   trig_col,
    }


# =============================================================================
# Function 4 — Pseudo-3D landslide delineation
# =============================================================================

def Determine_Pseudo_3D_landslides(Elev_Mat, Trig_Cells, Area_Mat, Slope_Mat,
                                   FD_Mat, Cell_size, Trig_Depths, Pressures,
                                   Indicator, upgrid_lookup=None):
    """
    Form pseudo-3D landslide bodies from triggering cells using upslope BFS.

    Starting from each triggering cell, the algorithm walks upslope through the
    D8 flow network and accumulates all cells satisfying the geometric failure
    criterion.  Cells sorted by descending contributing area are processed first
    so that large-drainage bodies claim their territory before nested cells.

    Parameters
    ----------
    Trig_Depths : ndarray or float
        Per-cell triggering depths (Indicator=1) or a single constant depth (Indicator=2).
    Pressures   : ndarray or float
        Pore pressures at triggering cells.
    Indicator   : int
        1 → Trig_Depths is a vector; 2 → Trig_Depths is a scalar constant.
    upgrid_lookup : ndarray (total_cells × 3)
        Precomputed upslope table from precompute_upgrid_all().

    Returns
    -------
    Vol, Area, FID, NL, Mat_LD_ind,
    Trig_Index_Accept, Trig_Depths_Accept, Pressures_Accept,
    Slope_Trig_Index_Accept, Fail_Index
    """
    # Initialise landslide counter
    NL = 0

    # Flat views of the 2D arrays: avoids repeated 2D indexing inside BFS
    elev_flat  = Elev_Mat.ravel()
    area_flat  = Area_Mat.ravel()
    slope_flat = Slope_Mat.ravel()

    # Retrieve contributing areas at all triggering cells for sorting
    Area_Mat_Trig = area_flat[Trig_Cells]

    # Sort triggering cells by descending contributing area so large-drainage
    # cells are processed before smaller nested cells claim the same territory
    Idx = np.argsort(Area_Mat_Trig)[::-1]
    Trig_Cells_Desc  = np.take(Trig_Cells,  Idx)
    Trig_Depths_Desc = np.take(Trig_Depths, Idx)
    Pressures_Desc   = np.take(Pressures,   Idx)

    # Total number of triggering cells to process
    NTC = len(Trig_Cells_Desc)

    # Initialise output accumulators
    Vol                     = []
    Area                    = []
    Trig_Index_Accept       = []
    Slope_Trig_Index_Accept = []
    Mat_LD_ind              = []
    Trig_Depths_Accept      = []
    Pressures_Accept        = []

    # DEM dimensions for index conversions
    m, n = Elev_Mat.shape

    # Landslide ID grid: NaN where no landslide has been assigned
    FID = np.full((m, n), np.nan, dtype=np.float32)
    # Boolean failure grid: True where a cell already belongs to a landslide
    Fail_Index = np.zeros((m, n), dtype=bool)

    # ── Loop over all triggering cells ────────────────────────────────────────
    for j in range(NTC):

        # Initialise the candidate landslide as an ordered list (BFS traversal)
        # and a set (O(1) membership checks replace O(N) setdiff1d per BFS step)
        LD_Index_list = [Trig_Cells_Desc[j]]
        LD_Index_set  = {Trig_Cells_Desc[j]}

        # Extract triggering cell index and its pore pressure
        Trig_Index = Trig_Cells_Desc[j]
        Pressure   = Pressures_Desc[j]

        # Convert the flat linear index to (row, col) for distance calculations
        Trig_Index_row, Trig_Index_col = np.unravel_index(Trig_Index, (m, n))

        # Assign triggering depth — either per-cell or constant, based on Indicator
        if Indicator == 1:
            Trig_Depth_cell = Trig_Depths_Desc[j]
        elif Indicator == 2:
            Trig_Depth_cell = Trig_Depths

        Count = 0

        # Only proceed if the triggering cell has non-zero contributing area
        if area_flat[Trig_Index] > 0:

            Elev_Trig  = elev_flat[Trig_Index]
            Trig_Slope = slope_flat[Trig_Index]

            # Failure plane elevation at the triggering cell
            Hf_Trig = Elev_Trig - Trig_Depth_cell
            # Precompute tan(slope) to avoid repeated computation inside the BFS loop
            tan_ts  = math.tan(math.radians(Trig_Slope))

            # ── Breadth-First Search (BFS): grow the landslide body upslope ──
            while Count < len(LD_Index_list):

                index = LD_Index_list[Count]

                # Retrieve precomputed upslope neighbors; drop -1 out-of-bounds sentinel
                _up_raw      = upgrid_lookup[index]
                UpGrid_Cells = _up_raw[_up_raw >= 0]

                Acc_Area_n      = area_flat[index]
                Acc_Area_UpGrid = area_flat[UpGrid_Cells]

                # Condition 1: upslope neighbors must have smaller contributing area
                UpGrid_Cells = UpGrid_Cells[Acc_Area_UpGrid <= Acc_Area_n]

                # Condition 2: upslope neighbors must be at or above the triggering elevation
                Elev_Upgrid  = elev_flat[UpGrid_Cells]
                UpGrid_Cells = UpGrid_Cells[Elev_Upgrid >= Elev_Trig]

                # Convert surviving neighbors to (row, col) for distance calculation
                UpGrid_row, UpGrid_col = np.unravel_index(UpGrid_Cells, (m, n))

                # Planimetric distance from the triggering cell to each neighbor
                UpGrid_dist = np.sqrt(
                    (UpGrid_row - Trig_Index_row)**2 +
                    (UpGrid_col - Trig_Index_col)**2
                ) * Cell_size

                # Projected failure plane elevation at each neighbor
                UpGrid_Hf = Hf_Trig + UpGrid_dist * tan_ts

                # Condition 3: surface elevation must exceed the failure plane
                UpGrid_Elev_surv = elev_flat[UpGrid_Cells]
                UpGrid_Z         = UpGrid_Elev_surv - UpGrid_Hf
                UpGrid_Cells     = UpGrid_Cells[UpGrid_Z > 0]

                # Add surviving neighbors to the landslide body without duplicates
                for cell in UpGrid_Cells.tolist():
                    if cell not in LD_Index_set:
                        LD_Index_set.add(cell)
                        LD_Index_list.append(cell)

                Count += 1

            # ── Geometry refinement and acceptance check ──────────────────────
            LD_Index = np.array(LD_Index_list)

            if len(LD_Index) > 2:

                Surf_Elev = elev_flat[LD_Index]
                LD_row, LD_col = np.unravel_index(LD_Index, (m, n))

                # Planimetric distances from triggering cell to all landslide cells
                LD_dist = np.sqrt(
                    (LD_row - Trig_Index_row)**2 +
                    (LD_col - Trig_Index_col)**2
                ) * Cell_size

                # Find the highest elevation and its distance from the triggering cell
                Max_elev    = np.max(Surf_Elev)
                Min_LD_dist = np.min(LD_dist[Surf_Elev == Max_elev])

                Elev_diff = Max_elev - Hf_Trig

                if Min_LD_dist == 0:
                    # Degenerate geometry: triggering cell is already at the maximum
                    Acceptable_LS = False
                else:
                    # Refined mean slope from triggering cell to the highest point
                    M_slope  = math.ceil(math.degrees(math.atan(Elev_diff / Min_LD_dist)))
                    # Rate of slope change along the landslide body
                    dx_slope = (M_slope - Trig_Slope) / Min_LD_dist
		    # Set negative slope changes to zero
                    if dx_slope < 0:
                        dx_slope = 0

                    # Recompute failure plane depths using the refined slope profile
                    Hf = Hf_Trig + LD_dist * np.tan(
                        np.radians(Trig_Slope + LD_dist * dx_slope)
                    )
                    LD_Z = Surf_Elev - Hf

                    # Retain only cells where the refined failure depth is positive
                    LD_Index = LD_Index[LD_Z > 0]
                    LD_Z     = LD_Z[LD_Z > 0]

                    Acceptable_LS = len(LD_Index) > 2

                # ── Accept this landslide ──────────────────────────────────────
                if Acceptable_LS:

                    NL += 1

                    Trig_Index_Accept.append(Trig_Index)
                    Slope_Trig_Index_Accept.append(Trig_Slope)
                    Trig_Depths_Accept.append(Trig_Depth_cell)
                    Pressures_Accept.append(Pressure)

                    # Landslide area = number of cells × cell area
                    Area.append(len(LD_Index) * Cell_size**2)
                    # Landslide volume = sum of failure depths × cell area
                    Vol.append(np.sum(LD_Z * Cell_size**2))

                    # Assign the landslide ID to all its constituent cells
                    FID.flat[LD_Index]        = NL
                    Mat_LD_ind.append(np.array(LD_Index))
                    Fail_Index.flat[LD_Index] = 1

    # ── Convert output lists to numpy arrays ──────────────────────────────────
    Mat_LD_ind = [np.array(i) for i in Mat_LD_ind]

    Vol  = np.array(Vol[:NL],  dtype=np.float32)
    Area = np.array(Area[:NL], dtype=np.float32)

    Trig_Index_Accept       = np.array(Trig_Index_Accept[:NL],       dtype=np.int64)
    Slope_Trig_Index_Accept = np.array(Slope_Trig_Index_Accept[:NL], dtype=np.float32)

    return (Vol, Area, FID, NL, Mat_LD_ind,
            Trig_Index_Accept, Trig_Depths_Accept,
            Pressures_Accept, Slope_Trig_Index_Accept, Fail_Index)


# =============================================================================
# Function 5 — Export best-matching landslide polygon to shapefile
# =============================================================================

def Modeled_landslides_shapefiles(FID, Cell_size, x, y,
                                  Coordinate_Reference_System,
                                  Landslide_ID,
                                  output_dir='.'):
    """
    Write all modeled landslide polygons to a shapefile named by Landslide_ID.

    Each landslide is represented as a single merged polygon (union of all
    constituent cell bounding boxes).  Using unary_union rather than one
    Polygon per cell reduces the geometry count by 10–500×.

    Parameters
    ----------
    FID              : ndarray (m × n)   Landslide ID per cell (NaN = no landslide).
    Landslide_ID     : int or str         ID used in the output filename.
    output_dir       : str or Path        Directory for the output shapefile.
    """
    # Skip writing if no landslide has been delineated yet
    if np.all(np.isnan(FID)):
        return

    # Get unique landslide IDs, excluding NaN (unassigned cells)
    unique_landslides = np.unique(FID[~np.isnan(FID)])
    all_gdfs = []
    # Half cell-size offset: each cell is represented by its bounding box
    h = 0.5 * Cell_size

    for ld_number in unique_landslides:
        # Find all cells belonging to this landslide
        rows_l, cols_l = np.where(FID == ld_number)
        if len(rows_l) == 0:
            continue

        # Build axis-aligned bounding boxes for each cell in the landslide
        cells = [
            _shapely_box(x[cols_l[ii]] - h, y[rows_l[ii]] - h,
                         x[cols_l[ii]] + h, y[rows_l[ii]] + h)
            for ii in range(len(rows_l))
            # Guard against coordinate arrays shorter than the cell index
            if (cols_l[ii] + 1 < len(x)) and (rows_l[ii] + 1 < len(y))
        ]
        if cells:
            # Merge all cell boxes into a single polygon for this landslide
            merged = _unary_union(cells)
            all_gdfs.append(gpd.GeoDataFrame(
                {'ld_number': [ld_number], 'geometry': [merged]},
                crs=Coordinate_Reference_System
            ))

    # Combine all per-landslide GeoDataFrames; create empty frame if none exist
    gdf_all = (pd.concat(all_gdfs, ignore_index=True)
               if all_gdfs
               else gpd.GeoDataFrame(columns=['ld_number', 'geometry'],
                                     crs=Coordinate_Reference_System))

    # Write to a shapefile named by the mapped landslide ID
    output_shapefile = str(Path(output_dir) / f'Predicted_landslides_time_{Landslide_ID}.shp')
    gdf_all.to_file(output_shapefile)


# =============================================================================
# Function 6 — Find DEM cells within the search radius of a mapped centroid
# =============================================================================

def Find_close_cells(Mapped_Centroid_X, Mapped_Centroid_Y,
                     x, y, R_search, Mapped_area_ST):
    """
    Return the linear indices of all DEM cells within the search radius around
    a mapped landslide centroid.

    The search radius is R_search × sqrt(mapped area), making it proportional
    to the expected landslide size.

    Parameters
    ----------
    Mapped_area_ST : float   Square root of the mapped landslide area (m).

    Returns
    -------
    Close_cells     : ndarray (int)   Flat linear indices of cells within radius.
    Close_cells_num : int             Count of those cells.
    """
    # Build a 2D coordinate grid from the 1D x and y vectors
    X, Y = np.meshgrid(x, y, indexing='xy')

    # Compute Euclidean distance from every DEM cell to the mapped centroid
    Dist_to_centroid = np.sqrt(
        (X - Mapped_Centroid_X)**2 +
        (Y - Mapped_Centroid_Y)**2
    )

    # Cells are "close" if their distance is within the scaled search radius
    Is_Close = Dist_to_centroid <= (R_search * Mapped_area_ST)

    # Convert the boolean mask to flat linear indices for indexing 2D arrays
    Close_cells = np.ravel_multi_index(np.where(Is_Close), Is_Close.shape)

    # Count the number of candidate cells
    Close_cells_num = len(Close_cells)

    return Close_cells, Close_cells_num


# =============================================================================
# Function 7 — Locate the DEM cell closest to a mapped landslide centroid
# =============================================================================

def find_closest_cell_centroid_to_LD_centroid(Mapped_Centroid_X,
                                              Mapped_Centroid_Y,
                                              x, y):
    """
    Find the (row, col) of the DEM cell whose coordinates are closest to the
    mapped landslide centroid.

    Handles NaN values in the coordinate vectors by working only on valid entries
    and mapping the result back to original DEM indices.

    Returns
    -------
    Centroid_row : int   Row index in the full DEM.
    Centroid_col : int   Column index in the full DEM.
    """
    # ── Match column (x) coordinate ───────────────────────────────────────────
    # Mask out NaN entries in the x-coordinate vector
    valid_x_mask = ~np.isnan(x)
    valid_x      = x[valid_x_mask]
    # Find the index of the closest valid x coordinate to the centroid
    col_idx_in_valid = np.argmin(np.abs(valid_x - Mapped_Centroid_X))
    # Map back to the original (unmasked) index space
    Centroid_col = np.where(valid_x_mask)[0][col_idx_in_valid]

    # ── Match row (y) coordinate ──────────────────────────────────────────────
    # Mask out NaN entries in the y-coordinate vector
    valid_y_mask = ~np.isnan(y)
    valid_y      = y[valid_y_mask]
    # Find the index of the closest valid y coordinate to the centroid
    row_idx_in_valid = np.argmin(np.abs(valid_y - Mapped_Centroid_Y))
    # Map back to the original (unmasked) index space
    Centroid_row = np.where(valid_y_mask)[0][row_idx_in_valid]

    return Centroid_row, Centroid_col


# =============================================================================
# Function 8 — Define the cropped DEM window around a mapped centroid
# =============================================================================

def find_cropped_DEM(Mapped_area, Centroid_row, Centroid_col,
                     Cell_size, rows, columns,
                     factor, Min_square_side_cells):
    """
    Compute the row/column bounds of a square window centred on a landslide
    centroid, scaled by the mapped landslide area.

    The window size is scaled to factor × sqrt(area), rounded to an odd number
    of cells so the centroid lies exactly at the centre, then clamped to the
    DEM boundary.

    Parameters
    ----------
    factor                : float   Physical size scaling factor.
    Min_square_side_cells : int     Minimum allowed window side length (cells).

    Returns
    -------
    start_row, end_row, start_col, end_col : int
    """
    # Compute the physical side length of the square window
    square_side_size = factor * math.sqrt(Mapped_area)

    # Convert from physical metres to number of grid cells
    Num_of_cells_square_side = round(square_side_size / Cell_size)

    # Enforce odd cell count so the centroid is exactly at the window centre
    if Num_of_cells_square_side % 2 == 0:
        Num_of_cells_square_side += 1

    # Enforce a minimum window size to ensure enough context for BFS
    if Num_of_cells_square_side < Min_square_side_cells:
        Num_of_cells_square_side = Min_square_side_cells

    # Half-side distance from centroid to window edge
    cells_half_side = (Num_of_cells_square_side - 1) / 2

    # Compute initial window bounds centred on the landslide centroid
    start_row = Centroid_row - cells_half_side
    end_row   = Centroid_row + cells_half_side
    start_col = Centroid_col - cells_half_side
    end_col   = Centroid_col + cells_half_side

    # ── Boundary corrections: shift window if it extends outside the DEM ──────
    # Top boundary exceeded — shift window downward
    if start_row < 0:
        end_row   = end_row - start_row
        start_row = 0
    # Bottom boundary exceeded — shift window upward
    if end_row > rows - 1:
        start_row = start_row - (end_row - rows + 1)
        end_row   = rows - 1
    # Left boundary exceeded — shift window rightward
    if start_col < 0:
        end_col   = end_col - start_col
        start_col = 0
    # Right boundary exceeded — shift window leftward
    if end_col > columns - 1:
        start_col = start_col - (end_col - columns + 1)
        end_col   = columns - 1

    # Final safety clamp: if the requested window is wider/taller than the DEM
    # itself, the two shifts above (top-then-bottom, left-then-right) can fight
    # each other and push a bound back past the opposite edge (e.g. start_row
    # negative again after being shifted for the bottom edge). Clamping here
    # guarantees valid in-bounds indices in that case, at the cost of the
    # window being truncated to the full DEM extent rather than centred.
    start_row = max(0, start_row)
    end_row   = min(rows - 1, end_row)
    start_col = max(0, start_col)
    end_col   = min(columns - 1, end_col)

    # Convert to integer indices for use in numpy slicing
    return int(start_row), int(end_row), int(start_col), int(end_col)


# =============================================================================
# Function 9 — Convert (x, y) world coordinates to raster (row, col) indices
# =============================================================================

def xy_to_rowcol(x, y, xmin, xmax, ymin, ymax, Cell_size):
    """
    Convert projected (x, y) coordinates to raster (row, col) grid indices.

    Assumes standard raster convention: row 0 is at the top (north), columns
    increase left to right (west to east).

    Returns
    -------
    row_index : int or ndarray
    col_index : int or ndarray
    """
    x = np.array(x)
    y = np.array(y)

    # Column index: distance from left edge divided by cell size
    col_index = np.rint((x - xmin) / Cell_size).astype(int)

    # Row index: distance from top edge divided by cell size (rows count downward)
    row_index = np.rint((ymax - y) / Cell_size).astype(int)

    return row_index, col_index


# =============================================================================
# Function 9b — Auto-derive x/y coordinate vectors from the lower-left corner
# =============================================================================

def compute_coordinate_vectors(rows, columns, xmin, ymin, Cell_size):
    """
    Build the x (easting) and y (northing) cell-center coordinate vectors for
    a raster from its lower-left corner and cell size, so that DEM.h5,
    Cell_size, xmin, and ymin fully determine the grid — no separate
    x_coordinates.h5 / y_coordinates.h5 files are needed.

    Convention: (xmin, ymin) is the center of the lower-left cell — i.e. the
    last row (row = rows-1, since row 0 is the top/north row) and first
    column (col = 0). x increases eastward with column index; y increases
    northward as row index decreases.

    Parameters
    ----------
    rows, columns : int     DEM dimensions.
    xmin, ymin    : float   Coordinates of the lower-left cell center (m).
    Cell_size     : float   Grid cell resolution (m).

    Returns
    -------
    x : ndarray (columns,)   Easting of each column.
    y : ndarray (rows,)      Northing of each row.
    """
    x = xmin + np.arange(columns, dtype=np.float64) * Cell_size
    y = ymin + (rows - 1 - np.arange(rows, dtype=np.float64)) * Cell_size
    return x, y


# =============================================================================
# Function 9c — Auto-derive Slope from the DEM (TopoToolbox gradient8 equivalent)
# =============================================================================

def compute_slope_gradient8(DEM, Cell_size, unit='degree'):
    """
    Compute the steepest 8-connected-neighborhood downward gradient of a DEM,
    equivalent to TopoToolbox's GRIDobj/gradient8.m (Schwanghart, 2017).

    For every cell, this is the max of:
      - the steepest drop to an orthogonal (N/S/E/W) neighbor, divided by
        Cell_size, and
      - the steepest drop to a diagonal (NE/NW/SE/SW) neighbor, divided by
        Cell_size * sqrt(2).

    This is implemented as two grayscale erosions (a "min over neighborhood"
    filter) rather than 8 separate pairwise comparisons, matching gradient8's
    imerode-based approach: erosion with the orthogonal cross-shaped
    neighborhood {center, N, S, E, W} and with the diagonal X-shaped
    neighborhood {center, NE, NW, SE, SW}; both include the center cell.
    NaN (no-data) cells are excluded from the erosion via +inf padding (so
    they never win the min) and are restored to NaN in the output.

    Parameters
    ----------
    DEM       : ndarray (m x n)   Digital elevation model (m).
    Cell_size : float             Grid cell resolution (m).
    unit      : str               'tangent', 'degree' (default), 'radian',
                                   'sine', or 'percent'.

    Returns
    -------
    Slope : ndarray (m x n)   Slope in the requested unit; NaN where DEM is NaN.
    """
    nrow, ncol = DEM.shape
    z = DEM.astype(np.float64)
    nanmask = np.isnan(z)
    # Replace no-data with +inf so it is never selected as the neighborhood min
    zf = np.where(nanmask, np.inf, z)
    padded = np.pad(zf, 1, mode='constant', constant_values=np.inf)

    def _shifted(dr, dc):
        return padded[1 + dr:1 + dr + nrow, 1 + dc:1 + dc + ncol]

    # Grayscale erosion = min over the neighborhood (each offset includes the center at (0,0))
    orth_offsets = [(0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)]
    diag_offsets = [(0, 0), (-1, -1), (-1, 1), (1, -1), (1, 1)]
    erode_orth = np.minimum.reduce([_shifted(dr, dc) for dr, dc in orth_offsets])
    erode_diag = np.minimum.reduce([_shifted(dr, dc) for dr, dc in diag_offsets])

    # inf - inf = nan for cells fully surrounded by no-data; harmless, masked below
    with np.errstate(invalid='ignore'):
        G_orth = (zf - erode_orth) / Cell_size
        G_diag = (zf - erode_diag) / (Cell_size * math.sqrt(2))
        G = np.maximum(G_orth, G_diag)
    G[nanmask] = np.nan

    if unit == 'tangent':
        Slope = G
    elif unit == 'degree':
        Slope = np.degrees(np.arctan(G))
    elif unit == 'radian':
        Slope = np.arctan(G)
    elif unit == 'sine':
        Slope = np.sin(np.arctan(G))
    elif unit == 'percent':
        Slope = G * 100
    else:
        raise ValueError(f"Unknown unit '{unit}'; expected tangent/degree/radian/sine/percent")

    return Slope


# =============================================================================
# Function 9d — Auto-derive Flow Direction / Flow Accumulation from the DEM
# =============================================================================
#
# Python port of TopoToolbox's FLOWobj(DEM,'preprocess','fill') + flowacc(FD),
# reverse-engineered and numerically validated cell-by-cell against reference
# Flow_Direction.h5 / Flow_Accumulation.h5 rasters generated by the real
# TopoToolbox (Schwanghart & Scherler, 2014):
#   - fill_sinks              ~ GRIDobj/fillsinks.m   (nargin==1 case)
#   - identify_flats_sills    ~ identifyflats.m
#   - _exact_edt / _imreconstruct_dilation / _graydist_quasi_euclidean
#                              ~ the bwdist / imreconstruct / graydist machinery
#                                FLOWobj.m uses to build the auxiliary "distance
#                                from higher ground, weighted toward the sill"
#                                surface that resolves flow direction across flats
#   - compute_flow_direction_topotoolbox ~ FLOWobj.m's steepest-neighbor /
#                                topological-priority selection (ix/ixc)
#   - compute_flow_accumulation_topotoolbox ~ flowacc.m's
#                                `A(ixc(r)) = A(ix(r)) + A(ixc(r))` traversal,
#                                implemented as Kahn's algorithm (topological
#                                sort by in-degree) rather than a literal global
#                                sort — equivalent result, no python-level loop
#                                over every edge
#
# Validated on the Example 2 DEM (3325x2024, ~51% NaN, mountainous terrain):
#   Flow direction   : 99.9959% exact cell match (133 / 3,245,448 differ)
#   Flow accumulation: 99.6220% exact cell match; 99.9999% within 1 cell;
#                       max upstream count matches the reference exactly
# The residual mismatch is entirely local pits immediately adjacent to NaN,
# where MATLAB's NaN-sorts-last behavior in FLOWobj's internal priority
# ranking does something that could not be fully reproduced from the
# available source (identifyflats.m explicitly excludes any cell touching
# NaN from flat/flow resolution, but the exact fallback FLOWobj then applies
# to such a cell isn't visible in the given source). This affects < 0.005%
# of cells and only within a few pixels of the NaN boundary.
# =============================================================================

def fill_sinks(DEM):
    """
    Priority-flood depression filling, matching GRIDobj/fillsinks.m's default
    (nargin==1) behavior: repeatedly raise the lowest unresolved cell up to
    its neighbor's elevation, seeded from the DEM's outer edge. Interior NaN
    cells act as additional open outlets — verified from fillsinks.m's own
    marker construction (interior NaN cells keep marker=+inf in the negated-
    elevation reconstruction, which floods straight back out to any adjacent
    cell's own unfilled elevation in the first pass) — matching how this DEM
    is clipped to a watershed/ridge boundary, where NaN means "outside the
    area of interest" and is reachable as a drain, not an internal barrier.

    Parameters
    ----------
    DEM : ndarray (m x n)   Digital elevation model (m); NaN = no data.

    Returns
    -------
    Filled : ndarray (m x n)   DEM with all interior depressions raised to
                                their pour-point elevation.
    """
    nrow, ncol = DEM.shape
    nanmask = np.isnan(DEM)
    filled = DEM.copy()
    closed = nanmask.copy()

    # Seed = the true array border (valid cells) — NaN cells are reachable as
    # additional open outlets through the normal BFS expansion below, since
    # any cell adjacent to NaN would otherwise be pushed onto the queue with
    # its own (unraised) elevation the moment a neighbor is processed; here we
    # seed NaN-adjacent cells directly for the same effect without needing a
    # NaN pseudo-elevation.
    seed_mask = np.zeros((nrow, ncol), dtype=bool)
    seed_mask[0, :] = True
    seed_mask[-1, :] = True
    seed_mask[:, 0] = True
    seed_mask[:, -1] = True
    if np.any(nanmask):
        padded_nan = np.pad(nanmask, 1, mode='constant', constant_values=True)
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                if dr == 0 and dc == 0:
                    continue
                seed_mask |= padded_nan[1 + dr:1 + dr + nrow, 1 + dc:1 + dc + ncol]
    seed_mask &= ~nanmask

    pq = []
    rows, cols = np.nonzero(seed_mask)
    for r, c in zip(rows.tolist(), cols.tolist()):
        heapq.heappush(pq, (float(filled[r, c]), r, c))
        closed[r, c] = True

    while pq:
        elev, r, c = heapq.heappop(pq)
        for dr, dc in _NEI8:
            rn, cn = r + dr, c + dc
            if 0 <= rn < nrow and 0 <= cn < ncol and not closed[rn, cn]:
                closed[rn, cn] = True
                ne = float(filled[rn, cn])
                new_elev = ne if ne > elev else elev
                filled[rn, cn] = new_elev
                heapq.heappush(pq, (new_elev, rn, cn))
    return filled


# D8 neighbor offsets (row, col) and their ArcGIS direction codes, shared by
# every function in this section
_NEI8 = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
_ORTHO = [(-1, 0), (1, 0), (0, -1), (0, 1)]
_DIAG = [(-1, -1), (-1, 1), (1, -1), (1, 1)]
_DIRCODE = {(-1, -1): 32, (-1, 0): 64, (-1, 1): 128, (0, -1): 16, (0, 1): 1,
            (1, -1): 8, (1, 0): 4, (1, 1): 2}


def _dilate3x3(a, fill):
    """Grayscale dilation (max over the full 3x3 neighborhood, i.e. MATLAB's ones(3))."""
    nrow, ncol = a.shape
    padded = np.pad(a, 1, mode='constant', constant_values=fill)
    out = np.full((nrow, ncol), fill)
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            np.maximum(out, padded[1 + dr:1 + dr + nrow, 1 + dc:1 + dc + ncol], out=out)
    return out


def _erode3x3(a, fill):
    """Grayscale erosion (min over the full 3x3 neighborhood, i.e. MATLAB's ones(3))."""
    nrow, ncol = a.shape
    padded = np.pad(a, 1, mode='constant', constant_values=fill)
    out = np.full((nrow, ncol), fill)
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            np.minimum(out, padded[1 + dr:1 + dr + nrow, 1 + dc:1 + dc + ncol], out=out)
    return out


def identify_flats_sills(DEM, nanmask):
    """
    Python port of identifyflats.m: flats are cells with no strictly-lower
    neighbor in the full 3x3 (8-connected + center) neighborhood; sills are
    non-flat cells adjacent to a flat cell of the exact same elevation (the
    point where a flat spills into lower terrain). Cells on the outer border
    or adjacent to NaN are always excluded from being flats.

    Returns
    -------
    flats, sills : ndarray (m x n), bool
    """
    nrow, ncol = DEM.shape
    z = np.where(nanmask, -np.inf, DEM)
    min3x3 = _erode3x3(z, fill=np.inf)
    flats = (min3x3 == z) & (~nanmask)
    flats[:, [0, -1]] = False
    flats[[0, -1], :] = False
    if np.any(nanmask):
        dil_nan = _dilate3x3(nanmask.astype(np.float64), fill=0.0) > 0
        flats[dil_nan] = False

    Imr = np.full((nrow, ncol), -np.inf)
    Imr[flats] = z[flats]
    max3x3 = _dilate3x3(Imr, fill=-np.inf)
    sills = (max3x3 == z) & (~flats)
    if np.any(nanmask):
        sills[nanmask] = False
    return flats, sills


def _exact_edt(binary_seed_mask):
    """
    Exact 2-D Euclidean distance transform (Felzenszwalt & Huttenlocher 2012):
    for every cell, the distance to the nearest True cell in binary_seed_mask.
    Matches MATLAB's bwdist(..., 'euclidean').
    """
    def edt_1d(f):
        n = len(f)
        d = np.zeros(n)
        v = np.zeros(n, dtype=np.int64)
        z = np.zeros(n + 1)
        k = 0
        v[0] = 0
        z[0] = -np.inf
        z[1] = np.inf
        for q in range(1, n):
            s = ((f[q] + q * q) - (f[v[k]] + v[k] * v[k])) / (2 * q - 2 * v[k])
            while s <= z[k]:
                k -= 1
                s = ((f[q] + q * q) - (f[v[k]] + v[k] * v[k])) / (2 * q - 2 * v[k])
            k += 1
            v[k] = q
            z[k] = s
            z[k + 1] = np.inf
        k = 0
        for q in range(n):
            while z[k + 1] < q:
                k += 1
            d[q] = (q - v[k]) ** 2 + f[v[k]]
        return d

    INF = 1e20
    nrow, ncol = binary_seed_mask.shape
    g = np.where(binary_seed_mask, 0.0, INF)
    for c in range(ncol):
        g[:, c] = edt_1d(g[:, c])
    for r in range(nrow):
        g[r, :] = edt_1d(g[r, :])
    return np.sqrt(g)


def _imreconstruct_dilation(marker, mask):
    """
    Grayscale morphological reconstruction by dilation (MATLAB's imreconstruct,
    8-connectivity / ones(3)): repeatedly dilate the marker, clipped to never
    exceed mask, until it reaches a fixed point.
    """
    j = np.minimum(marker, mask)
    while True:
        jnew = np.minimum(_dilate3x3(j, fill=-np.inf), mask)
        if np.array_equal(jnew, j):
            return j
        j = jnew


def _graydist_quasi_euclidean(cost, seed_mask, restrict_mask):
    """
    Grayscale-weighted geodesic distance transform (MATLAB's graydist with the
    'quasi-euclidean' method): the shortest path from any True cell in
    seed_mask, where each step's cost is the step length (1 for orthogonal,
    sqrt(2) for diagonal) times the average of `cost` at the two cells,
    restricted to cells where restrict_mask is True (Dijkstra).
    """
    nrow, ncol = cost.shape
    INF = 1e30
    dist = np.full((nrow, ncol), INF)
    pq = []
    sr, sc = np.nonzero(seed_mask)
    for r, c in zip(sr.tolist(), sc.tolist()):
        dist[r, c] = 0.0
        heapq.heappush(pq, (0.0, r, c))
    while pq:
        d, r, c = heapq.heappop(pq)
        if d > dist[r, c] + 1e-9:
            continue
        for dr, dc in _NEI8:
            rn, cn = r + dr, c + dc
            if 0 <= rn < nrow and 0 <= cn < ncol and restrict_mask[rn, cn]:
                step = math.sqrt(2) if (dr != 0 and dc != 0) else 1.0
                w = step * (cost[r, c] + cost[rn, cn]) / 2.0
                nd = d + w
                if nd < dist[rn, cn] - 1e-9:
                    dist[rn, cn] = nd
                    heapq.heappush(pq, (nd, rn, cn))
    return dist


def compute_flow_direction_topotoolbox(DEM, Cell_size):
    """
    Compute D8 flow direction (ArcGIS 1-128 convention), equivalent to
    TopoToolbox's FD = FLOWobj(DEM, 'preprocess', 'fill').

    Steps: fill depressions -> identify flats/sills -> build the auxiliary
    "distance from higher ground, weighted geodesic distance toward the sill"
    surface that resolves ties within flats -> pick, for every cell, the
    steepest neighbor under a composite (elevation, flat-tiebreak,
    column-major-index) ranking — matching FLOWobj.m's pp-rank / imdilate
    steepest-neighbor selection, including its stable-sort tie-break order.

    Parameters
    ----------
    DEM       : ndarray (m x n)   Digital elevation model (m); NaN = no data.
    Cell_size : float             Grid cell resolution (m).

    Returns
    -------
    FlowDir : ndarray (m x n)   D8 direction codes (1,2,4,8,16,32,64,128);
                                 0 = no downhill neighbor (undefined/sink);
                                 NaN where DEM is NaN.
    """
    DEM = DEM.astype(np.float64)  # match the precision this algorithm was validated at
    nrow, ncol = DEM.shape
    nanmask = np.isnan(DEM)

    dem_filled = fill_sinks(DEM)
    flats, sills = identify_flats_sills(dem_filled, nanmask)

    # PreSillPixel: flat neighbors of a sill at the sill's own elevation —
    # the seed points flow converges toward within each flat
    presill_mask = np.zeros((nrow, ncol), dtype=bool)
    sr, sc = np.nonzero(sills)
    if len(sr):
        sill_elev = dem_filled[sr, sc]
        for dr, dc in _NEI8:
            rn, cn = sr + dr, sc + dc
            valid = (rn >= 0) & (rn < nrow) & (cn >= 0) & (cn < ncol)
            rn_v, cn_v = rn[valid], cn[valid]
            sel = flats[rn_v, cn_v] & (dem_filled[rn_v, cn_v] == sill_elev[valid])
            presill_mask[rn_v[sel], cn_v[sel]] = True

    # Auxiliary "distance from higher ground" surface (bwdist + imreconstruct)
    D_boundary = _exact_edt(~flats)
    mask = np.where(flats, np.inf, 0.0)
    recon = _imreconstruct_dilation(D_boundary + 1.0, mask)
    D_cost = (recon - D_boundary) * Cell_size

    # Weighted geodesic distance from the sills, through the flats only —
    # this is the tie-break value used to route flow across a flat toward its outlet
    G = _graydist_quasi_euclidean(D_cost, presill_mask, flats)

    # Composite secondary ranking key: G for flat cells (finite, smaller =
    # closer to the sill = more "downhill"), far below that for non-flat
    # cells (always preferred over a flat neighbor at the same elevation),
    # with a tiny column-major-linear-index perturbation as the final
    # tie-break — matching FLOWobj.m's stable-sort-by-original-index fallback
    # when both elevation and the D/graydist value are exactly tied.
    NEG_BASE = -1e6
    lin_idx_colmajor = (np.arange(nrow)[:, None] + np.arange(ncol)[None, :] * nrow).astype(np.float64)
    key2 = np.where(flats, G, NEG_BASE) - 1e-9 * lin_idx_colmajor

    z_full = np.where(nanmask, np.inf, dem_filled)
    padded_z = np.pad(z_full, 1, mode='constant', constant_values=np.inf)
    padded_k2 = np.pad(key2, 1, mode='constant', constant_values=NEG_BASE)
    padded_nan = np.pad(nanmask, 1, mode='constant', constant_values=True)

    def best_over(offsets):
        best_dem = np.full((nrow, ncol), np.inf)
        best_key = np.full((nrow, ncol), NEG_BASE)
        best_dr = np.zeros((nrow, ncol), dtype=np.int8)
        best_dc = np.zeros((nrow, ncol), dtype=np.int8)
        have_any = np.zeros((nrow, ncol), dtype=bool)
        for dr, dc in offsets:
            nb_dem = padded_z[1 + dr:1 + dr + nrow, 1 + dc:1 + dc + ncol]
            nb_key = padded_k2[1 + dr:1 + dr + nrow, 1 + dc:1 + dc + ncol]
            nb_nan = padded_nan[1 + dr:1 + dr + nrow, 1 + dc:1 + dc + ncol]
            better = (~nb_nan) & ((nb_dem < best_dem) | ((nb_dem == best_dem) & (nb_key < best_key)))
            best_dem = np.where(better, nb_dem, best_dem)
            best_key = np.where(better, nb_key, best_key)
            best_dr = np.where(better, dr, best_dr)
            best_dc = np.where(better, dc, best_dc)
            have_any |= ~nb_nan
        return best_dem, best_key, best_dr, best_dc, have_any

    ortho_dem, ortho_key, ortho_dr, ortho_dc, ortho_have = best_over(_ORTHO)
    diag_dem, diag_key, diag_dr, diag_dc, diag_have = best_over(_DIAG)

    # Steepness comparison (real elevation drop / true distance) decides
    # ortho vs. diag, matching FLOWobj.m's G1/G2; diag only wins when it is
    # at least as steep AND genuinely ranks lower (mirrors its rank-based
    # xxx2>xxx1 confirmation check)
    G1s = (dem_filled - ortho_dem) / Cell_size
    G2s = (dem_filled - diag_dem) / (Cell_size * math.sqrt(2))
    diag_better_rank = (diag_dem < ortho_dem) | ((diag_dem == ortho_dem) & (diag_key < ortho_key))
    use_diag = ortho_have & diag_have & (G1s <= G2s) & diag_better_rank
    use_diag |= (~ortho_have) & diag_have

    target_dr = np.where(use_diag, diag_dr, ortho_dr)
    target_dc = np.where(use_diag, diag_dc, ortho_dc)
    target_dem = np.where(use_diag, diag_dem, ortho_dem)
    target_key = np.where(use_diag, diag_key, ortho_key)

    # A target is only valid if strictly "lower" under the composite ranking —
    # otherwise there is no genuine downhill neighbor (FD = 0, undefined/sink)
    target_is_lower = (target_dem < dem_filled) | ((target_dem == dem_filled) & (target_key < key2))
    have_target = (ortho_have | diag_have) & target_is_lower

    code_map = np.zeros((nrow, ncol), dtype=np.float64)
    for (dr, dc), code in _DIRCODE.items():
        sel = have_target & (target_dr == dr) & (target_dc == dc)
        code_map[sel] = code

    return np.where(nanmask, np.nan, code_map)


def compute_flow_accumulation_topotoolbox(FlowDir):
    """
    D8 flow accumulation (upstream cell count), equivalent to TopoToolbox's
    flowacc(FD): every cell starts with a weight of 1 and accumulates the
    weight of every cell that drains into it. Implemented as Kahn's algorithm
    (topological sort by in-degree, processed wave by wave) rather than
    flowacc.m's literal global sort + linear pass — an equivalent result,
    fully vectorised with no per-edge Python loop.

    Multiply the result by Cell_size**2 to convert cell count to contributing
    area (m^2), matching flowacc(FD).*Cell_size^2.

    Parameters
    ----------
    FlowDir : ndarray (m x n)   D8 direction codes as returned by
                                 compute_flow_direction_topotoolbox.

    Returns
    -------
    Acc : ndarray (m x n)   Upstream cell count (float); NaN where FlowDir is NaN.
    """
    nrow, ncol = FlowDir.shape
    nanmask = np.isnan(FlowDir)

    row_idx = np.repeat(np.arange(nrow), ncol)
    col_idx = np.tile(np.arange(ncol), nrow)
    fd_flat = FlowDir.ravel()

    target = np.full(nrow * ncol, -1, dtype=np.int64)
    for (dr, dc), code in _DIRCODE.items():
        sel = fd_flat == code
        nr = row_idx[sel] + dr
        nc = col_idx[sel] + dc
        inb = (nr >= 0) & (nr < nrow) & (nc >= 0) & (nc < ncol)
        src_idx = np.flatnonzero(sel)[inb]
        tgt_idx = nr[inb] * ncol + nc[inb]
        target[src_idx] = tgt_idx

    nan_flat = nanmask.ravel()
    in_degree = np.zeros(nrow * ncol, dtype=np.int64)
    valid_targets = target[target >= 0]
    np.add.at(in_degree, valid_targets, 1)

    acc = np.where(nan_flat, 0.0, 1.0)
    remaining = in_degree.copy()
    queue = np.flatnonzero((remaining == 0) & ~nan_flat)
    while queue.size:
        tgt = target[queue]
        valid_t = tgt >= 0
        if np.any(valid_t):
            np.add.at(acc, tgt[valid_t], acc[queue[valid_t]])
            np.add.at(remaining, tgt[valid_t], -1)
            candidates = np.unique(tgt[valid_t])
            queue = candidates[remaining[candidates] == 0]
        else:
            queue = np.array([], dtype=np.int64)

    return np.where(nanmask, np.nan, acc.reshape(nrow, ncol))


# =============================================================================
# Function 10 — Back-analyses one mapped landslide
# =============================================================================

def process_mapped_landslide(
        Landslide_ID,
        Elev_Mat_sub, Slope_Mat_sub, FD_Mat_sub, Area_Mat_sub,
        x_sub, y_sub, Pressures_4D_array_sub, Theta_4D_array_sub,
        Cell_size, R_search,
        Phi_single_min, Phi_single_max, Phi_single_increment,
        C_single_min, C_single_max, C_single_increment,
        Gamma_W, Gamma_soil, Depths_vector,
        Coordinate_Reference_System,
        Strength_variation_with_theta, Theta_s, Theta_r,
        Total_num_iterations, xmin, xmax, ymin, ymax, Time_points,
        output_dir='.', ld_dir='.', log_queue=None):
    """
    Back-analyse one mapped landslide to find the (c, Phi, t) combination whose
    modeled landslide best matches the mapped landslide in location, area,
    and volume.

    All (Phi, c, t) combinations are evaluated.  For each combination the local
    error (distance + area + volume mismatch) is computed and the minimum is
    retained.  The global minimum across all combinations is then reported.

    Outputs written to output_dir:
        acceptable_combinations_for_LD_{ID}.xlsx   — all equal-minimum solutions
        Predicted_landslides_time_{ID}.shp          — best-matching polygon
    """
    start_time = datetime.now()

    # Sentinel error value assigned to iterations that produce no valid landslide.
    # Hardcoded; not a user input — any real error will always be smaller than this.
    Eps_max = 1_000_000

    # ── Load mapped landslide properties from its Excel file ──────────────────
    excel_name    = str(Path(ld_dir) / f'LD{Landslide_ID}.xlsx')
    Mapped_LD_X_Y = pd.read_excel(excel_name).values

    # Mapped area — minimum threshold check (informational only; no rejection here)
    Mapped_area = Mapped_LD_X_Y[0, 0]
    if Mapped_area < Cell_size ** 2 * 3:
        pass

    # Centroid coordinates and volume of the mapped landslide
    Mapped_Centroid_X = Mapped_LD_X_Y[0, 1]
    Mapped_Centroid_Y = Mapped_LD_X_Y[0, 2]
    Mapped_volume     = Mapped_LD_X_Y[0, 3]
    # Square root of mapped area is used as the search-radius denominator
    Mapped_area_ST    = np.sqrt(Mapped_area)

    # Extract the initial (t=0) pore pressure slice for reference
    Initial_pressures_3D_array_sub = Pressures_4D_array_sub[:, :, :, 0]

    # ── Initialise result arrays (pre-allocated for all iterations) ────────────
    Counter = -1   # incremented before first use → first valid index is 0

    # Error components for every iteration
    Errors      = np.zeros(Total_num_iterations)
    Errors_CD   = np.zeros(Total_num_iterations)
    Errors_Area = np.zeros(Total_num_iterations)
    Errors_Vol  = np.zeros(Total_num_iterations)

    # Parameter values for every iteration
    Phis  = np.zeros(Total_num_iterations)
    Cs    = np.zeros(Total_num_iterations)
    Times = np.zeros(Total_num_iterations)

    # Modelled landslide geometry for every iteration
    Areas = np.zeros(Total_num_iterations)
    Vols  = np.zeros(Total_num_iterations)
    CDs_x = np.zeros(Total_num_iterations)
    CDs_y = np.zeros(Total_num_iterations)

    # Triggering cell properties for every iteration
    Trigs_Indices = np.zeros(Total_num_iterations)
    Trigs_x       = np.zeros(Total_num_iterations)
    Trigs_y       = np.zeros(Total_num_iterations)
    Trigs_Slope   = np.zeros(Total_num_iterations)
    Trigs_Z       = np.zeros(Total_num_iterations)
    Trigs_P       = np.zeros(Total_num_iterations)

    # ── Identify candidate triggering cells within the search radius ──────────
    Close_cells, Close_cells_num = Find_close_cells(
        Mapped_Centroid_X, Mapped_Centroid_Y,
        x_sub, y_sub, R_search, Mapped_area_ST
    )

    # ── Precompute upslope-neighbor lookup for every cell in the sub-DEM ──────
    # This vectorised step runs once per landslide and eliminates all T_UpGrid
    # calls during BFS traversal inside the inner (c, Phi, t) loops
    upgrid_lookup_sub = precompute_upgrid_all(FD_Mat_sub)

    # ── Filter candidate cells: exclude NaN elevation and near-flat slopes ────
    # These masks are fixed for this landslide regardless of c, Phi, or t
    close_rows, close_cols = np.unravel_index(Close_cells, Elev_Mat_sub.shape)

    # Valid mask: cells with a real (non-NoData) elevation
    valid_mask  = ~np.isnan(Elev_Mat_sub[close_rows, close_cols])
    # Active mask: valid cells with a slope above the flat-cell threshold
    active_mask = valid_mask & (Slope_Mat_sub[close_rows, close_cols] > 0.0001)

    active_close  = Close_cells[active_mask]                      # shape (M,)
    active_rows_a = close_rows[active_mask]                       # shape (M,)
    active_cols_a = close_cols[active_mask]                       # shape (M,)
    active_slopes = Slope_Mat_sub[active_rows_a, active_cols_a]   # shape (M,)

    # ── Extract pore pressure and θ for active cells, all depths, all times ───
    # Shape: (M, D, T) — computed once and reused for every (c, Phi) pair
    P_all = Pressures_4D_array_sub[active_rows_a, active_cols_a, :, :]

    # Extract θ for active cells when Bishop coefficient varies with saturation
    if Strength_variation_with_theta == 1:
        Theta_all = Theta_4D_array_sub[active_rows_a, active_cols_a, :, :]

    # ── Precompute slope-geometry terms (independent of c, Phi, t) ────────────
    sin_slopes    = np.sin(np.radians(active_slopes))   # (M,)
    cos_slopes    = np.cos(np.radians(active_slopes))   # (M,)
    cos_slopes_sq = cos_slopes ** 2                     # (M,)

    # FS denominator: γ · z · sin(α) · cos(α), shape (M, D)
    denom      = (Gamma_soil
                  * sin_slopes[:, None]
                  * cos_slopes[:, None]
                  * Depths_vector[None, :])
    # Protect against zero denominator (flat cells; already excluded by active_mask
    # but added as a numerical safeguard)
    denom_safe  = np.where(denom == 0, 1e-10, denom)
    # Precompute the reciprocal to replace repeated division in the (c, Phi) loop
    recip_denom = 1.0 / denom_safe   # (M, D)

    # ── Precompute Bishop coefficient and a1 (geometry + pressure term) ───────
    # a1[m,d,t] = (γ·z[d]·cos²α[m] - γ_w·P[m,d,t]·Bishop) / denom[m,d]
    # This is independent of c and Phi, so it is computed once for the entire landslide.
    # Where a1 ≤ 0 the effective normal stress is non-positive; FS reduces to a2·c.
    if Strength_variation_with_theta == 0:
        # Fully saturated assumption: Bishop χ = 1 everywhere (scalar)
        Bishop = 1.0
    else:
        # χ scales with degree of saturation: (θ - θ_r) / (θ_s - θ_r), clamped to [0,1]
        Bishop = (Theta_all - Theta_r) / (Theta_s - Theta_r)
        Bishop = np.clip(Bishop, 0.0, 1.0)

    # Numerator of the effective normal stress term (shape M, D)
    numerator_base = (Gamma_soil
                      * cos_slopes_sq[:, None]
                      * Depths_vector[None, :])
    # Full a1 array: shape (M, D, T) via broadcasting
    a1 = ((numerator_base[:, :, None] - Gamma_W * P_all * Bishop)
          * recip_denom[:, :, None])

    # Boolean mask where effective normal stress is non-positive
    mask_low = a1 <= 0   # (M, D, T)

    # ── Precompute BFS (Breadth-First Search) landslide shapes ───────────────
    # Key insight: a modeled landslide's SHAPE (area, volume, centroid) depends
    # only on the triggering cell, triggering depth, and fixed terrain — it is
    # independent of c, Phi, and the time step.  Running BFS once per (cell, depth)
    # and caching eliminates the BFS bottleneck from the inner loop entirely.
    _sub_m, _sub_n = Elev_Mat_sub.shape
    _elev_flat  = Elev_Mat_sub.ravel()
    _area_flat  = Area_Mat_sub.ravel()
    _slope_flat = Slope_Mat_sub.ravel()

    # Dictionary: (cell_index, depth_index) → precomputed result dict or None
    _bfs_cache = {}
    for _ci in range(len(active_close)):
        _cell = int(active_close[_ci])
        for _di in range(len(Depths_vector)):
            _res = _bfs_single_cell(
                _cell, _di, Depths_vector,
                _elev_flat, _area_flat, _slope_flat,
                _sub_m, _sub_n, Cell_size, upgrid_lookup_sub, x_sub, y_sub
            )
            if _res is not None:
                _bfs_cache[(_cell, _di)] = _res

    # ── Triple loop: Phi × c × t ──────────────────────────────────────────────
    for Phi in np.arange(Phi_single_min,
                         Phi_single_max + Phi_single_increment,
                         Phi_single_increment):

        # Precompute tan(Phi) once for all c values at this friction angle
        tan_phi = np.tan(np.radians(Phi))

        for c in np.arange(C_single_min,
                            C_single_max + C_single_increment,
                            C_single_increment):

            # Send a progress message to the GUI log queue if provided
            if log_queue is not None:
                log_queue.put(f'  LD {Landslide_ID}  c={c}  Phi={Phi}\n')

            # ── Vectorised FS for all active cells, all depths, all times ─────
            # FS[m,d,t] = a1[m,d,t]·tan(Phi) + a2[m,d]·c
            # Where a1 ≤ 0 (non-positive normal stress): FS = a2[m,d]·c
            a2_c   = recip_denom[:, :, None] * c                      # (M, D, 1)
            FS_all = np.where(mask_low, a2_c, a1 * tan_phi + a2_c)    # (M, D, T)

            # A cell fails where FS ≤ 1; the surface depth layer (index 0) is excluded
            failure_all          = FS_all <= 1.0                       # (M, D, T)
            failure_all[:, 0, :] = False

            # Cells already failing at t=0 are treated as pre-existing failures
            init_fail = failure_all[:, :, 0]                           # (M, D)

            # New failures: fail at time t but stable at the initial time step
            new_fail = failure_all & ~init_fail[:, :, None]            # (M, D, T)

            # ── Time step loop: evaluate one time step at a time ──────────────
            for t in range(1, Time_points):

                Counter += 1

                # Record the parameter combination for this iteration
                Phis[Counter]  = Phi
                Cs[Counter]    = c
                Times[Counter] = t

                # Find which active cells newly fail at this time step and depth
                cell_idx, depth_idx = np.where(new_fail[:, :, t])

                # No new failures at this time step — assign maximum error and skip
                if len(cell_idx) == 0:
                    Errors[Counter] = Eps_max
                    continue

                # ── Find the best-matching modeled landslide ─────────────────
                # No BFS is run here — all shapes were cached before this loop.
                # Iterate over newly failing cells and look up their cached shape.
                best_err      = Eps_max
                best_res      = None
                best_k        = -1
                best_err_cd   = 0.0
                best_err_area = 0.0
                best_err_vol  = 0.0

                for k in range(len(cell_idx)):
                    key = (int(active_close[cell_idx[k]]), int(depth_idx[k]))
                    res = _bfs_cache.get(key)
                    # Skip this cell if BFS found it invalid (too small, sink, etc.)
                    if res is None:
                        continue

                    # Centroid distance error (normalised by sqrt of mapped area)
                    dist_cd = math.sqrt((res['cx'] - Mapped_Centroid_X)**2 +
                                        (res['cy'] - Mapped_Centroid_Y)**2)
                    e_cd    = abs(dist_cd / Mapped_area_ST) if Mapped_area_ST != 0 else 0.0

                    # Area mismatch error (relative)
                    e_area  = ((res['area'] - Mapped_area)   / Mapped_area
                               if Mapped_area   != 0 else 0.0)
                    # Volume mismatch error (relative)
                    e_vol   = ((res['vol']  - Mapped_volume) / Mapped_volume
                               if Mapped_volume != 0 else 0.0)

                    # Combined local error = Euclidean norm of the three components
                    err = math.sqrt(e_cd**2 + e_area**2 + e_vol**2)

                    # Update the best match if this landslide has a smaller error
                    if err < best_err:
                        best_err      = err
                        best_res      = res
                        best_k        = k
                        best_err_cd   = e_cd
                        best_err_area = e_area
                        best_err_vol  = e_vol

                # No valid modeled landslide found — assign maximum error and skip
                if best_res is None:
                    Errors[Counter] = Eps_max
                    continue

                # Depth index of the best-matching modeled landslide
                _di_best = int(depth_idx[best_k])

                # Store the results for the best match at this (Phi, c, t) combo
                Errors[Counter]      = best_err
                Errors_CD[Counter]   = best_err_cd
                Errors_Area[Counter] = best_err_area
                Errors_Vol[Counter]  = best_err_vol
                Areas[Counter]       = best_res['area']
                Vols[Counter]        = best_res['vol']
                CDs_x[Counter]       = best_res['cx']
                CDs_y[Counter]       = best_res['cy']
                Trigs_Indices[Counter] = best_res['trig_index']
                # Store triggering cell coordinates (handle 1D and 2D coordinate arrays)
                if x_sub.ndim == 1:
                    Trigs_x[Counter] = x_sub[best_res['trig_col']]
                    Trigs_y[Counter] = y_sub[best_res['trig_row']]
                else:
                    Trigs_x[Counter] = x_sub[best_res['trig_row'], best_res['trig_col']]
                    Trigs_y[Counter] = y_sub[best_res['trig_row'], best_res['trig_col']]
                Trigs_Slope[Counter] = best_res['trig_slope']
                Trigs_Z[Counter]     = float(Depths_vector[_di_best])
                Trigs_P[Counter]     = float(P_all[cell_idx[best_k], _di_best, t])

    # ── Post-processing: identify global minimum error ────────────────────────
    # Trim arrays to the number of completed iterations
    Errors = Errors[:Counter]

    # Find the smallest error across all (Phi, c, t) combinations
    Min_Global_Error       = np.min(Errors)
    # All combinations that achieve this minimum are equally acceptable solutions
    Index_Min_Global_Error = np.where(Errors == Min_Global_Error)[0]

    # Extract the full result vectors for all acceptable combinations
    Errors_excel      = Errors[Index_Min_Global_Error]
    Errors_CD_excel   = Errors_CD[Index_Min_Global_Error]
    Errors_Area_excel = Errors_Area[Index_Min_Global_Error]
    Errors_Vol_excel  = Errors_Vol[Index_Min_Global_Error]
    Phis_excel        = Phis[Index_Min_Global_Error]
    Cs_excel          = Cs[Index_Min_Global_Error]
    Times_excel       = Times[Index_Min_Global_Error]
    Areas_excel       = Areas[Index_Min_Global_Error]
    Vols_excel        = Vols[Index_Min_Global_Error]
    CDs_x_excel       = CDs_x[Index_Min_Global_Error]
    CDs_y_excel       = CDs_y[Index_Min_Global_Error]
    Trigs_Indices_excel = Trigs_Indices[Index_Min_Global_Error]
    Trigs_x_excel     = Trigs_x[Index_Min_Global_Error]
    Trigs_y_excel     = Trigs_y[Index_Min_Global_Error]
    Trigs_Slope_excel = Trigs_Slope[Index_Min_Global_Error]
    Depths_excel      = Trigs_Z[Index_Min_Global_Error]
    Pressures_excel   = Trigs_P[Index_Min_Global_Error]

    # ── Convert triggering cell coordinates to row/col in the full DEM ────────
    # The cropped sub-DEM uses local indices; convert back to the main raster grid
    Trig_row_Excel, Trig_col_Excel = xy_to_rowcol(
        Trigs_x_excel, Trigs_y_excel, xmin, xmax, ymin, ymax, Cell_size
    )

    # ── Compute effective normal stress and shear strength (Mohr-Coulomb) ──────
    # σ_n' = γ·z·cos²α − γ_w·P
    Normal_Stress_excel  = (Gamma_soil * Depths_excel
                            * np.cos(np.radians(Trigs_Slope_excel))**2
                            - Pressures_excel * Gamma_W)
    # τ = c + σ_n' · tan(Phi)
    Shear_Strength_excel = Cs_excel + Normal_Stress_excel * np.tan(np.radians(Phis_excel))

    # ── Assemble and write the Excel output ───────────────────────────────────
    data = {
        'Errors (unitless)':                       Errors_excel,
        'Errors_CD (unitless)':                     Errors_CD_excel,
        'Errors_Area (unitless)':                   Errors_Area_excel,
        'Errors_Vol (unitless)':                    Errors_Vol_excel,
        'Phis (deg)':                               Phis_excel,
        'Cs (kPa)':                                 Cs_excel,
        'Times (time step index)':                  Times_excel,
        'Areas (m^2)':                              Areas_excel,
        'Vols (m^3)':                               Vols_excel,
        'CDs_x (m)':                                CDs_x_excel,
        'CDs_y (m)':                                CDs_y_excel,
        'Trigs_Indices_in_cropped_DEM (unitless)':  Trigs_Indices_excel,
        'Trigs_x (m)':                               Trigs_x_excel,
        'Trigs_y (m)':                               Trigs_y_excel,
        'Trigs_row_main_DEM (unitless)':            Trig_row_Excel,
        'Trigs_col_main_DEM (unitless)':            Trig_col_Excel,
        'Trigs_Slope (deg)':                        Trigs_Slope_excel,
        'Trig_Depths (m)':                          Depths_excel,
        'Pressures (m)':                            Pressures_excel,
        'Effective_Normal_Stress (kPa)':            Normal_Stress_excel,
        'Shear_Strength (kPa)':                     Shear_Strength_excel,
    }

    df = pd.DataFrame(data)
    # Write one row per acceptable solution to the Excel output file
    excel_file = str(Path(output_dir) / f'acceptable_combinations_for_LD_{Landslide_ID}.xlsx')
    df.to_excel(excel_file, index=False)

    # ── Re-run BFS for the first acceptable solution to generate the shapefile ─
    # Take the first acceptable combination and reproduce the landslide geometry
    # to export it as a shapefile for GIS visualisation
    Depth1      = Depths_excel[0]
    Trig_index1 = int(Trigs_Indices_excel[0])
    Pressures1  = Pressures_excel[0]

    # Run Determine_Pseudo_3D_landslides with the best triggering cell and depth.
    # Indicator=2 signals that a single constant depth value is used.
    (Vol1, Area1, FID1, NL1, Mat_LD_ind1,
     Trig_Index_Accept1, Trig_Depths_Accept1, Pressures_Accept1,
     Slope_Trig_Index_Accept1, Fail_Index1) = Determine_Pseudo_3D_landslides(
        Elev_Mat_sub, Trig_index1, Area_Mat_sub, Slope_Mat_sub, FD_Mat_sub,
        Cell_size, Trig_index1, Pressures1, 2,
        upgrid_lookup=upgrid_lookup_sub
    )

    # Write the best-matching landslide polygon to a shapefile
    Modeled_landslides_shapefiles(
        FID1, Cell_size, x_sub, y_sub,
        Coordinate_Reference_System, Landslide_ID,
        output_dir=output_dir
    )

    # ── Reset intermediate arrays for garbage collection ──────────────────────
    # These arrays are large; releasing them explicitly frees memory in the worker
    # process before the next landslide is dispatched
    Errors = Errors_CD = Errors_Area = Errors_Vol = np.array([])
    Phis   = Cs = Times = Areas = Vols = np.array([])
    CDs_x  = CDs_y = Trigs_Indices = np.array([])
    Trigs_x = Trigs_y = Trigs_Slope = Trigs_Z = Trigs_P = np.array([])


# =============================================================================
# Function 10 — Aggregate all landslides into one summary workbook
# =============================================================================

def generate_summary_excel(output_dir):
    """
    Aggregate every acceptable_combinations_for_LD_{ID}.xlsx file in
    output_dir into a single Back_Calculated_Landslides_Summary.xlsx —
    one row per landslide with the mean/SD of its back-calculated strength
    parameters. Only solutions with positive effective normal stress are
    kept (matching Mohr-Coulomb: negative normal stress has no physical
    shear-strength solution); a landslide with no positive-stress solution
    is instead listed in a separate 'Excluded_Landslides' sheet.

    Returns
    -------
    (summary_df, excluded) : (DataFrame or None, list[int])
        summary_df is None if no landslide produced any usable solution.
    """
    out_path = Path(output_dir)
    pattern  = _re.compile(r'^acceptable_combinations_for_LD_(\d+)\.xlsx$', _re.IGNORECASE)
    ld_files = sorted(
        [(int(m.group(1)), f) for f in out_path.iterdir()
         if (m := pattern.match(f.name))],
        key=lambda item: item[0]
    )

    rows, excluded = [], []
    for num, fpath in ld_files:
        try:
            df_ld = pd.read_excel(fpath, header=0)
        except Exception:
            continue
        M = df_ld.values
        if M.shape[1] < 21:
            continue
        # Column layout matches process_mapped_landslide's `data` dict above:
        # Errors, Errors_CD, Errors_Area, Errors_Vol, Phis, Cs, Times, Areas,
        # Vols, CDs_x, CDs_y, Trigs_Indices_in_cropped_DEM, Trigs_x, Trigs_y,
        # Trigs_row_main_DEM, Trigs_col_main_DEM, Trigs_Slope, Trig_Depths,
        # Pressures, Effective_Normal_Stress, Shear_Strength
        Total_error  = M[:, 0].astype(float)
        CD_error     = M[:, 1].astype(float)
        Area_error   = M[:, 2].astype(float)
        Volume_error = M[:, 3].astype(float)
        Phi          = M[:, 4].astype(float)
        cohesion     = M[:, 5].astype(float)
        Area_modeled = M[:, 7].astype(float)
        Vol_modeled  = M[:, 8].astype(float)
        Trig_row     = M[:, 14].astype(float)
        Trig_col     = M[:, 15].astype(float)
        Trig_Slope   = M[:, 16].astype(float)
        Trig_Depths  = M[:, 17].astype(float)
        ENS          = M[:, -2].astype(float)  # Effective_Normal_Stress
        SS           = M[:, -1].astype(float)  # Shear_Strength

        pos = ENS > 0
        if not np.any(pos):
            excluded.append(num)
            continue
        ENS = ENS[pos]; SS = SS[pos]; cohesion = cohesion[pos]
        Phi = Phi[pos]; Trig_Depths = Trig_Depths[pos]
        Trig_Slope = Trig_Slope[pos]; Trig_row = Trig_row[pos]
        Trig_col = Trig_col[pos]; Total_error = Total_error[pos]
        CD_error = CD_error[pos]; Area_error = Area_error[pos]
        Volume_error = Volume_error[pos]
        Area_modeled = Area_modeled[pos]; Vol_modeled = Vol_modeled[pos]

        mapped_area = Area_modeled / (1 + Area_error)
        mapped_vol  = Vol_modeled  / (1 + Volume_error)
        avg_depth   = mapped_vol / mapped_area

        rows.append([
            num, mapped_area[0], mapped_vol[0],
            np.mean(ENS), np.std(ENS, ddof=0),
            np.mean(SS),  np.std(SS,  ddof=0),
            np.mean(SS) / np.mean(ENS),
            np.mean(Trig_Slope),
            np.mean(cohesion), np.std(cohesion, ddof=0),
            np.mean(Phi),      np.std(Phi,      ddof=0),
            np.mean(Trig_Depths), np.std(Trig_Depths, ddof=0),
            Total_error[0], CD_error[0], Area_error[0], Volume_error[0],
            avg_depth[0], Trig_row[0], Trig_col[0],
        ])

    if not rows:
        return None, excluded

    cols = [
        'Landslide Number', 'Mapped Area (m^2)', 'Mapped Volume (m^3)',
        'Average Effective Normal Stress (kPa)', 'Effective Normal Stress SD (kPa)',
        'Average Shear Strength (kPa)', 'Shear Strength SD (kPa)',
        'Normalized Shear Strength (unitless)', 'Slope of Triggering Cell (deg)',
        'Average cohesion (kPa)', 'cohesion SD (kPa)', 'Average Phi (deg)', 'Phi SD (deg)',
        'Average Triggering depth (m)', 'Triggering depth SD (m)',
        'Total error (unitless)', 'CD error (unitless)', 'Area error (unitless)', 'Volume error (unitless)',
        'Average Mapped depth (m)',
        'Row of triggering cell in main DEM (unitless)', 'Col of triggering cell in main DEM (unitless)',
    ]
    summary_df = pd.DataFrame(rows, columns=cols)
    summary_path = out_path / 'Back_Calculated_Landslides_Summary.xlsx'
    with pd.ExcelWriter(str(summary_path), engine='openpyxl') as writer:
        summary_df.to_excel(writer, sheet_name='Sheet1', index=False)
        if excluded:
            pd.DataFrame({'Excluded_Landslide_Number': excluded}).to_excel(
                writer, sheet_name='Excluded_Landslides', index=False)
        # Auto-fit column widths to header text on every sheet
        for sheet in writer.sheets.values():
            for col_cells in sheet.iter_cols():
                header = col_cells[0].value  # first row is the header
                if header is not None:
                    sheet.column_dimensions[col_cells[0].column_letter].width = \
                        max(len(str(header)) + 2, 10)

    return summary_df, excluded


# =============================================================================
# Parallel worker helper
# =============================================================================

def _worker_stdout_init():
    """
    Redirect worker-process stdout to /dev/null at process startup.

    When the GUI launches workers via ProcessPoolExecutor, their stdout is
    connected to a pipe that nothing reads.  Once the 64 KB Windows pipe buffer
    fills, every print() blocks until it drains — serialising all workers.
    Redirecting to devnull at init time eliminates this bottleneck.
    """
    import sys
    sys.stdout = open(os.devnull, 'w')


def load_dem(file_path):
    """
    Load a DEM from either an HDF5 file (no georeferencing) or a
    georeferenced raster such as a GeoTIFF (via rasterio).

    Returns (elevation, geo):
        elevation : float32 array, no-data cells set to NaN.
        geo       : None for HDF5, or (Cell_size, xmin, ymin) derived from
                    the raster's embedded geotransform for GeoTIFF/other
                    GDAL-readable formats — (xmin, ymin) is the raster's
                    lower-left bounding-box corner, matching the convention
                    already used by the manually-entered Cell_size/xmin/ymin
                    fields elsewhere in CRISIS. Letting the caller auto-fill
                    those fields from this avoids the manual-entry mismatches
                    that used to cause misaligned rasters.

    Identical to forward_analysis.load_dem — kept as its own copy here (same
    convention as compute_slope_gradient8 and the other utility functions
    duplicated between forward_analysis.py and back_analysis.py) so this
    module has no import-time dependency on forward_analysis.py being
    present.
    """
    suffix = Path(file_path).suffix.lower()
    if suffix not in ('.tif', '.tiff'):
        with h5py.File(file_path, 'r') as f:
            return f['data'][:].astype(np.float32), None

    try:
        import rasterio
    except ImportError as exc:
        raise ImportError(
            f"Reading '{Path(file_path).name}' as a GeoTIFF DEM requires the "
            "'rasterio' package, which is not installed. Install it with: "
            "pip install rasterio"
        ) from exc

    with rasterio.open(file_path) as src:
        if src.crs is None:
            raise ValueError(
                f"{Path(file_path).name}: this GeoTIFF has no coordinate "
                "reference system (CRS) embedded, so CRISIS cannot verify "
                "its Cell_size/xmin/ymin would be in meters. Assign a "
                "projected CRS to it in GIS software first."
            )
        if src.crs.is_geographic:
            raise ValueError(
                f"{Path(file_path).name}: this GeoTIFF is in a geographic "
                f"CRS ({src.crs}) — its coordinates are in degrees, not "
                "meters. CRISIS requires Cell_size/xmin/ymin in meters. "
                "Reproject this DEM to a projected CRS (e.g. the UTM zone "
                "or state plane matching your study area) in GIS software "
                "first — e.g. QGIS: Raster > Projections > Warp (Reproject); "
                "ArcGIS Pro: Project Raster."
            )
        _linear_unit = (src.crs.linear_units or '').lower()
        if _linear_unit not in ('metre', 'meter', 'metres', 'meters'):
            raise ValueError(
                f"{Path(file_path).name}: this GeoTIFF's projected CRS uses "
                f"'{src.crs.linear_units}' as its linear unit, not meters. "
                "CRISIS requires Cell_size/xmin/ymin in meters — reproject "
                "this DEM to a meters-based projected CRS first."
            )

        transform = src.transform
        if transform.b != 0 or transform.d != 0:
            raise ValueError(
                f"{Path(file_path).name}: this GeoTIFF's grid is rotated or "
                "sheared, which CRISIS does not support — the DEM must be a "
                "plain north-up grid."
            )
        Cell_size = float(transform.a)
        if abs(abs(transform.e) - Cell_size) > 0.01 * Cell_size:
            raise ValueError(
                f"{Path(file_path).name}: this GeoTIFF's pixels are not "
                f"square (x resolution {transform.a:.6g} m vs. y resolution "
                f"{abs(transform.e):.6g} m) — CRISIS requires a single "
                "uniform Cell_size."
            )
        xmin = float(src.bounds.left)
        ymin = float(src.bounds.bottom)

        elevation = src.read(1).astype(np.float32)
        if src.nodata is not None:
            elevation[elevation == np.float32(src.nodata)] = np.nan

    return elevation, (Cell_size, xmin, ymin)


# =============================================================================
# Main entry point — callable from the CRISIS GUI
# =============================================================================

def run_model(params, log_callback=None, precomputed_rasters=None):
    """
    Run the full back-analysis pipeline using parameters from the CRISIS GUI.

    Parameters
    ----------
    params       : dict       Parameter dict from the GUI or a JSON config file.
    log_callback : callable   function(msg, tag='') for progress reporting in
                              the GUI log widget.  Defaults to print.
    precomputed_rasters : dict, optional
        Elev_Mat/Slope_Mat/FD_Mat/Area_Mat_counts already computed for this
        exact dem_file + Cell_size (e.g. by the GUI's Topography preview),
        keyed as {'dem_file', 'Cell_size', 'Elev_Mat', 'Slope_Mat', 'FD_Mat',
        'Area_Mat_counts'}. When the dem_file/Cell_size match the current
        params, these are reused instead of recomputing Slope/Flow Direction/
        Flow Accumulation from scratch — Flow Direction alone can take about
        a minute, so this avoids paying that cost twice (once for the GUI
        preview, once for the actual run) when nothing has changed.
    """
    # ── Auto-derive Cell_size/xmin/ymin from a GeoTIFF DEM, if given ──────────
    # A GeoTIFF carries its own geotransform, so Cell_size/xmin/ymin can be
    # read directly from the file instead of requiring manual entry (and
    # risking a mismatch with the actual raster). Done before params is read
    # below so a GeoTIFF-based run can leave those three fields blank/null.
    # The loaded array is stashed to avoid reading the file twice.
    _preloaded_dem_array = None
    _dem_file_raw = params.get('dem_file', '')
    if str(_dem_file_raw).lower().endswith(('.tif', '.tiff')):
        _preloaded_dem_array, _dem_geo = load_dem(_dem_file_raw)
        if _dem_geo is not None:
            params = dict(params)  # don't mutate the caller's dict
            params['Cell_size'], params['xmin'], params['ymin'] = _dem_geo
            _msg = (f"Auto-derived from GeoTIFF DEM: Cell_size={params['Cell_size']:.6g} m, "
                    f"xmin={params['xmin']:.6g}, ymin={params['ymin']:.6g}\n")
            log_callback(_msg, tag='info') if log_callback else print(_msg, end='')

    def _log(msg, tag=''):
        if log_callback:
            log_callback(msg, tag=tag)
        else:
            print(msg, end='')

    # ── Unpack all parameters from the GUI dict ───────────────────────────────
    def _get(key, default=None):
        return params.get(key, default)

    dem_file             = _get('dem_file', '')
    hydro_dir            = _get('hydro_files_dir', '')
    theta_dir            = _get('theta_files_dir', '')
    sv_theta             = int(_get('Strength_variation_with_theta') or 0)
    Cell_size            = float(_get('Cell_size') or 1.0)
    Gamma_soil           = float(_get('Gamma_soil') or 22.0)
    Gamma_W              = 9.81   # unit weight of water (kN/m³) — physical constant
    z_min                = float(_get('z_min') or 0.125)
    z_max                = float(_get('z_max') or 2.875)
    xmin                 = float(_get('xmin') or 0.0)
    ymin                 = float(_get('ymin') or 0.0)
    R_search             = float(_get('R_search') or 1.2)
    CRS                  = str(_get('Coordinate_Reference_System') or 'EPSG:4326')
    C_single_min         = float(_get('C_single_min') or 0.0)
    C_single_max         = float(_get('C_single_max') or 30.0)
    C_single_increment   = float(_get('C_single_increment') or 2.0)
    Phi_single_min       = float(_get('Phi_single_min') or 25.0)
    Phi_single_max       = float(_get('Phi_single_max') or 55.0)
    Phi_single_increment = float(_get('Phi_single_increment') or 2.0)
    Theta_s              = _get('Theta_s')
    Theta_r              = _get('Theta_r')
    Theta_s              = float(Theta_s) if Theta_s is not None else None
    Theta_r              = float(Theta_r) if Theta_r is not None else None
    ids_file             = _get('landslide_ids_file', '')
    ld_dir               = _get('landslide_files_dir', '')
    _title               = (_get('project_title') or 'CRISIS').strip() or 'CRISIS'
    output_dir           = Path(_get('output_dir') or '.') / f'{_title}_Outputs'

    # ── Validate required inputs ──────────────────────────────────────────────
    missing = []
    for label, path in [
        ('DEM',                   dem_file),
        ('Pore Pressure Directory', hydro_dir),
        ('Landslide IDs File',    ids_file),
        ('Landslide Files Directory', ld_dir),
    ]:
        if not path:
            missing.append(label)
    # xmin/ymin are the lower-left corner used to auto-derive x/y coordinates
    # and must be given explicitly now that no coordinate files are read
    for label, val in [('xmin', _get('xmin')), ('ymin', _get('ymin'))]:
        if val is None or val == '':
            missing.append(label)
    if sv_theta == 1:
        for label, val in [('Theta_s', Theta_s), ('Theta_r', Theta_r)]:
            if val is None:
                missing.append(label)
    if missing:
        _log(f'✗  Missing required inputs: {", ".join(missing)}\n', tag='err')
        return

    # Create the output directory (including any missing parent directories)
    output_dir.mkdir(parents=True, exist_ok=True)
    _log(f'Output directory: {output_dir}\n', tag='info')

    # ── Load static topographic rasters ───────────────────────────────────────
    def load_h5(path):
        """Load the 'data' dataset from an HDF5 file as float32."""
        with h5py.File(path, 'r') as f:
            return f['data'][:].astype(np.float32)

    # Reuse Slope/Flow Direction/Flow Accumulation from the GUI's Topography
    # preview if they were computed for this exact DEM file + Cell_size —
    # Flow Direction/Accumulation are the expensive step (~1 minute), so this
    # avoids computing them twice for a single run
    cache = precomputed_rasters or {}
    cache_valid = (
        cache.get('dem_file') == dem_file
        and cache.get('Elev_Mat') is not None
        and cache.get('Slope_Mat') is not None
        and cache.get('FD_Mat') is not None
        and cache.get('Area_Mat_counts') is not None
        and abs(float(cache.get('Cell_size', float('nan'))) - Cell_size) < 1e-9
    )

    if cache_valid:
        _log('Reusing Slope / Flow Direction / Flow Accumulation from the Topography preview '
             '(same DEM + Cell_size — skipping recomputation).\n', tag='info')
        Elev_Mat  = cache['Elev_Mat']
        Slope_Mat = cache['Slope_Mat'].astype(np.float32)
        FD_Mat    = cache['FD_Mat'].astype(np.float32)
        Area_Mat  = cache['Area_Mat_counts'] * Cell_size ** 2
    else:
        _log('Loading raster files…\n')
        # DEM: replace no-data values. Reuse the array already loaded above
        # for a GeoTIFF DEM instead of reading the file a second time; a NaN
        # mask (GeoTIFF nodata) is unaffected by the '< -900' filter below,
        # so this is safe either way.
        Elev_Mat = (_preloaded_dem_array if _preloaded_dem_array is not None
                    else load_h5(dem_file))
        Elev_Mat[Elev_Mat < -900] = np.nan

        # Auto-compute Slope from the DEM using the gradient8 (steepest
        # 8-connected neighborhood) method — no Slope.h5 file needed
        _log('Computing slope from DEM (gradient8 method)…\n')
        Slope_Mat = compute_slope_gradient8(Elev_Mat, Cell_size, unit='degree').astype(np.float32)

        # Auto-compute Flow Direction (TopoToolbox FLOWobj-equivalent) from
        # the DEM — no Flow_Direction.h5 file needed. This step fills
        # depressions and resolves flats, so it takes noticeably longer than
        # the other rasters (roughly half a minute on a ~3000x2000 DEM).
        _log('Computing flow direction from DEM (FLOWobj-equivalent, this can take ~1 minute)…\n')
        FD_Mat = compute_flow_direction_topotoolbox(Elev_Mat, Cell_size).astype(np.float32)

        # Auto-compute Flow Accumulation (TopoToolbox flowacc-equivalent)
        # from the flow direction just computed, then convert cell count to
        # contributing area (m²) — no Flow_Accumulation.h5 file needed
        _log('Computing flow accumulation from flow direction…\n')
        Area_Mat = compute_flow_accumulation_topotoolbox(FD_Mat)
        Area_Mat = Area_Mat * Cell_size ** 2

    # Determine grid dimensions from the DEM
    rows, columns = Elev_Mat.shape
    _log(f'DEM shape: {rows} × {columns}\n')

    # Derive upper-right corner from lower-left corner + raster dimensions.
    # xmax and ymax are NOT user inputs — they are computed here automatically.
    xmax = xmin + columns * Cell_size
    ymax = ymin + rows    * Cell_size
    _log(f'Computed xmax = {xmax:.6f},  ymax = {ymax:.6f}\n')

    # Auto-compute x/y cell-center coordinate vectors from the lower-left
    # corner (xmin, ymin) and Cell_size — no coordinate files needed
    x, y = compute_coordinate_vectors(rows, columns, xmin, ymin, Cell_size)
    _log('Computed x/y coordinate vectors from xmin, ymin, and Cell_size.\n')

    # ── Detect Depth_points and Time_points from pore pressure files ─────────
    hydro_path = Path(hydro_dir)
    _pp_files  = sorted(hydro_path.glob('Pressure_head_T*Z*.h5'))
    if not _pp_files:
        _log(f'✗  No Pressure_head_T*Z*.h5 files found in {hydro_path}\n', tag='err')
        return
    _t_vals, _d_vals = set(), set()
    for _f in _pp_files:
        _m = _re.search(r'Pressure_head_T(\d+)Z(\d+)\.h5', _f.name)
        if _m:
            _t_vals.add(int(_m.group(1)))
            _d_vals.add(int(_m.group(2)))
    # Files are 0-indexed for T (T0…T_N) and 1-indexed for Z (Z1…Z_D)
    _detected_tp = max(_t_vals) + 1
    _detected_dp = max(_d_vals)
    _log(f'Detected from directory: {_detected_tp} time points × {_detected_dp} depth layers\n')

    # Validate against user-supplied values if provided
    _user_tp = int(_get('Time_points') or 0)
    _user_dp = int(_get('Depth_points') or 0)
    if _user_tp and _user_tp != _detected_tp:
        _log(f'✗  Time_points mismatch: config says {_user_tp} but directory contains {_detected_tp} time steps.\n', tag='err')
        return
    if _user_dp and _user_dp != _detected_dp:
        _log(f'✗  Depth_points mismatch: config says {_user_dp} but directory contains {_detected_dp} depth layers.\n', tag='err')
        return

    Time_points  = _detected_tp
    Depth_points = _detected_dp

    # Build the depth discretization vector from z_min to z_max
    Depths_vector = np.linspace(z_min, z_max, Depth_points, dtype=np.float32)

    # ── Load the 4D pore pressure array (rows × cols × depths × times) ────────
    _log(f'Loading pore pressure files ({Time_points} × {Depth_points})…\n')
    Pressures_4D_array = np.full(
        (rows, columns, Depth_points, Time_points), np.nan, dtype=np.float32
    )
    for t in range(Time_points):
        for d in range(Depth_points):
            fpath = hydro_path / f'Pressure_head_T{t}Z{d+1}.h5'
            if fpath.exists():
                data = load_h5(str(fpath))
                # Raster size must match the DEM exactly — a mismatch here
                # used to be silently cropped to (rows, columns), which could
                # misalign pore pressure data against elevation with no warning
                if data.shape[:2] != (rows, columns):
                    _log(f'✗  {fpath.name}: raster size {data.shape[0]}×{data.shape[1]} '
                         f'does not match DEM size {rows}×{columns}.\n', tag='err')
                    return
                # Cap pore pressure head at the depth of each layer
                data[data > Depths_vector[d]] = Depths_vector[d]

                Pressures_4D_array[:, :, d, t] = data
        # Log progress roughly every 10% of time steps
        if t % max(1, Time_points // 10) == 0:
            _log(f'  Loaded time step {t}/{Time_points - 1}\n')

    # ── Load the 4D volumetric water content array ────────────────────────────
    if sv_theta == 0:
        # Fully saturated assumption: Bishop χ is fixed at 1.0 downstream and
        # this array's contents are never read, so no Theta_s value is
        # required here — just allocate a placeholder.
        Theta_4D = np.zeros(
            (rows, columns, Depth_points, Time_points), dtype=np.float32
        )
    else:
        # Load θ from HDF5 files one (t, d) slice at a time
        _log('Loading volumetric water content files…\n')
        Theta_4D   = np.zeros((rows, columns, Depth_points, Time_points), dtype=np.float32)
        theta_path = Path(theta_dir) if theta_dir else hydro_path
        for t in range(Time_points):
            for d in range(Depth_points):
                fpath = theta_path / f'Theta_T{t}Z{d+1}.h5'
                if fpath.exists():
                    data = load_h5(str(fpath))
                    if data.shape[:2] != (rows, columns):
                        _log(f'✗  {fpath.name}: raster size {data.shape[0]}×{data.shape[1]} '
                             f'does not match DEM size {rows}×{columns}.\n', tag='err')
                        return
                    Theta_4D[:, :, d, t] = data

    # ── Read the list of mapped landslide IDs ─────────────────────────────────
    _log('Reading landslide inventory…\n')
    id_df         = pd.read_excel(ids_file, header=None)
    Landslide_IDs = (pd.to_numeric(id_df.iloc[:, 0], errors='coerce')
                     .dropna().astype(int).values)
    _log(f'Found {len(Landslide_IDs)} mapped landslides: {Landslide_IDs}\n')

    # ── Compute total iteration count for progress reporting ──────────────────
    c_vals   = list(np.arange(C_single_min,   C_single_max   + C_single_increment,   C_single_increment))
    phi_vals = list(np.arange(Phi_single_min, Phi_single_max + Phi_single_increment, Phi_single_increment))
    Total_num_iterations = len(phi_vals) * len(c_vals) * max(1, Time_points - 1)
    _log(f'Total iterations per landslide: {Total_num_iterations}\n')

    # ── Extract per-landslide sub-arrays from the full rasters ────────────────
    # Each worker receives only its own pre-cropped sub-arrays so pickling cost
    # is proportional to one landslide's data, not the full domain
    _log('Extracting per-landslide sub-arrays…\n')
    Elev_Mat_list           = []
    Slope_Mat_list          = []
    FD_Mat_list             = []
    Area_Mat_list           = []
    x_list                  = []
    y_list                  = []
    Pressures_4D_array_list = []
    Theta_4D_array_list     = []

    for LD_ID in Landslide_IDs:
        excel_path = Path(ld_dir) / f'LD{LD_ID}.xlsx'
        if not excel_path.exists():
            _log(f'  Warning: {excel_path} not found — skipping.\n', tag='err')
            continue
        ld_data = pd.read_excel(str(excel_path)).values
        cx, cy  = float(ld_data[0, 1]), float(ld_data[0, 2])
        area    = float(ld_data[0, 0])
        # Search radius defines the half-width of the sub-array window
        radius  = R_search * np.sqrt(area) + Cell_size

        # Locate the centroid cell in the coordinate arrays
        ix = (np.argmin(np.abs(x[0, :] - cx)) if x.ndim == 2
              else np.argmin(np.abs(x - cx)))
        iy = (np.argmin(np.abs(y[:, 0] - cy)) if y.ndim == 2
              else np.argmin(np.abs(y - cy)))
        n_cells = max(1, int(np.ceil(radius / Cell_size)))

        # Clip the window to the DEM boundary
        r0 = max(0, iy - n_cells);  r1 = min(rows    - 1, iy + n_cells)
        c0 = max(0, ix - n_cells);  c1 = min(columns - 1, ix + n_cells)

        # Crop all rasters and coordinate arrays to the sub-window
        Elev_Mat_list.append(Elev_Mat[r0:r1+1, c0:c1+1])
        Slope_Mat_list.append(Slope_Mat[r0:r1+1, c0:c1+1])
        FD_Mat_list.append(FD_Mat[r0:r1+1, c0:c1+1])
        Area_Mat_list.append(Area_Mat[r0:r1+1, c0:c1+1])
        x_list.append(x[r0:r1+1, c0:c1+1] if x.ndim == 2 else x[c0:c1+1])
        y_list.append(y[r0:r1+1, c0:c1+1] if y.ndim == 2 else y[r0:r1+1])
        Pressures_4D_array_list.append(Pressures_4D_array[r0:r1+1, c0:c1+1, :, :])
        Theta_4D_array_list.append(Theta_4D[r0:r1+1, c0:c1+1, :, :])

    # Abort if no valid landslide data was loaded
    if not Elev_Mat_list:
        _log('✗  No valid landslide data loaded. Check the landslide files directory.\n', tag='err')
        return

    _log(f'Processing {len(Elev_Mat_list)} landslide(s) in parallel…\n', tag='info')

    # ── Collect valid landslide IDs (those with an existing LD{ID}.xlsx) ──────
    valid_ids = [
        LD_ID for LD_ID in Landslide_IDs
        if (Path(ld_dir) / f'LD{LD_ID}.xlsx').exists()
    ]

    # ── Set up a Manager queue for worker progress messages ───────────────────
    # multiprocessing.Queue cannot be pickled on Windows (spawn-based start method);
    # a Manager proxy queue can be safely passed to spawned worker processes
    _manager       = _Manager()
    progress_queue = _manager.Queue()
    _drain_stop    = threading.Event()

    # Drain the progress queue on a background thread so messages reach the GUI
    # without blocking the worker processes
    def _drain():
        while not _drain_stop.is_set() or not progress_queue.empty():
            try:
                msg = progress_queue.get(timeout=0.5)
                _log(msg)
            except Exception:
                pass

    drain_thread = threading.Thread(target=_drain, daemon=True)
    drain_thread.start()

    # ── Build per-landslide argument tuples ───────────────────────────────────
    args_list = [
        (
            valid_ids[i],
            Elev_Mat_list[i], Slope_Mat_list[i], FD_Mat_list[i],
            Area_Mat_list[i], x_list[i], y_list[i],
            Pressures_4D_array_list[i], Theta_4D_array_list[i],
            Cell_size, R_search,
            Phi_single_min, Phi_single_max, Phi_single_increment,
            C_single_min,   C_single_max,   C_single_increment,
            Gamma_W, Gamma_soil, Depths_vector,
            CRS,
            sv_theta, Theta_s, Theta_r,
            Total_num_iterations, xmin, xmax, ymin, ymax, Time_points,
            str(output_dir), str(ld_dir), progress_queue,
        )
        for i in range(len(valid_ids))
    ]

    # ── Dispatch all landslides — one process per CPU core ────────────────────
    # ProcessPoolExecutor gives each worker its own Python interpreter and GIL,
    # so the pure-Python BFS loop runs in true parallel across all CPU cores.
    # n_workers can be set explicitly in the config (useful on HPC to match the
    # allocated core count); defaults to all available cores.
    _req_workers = _get('n_workers')
    n_workers = min(len(args_list),
                    int(_req_workers) if _req_workers else (os.cpu_count() or 1))
    completed = 0
    with ProcessPoolExecutor(max_workers=n_workers,
                             initializer=_worker_stdout_init) as executor:
        futures = {
            executor.submit(process_mapped_landslide, *args): valid_ids[i]
            for i, args in enumerate(args_list)
        }
        # Collect results as workers finish (order is non-deterministic)
        for future in as_completed(futures):
            LD = futures[future]
            try:
                future.result()
                completed += 1
                _log(f'  ✓  Landslide {LD} done  ({completed}/{len(args_list)})\n', tag='ok')
            except Exception as exc:
                _log(f'  ✗  Landslide {LD} error: {exc}\n', tag='err')

    # Signal the drain thread to stop and wait for it to flush remaining messages
    _drain_stop.set()
    drain_thread.join(timeout=5)

    # ── Aggregate every landslide's result into one summary workbook ──────────
    _log('Generating summary workbook...\n')
    try:
        summary_df, excluded = generate_summary_excel(output_dir)
        if summary_df is None:
            _log('No landslide produced a usable (positive effective stress) '
                 'solution — summary workbook not written.\n', tag='err')
        else:
            if excluded:
                _log(f'Excluded {len(excluded)} landslide(s) (non-positive effective '
                     f'normal stress).\n', tag='dim')
            _log(f'Summary saved → {output_dir}\\Back_Calculated_Landslides_Summary.xlsx\n',
                 tag='ok')
    except Exception as exc:
        _log(f'Summary workbook error: {exc}\n', tag='err')

    _log(f'\nBack-analysis complete. Outputs saved to: {output_dir}\n', tag='ok')


# =============================================================================
# Standalone / HPC entry point
# =============================================================================

if __name__ == '__main__':
    # Require exactly one argument: the path to a JSON configuration file
    if len(sys.argv) < 2:
        print("Usage: python back_analysis.py config.json")
        sys.exit(1)

    # Load all model parameters from the JSON config file into a plain Python dict
    with open(sys.argv[1], 'r') as fh:
        params = json.load(fh)

    # Run the full back-analysis; progress is printed to stdout by default
    run_model(params)
