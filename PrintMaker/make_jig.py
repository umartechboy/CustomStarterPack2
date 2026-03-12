import bpy
import bmesh
import mathutils
import math
import os

# ==========================================
# PROCESS CONTROL VARIABLES
# ==========================================
GLB_INPUT_PATH   = r"C:\Users\Tayyaba\Github\CustomStarterPack2\PrintMaker\bin\Debug\net8.0\base_character_3d.glb"
BLEND_OUTPUT_PATH = r"C:\Users\Tayyaba\Github\CustomStarterPack2\PrintMaker\bin\Debug\net8.0\output_jig.blend"

HEIGHT           = 100.0   # The fixed Z-height the model is scaled to before processing
OVERLAP          = 5.0    # How deep the model sinks into the jig cavity (in mm)
BOTTOM_THICKNESS = 1.0     # Solid material thickness directly under the lowest point of the model
INFLATION        = 0.4     # Amount to inflate the model for physical clearance
TRIANGLES        = 50000   # Target triangle count for mesh simplification

JIG_X            = 40.0    # Fixed total width of the Jig box
JIG_Y            = 50.0   # Fixed total length of the Jig box

# ==========================================
# HELPER FUNCTIONS
# ==========================================
def analyze_mesh_health(step_name, obj):
    """Diagnose if a mesh is water-tight (manifold)."""
    if not obj or obj.type != 'MESH': return
    bpy.context.view_layer.update()
    
    bbox = [obj.matrix_world @ mathutils.Vector(b) for b in obj.bound_box]
    dx = max(b.x for b in bbox) - min(b.x for b in bbox)
    dy = max(b.y for b in bbox) - min(b.y for b in bbox)
    dz = max(b.z for b in bbox) - min(b.z for b in bbox)
    
    obj.data.calc_loop_triangles()
    tri_count = len(obj.data.loop_triangles)
    
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bad_edges = len([e for e in bm.edges if not e.is_manifold])
    bm.free()
    
    health = "PERFECT" if bad_edges == 0 else f"WARNING: {bad_edges} Non-Manifold Edges"
    print(f"\n--- [DIAGNOSTIC] {step_name} ---")
    print(f"  Object    : {obj.name} | Tris: {tri_count:,}")
    print(f"  Size      : X: {dx:.1f} | Y: {dy:.1f} | Z: {dz:.1f}")
    print(f"  Health    : {health}")
    print("-" * 35)

# ==========================================
# 0. CLEANUP SCENE
# ==========================================
bpy.ops.object.select_all(action='DESELECT')
for obj in bpy.context.scene.objects:
    if obj.type == 'MESH': obj.select_set(True)
bpy.ops.object.delete()

# ==========================================
# 1. IMPORT & SCALE
# ==========================================
print("\n[PROCESS] Importing and Scaling...")
bpy.ops.import_scene.gltf(filepath=GLB_INPUT_PATH)
model = bpy.context.selected_objects[0]
model.name = "Trimmed_Model"
bpy.context.view_layer.objects.active = model

bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
bbox = [model.matrix_world @ mathutils.Vector(b) for b in model.bound_box]
z_height = max(b.z for b in bbox) - min(b.z for b in bbox)

scale_factor = HEIGHT / z_height
model.scale = (scale_factor, scale_factor, scale_factor)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

# ==========================================
# 2. ALIGN MODEL TO ORIGIN (Z=0, Centered X/Y)
# ==========================================
bbox = [model.matrix_world @ mathutils.Vector(b) for b in model.bound_box]
cx = (max(b.x for b in bbox) + min(b.x for b in bbox)) / 2.0
cy = (max(b.y for b in bbox) + min(b.y for b in bbox)) / 2.0
z_min = min(b.z for b in bbox)

model.location.x -= cx
model.location.y -= cy
model.location.z -= z_min
bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)
# The model's lowest point is now exactly at Z=0. Center is X=0, Y=0.

# ==========================================
# 3. TRIM UPPER PART (COMPUTED FROM OVERLAP)
# ==========================================
print("\n[PROCESS] Trimming unnecessary upper geometry...")
# We only need the model up to the OVERLAP height, plus a little safety margin
trim_height = OVERLAP + 5.0 

bpy.ops.mesh.primitive_cube_add(size=1)
cutter = bpy.context.active_object
cutter.scale = (1000, 1000, 1000)
# A cube of size 1 scaled to 1000 has a half-height of 500
cutter.location = (0, 0, trim_height + 500)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

