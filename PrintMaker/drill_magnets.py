#!/usr/bin/env python3
"""
drill_magnets.py — fügt 4 Magnet-Bohrungen im Quadrat-Layout in ein STL ein.

Beispiel:
  python drill_magnets.py --input card_figure.stl --output card_figure_magnetic.stl \
      --side bottom --magnet-diameter 8 --magnet-height 3 \
      --layout square --inset-factor 0.30

Werte für SimpelMe (Amazon B0DMNR5D6C, 8×3mm Magnete):
  --magnet-diameter 8   (Bohrung wird 8.2 mm Ø, +0.2 mm Toleranz)
  --magnet-height   3   (Bohrung wird 3.3 mm tief,  +0.3 mm Tiefen-Toleranz)
"""

import argparse
import sys
import trimesh
from trimesh.creation import cylinder
import numpy as np


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--input", required=True, help="Input STL file")
    p.add_argument("--output", required=True, help="Output STL file")
    p.add_argument("--side", choices=["top", "bottom", "front", "back", "left", "right"], required=True,
                   help="Auf welcher Seite die Magneten sitzen. "
                        "top/bottom = ±Z, front/back = ±Y, left/right = ±X")
    p.add_argument("--magnet-diameter", type=float, default=8.0, help="Magnet-Ø in mm")
    p.add_argument("--magnet-height",   type=float, default=3.0, help="Magnet-Höhe in mm")
    p.add_argument("--radial-tolerance", type=float, default=0.2,
                   help="Extra Radius für sauberen Magnet-Sitz (mm)")
    p.add_argument("--depth-extra",     type=float, default=0.3,
                   help="Extra Tiefe für sauberen Magnet-Sitz (mm)")
    p.add_argument("--spacing-x", type=float, default=20.0,
                   help="Halber X-Abstand vom Center (mm). 20 = Magnete sind 40mm auseinander in X.")
    p.add_argument("--spacing-y", type=float, default=30.0,
                   help="Halber Y-Abstand vom Center (mm). 30 = Magnete sind 60mm auseinander in Y.")
    p.add_argument("--count", type=int, default=4, choices=[1, 2, 4],
                   help="1 (center) | 2 (links/rechts) | 4 (Quadrat-Layout)")
    p.add_argument("--center-x", type=float, default=None,
                   help="X-Offset vom Mesh-Center (mm). Default: mesh-centroid.")
    p.add_argument("--center-y", type=float, default=None,
                   help="Y-Offset vom Mesh-Center (mm). Default: mesh-centroid.")
    p.add_argument("--center-z", type=float, default=None,
                   help="Z-Offset vom Mesh-Center (mm). Default: mesh-centroid.")
    return p.parse_args()


def magnet_positions(bounds, spacing_x, spacing_y, count, center_x=None, center_y=None):
    """(x, y)-Positionen relativ zum (überschreibbaren) Center mit absoluten Spacings."""
    min_b, max_b = bounds[0], bounds[1]
    default_cx = (min_b[0] + max_b[0]) / 2.0
    default_cy = (min_b[1] + max_b[1]) / 2.0
    cx = center_x if center_x is not None else default_cx
    cy = center_y if center_y is not None else default_cy
    if count == 1:
        return [(cx, cy)]
    if count == 2:
        # 2 Magnete: vertikal verteilt (in Y) — z.B. für oben/unten Layout
        return [(cx, cy - spacing_y), (cx, cy + spacing_y)]
    return [
        (cx - spacing_x, cy - spacing_y),
        (cx + spacing_x, cy - spacing_y),
        (cx - spacing_x, cy + spacing_y),
        (cx + spacing_x, cy + spacing_y),
    ]


