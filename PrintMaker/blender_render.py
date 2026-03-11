# starter_pack_card_layout.py
# One-file Blender script: orient, layout, and export a rounded-card STL
# Blender 3.x / 4.x

import struct
import bpy, bmesh, os, sys, math, argparse, json
from math import radians
from math import degrees
from mathutils import Vector, Matrix

from blender_utils import *
def setup_render_lights():
    """Setup area lights for orthographic rendering (XY plane view) - 3-light setup"""
    import time
    lights = []
    
    # Generate a unique timestamp for light names
    timestamp = str(int(time.time()))[-4:]
    
    # Camera is at (0, 0, dist) looking along -Z (towards XY plane)
    
    # 1) FRONT light - near camera position, strongest light (as SQUARE)
    bpy.ops.object.light_add(type='AREA', location=(0, 50, 75))
    front_light = bpy.context.active_object
    front_light.name = f"Render_Front_Light_{timestamp}"
    front_light.data.energy = 40000  # Strongest light
    front_light.data.shape = 'SQUARE'  # Changed to SQUARE
    front_light.data.size = 50  # Both dimensions will be 100 (square)
    front_light.rotation_euler = (-0.2, 0, 0)  # Tilted down toward scene
    lights.append(front_light)
    
    # 2) LEFT light - positioned to left side (as SQUARE)
    bpy.ops.object.light_add(type='AREA', location=(-100, 25, 60))
    left_light = bpy.context.active_object
    left_light.name = f"Render_Left_Light_{timestamp}"
    left_light.data.energy = 60000  # Medium strength
    left_light.data.shape = 'SQUARE'  # Changed to SQUARE
    left_light.data.size = 200  # Both dimensions will be 40 (square)
    left_light.rotation_euler = (-0.15, -1.0, 0)  # Facing toward scene center
    lights.append(left_light)
    
    # 3) RIGHT light - positioned to right side (as SQUARE)
    bpy.ops.object.light_add(type='AREA', location=(100, 25, 60))
    right_light = bpy.context.active_object
    right_light.name = f"Render_Right_Light_{timestamp}"
    right_light.data.energy = 60000  # Medium strength
    right_light.data.shape = 'SQUARE'  # Changed to SQUARE
    right_light.data.size = 200  # Both dimensions will be 40 (square)
    right_light.rotation_euler = (-0.15, 1.0, 0)  # Facing toward scene center
    lights.append(right_light)
    
    # 4) Top fill light for better overall illumination (as SQUARE)
    bpy.ops.object.light_add(type='AREA', location=(0, 0, 125))
    top_light = bpy.context.active_object
    top_light.name = f"Render_Top_Fill_{timestamp}"
    top_light.data.energy = 200000
    top_light.data.shape = 'SQUARE'  # Changed to SQUARE
    top_light.data.size = 250  # Both dimensions will be 50 (square)
    top_light.rotation_euler = (0, 0, 0)  # Pointing straight down
    lights.append(top_light)
    
    # Brighter ambient for better overall illumination
    world = bpy.context.scene.world
    if world:
        world.use_nodes = True
        bg = world.node_tree.nodes.get("Background")
        if bg:
            bg.inputs['Color'].default_value = (0.15, 0.15, 0.15, 1.0)
            bg.inputs['Strength'].default_value = 0.2
    
    return lights
