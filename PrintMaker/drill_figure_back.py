#!/usr/bin/env python3
"""
drill_figure_back.py — bohrt 2 Magnet-Löcher in den RÜCKEN einer Figur.

Auto-Z-range-detection:
  Falls --z1/--z2 nicht angegeben sind, scannt die Z-Range der Figur, findet
  wo Material ist und platziert die Magnete dort mit 40mm Abstand.

Surface-Detection:
  Für jeden Z-Punkt: probt entlang Y, findet echte Rücken-Surface.

Usage:
  python drill_figure_back.py --input X.stl --output Y.stl \\
      --magnet-diameter 6 --magnet-height 2 \\
      [--z1 -20 --z2 20] (Auto-detect falls nicht angegeben)
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
    p.add_argument("--magnet-diameter", type=float, default=6.0)
    p.add_argument("--magnet-height",   type=float, default=2.0)
    p.add_argument("--radial-tolerance", type=float, default=0.2)
    p.add_argument("--depth-extra",     type=float, default=0.3)
    p.add_argument("--z1", type=float, default=None, help="Z des ersten Magneten (auto if None)")
    p.add_argument("--z2", type=float, default=None, help="Z des zweiten Magneten (auto if None)")
    p.add_argument("--spacing-z", type=float, default=30.0,
                   help="Abstand zwischen Magneten in Z, falls auto-detect benutzt")
    p.add_argument("--center-x", type=float, default=None,
                   help="X-Position (default: figure-centroid X)")
    return p.parse_args()


def find_back_surface_y(mesh, x, z, y_min, y_max, step=0.3):
    """Find LARGEST Y where (x, y, z) is inside the mesh — i.e. the BACK surface.
    Hunyuan3D 3D outputs orient figures with face/chest toward Y_min, back toward Y_max."""
    for y in np.arange(y_max, y_min, -step):
        if mesh.contains(np.array([[x, y, z]]))[0]:
            return y + step / 2  # slightly behind for clean drill start
    return None


def find_material_z_range(mesh, x, step=2.0):
    """Probe entlang Z bei X=x, finde Z-Bereich wo Material vorhanden ist."""
    z_min_bound, z_max_bound = mesh.bounds[0, 2], mesh.bounds[1, 2]
    y_min, y_max = mesh.bounds[0, 1], mesh.bounds[1, 1]
    z_with_material = []
    for z in np.arange(z_min_bound, z_max_bound, step):
        # Probe entlang Y: irgendwo Material?
        has_material = False
        for y in np.arange(y_min, y_max, 1.0):
            if mesh.contains(np.array([[x, y, z]]))[0]:
                has_material = True
                break
        if has_material:
            z_with_material.append(z)
    if not z_with_material:
        return None, None
    return min(z_with_material), max(z_with_material)


def main():
    args = parse_args()
    print(f"\n=== drill_figure_back.py ===\n")

    mesh = trimesh.load(args.input, force="mesh")
    print(f"  Loaded {len(mesh.faces):,} faces, watertight={mesh.is_watertight}")

    radius = args.magnet_diameter / 2.0 + args.radial_tolerance
    depth  = args.magnet_height + args.depth_extra
    overhang = 1.0

    cx_default = (mesh.bounds[0,0] + mesh.bounds[1,0]) / 2.0
    cx = args.center_x if args.center_x is not None else cx_default

    y_min = mesh.bounds[0, 1]
    y_max = mesh.bounds[1, 1]

    # Auto-detect Z positions falls nicht angegeben
    if args.z1 is None or args.z2 is None:
        print(f"  Auto-detect Z-range (probing X={cx:.1f})...")
        z_lo, z_hi = find_material_z_range(mesh, cx)
        if z_lo is None:
            print(f"  ⚠️ Keine Material-Z-Range gefunden — fallback auf bounding-box-center", file=sys.stderr)
            z_center = (mesh.bounds[0, 2] + mesh.bounds[1, 2]) / 2.0
        else:
            # Anchor in upper torso (legs often have gap → drill into empty space)
            z_center = z_hi - 35.0  # mid-chest anchor (avoid magnets too close to head/text region)
            if z_center < z_lo + 10: z_center = (z_lo + z_hi) / 2.0
            print(f"    Material Z-Range: {z_lo:.1f} bis {z_hi:.1f}, center={z_center:.1f}")
        half = args.spacing_z / 2.0
        z1 = z_center - half if args.z1 is None else args.z1
        z2 = z_center + half if args.z2 is None else args.z2
    else:
        z1, z2 = args.z1, args.z2

    print(f"  Finding back surface at Z=[{z1:.1f}, {z2:.1f}], X={cx:.1f}...")
    magnets = []
    for z in [z1, z2]:
        surface_y = find_back_surface_y(mesh, cx, z, y_min, y_max)
        if surface_y is None:
            print(f"  ⚠️ No back surface found at Z={z} — figure leer dort, skip")
            continue
        magnets.append((cx, surface_y, z))
        print(f"    Magnet @ Z={z:+.1f}: surface at Y={surface_y:.2f}")

    if not magnets:
        print("FAIL: kein Magnet platzierbar", file=sys.stderr)
        sys.exit(2)

    rot = trimesh.transformations.rotation_matrix(np.pi/2, [1, 0, 0])
    cyl_height = depth + overhang

    result = mesh
    for i, (mx, my, mz) in enumerate(magnets, 1):
        c = cylinder(radius=radius, height=cyl_height, sections=48)
        c.apply_transform(rot)
        cyl_center_y = my + overhang - cyl_height/2.0  # drill INWARD from back (toward y_min)
        c.apply_translation([mx, cyl_center_y, mz])
        try:
            new_result = result.difference(c, engine="manifold")
            if new_result is None or new_result.is_empty:
                print(f"  ⚠️ Hole {i} empty result")
                continue
            result = new_result
            print(f"  ✓ Hole {i} drilled at ({mx:.1f}, {my:.2f}, {mz:+.1f}), depth={depth:.1f}mm, faces={len(result.faces):,}")
        except Exception as e:
            print(f"  ✗ Hole {i} failed: {e}", file=sys.stderr)

    result.export(args.output)
    print(f"\n[done] → {args.output} ({len(result.faces):,} faces)")
    import json
    print("MAGNETS_JSON: " + json.dumps({"z_positions": [float(mz) for (mx,my,mz) in magnets], "z_bottom": float(mesh.bounds[0,2]), "center_x": float(cx)}))


if __name__ == "__main__":
    main()
