#!/usr/bin/env python3
"""
drill_plate_basis.py — drills magnet holes into the front face (Z+) of a flat card plate.

Holes are placed side-by-side in X (matching figure's horizontal magnet layout).

Usage:
  python drill_plate_basis.py --input plate.stl --output plate.stl \
      --magnet-diameter 6 --magnet-height 2 \
      --center-x 0 --center-y 0 --spacing-x 20 [--side top|bottom]
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
    p.add_argument("--magnet-diameter",  type=float, default=6.0)
    p.add_argument("--magnet-height",    type=float, default=2.0)
    p.add_argument("--radial-tolerance", type=float, default=0.2)
    p.add_argument("--depth-extra",      type=float, default=0.3)
    p.add_argument("--surface-z",        type=float, default=None,
                   help="Override surface Z. Default: auto-detect via probing.")
    p.add_argument("--center-x",  type=float, default=0.0)
    p.add_argument("--center-y",  type=float, default=0.0)
    p.add_argument("--spacing-x", type=float, default=20.0,
                   help="Distance between the two holes in X (center-to-center)")
    p.add_argument("--side", choices=["top", "bottom"], default="top",
                   help="top = drill downward from surface-z. bottom = drill upward.")
    return p.parse_args()


def find_material_z(mesh, x, y, z_min, z_max, side="top", step=0.25):
    """Find the real material surface at (x, y) by probing along Z."""
    if side == "top":
        for z in np.arange(z_max, z_min - step, -step):
            if mesh.contains(np.array([[x, y, z]]))[0]:
                return z
    else:
        for z in np.arange(z_min, z_max + step, step):
            if mesh.contains(np.array([[x, y, z]]))[0]:
                return z
    return None


def main():
    args = parse_args()
    print(f"\n=== drill_plate_basis.py ===\n")

    mesh = trimesh.load(args.input, force="mesh")
    print(f"  Loaded {len(mesh.faces):,} faces, watertight={mesh.is_watertight}")
    print(f"  Bounds: {mesh.bounds.tolist()}")

    radius = args.magnet_diameter / 2.0 + args.radial_tolerance
    depth  = args.magnet_height + args.depth_extra
    overhang = 0.3
    cyl_h = depth + overhang

    # Two holes side-by-side in X, same Y
    half = args.spacing_x / 2.0
    positions = [
        (args.center_x - half, args.center_y),
        (args.center_x + half, args.center_y),
    ]
    print(f"  Hole XY positions: {positions}")

    # Auto-detect surface Z
    if args.surface_z is None:
        z_min, z_max = mesh.bounds[0, 2], mesh.bounds[1, 2]
        z_surfaces = []
        for x, y in positions:
            zs = find_material_z(mesh, x, y, z_min, z_max, side=args.side)
            if zs is not None:
                z_surfaces.append(zs)
                print(f"  Probe ({x:+.1f}, {y:+.1f}): surface Z={zs:.2f}")
        if not z_surfaces:
            print(f"  WARNING: could not find material surface — fallback to bounding box")
            surface_z = z_max if args.side == "top" else z_min
        else:
            surface_z = min(z_surfaces) if args.side == "top" else max(z_surfaces)
        print(f"  Auto-detected surface_z = {surface_z:.2f}")
    else:
        surface_z = args.surface_z
        print(f"  Manual surface_z = {surface_z:.2f}")

    result = mesh
    for i, (x, y) in enumerate(positions, 1):
        c = cylinder(radius=radius, height=cyl_h, sections=48)
        if args.side == "top":
            cz = surface_z + overhang - cyl_h / 2.0
        else:
            cz = surface_z - overhang + cyl_h / 2.0
        c.apply_translation([x, y, cz])
        try:
            new_result = result.difference(c, engine="manifold")
            if new_result is None or new_result.is_empty:
                print(f"  WARNING: hole {i} empty result — skipped")
                continue
            result = new_result
            print(f"  ✓ Hole {i} drilled at ({x:.1f}, {y:+.1f}, cz={cz:.2f}), depth={depth:.1f}mm")
        except Exception as e:
            print(f"  ✗ Hole {i} failed: {e}", file=sys.stderr)

    result.export(args.output)
    print(f"\n[done] → {args.output} ({len(result.faces):,} faces)")


if __name__ == "__main__":
    main()
