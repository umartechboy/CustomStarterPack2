import bpy
import bmesh
import mathutils
import math
import os

# ==========================================
# HELPER: CREATE BOX FROM BOUNDS
# ==========================================
def create_box(name, min_bounds, max_bounds):
    """Creates a cube perfectly bounded by two 3D coordinate vectors."""
    dx = max_bounds[0] - min_bounds[0]
    dy = max_bounds[1] - min_bounds[1]
    dz = max_bounds[2] - min_bounds[2]
    
    cx = (max_bounds[0] + min_bounds[0]) / 2.0
    cy = (max_bounds[1] + min_bounds[1]) / 2.0
    cz = (max_bounds[2] + min_bounds[2]) / 2.0
    
    bpy.ops.mesh.primitive_cube_add(size=1)
    box = bpy.context.active_object
    box.name = name
    box.scale = (dx, dy, dz)
    box.location = (cx, cy, cz)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return box

# ==========================================
# CORE 3D SPATIAL JIG FUNCTION
# ==========================================
def generate_jig_in_place(
    raw_model, 
    master_min, 
    master_max, 
    overlap, 
    inflation=0.4, 
    target_tris=50000, 
    direction='+Z'
):
    print(f"\n[FUNC] Generating absolute {direction} Jig...")
    
    # 1. Duplicate working model
    working_model = raw_model.copy()
    working_model.data = raw_model.data.copy()
    working_model.name = f"Working_Cutter_{direction}"
    bpy.context.collection.objects.link(working_model)
    bpy.context.view_layer.objects.active = working_model

    # 2. Get absolute model bounds
    bbox = [working_model.matrix_world @ mathutils.Vector(b) for b in working_model.bound_box]
    mod_min = (min(b.x for b in bbox), min(b.y for b in bbox), min(b.z for b in bbox))
    mod_max = (max(b.x for b in bbox), max(b.y for b in bbox), max(b.z for b in bbox))

    # 3. SPATIAL MAPPING LOGIC
    # Based on the requested sweep direction, we calculate:
    # - The spatial bounds of the Jig Box
    # - The spatial bounds of the massive Cutter that chops off the unneeded model parts
    # - The vector the model sweeps in to punch the cavity
    clearance = 5.0 # Keep 5mm of model past the overlap just to ensure clean cuts
    inf = 1000.0    # Massive coordinate for cutters
    
    if direction == '+Z': # Model escapes Upwards -> Jig is on the Bottom
        jig_min = (master_min[0], master_min[1], master_min[2])
        jig_max = (master_max[0], master_max[1], mod_min[2] + overlap)
        cut_min = (-inf, -inf, mod_min[2] + overlap + clearance)
        cut_max = (inf, inf, inf)
        sweep_vec = mathutils.Vector((0, 0, 1))
        
    elif direction == '-Z': # Model escapes Downwards -> Jig is on the Top
        jig_min = (master_min[0], master_min[1], mod_max[2] - overlap)
        jig_max = (master_max[0], master_max[1], master_max[2])
        cut_min = (-inf, -inf, -inf)
        cut_max = (inf, inf, mod_max[2] - overlap - clearance)
        sweep_vec = mathutils.Vector((0, 0, -1))
        
    elif direction == '+X': # Model escapes Right -> Jig is on the Left
        jig_min = (master_min[0], master_min[1], master_min[2])
        jig_max = (mod_min[0] + overlap, master_max[1], master_max[2])
        cut_min = (mod_min[0] + overlap + clearance, -inf, -inf)
        cut_max = (inf, inf, inf)
        sweep_vec = mathutils.Vector((1, 0, 0))
        
    elif direction == '-X': # Model escapes Left -> Jig is on the Right
        jig_min = (mod_max[0] - overlap, master_min[1], master_min[2])
        jig_max = (master_max[0], master_max[1], master_max[2])
        cut_min = (-inf, -inf, -inf)
        cut_max = (mod_max[0] - overlap - clearance, inf, inf)
        sweep_vec = mathutils.Vector((-1, 0, 0))
        
    elif direction == '+Y': # Model escapes Back -> Jig is on the Front
        jig_min = (master_min[0], master_min[1], master_min[2])
        jig_max = (master_max[0], mod_min[1] + overlap, master_max[2])
        cut_min = (-inf, mod_min[1] + overlap + clearance, -inf)
        cut_max = (inf, inf, inf)
        sweep_vec = mathutils.Vector((0, 1, 0))
        
    elif direction == '-Y': # Model escapes Front -> Jig is on the Back
        jig_min = (master_min[0], mod_max[1] - overlap, master_min[2])
        jig_max = (master_max[0], master_max[1], master_max[2])
        cut_min = (-inf, -inf, -inf)
        cut_max = (inf, mod_max[1] - overlap - clearance, inf)
        sweep_vec = mathutils.Vector((0, -1, 0))

    # 4. Trim Excessive Model
    trim_cutter = create_box(f"Trim_{direction}", cut_min, cut_max)
    bpy.context.view_layer.objects.active = working_model
    trim_mod = working_model.modifiers.new(type="BOOLEAN", name="Trim")
    trim_mod.object = trim_cutter
    trim_mod.operation = 'DIFFERENCE'
    trim_mod.solver = 'EXACT'
    bpy.ops.object.modifier_apply(modifier=trim_mod.name)
    bpy.data.objects.remove(trim_cutter, do_unlink=True)

    # 5. Simplify & Inflate
    working_model.data.calc_loop_triangles()
    if len(working_model.data.loop_triangles) > target_tris:
        decimate_mod = working_model.modifiers.new(type="DECIMATE", name="Optimize")
        decimate_mod.decimate_type = 'COLLAPSE'
        decimate_mod.ratio = target_tris / len(working_model.data.loop_triangles)
        bpy.ops.object.modifier_apply(modifier=decimate_mod.name)

    bpy.ops.object.editmode_toggle()
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.editmode_toggle()

    disp_mod = working_model.modifiers.new(type="DISPLACE", name="Inflate")
    disp_mod.strength = inflation
    disp_mod.mid_level = 0.0
    bpy.ops.object.modifier_apply(modifier=disp_mod.name)

    # 6. Create the specific Jig Box side
    final_jig = create_box(f"Jig_{direction}", jig_min, jig_max)

    # 7. Sweep the Master Cutter
    # Must clear the overlap + a 2mm safety margin
    move_distance = overlap + 2.0 
    step_size = 0.5
    steps = int(math.ceil(move_distance / step_size))

    bpy.ops.object.select_all(action='DESELECT')
    cutter_parts = []
    for i in range(steps + 1):
        dup = working_model.copy()
        dup.data = working_model.data.copy()
        bpy.context.collection.objects.link(dup)
        
        # Translate purely along the designated vector
        translation = sweep_vec * (i * step_size)
        dup.location.x += translation.x
        dup.location.y += translation.y
        dup.location.z += translation.z
        cutter_parts.append(dup)

    for part in cutter_parts: part.select_set(True)
    bpy.context.view_layer.objects.active = cutter_parts[0]
    bpy.ops.object.join()
    master_cutter = bpy.context.active_object

    remesh_mod = master_cutter.modifiers.new(type='REMESH', name='Fuse_Slices')
    remesh_mod.mode = 'VOXEL'
    remesh_mod.voxel_size = 0.5
    bpy.ops.object.modifier_apply(modifier=remesh_mod.name)

    # 8. Punch the cavity
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = final_jig

    final_cut = final_jig.modifiers.new(type="BOOLEAN", name="Jig_Cut")
    final_cut.object = master_cutter
    final_cut.operation = 'DIFFERENCE'
    final_cut.solver = 'EXACT' 
    final_cut.double_threshold = 0.0001 
    bpy.ops.object.modifier_apply(modifier=final_cut.name)

    # 9. Cleanup Temporary Objects
    bpy.data.objects.remove(working_model, do_unlink=True)
    bpy.data.objects.remove(master_cutter, do_unlink=True)

    return final_jig