def create_card_corner_markers(card_obj, card_width, card_height, marker_size=8.0, marker_thickness=0.3):
    """
    Create L-shaped corner markers at the four corners of the card.
    Each marker is made of two thin rectangles forming an L shape that fits inside the card.
    
    Args:
        card_obj: The card object
        card_width: Total width of the card (mm)
        card_height: Total height of the card (mm)
        marker_size: Size of the L shape arms (mm)
        marker_thickness: Thickness of the L shape lines (mm)
    
    Returns:
        List of marker objects
    """
    import bpy
    import bmesh
    from mathutils import Vector
    
    markers = []
    
    # Card half dimensions
    half_w = card_width / 2.0
    half_h = card_height / 2.0
    
    # Corner configurations: (corner_x, corner_y, x_sign, y_sign, rotation)
    # x_sign: +1 for right side, -1 for left side
    # y_sign: +1 for top side, -1 for bottom side
    corners = [
        # Bottom-left: L shape goes right (horizontal) and up (vertical)
        (-half_w, -half_h, +1, +1, 0),
        # Bottom-right: L shape goes left (horizontal) and up (vertical)  
        ( half_w, -half_h, -1, +1, 90),
        # Top-right: L shape goes left (horizontal) and down (vertical)
        ( half_w,  half_h, -1, -1, 180),
        # Top-left: L shape goes right (horizontal) and down (vertical)
        (-half_w,  half_h, +1, -1, 270),
    ]
    
    corner_names = ["BottomLeft", "BottomRight", "TopRight", "TopLeft"]
    
    # Create an L shape at each corner
    for (corner_x, corner_y, x_sign, y_sign, rotation), name in zip(corners, corner_names):
        bm = bmesh.new()
        
        # Create horizontal rectangle (along X axis)
        # Vertices for horizontal rectangle
        h_verts = [
            Vector((0, -marker_thickness/2, 0)),
            Vector((x_sign * marker_size, -marker_thickness/2, 0)),
            Vector((x_sign * marker_size,  marker_thickness/2, 0)),
            Vector((0,  marker_thickness/2, 0)),
        ]
        
        # Create vertical rectangle (along Y axis)
        # Vertices for vertical rectangle
        v_verts = [
            Vector((-marker_thickness/2, 0, 0)),
            Vector(( marker_thickness/2, 0, 0)),
            Vector(( marker_thickness/2, y_sign * marker_size, 0)),
            Vector((-marker_thickness/2, y_sign * marker_size, 0)),
        ]
        
        # Create faces for both rectangles
        h_face = bm.faces.new([bm.verts.new(v) for v in h_verts])
        v_face = bm.faces.new([bm.verts.new(v) for v in v_verts])
        
        # Merge overlapping vertices at the corner (0,0)
        # Find vertices at (0,0) and merge them
        bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=0.001)
        
        # Extrude the L shape upward slightly
        extruded = bmesh.ops.extrude_face_region(bm, geom=[h_face, v_face])
        extruded_verts = [ele for ele in extruded['geom'] if isinstance(ele, bmesh.types.BMVert)]
        bmesh.ops.translate(bm, verts=extruded_verts, vec=Vector((0, 0, marker_thickness)))
        
        # Create mesh and object
        me = bpy.data.meshes.new(f"CornerMarker_{name}")
        bm.to_mesh(me)
        bm.free()
        
        marker = bpy.data.objects.new(f"CornerMarker_{name}", me)
        
        # Position at card corner
        marker.location = Vector((corner_x, corner_y, 0.1))  # Slightly above card
        
        # Add a bright red emission material so markers are clearly visible
        mat = bpy.data.materials.new(f"MarkerMaterial_{name}")
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Color"].default_value = (1.0, 0.0, 0.0, 1.0)  # Bright red
        em.inputs["Strength"].default_value = 10.0  # Very bright
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
        
        marker.data.materials.append(mat)
        
        # Link to scene
        bpy.context.scene.collection.objects.link(marker)
        markers.append(marker)
    
    return markers
