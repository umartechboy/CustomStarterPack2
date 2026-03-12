import bpy
import bmesh
import mathutils
import math
import os

# ==========================================
# CONFIGURATION
# ==========================================
GLB_INPUT_PATH = r"C:\Users\Tayyaba\Github\CustomStarterPack2\PrintMaker\bin\Debug\net8.0\base_character_3d.glb"
BLEND_OUTPUT_PATH = r"C:\Users\Tayyaba\Github\CustomStarterPack2\PrintMaker\bin\Debug\net8.0\output_jig.blend"
TARGET_TRIS = 50000 

def analyze_mesh_health(step_name, obj):
    """Diagnose if a mesh is water-tight (manifold)."""
    if not obj or obj.type != 'MESH':
        return
        
    bpy.context.view_layer.update()
    
    # Calculate bounds and tris
    bbox = [obj.matrix_world @ mathutils.Vector(b) for b in obj.bound_box]
    dx = max(b.x for b in bbox) - min(b.x for b in bbox)
    dy = max(b.y for b in bbox) - min(b.y for b in bbox)
    dz = max(b.z for b in bbox) - min(b.z for b in bbox)
    
    obj.data.calc_loop_triangles()
    tri_count = len(obj.data.loop_triangles)
    
    # BMesh diagnostic for Non-Manifold edges (holes, internal faces)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    non_manifold_edges = [e for e in bm.edges if not e.is_manifold]
    bad_edges = len(non_manifold_edges)
    bm.free()
    
    health_status = "PERFECT (Water-tight)" if bad_edges == 0 else f"WARNING: {bad_edges} Non-Manifold Edges"
    
    print(f"\n--- [DIAGNOSTIC] {step_name} ---")
    print(f"  Object    : {obj.name}")
    print(f"  Size      : X: {dx:.1f} | Y: {dy:.1f} | Z: {dz:.1f}")
    print(f"  Triangles : {tri_count:,}")
    print(f"  Health    : {health_status}")
    print("-" * 35)

# ==========================================
# 0. CLEANUP SCENE
# ==========================================
bpy.ops.object.select_all(action='DESELECT')
for obj in bpy.context.scene.objects:
    if obj.type == 'MESH':
        obj.select_set(True)
bpy.ops.object.delete()

# ==========================================
# 1. IMPORT & INITIAL SETUP
# ==========================================
print("\n[PROCESS] Importing GLB...")
bpy.ops.import_scene.gltf(filepath=GLB_INPUT_PATH)
model = bpy.context.selected_objects[0]
model.name = "Trimmed_Model"
bpy.context.view_layer.objects.active = model

# ==========================================
# 2. SCALE TO Z = 100
# ==========================================
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
bbox = [model.matrix_world @ mathutils.Vector(b) for b in model.bound_box]
z_height = max(b.z for b in bbox) - min(b.z for b in bbox)
scale_factor = 100.0 / z_height
model.scale = (scale_factor, scale_factor, scale_factor)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

# ==========================================
# 3. TRIM UPPER PART
# ==========================================
print("\n[PROCESS] Trimming upper part...")
bbox = [model.matrix_world @ mathutils.Vector(b) for b in model.bound_box]
z_min = min(b.z for b in bbox)

bpy.ops.mesh.primitive_cube_add(size=1)
cutter = bpy.context.active_object
cutter.scale = (1000, 1000, 1000)
cutter.location = (0, 0, z_min + 11 + 500)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

bpy.context.view_layer.objects.active = model
trim_mod = model.modifiers.new(type="BOOLEAN", name="Trim_Top")
trim_mod.object = cutter
trim_mod.operation = 'DIFFERENCE'
trim_mod.solver = 'EXACT'
bpy.ops.object.modifier_apply(modifier=trim_mod.name)
bpy.data.objects.remove(cutter, do_unlink=True)

# ==========================================
# 3.5. DECIMATE
# ==========================================
print("\n[PROCESS] Decimating...")
model.data.calc_loop_triangles()
current_tris = len(model.data.loop_triangles)

if current_tris > TARGET_TRIS:
    decimate_ratio = TARGET_TRIS / current_tris
    decimate_mod = model.modifiers.new(type="DECIMATE", name="Optimize")
    decimate_mod.decimate_type = 'COLLAPSE'
    decimate_mod.ratio = decimate_ratio
    bpy.ops.object.modifier_apply(modifier=decimate_mod.name)