def magnet_positions_xz(bounds, spacing_x, spacing_z, count, center_x=None, center_z=None):
    """(x, z)-Positionen für Drill entlang Y-Achse (front/back)."""
    min_b, max_b = bounds[0], bounds[1]
    default_cx = (min_b[0] + max_b[0]) / 2.0
    default_cz = (min_b[2] + max_b[2]) / 2.0
    cx = center_x if center_x is not None else default_cx
    cz = center_z if center_z is not None else default_cz
    if count == 1:
        return [(cx, cz)]
    if count == 2:
        # 2 Magnete vertikal verteilt (in Z = Höhe) — z.B. Rücken-Magnete oben+unten
        return [(cx, cz - spacing_z), (cx, cz + spacing_z)]
    return [
        (cx - spacing_x, cz - spacing_z),
        (cx + spacing_x, cz - spacing_z),
        (cx - spacing_x, cz + spacing_z),
        (cx + spacing_x, cz + spacing_z),
    ]


def magnet_positions_yz(bounds, spacing_y, spacing_z, count, center_y=None, center_z=None):
    """(y, z)-Positionen für Drill entlang X-Achse (left/right)."""
    min_b, max_b = bounds[0], bounds[1]
    default_cy = (min_b[1] + max_b[1]) / 2.0
    default_cz = (min_b[2] + max_b[2]) / 2.0
    cy = center_y if center_y is not None else default_cy
    cz = center_z if center_z is not None else default_cz
    if count == 1:
        return [(cy, cz)]
    if count == 2:
        return [(cy, cz - spacing_z), (cy, cz + spacing_z)]
    return [
        (cy - spacing_y, cz - spacing_z),
        (cy + spacing_y, cz - spacing_z),
        (cy - spacing_y, cz + spacing_z),
        (cy + spacing_y, cz + spacing_z),
    ]