def render_scene_ortho(output_path, res_x=1920, res_y=1080):
    """Render the entire scene with orthographic projection (XY plane view)"""
    import bpy
    from mathutils import Vector, Matrix
    
    bpy.context.view_layer.update()
    
    # 1) Collect all objects we want to render:
    # - All MESH objects (models, figures, accessories)
    # - All FONT/CURVE objects (text group)
    # - Corner markers (we'll create these)
    # But NOT the card itself
    all_objs = list(bpy.data.objects)
    
    # Find the card object (look for "Card" or similar)
    card_obj = None
    for o in all_objs:
        if "card" in o.name.lower() and o.type == 'MESH':
            card_obj = o
            break
    
    # Create corner markers if we have a card
    marker_objs = []
    if card_obj:
        try:
            # Get card dimensions from the card object bounds
            mn, mx = world_aabb(card_obj)
            card_width = mx.x - mn.x
            card_height = mx.y - mn.y
            
            print(f"Card dimensions from bounds: {card_width:.2f} x {card_height:.2f} mm")
            
            # Create corner markers
            marker_objs = create_card_corner_markers(
                card_obj, 
                card_width, 
                card_height,
                marker_size=2.0,  # 8mm crosshair arms
                marker_thickness=0.1  # 0.3mm thick lines
            )
            print(f"Created {len(marker_objs)} corner markers for card")
        except Exception as e:
            print(f"Failed to create corner markers: {e}")
    
    # Objects to render: everything except the card, but INCLUDING markers
    render_objs = []
    for o in all_objs:
        # Include objects by type
        if o.type in {'MESH', 'FONT', 'CURVE'}:
            # Skip the card if found
            if card_obj and o == card_obj:
                continue
            render_objs.append(o)
    
    # Add markers to render objects
    render_objs.extend(marker_objs)
    
    if not render_objs:
        print("[WARN] No objects to render; skipping.")
        return
    
    # 2) Hide everything else temporarily
    prev_hide = {o: o.hide_render for o in all_objs}
    for o in all_objs:
        o.hide_render = True
    for o in render_objs:
        o.hide_render = False
    
    bpy.context.view_layer.update()
    
    # 3) Union AABB of all renderable objects in WORLD space (including markers)
    mn = Vector((+1e30, +1e30, +1e30))
    mx = Vector((-1e30, -1e30, -1e30))
    for obj in render_objs:
        a, b = world_aabb(obj)
        mn.x = min(mn.x, a.x); mn.y = min(mn.y, a.y); mn.z = min(mn.z, a.z)
        mx.x = max(mx.x, b.x); mx.y = max(mx.y, b.y); mx.z = max(mx.z, b.z)
    
    center = (mn + mx) * 0.5
    w = (mx.x - mn.x)
    h = (mx.y - mn.y)
    
    if w <= 1e-9 or h <= 1e-9:
        print("[WARN] Zero XY bounds; skipping render.")
        for o, hflag in prev_hide.items(): 
            o.hide_render = hflag
        return
    
    print(f"[DEBUG] Render objects: {[o.name for o in render_objs]}")
    print(f"[DEBUG] Bounds: w={w:.2f}, h={h:.2f}, center={center}")
    
    # 4) Setup orthographic camera for XY plane view
    cam = bpy.data.objects.get("_TMP_SceneCam")
    if not cam:
        cam_data = bpy.data.cameras.new("_TMP_SceneCam")
        cam = bpy.data.objects.new("_TMP_SceneCam", cam_data)
        bpy.context.scene.collection.objects.link(cam)
    
    cam.data.type = 'ORTHO'
    
    # Camera looking along -Z axis (top view of XY plane)
    # Right = +X, Up = +Y, Forward = -Z
    right = Vector((1, 0, 0))
    up    = Vector((0, 1, 0))
    dist  = 50.0  # Distance from scene (orthographic ignores this for projection)
    
    # Position camera so it looks at the scene from above
    # Center in XY, positioned above the scene in Z
    cam.matrix_world = Matrix((
        ( right.x, up.x,  0.0, center.x              ),
        ( right.y, up.y,  0.0, center.y              ),
        ( right.z, up.z,  1.0, center.z + dist       ),
        (   0.0,    0.0,  0.0, 1.0                   ),
    ))
    
    # Add margin (10% around the objects)
    margin = 0.1
    w *= (1.0 + margin * 2.0)
    h *= (1.0 + margin * 2.0)
    cam.data.ortho_scale = max(w, h)
    
    # 5) Setup lighting for the scene - KEEP LIGHTS IN SCENE FOR DEBUGGING
    lights = setup_render_lights()
    
    # 6) Configure render settings - KEEP CYCLES
    sc = bpy.context.scene
    sc.camera = cam
    
    # Keep CYCLES as the renderer
    sc.render.engine = 'CYCLES'
    
    # Configure CYCLES settings for faster rendering
    sc.cycles.samples = 64  # Reduced for speed
    sc.cycles.use_denoising = True
    
    # Enable GPU if available
    sc.cycles.device = 'GPU'
    try:
        prefs = bpy.context.preferences
        cprefs = prefs.addons['cycles'].preferences
        cprefs.get_devices()
        for device in cprefs.devices:
            if device.type in ['CUDA', 'OPTIX', 'HIP']:
                device.use = True
    except:
        sc.cycles.device = 'CPU'
    
    # Set resolution - use fixed resolution from args
    sc.render.resolution_x = res_x
    sc.render.resolution_y = res_y
    
    # Calculate aspect ratio and adjust ortho scale if needed
    scene_aspect = w / h if h > 0 else 1.0
    render_aspect = res_x / res_y if res_y > 0 else 1.0
    
    # Adjust ortho scale to fit the render aspect ratio
    if scene_aspect > render_aspect:
        # Scene is wider than render area, scale based on width
        cam.data.ortho_scale = w * (1.0 + margin * 2.0)
    else:
        # Scene is taller than render area, scale based on height
        # Adjust width to match aspect ratio
        needed_width = h * render_aspect
        cam.data.ortho_scale = max(needed_width, h) * (1.0 + margin * 2.0)
    
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_mode = 'RGBA'
    sc.render.film_transparent = True
    
    # Ensure output directory exists
    abs_path = bpy.path.abspath(output_path)
    abs_path = os.path.abspath(abs_path)
    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
    sc.render.filepath = abs_path
    
    # 7) Render
    print(f"Rendering scene to: {output_path}")
    print(f"  Camera ortho scale: {cam.data.ortho_scale:.2f}")
    print(f"  Resolution: {sc.render.resolution_x}x{sc.render.resolution_y}")
    print(f"  Objects rendered: {len(render_objs)}")
    print(f"  Lights created: {[light.name for light in lights]}")
    
    bpy.ops.render.render(write_still=True)
    
    # 8) Cleanup - BUT DON'T DELETE LIGHTS OR MARKERS
    # Remove temporary camera only
    if "_TMP_SceneCam" in bpy.data.objects:
        bpy.data.objects.remove(cam, do_unlink=True)
    
    # DO NOT remove lights or markers - keep them in scene for debugging
    # They will be saved with the .blend file
    
    # Restore visibility
    for o, hflag in prev_hide.items():
        o.hide_render = hflag
    
    print(f"Scene render complete: {output_path}")
    print(f"Lights kept in scene for debugging: {[light.name for light in lights]}")
    print(f"Corner markers kept in scene: {len(marker_objs)}")