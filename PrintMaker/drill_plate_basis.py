#!/usr/bin/env python3
"""
drill_plate_basis.py — bohrt Magnetlöcher in die VORDERSEITE (Z+) einer flachen Karten-Platte.

Auto-Surface-Detection:
  - Probt entlang Z-Achse am Magnet-Zentrum
  - Findet das echte Material-Top (NICHT Bounding-Box-Top, weil Voxel-Remesh
    Artefakte oder Foto-Relief die bounds aufblähen können)
  - Bohrt 2.3mm tief von dort nach unten

Usage:
  python drill_plate_basis.py --input plate.stl --output plate.stl \\
      --magnet-diameter 6 --magnet-height 2 \\
      --center-x 0 --spacing-y 20 [--side top|bottom]
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
    p.add_argument("--surface-z", type=float, default=None,
                   help="Override surface-Z. Default: auto-detect via probing.")
    p.add_argument("--center-x", type=float, default=0.0)
    p.add_argument("--spacing-y", type=float, default=20.0)
    p.add_argument("--center-y", type=float, default=0.0, help="Y-Mitte (default 0). Verschiebt beide Magnete um diesen Y-Offset.")
    p.add_argument("--side", choices=["top", "bottom"], default="top",
                   help="top = bohrt von surface-z NACH UNTEN (ins Material). bottom = NACH OBEN.")
    return p.parse_args()


def find_material_z(mesh, x, y, z_min, z_max, side="top", step=0.25):
    """Finde das echte Material-Top (oder -Bottom) bei (x, y) via Probing."""
    if side == "top":
        # Probe von z_max nach unten, finde erstes INSIDE
        for z in np.arange(z_max, z_min - step, -step):
            if mesh.contains(np.array([[x, y, z]]))[0]:
                return z
    else:
        # Probe von z_min nach oben, finde erstes INSIDE
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

    positions = [(args.center_x, args.center_y - args.spacing_y), (args.center_x, args.center_y + args.spacing_y)]

    # Auto-detect surface-z falls nicht overridden
    if args.surface_z is None:
        z_min, z_max = mesh.bounds[0, 2], mesh.bounds[1, 2]
        # Finde echte Material-Surfaces an beiden Magnet-Positionen
        z_surfaces = []
        for x, y in positions:
            zs = find_material_z(mesh, x, y, z_min, z_max, side=args.side)
            if zs is not None:
                z_surfaces.append(zs)
                print(f"  Probe ({x:+.1f}, {y:+.1f}): {args.side} material surface @ Z={zs:.2f}")
        if not z_surfaces:
            print(f"  ⚠️ Konnte keine Material-Surface finden — fallback auf bounding-box")
            surface_z = z_max if args.side == "top" else z_min
        else:
            # Verwende den NIEDRIGSTEN (für top) oder HÖCHSTEN (für bottom) Wert
            # um sicherzustellen dass beide Magnete ins Material kommen
            surface_z = min(z_surfaces) if args.side == "top" else max(z_surfaces)
        print(f"  → Auto-detected surface-z = {surface_z:.2f}")
    else:
        surface_z = args.surface_z
        print(f"  → Manual surface-z = {surface_z:.2f}")

    result = mesh
    for i, (x, y) in enumerate(positions, 1):
        c = cylinder(radius=radius, height=cyl_h, sections=48)
        if args.side == "top":
            # Cylinder spans (surface_z + overhang) bis (surface_z - depth)
            cz = surface_z + overhang - cyl_h / 2.0
        else:
            cz = surface_z - overhang + cyl_h / 2.0
        c.apply_translation([x, y, cz])
        try:
            new_result = result.difference(c, engine="manifold")
            if new_result is None or new_result.is_empty:
                print(f"  ⚠️ Hole {i} produced empty result, skipped")
                continue
            result = new_result
            print(f"  ✓ Hole {i} drilled at ({x:.1f}, {y:+.1f}, cyl_center_z={cz:.2f}), "
                  f"depth={depth}mm, faces={len(result.faces):,}")
        except Exception as e:
            print(f"  ✗ Hole {i} failed: {e}", file=sys.stderr)

    result.export(args.output)
    print(f"\n[done] → {args.output} ({len(result.faces):,} faces)")


if __name__ == "__main__":
    main()