# ==========================================
# FULL 6-SIDED EXECUTION PIPELINE
# ==========================================
if __name__ == "__main__":
    GLB_INPUT_PATH   = r"C:\Users\Tayyaba\Github\CustomStarterPack2\PrintMaker\bin\Debug\net8.0\base_character_3d.glb"
    BLEND_OUTPUT_PATH = r"C:\Users\Tayyaba\Github\CustomStarterPack2\PrintMaker\bin\Debug\net8.0\output_jig.blend"
    
    # 1. Cleanup
    bpy.ops.object.select_all(action='DESELECT')
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH': obj.select_set(True)
    bpy.ops.object.delete()

    # 2. Import and Pre-Scale
    bpy.ops.import_scene.gltf(filepath=GLB_INPUT_PATH)
    raw_model = bpy.context.selected_objects[0]
    raw_model.name = "Original_Model"
    bpy.context.view_layer.objects.active = raw_model
    
    HEIGHT = 100.0
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bbox = [raw_model.matrix_world @ mathutils.Vector(b) for b in raw_model.bound_box]
    z_height = max(b.z for b in bbox) - min(b.z for b in bbox)
    scale_factor = HEIGHT / z_height
    raw_model.scale = (scale_factor, scale_factor, scale_factor)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    # 3. Center model absolutely at (0,0,0)
    bbox = [raw_model.matrix_world @ mathutils.Vector(b) for b in raw_model.bound_box]
    cx = (max(b.x for b in bbox) + min(b.x for b in bbox)) / 2.0
    cy = (max(b.y for b in bbox) + min(b.y for b in bbox)) / 2.0
    cz = (max(b.z for b in bbox) + min(b.z for b in bbox)) / 2.0
    raw_model.location = (-cx, -cy, -cz)
    bpy.ops.object.transform_apply(location=True, rotation=False, scale=False)

    # 4. Define Absolute Master Box (e.g., a 150x150x150mm block)
    MASTER_X, MASTER_Y, MASTER_Z = 80, 50, 110
    master_min = (-MASTER_X/2, -MASTER_Y/2, -MASTER_Z/2)
    master_max = (MASTER_X/2, MASTER_Y/2, MASTER_Z/2)

    OVERLAP = 5.0 # The uniform overlap for every side

    # 5. Generate all 6 absolute jigsaw pieces!
    directions = ['+Z', '-Z', '+X', '-X', '+Y', '-Y']
    for d in directions:
        generate_jig_in_place(
            raw_model=raw_model,
            master_min=master_min,
            master_max=master_max,
            overlap=OVERLAP,
            direction=d
        )

    # 6. Save
    bpy.context.view_layer.update()
    bpy.ops.wm.save_as_mainfile(filepath=BLEND_OUTPUT_PATH)
    print(f"\n[SUCCESS] 6-Sided Absolute Packing Generation Complete!")