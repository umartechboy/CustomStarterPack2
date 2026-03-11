# starter_pack_card_layout.py
# One-file Blender script: orient, layout, and export a rounded-card STL
# Blender 3.x / 4.x

import struct
import bpy, bmesh, os, sys, math, argparse, json
from math import radians
from math import degrees
from mathutils import Vector, Matrix

from blender_utils import *
def obj_xy_aabb(obj):
    """Return (minx, miny, maxx, maxy) AABB for a single object in world space."""
    mn, mx = world_aabb(obj)
    return float(mn.x), float(mn.y), float(mx.x), float(mx.y)
def group_xy_aabb(children):
    """Return AABB for a list of objects (e.g., the text group)."""
    mn, mx = union_aabb(children)
    return float(mn.x), float(mn.y), float(mx.x), float(mx.y)
def pack_xy_record(name, minx, miny, maxx, maxy, rot_z_rad=0.0):
    cx = 0.5*(minx + maxx)
    cy = 0.5*(miny + maxy)
    w  = (maxx - minx)
    h  = (maxy - miny)
    return {
        "name": name,
        "center": {"x": cx, "y": cy},
        "size":   {"w": w,  "h": h},
        "rotation_z_deg": float(degrees(rot_z_rad)),
    }
def write_layout_json(path, meta, records):
    payload = {"meta": meta, "items": records}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"[OK] Layout JSON: {path}")
def _make_temp_mesh_from_obj(obj):
    """Create a temp MESH object from any object (FONT/CURVE/SURFACE/MESH) using evaluated geometry."""
    deps = bpy.context.evaluated_depsgraph_get()
    eo = obj.evaluated_get(deps)

    # get evaluated mesh (works for mesh/curve/font/surface with geometry settings)
    me_eval = eo.to_mesh()
    if not me_eval:
        return None

    # copy into a real datablock we can link
    me_real = bpy.data.meshes.new(obj.name + "_TmpMesh")
    me_real.from_mesh(me_eval)
    eo.to_mesh_clear()

    tmp = bpy.data.objects.new(obj.name + "_Tmp", me_real)
    # keep world transform so geometry lands where you see it
    tmp.matrix_world = eo.matrix_world.copy()
    bpy.context.scene.collection.objects.link(tmp)
    return tmp
def _collect_export_objects_with_temps():
    """Collect all meshes + temp meshes for curves/fonts/surfaces; returns (export_objs, temps_to_delete)."""
    export_objs = []
    temps = []
    for o in bpy.data.objects:
        if o.type == "MESH":
            export_objs.append(o)
        elif o.type in {"CURVE", "FONT", "SURFACE"}:
            t = _make_temp_mesh_from_obj(o)
            if t:
                export_objs.append(t)
                temps.append(t)
    return export_objs, temps
def _cleanup_temps(temps):
    for t in temps:
        try:
            me = t.data
            bpy.data.objects.remove(t, do_unlink=True)
            if me.users == 0:
                bpy.data.meshes.remove(me, do_unlink=True)
        except Exception:
            pass
def _enable_stl_addon() -> bool:
    try:
        import addon_utils
        for modname in ("io_mesh_stl", "io_scene_stl"):
            for m in addon_utils.modules():
                if m.__name__ == modname:
                    addon_utils.enable(modname, default_set=False, persistent=False)
                    return True
            try:
                bpy.ops.preferences.addon_enable(module=modname)
                return True
            except Exception:
                continue
    except Exception:
        pass
    return False
def _try_addon_export_stl(path_stl: str) -> bool:
    """Try official add-on export, including Text/Curves via temp meshes. Returns True on success."""
    if not _enable_stl_addon():
        return False

    export_objs, temps = _collect_export_objects_with_temps()
    if not export_objs:
        _cleanup_temps(temps)
        raise RuntimeError("No geometry to export.")

    # select only our export set
    bpy.ops.object.select_all(action='DESELECT')
    for o in export_objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = export_objs[0]

    try:
        # operator name is standard when add-on is present
        if hasattr(bpy.ops, "export_mesh") and hasattr(bpy.ops.export_mesh, "stl"):
            bpy.ops.export_mesh.stl(filepath=path_stl, use_selection=True, ascii=False)
            print(f"[OK] Combined STL (add-on): {path_stl}")
            return True
        return False
    except Exception as e:
        print(f"[WARN] STL add-on export failed: {e}")
        return False
    finally:
        _cleanup_temps(temps)
def _iter_world_tris_any(obj):
    """Yield world-space triangles (v0,v1,v2) for any supported object via evaluated mesh."""
    deps = bpy.context.evaluated_depsgraph_get()
    eo = obj.evaluated_get(deps)
    me = eo.to_mesh()
    try:
        if not me:
            return
        me.calc_loop_triangles()
        verts = me.vertices
        M = eo.matrix_world
        for tri in me.loop_triangles:
            v0 = M @ verts[tri.vertices[0]].co
            v1 = M @ verts[tri.vertices[1]].co
            v2 = M @ verts[tri.vertices[2]].co
            yield (v0, v1, v2)
    finally:
        eo.to_mesh_clear()
def _write_binary_stl_all(path_stl: str):
    """Addon-free writer that includes Mesh/Text/Curves/Surface."""
    objs = [o for o in bpy.data.objects if o.type in _GEOM_TYPES]
    if not objs:
        raise RuntimeError("No geometry objects to export (MESH/CURVE/FONT/SURFACE).")

    # Count triangles
    tri_count = 0
    for o in objs:
        for _ in _iter_world_tris_any(o):
            tri_count += 1

    with open(path_stl, "wb") as f:
        f.write(b"Generated by Blender script".ljust(80, b"\0"))
        f.write(struct.pack("<I", tri_count))
        for o in objs:
            for v0, v1, v2 in _iter_world_tris_any(o):
                n = (v1 - v0).cross(v2 - v0)
                ln = n.length
                if ln > 1e-20: n /= ln
                else:          n = Vector((0.0, 0.0, 0.0))
                f.write(struct.pack(
                    "<12fH",
                    float(n.x), float(n.y), float(n.z),
                    float(v0.x), float(v0.y), float(v0.z),
                    float(v1.x), float(v1.y), float(v1.z),
                    float(v2.x), float(v2.y), float(v2.z),
                    0
                ))
    print(f"[OK] Combined STL (addon-free): {path_stl}")
def export_scene_as_stl(path_stl: str):
    """First try official add-on (including text/curves via temp meshes), else fallback to built-in writer."""
    if _try_addon_export_stl(path_stl):
        return
    _write_binary_stl_all(path_stl)