# ==========================================
# 4. FIX NORMALS & INFLATE (0.4mm)
# ==========================================
print("\n[PROCESS] Recalculating Normals and Inflating...")
bpy.context.view_layer.objects.active = model
bpy.ops.object.editmode_toggle()
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.normals_make_consistent(inside=False)
bpy.ops.object.editmode_toggle()

disp_mod = model.modifiers.new(type="DISPLACE", name="Inflate")
disp_mod.strength = 0.4
disp_mod.mid_level = 0.0
bpy.ops.object.modifier_apply(modifier=disp_mod.name)

analyze_mesh_health("After Prep & Inflation", model)

# ==========================================
# 5. CREATE RAW CUBE
# ==========================================
print("\n[PROCESS] Creating bounding cubes...")
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
bbox = [model.matrix_world @ mathutils.Vector(b) for b in model.bound_box]
min_x, max_x = min(b.x for b in bbox), max(b.x for b in bbox)
min_y, max_y = min(b.y for b in bbox), max(b.y for b in bbox)
min_z, max_z = min(b.z for b in bbox), max(b.z for b in bbox)

dx, dy, dz = max_x - min_x, max_y - min_y, max_z - min_z
cx, cy, cz = (max_x + min_x) / 2.0, (max_y + min_y) / 2.0, (max_z + min_z) / 2.0

bpy.ops.mesh.primitive_cube_add(size=1)
raw_cube = bpy.context.active_object
raw_cube.name = "Raw_Cube"
raw_cube.scale = (dx + 2.0, dy + 2.0, dz + 2.0)
raw_cube.location = (cx, cy, cz)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

final_jig = raw_cube.copy()
final_jig.data = raw_cube.data.copy()
final_jig.name = "Final_Jig"
bpy.context.collection.objects.link(final_jig)

# ==========================================
# 6. CREATE MASTER SWEPT CUTTER
# ==========================================
move_distance = (dz / 2.0) + 1.0 + 1.0
step_size = 0.5
steps = int(math.ceil(move_distance / step_size))

print(f"\n[PROCESS] Stacking {steps} cutter slices...")
bpy.ops.object.select_all(action='DESELECT')

cutter_parts = []
for i in range(steps + 1):
    dup = model.copy()
    dup.data = model.data.copy()
    bpy.context.collection.objects.link(dup)
    dup.location.z += (i * step_size)
    cutter_parts.append(dup)

for part in cutter_parts:
    part.select_set(True)
bpy.context.view_layer.objects.active = cutter_parts[0]
bpy.ops.object.join()
master_cutter = bpy.context.active_object
master_cutter.name = "Master_Cutter"

# --- THE FIX: VOXEL REMESH THE CUTTER ---
print("  Fusing cutter slices into a solid manifold block (Voxel Remesh)...")
remesh_mod = master_cutter.modifiers.new(type='REMESH', name='Fuse_Slices')
remesh_mod.mode = 'VOXEL'
remesh_mod.voxel_size = 0.5 # 0.5mm voxels will fuse the 0.5mm step gaps perfectly
bpy.ops.object.modifier_apply(modifier=remesh_mod.name)

analyze_mesh_health("Master Cutter (Pre-Cut)", master_cutter)

# ==========================================
# 7. PERFORM SINGLE BOOLEAN CUT
# ==========================================
print("\n[PROCESS] Executing final boolean cut...")
bpy.ops.object.select_all(action='DESELECT')
bpy.context.view_layer.objects.active = final_jig

final_cut = final_jig.modifiers.new(type="BOOLEAN", name="Jig_Cut")
final_cut.object = master_cutter
final_cut.operation = 'DIFFERENCE'
final_cut.solver = 'EXACT' # Now that the cutter is manifold, EXACT is safer
# Adding a slight solver tolerance can help with perfectly flush faces
final_cut.double_threshold = 0.0001 
bpy.ops.object.modifier_apply(modifier=final_cut.name)

analyze_mesh_health("Final Jig (Post-Cut)", final_jig)

# ==========================================
# 8. DEBUG LAYOUT & SAVE
# ==========================================
print("\n[PROCESS] Arranging items for debug viewing...")
offset = dx + 20.0

raw_cube.location.x -= offset       
final_jig.location.x += offset      
master_cutter.location.x += (offset * 2) 

bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=BLEND_OUTPUT_PATH)
print(f"\n[SUCCESS] Saved successfully to: {BLEND_OUTPUT_PATH}")