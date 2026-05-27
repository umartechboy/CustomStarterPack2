#!/usr/bin/env python3
"""
drill_figure_back.py — drills 2 magnet holes side-by-side into the BACK of a figure.

Axis assumption: Z=up, Y=front-to-back (front=low Y, back=high Y), X=left-right.
Verify this matches your model orientation before relying on results.

Strategy:
  1. Restrict search to middle 40% of figure Z-height (center ±20%) to avoid head/feet.
  2. Find the vertex with the lowest Y (frontmost point) in that Z band.
  3. Use that vertex's Z and X as the drill anchor.
  4. Find the back surface at that (X, Z) position.
  5. Drill 2 holes side-by-side: same Z, offset left/right in X by --spacing-x/2.
"""

import argparse
import sys
import numpy as np
import trimesh
from trimesh.creation import cylinder


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--input",  required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--magnet-diameter",    type=float, default=6.0)
    p.add_argument("--magnet-height",      type=float, default=2.0)
    p.add_argument("--radial-tolerance",   type=float, default=0.2)
    p.add_argument("--depth-extra",        type=float, default=0.3)
    p.add_argument("--spacing-x",          type=float, default=20.0,
                   help="Distance between the two holes in X (center-to-center)")
    p.add_argument("--center-x",           type=float, default=None,
                   help="Override X center. Default: X of frontmost vertex in mid-body band.")
    p.add_argument("--center-z",           type=float, default=None,
                   help="Override Z of holes. Default: Z of frontmost vertex in mid-body band.")
    return p.parse_args()


def find_back_surface_y(mesh, x, z, y_min, y_max, step=0.3):
    """Find largest Y inside the mesh at (x, z) — i.e. the back surface."""
    for y in np.arange(y_max, y_min, -step):
        if mesh.contains(np.array([[x, y, z]]))[0]:
            return y + step / 2
    return None


def main():
    args = parse_args()
    print(f"\n=== drill_figure_back.py (side-by-side mode) ===\n")

    mesh = trimesh.load(args.input, force="mesh")
    print(f"  Loaded {len(mesh.faces):,} faces, watertight={mesh.is_watertight}")
    print(f"  Bounds: {mesh.bounds.tolist()}")

    z_min, z_max = mesh.bounds[0, 2], mesh.bounds[1, 2]
    z_height = z_max - z_min
    z_center = z_min + z_height / 2.0

    # Restrict to middle 40% of Z (center ±20%)
    z_band_lo = z_center - 0.20 * z_height
    z_band_hi = z_center + 0.20 * z_height
    print(f"  Z range: [{z_min:.1f}, {z_max:.1f}], center={z_center:.1f}")
    print(f"  Search band: Z=[{z_band_lo:.1f}, {z_band_hi:.1f}]")

    # Find frontmost vertex (lowest Y) in the Z band
    verts = mesh.vertices
    in_band = (verts[:, 2] >= z_band_lo) & (verts[:, 2] <= z_band_hi)
    band_verts = verts[in_band]

    if len(band_verts) == 0:
        print("  WARNING: no vertices in Z band — falling back to full mesh", file=sys.stderr)
        band_verts = verts

    frontmost_idx = np.argmin(band_verts[:, 1])
    frontmost = band_verts[frontmost_idx]
    print(f"  Frontmost vertex in band: X={frontmost[0]:.2f}, Y={frontmost[1]:.2f}, Z={frontmost[2]:.2f}")

    anchor_x = args.center_x if args.center_x is not None else frontmost[0]
    anchor_z = args.center_z if args.center_z is not None else frontmost[2]
    print(f"  Drill anchor: X={anchor_x:.2f}, Z={anchor_z:.2f}")

    # Find back surface at anchor (X, Z)
    y_min, y_max = mesh.bounds[0, 1], mesh.bounds[1, 1]
    surface_y = find_back_surface_y(mesh, anchor_x, anchor_z, y_min, y_max)
    if surface_y is None:
        print("FAIL: could not find back surface at anchor point", file=sys.stderr)
        sys.exit(2)
    print(f"  Back surface Y at anchor: {surface_y:.2f}")

    # Two hole positions: same Z, offset left/right in X
    half = args.spacing_x / 2.0
    hole_positions = [
        (anchor_x - half, surface_y, anchor_z),
        (anchor_x + half, surface_y, anchor_z),
    ]
    print(f"  Hole positions: {[(f'{x:.1f}', f'{y:.2f}', f'{z:.1f}') for x,y,z in hole_positions]}")

    radius   = args.magnet_diameter / 2.0 + args.radial_tolerance
    depth    = args.magnet_height + args.depth_extra
    overhang = 1.0
    cyl_h    = depth + overhang

    # Cylinder rotated to drill along Y axis
    rot = trimesh.transformations.rotation_matrix(np.pi / 2, [1, 0, 0])

    result = mesh
    for i, (mx, my, mz) in enumerate(hole_positions, 1):
        c = cylinder(radius=radius, height=cyl_h, sections=48)
        c.apply_transform(rot)
        cyl_center_y = my + overhang - cyl_h / 2.0  # drill inward from back toward front
        c.apply_translation([mx, cyl_center_y, mz])
        try:
            new_result = result.difference(c, engine="manifold")
            if new_result is None or new_result.is_empty:
                print(f"  WARNING: hole {i} empty result — skipped")
                continue
            result = new_result
            print(f"  ✓ Hole {i} drilled at ({mx:.1f}, {my:.2f}, {mz:.1f}), depth={depth:.1f}mm")
        except Exception as e:
            print(f"  ✗ Hole {i} failed: {e}", file=sys.stderr)

    result.export(args.output)
    print(f"\n[done] → {args.output} ({len(result.faces):,} faces)")

    import json
    print("MAGNETS_JSON: " + json.dumps({
        "z_positions": [mz for _, _, mz in hole_positions],
        "x_positions": [mx for mx, _, _ in hole_positions],
        "z_bottom": float(z_min),
        "center_x": float(anchor_x),
        "anchor_z": float(anchor_z),
    }))


if __name__ == "__main__":
    main()