bpy.context.view_layer.objects.active = model
trim_mod = model.modifiers.new(type="BOOLEAN", name="Trim_Top")
trim_mod.object = cutter
trim_mod.operation = 'DIFFERENCE'
trim_mod.solver = 'EXACT'
bpy.ops.object.modifier_apply(modifier=trim_mod.name)
bpy.data.objects.remove(cutter, do_unlink=True)

# ==========================================
# 4. DECIMATE & INFLATE
# ==========================================
print("\n[PROCESS] Optimizing and Inflating...")
model.data.calc_loop_triangles()
if len(model.data.loop_triangles) > TRIANGLES:
    decimate_mod = model.modifiers.new(type="DECIMATE", name="Optimize")
    decimate_mod.decimate_type = 'COLLAPSE'
    decimate_mod.ratio = TRIANGLES / len(model.data.loop_triangles)
    bpy.ops.object.modifier_apply(modifier=decimate_mod.name)

bpy.context.view_layer.objects.active = model
bpy.ops.object.editmode_toggle()
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.normals_make_consistent(inside=False)
bpy.ops.object.editmode_toggle()

disp_mod = model.modifiers.new(type="DISPLACE", name="Inflate")
disp_mod.strength = INFLATION
disp_mod.mid_level = 0.0
bpy.ops.object.modifier_apply(modifier=disp_mod.name)
analyze_mesh_health("Prepared Model", model)

# ==========================================
# 5. CREATE FIXED-SIZE JIG BOX
# ==========================================
print("\n[PROCESS] Creating parameterized Jig Box...")
jig_z_total = OVERLAP + BOTTOM_THICKNESS
jig_center_z = (OVERLAP - BOTTOM_THICKNESS) / 2.0

bpy.ops.mesh.primitive_cube_add(size=1)
raw_cube = bpy.context.active_object
raw_cube.name = "Raw_Cube"
raw_cube.scale = (JIG_X, JIG_Y, jig_z_total)
raw_cube.location = (0, 0, jig_center_z)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

final_jig = raw_cube.copy()
final_jig.data = raw_cube.data.copy()
final_jig.name = "Final_Jig"
bpy.context.collection.objects.link(final_jig)

# ==========================================
# 6. CREATE MASTER SWEPT CUTTER
# ==========================================
# Model starts at Z=0. Jig top is at Z=OVERLAP.
move_distance = OVERLAP + 2.0 # +2mm to ensure it completely clears the top
step_size = 0.5
steps = int(math.ceil(move_distance / step_size))

print(f"\n[PROCESS] Sweeping Master Cutter ({steps} slices)...")
bpy.ops.object.select_all(action='DESELECT')

cutter_parts = []
for i in range(steps + 1):
    dup = model.copy()
    dup.data = model.data.copy()
    bpy.context.collection.objects.link(dup)
    dup.location.z += (i * step_size)
    cutter_parts.append(dup)

for part in cutter_parts: part.select_set(True)
bpy.context.view_layer.objects.active = cutter_parts[0]
bpy.ops.object.join()
master_cutter = bpy.context.active_object
master_cutter.name = "Master_Cutter"

remesh_mod = master_cutter.modifiers.new(type='REMESH', name='Fuse_Slices')
remesh_mod.mode = 'VOXEL'
remesh_mod.voxel_size = 0.5
bpy.ops.object.modifier_apply(modifier=remesh_mod.name)
analyze_mesh_health("Master Cutter", master_cutter)

# ==========================================
# 7. PERFORM SINGLE BOOLEAN CUT
# ==========================================
print("\n[PROCESS] Executing cavity cut...")
bpy.ops.object.select_all(action='DESELECT')
bpy.context.view_layer.objects.active = final_jig

final_cut = final_jig.modifiers.new(type="BOOLEAN", name="Jig_Cut")
final_cut.object = master_cutter
final_cut.operation = 'DIFFERENCE'
final_cut.solver = 'EXACT' 
final_cut.double_threshold = 0.0001 
bpy.ops.object.modifier_apply(modifier=final_cut.name)
analyze_mesh_health("Final Jig", final_jig)

# ==========================================
# 8. DEBUG LAYOUT & SAVE
# ==========================================
print("\n[PROCESS] Arranging items for debug viewing...")
offset = JIG_X + 20.0

raw_cube.location.x -= offset       
final_jig.location.x += offset      
master_cutter.location.x += (offset * 2) 

bpy.context.view_layer.update()
bpy.ops.wm.save_as_mainfile(filepath=BLEND_OUTPUT_PATH)
print(f"\n[SUCCESS] Saved successfully to: {BLEND_OUTPUT_PATH}")