def main():
    args = parse_args()

    mesh = trimesh.load(args.input, force="mesh")
    if not isinstance(mesh, trimesh.Trimesh) or mesh.is_empty:
        print(f"[ERROR] Konnte STL nicht laden oder leer: {args.input}", file=sys.stderr)
        sys.exit(1)

    print(f"[drill_magnets] Input: {args.input}")
    print(f"[drill_magnets] Bounds: {mesh.bounds.tolist()}")
    print(f"[drill_magnets] Size:   {(mesh.bounds[1]-mesh.bounds[0]).tolist()}")
    print(f"[drill_magnets] Watertight={mesh.is_watertight}, Volume={mesh.is_volume}")

    # === REPAIR: nicht-manifolde Meshes für Boolean fähig machen ===
    if not mesh.is_watertight or not mesh.is_volume:
        print("[drill_magnets] Repairing mesh (merge verts, fix winding, fill holes)...")
        mesh.merge_vertices()
        mesh.update_faces(mesh.nondegenerate_faces())
        mesh.update_faces(mesh.unique_faces())
        try:
            trimesh.repair.fix_winding(mesh)
            trimesh.repair.fix_normals(mesh)
            trimesh.repair.fill_holes(mesh)
        except Exception as e:
            print(f"[drill_magnets] repair warning: {e}")
        print(f"[drill_magnets] After repair: watertight={mesh.is_watertight}, volume={mesh.is_volume}")

    radius = (args.magnet_diameter / 2.0) + args.radial_tolerance
    depth  = args.magnet_height + args.depth_extra

    # Cylinder = genau die gewünschte Tiefe + 0.5mm overhang außerhalb der Surface
    # (verhindert dass die Bohrung durch dünne Platten durchschlägt)
    overhang = 0.5
    cyl_height = depth + overhang

    # ── Axis-aware Drilling ──
    # Bestimme welche Achse die Bohrung folgt und welche 2 Achsen die Position bestimmen
    if args.side in ("top", "bottom"):
        drill_axis = "z"
        # Magnete im XY-Plane positionieren
        positions_2d = magnet_positions(mesh.bounds, args.spacing_x, args.spacing_y, args.count,
                                         center_x=args.center_x, center_y=args.center_y)
    elif args.side in ("front", "back"):
        drill_axis = "y"
        # Magnete im XZ-Plane positionieren (spacing_x = X, spacing_y wird Z)
        # Wir benutzen --center-z für die Z-Mitte
        cz_default = (mesh.bounds[0,2] + mesh.bounds[1,2]) / 2.0
        center_x = args.center_x
        center_z = args.center_z if args.center_z is not None else cz_default
        positions_2d_raw = magnet_positions_xz(mesh.bounds, args.spacing_x, args.spacing_y, args.count,
                                                center_x=center_x, center_z=center_z)
        positions_2d = positions_2d_raw  # list of (x, z)
    else:  # left, right
        drill_axis = "x"
        cy_default = (mesh.bounds[0,1] + mesh.bounds[1,1]) / 2.0
        cz_default = (mesh.bounds[0,2] + mesh.bounds[1,2]) / 2.0
        center_y = args.center_y if args.center_y is not None else cy_default
        center_z = args.center_z if args.center_z is not None else cz_default
        positions_2d = magnet_positions_yz(mesh.bounds, args.spacing_x, args.spacing_y, args.count,
                                            center_y=center_y, center_z=center_z)

    # Surface-Z (oder X / Y) bestimmen
    if args.side == "bottom":  z_surface = mesh.bounds[0, 2]
    elif args.side == "top":   z_surface = mesh.bounds[1, 2]
    elif args.side == "back":  z_surface = mesh.bounds[0, 1]  # Y-min
    elif args.side == "front": z_surface = mesh.bounds[1, 1]  # Y-max
    elif args.side == "left":  z_surface = mesh.bounds[0, 0]  # X-min
    elif args.side == "right": z_surface = mesh.bounds[1, 0]  # X-max

    # Cylinder-Center entlang der drill axis
    if args.side in ("bottom", "back", "left"):
        # Drill INTO mesh from MIN side, going POSITIVE
        cyl_axis_center = z_surface - overhang + (cyl_height / 2.0)
    else:
        # Drill INTO mesh from MAX side, going NEGATIVE
        cyl_axis_center = z_surface + overhang - (cyl_height / 2.0)

    print(f"[drill_magnets] Drilling {len(positions_2d)} hole(s), "
          f"Ø {radius*2:.2f} mm × {depth:.2f} mm depth, side={args.side} (axis={drill_axis})")
    for i, (a, b) in enumerate(positions_2d):
        print(f"  Hole {i+1}: ({a:.2f}, {b:.2f}) surface={z_surface:.2f}")

    # Rotationsmatrix für Cylinder-Achse
    import numpy as np
    if drill_axis == "z":
        rot = None  # cylinder default along Z
    elif drill_axis == "y":
        # Rotate 90° around X-axis so cylinder axis becomes Y
        rot = trimesh.transformations.rotation_matrix(np.pi/2, [1, 0, 0])
    else:  # x
        rot = trimesh.transformations.rotation_matrix(np.pi/2, [0, 1, 0])

    # Bohrungen NACHEINANDER subtrahieren
    result = mesh
    for i, (a, b) in enumerate(positions_2d):
        c = cylinder(radius=radius, height=cyl_height, sections=48)
        if rot is not None:
            c.apply_transform(rot)
        # Position: zwei Achsen aus positions_2d, dritte = cyl_axis_center
        if drill_axis == "z":
            c.apply_translation([a, b, cyl_axis_center])
        elif drill_axis == "y":
            c.apply_translation([a, cyl_axis_center, b])  # (x, y, z) with z from positions
        else:  # x
            c.apply_translation([cyl_axis_center, a, b])
        try:
            new_result = result.difference(c, engine="manifold")
        except Exception as e:
            print(f"[drill_magnets] manifold engine failed on hole {i+1}: {e}")
            try:
                new_result = result.difference(c)
            except Exception as e2:
                print(f"[drill_magnets] ALL engines failed on hole {i+1}: {e2}", file=sys.stderr)
                continue
        if new_result is None or new_result.is_empty:
            print(f"[drill_magnets] WARNING: Hole {i+1} produced empty result — skipped")
            continue
        result = new_result
        print(f"  ✓ Hole {i+1} drilled, faces={len(result.faces)}")

    if result is None or result.is_empty:
        print(f"[ERROR] Boolean-Result ist leer.", file=sys.stderr)
        sys.exit(2)

    result.export(args.output)
    print(f"[drill_magnets] OK → {args.output}")


if __name__ == "__main__":
    main()
