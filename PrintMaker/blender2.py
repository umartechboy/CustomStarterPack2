# starter_pack_card_layout.py
# One-file Blender script: orient, layout, and export a rounded-card STL
# Blender 3.x / 4.x

import struct
import bpy, bmesh, os, sys, math, argparse, json
from math import radians
from math import degrees
from mathutils import Vector, Matrix

import sys, os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from blender_utils import *
from blender_export import *
from blender_render import *
from make_jig import generate_jig_in_place
# ----------------------------- CLI -----------------------------
def parse_args():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--")+1:]
    p = argparse.ArgumentParser(description="Starter Pack card layout")
    # Inputs
    p.add_argument("--figure", required=True, help="Path to main figure (glb/gltf/obj/stl)")
    p.add_argument("--acc", nargs="*", default=[], help="Up to 3 accessory file paths")
    # Card & layout
    p.add_argument("--card_width", type=float, required=True, help="Card width (mm)")
    p.add_argument("--card_height", type=float, required=True, help="Card height (mm)")
    p.add_argument("--card_thickness", type=float, required=True, help="Card thickness (mm)")
    p.add_argument("--upper_ratio", type=float, default=0.25, help="Upper band ratio of card_height (e.g., 0.25 for card_height/4)")
    p.add_argument("--margin_accessories", type=float, default=2.0, help="Accessory margin (mm) inside each accessory slot")
    p.add_argument("--margin_figure", type=float, default=4.0, help="Figure margin (mm) inside figure slot")
    p.add_argument("--padding_card", type=float, default=4.0, help="Card Padding (mm)")
    p.add_argument("--T", type=float, default=0.0, help="Target top-face Z above ground (mm) after placement")
    p.add_argument("--fillet", type=float, default=5.0, help="Card corner fillet radius (mm)")
    # Orientation overrides (optional)
    p.add_argument("--flip_head", action="store_true", help="Flip main figure 'head' direction (swap +Y/-Y)")
    p.add_argument("--acc_front_up", action="store_true", help="Rotate accessories so their 'front' faces +Y (best-effort)")
    # Output
    p.add_argument("--outdir", required=True, help="Output folder")
    p.add_argument("--middir", required=True, help="Middle Output folder")
    p.add_argument("--job_id", default="run", help="Job id for filenames")
    p.add_argument("--save_blend", action="store_true", help="Also save a .blend for inspection")
    p.add_argument("--title",      type=str, default="Starter Pack")
    p.add_argument("--subtitle",   type=str, default="By M3D")
    p.add_argument("--TS",         type=float, default=14.0,  help="Title font size X (Blender text size)")
    p.add_argument("--MT",         type=float, default=0.0,   help="Vertical margin between title and subtitle")
    p.add_argument("--TH",         type=float, default=20.0,  help="Target total height (Y-extent) of the two-line group")
    p.add_argument("--font",       type=str,   default="",     help="Optional TTF/OTF path for both texts")
    p.add_argument("--text_extr",  type=float, default=0.8,   help="Text extrusion (depth in Z)")
    p.add_argument("--text_lift",  type=float, default=-0.2,   help="Lift above card top to avoid z-fighting")
    #Keyhole
    p.add_argument("--has_hole", action="store_true", help="If set, cut a key hole through the card")
    p.add_argument("--hole_d", type=float, default=6.0, help="Key hole diameter (mm)")
    p.add_argument("--hole_margin", type=float, default=4.0, help="Inset from card edges (mm)")
    p.add_argument("--hole_corner", type=str, default="top_right", choices=["top_right","top_left","bottom_right","bottom_left"])
    p.add_argument("--model_name_seed", type=str, default="card", choices=["card", "keychain"])
    
    # render with Texture
    p.add_argument("--render_resx", type=int, default=1920, help="Render resolution X")
    p.add_argument("--render_resy", type=int, default=1080, help="Render resolution Y")

    # Jigs
    p.add_argument("--jigs_requested", type=str, default="", help="Comma separated list of jigs +Z,-Z,+X etc.")
    p.add_argument("--overlap_x", type=float, default=3.0)
    p.add_argument("--overlap_y", type=float, default=5.0)
    p.add_argument("--overlap_z", type=float, default=5.0)
    p.add_argument("--inflation_margin", type=float, default=0.4)
    p.add_argument("--grid_height", type=float, default=50.0)

    args = p.parse_args(argv)
    # Limit accessories to 3 as requested
    args.acc = list(args.acc[:3])
    return args
    
import math
import bpy
    
_GEOM_TYPES = {"MESH", "CURVE", "FONT", "SURFACE"}  # what we want in STL

def main():
    args = parse_args()
    ensure_outdir(args.outdir)
    ensure_middir(args.middir)

    clear_scene()
    set_units_mm()


    # Make card (top at Z=0, bottom at -card_thickness)
    # card = create_rounded_card(args.card_width, args.card_height, args.card_thickness, args.fillet)
    # Make card (top at Z=0, bottom at -card_thickness)
    card = create_beveled_card(args.card_width, args.card_height, args.card_thickness, args.fillet)
    if args.has_hole:
        cut_key_hole(card_obj=card, card_w=args.card_width, card_h=args.card_height, card_th=args.card_thickness, hole_d=args.hole_d, hole_margin=args.hole_margin, corner=args.hole_corner)

    args.card_width -= args.padding_card * 2
    args.card_height -= args.padding_card * 2
    
    # --- 1) build the two texts ---
    title_obj = make_text(args.title,    size=args.TS,        extrude=args.text_extr, font_path=args.font, roll_deg=-90)
    sub_obj   = make_text(args.subtitle, size=args.TS * 0.6,  extrude=args.text_extr, font_path=args.font, roll_deg=-90)
    # stack them (subtitle below title) with margin MT
    place_sub_below_title(title_obj, sub_obj, margin_MT=float(args.MT))

    # --- 2) group them under an Empty, so we can scale/position as one ---
    text_group = group_under_empty([title_obj, sub_obj], name="TextGroup")

    # --- 3) fit group into the top slot (height = card_height/5), and make total text height = TH ---
    slot_top_y    = +args.card_height/2.0
    slot_bottom_y = slot_top_y - (args.card_height/5.0)

    scale_group_y_to_height(
        text_group,
        children=[title_obj, sub_obj],
        target_height=float(args.TH),                # total group height you want
        slot_bottom_y=slot_bottom_y,
        slot_top_y=slot_top_y,
    )

    # center horizontally (X=0) and sit on card top with a tiny lift
    # (group_under_empty already centered X via union; ensure x=0 if your card is centered)
    text_group.location.x = 0.0
    lift_group_to_card_top(text_group, [title_obj, sub_obj], card_obj=card, lift=float(args.text_lift))


    # Compute bands/regions (XY, top view)
    H_upper = args.card_height * args.upper_ratio               # upper band height
    H_lower = args.card_height - H_upper                        # lower band height
    # Lower-left (figure) width 3/5W, lower-right (accessories) width 2/5W
    W_left  = args.card_width * (3.0/5.0)
    W_right = args.card_width - W_left                         # 2/5W

    # Regions defined with centers to simplify placement
    # Coordinate frame: origin at card center, +Y up, +X right. Card top lies on Z=0.
    # LOWER band spans from y = -args.card_height/2  ..  y = -args.card_height/2 + H_lower
    lower_y_min = -args.card_height/2.0
    lower_y_max = lower_y_min + H_lower
    lower_y_center = 0.5*(lower_y_min + lower_y_max)

    # Upper band center (for text, if you later want it)
    upper_y_min = lower_y_max
    upper_y_max = args.card_height/2.0
    upper_y_center = 0.5*(upper_y_min + upper_y_max)

    # Left figure slot (in lower band): width = W_left, height = H_lower
    fig_slot_w = W_left
    fig_slot_h = H_lower

    # Right accessories column: width = W_right, height = (2/3) * card_height  (as specified)
    acc_slot_w = W_right
    acc_slot_h = (2.0/3.0) * args.card_height
    acc_y_center = lower_y_center  # center the 2/3H column within lower band

    # Accessory vertical partitioning into 3 equal parts
    acc_cell_h = acc_slot_h / 3.0

    # X centers
    left_x_min = -args.card_width/2.0
    left_x_center = left_x_min + fig_slot_w/2.0
    right_x_max = args.card_width/2.0
    right_x_center = right_x_max - acc_slot_w/2.0

    # Create empties for slots (handy for debugging in UI)
    # (Comment these three lines out if you don’t need helpers)
    # bpy.ops.object.empty_add(type='PLAIN_AXES', location=(left_x_center, lower_y_center, 0)); bpy.context.active_object.name="FIGURE_SLOT"
    # bpy.ops.object.empty_add(type='PLAIN_AXES', location=(right_x_center, acc_y_center + acc_cell_h*+1, 0)); bpy.context.active_object.name="ACC1_SLOT"
    # bpy.ops.object.empty_add(type='PLAIN_AXES', location=(right_x_center, acc_y_center + acc_cell_h* 0, 0)); bpy.context.active_object.name="ACC2_SLOT"


    # ----------------- import + orient + fit + place -----------------
    # Figure
    fig = import_model_with_textures(args.figure, "Figure")
    slot_depth = 10000
    if fig:        
        needs_roll = needs_x_roll(fig)
        apply_xforms(fig)
        if needs_roll:
            roll_about_parallel_world_x(fig, -90)
        
        # orient_object(fig, head_bias=True)          # main character
        center_xy(fig);             # center before fitting
        rest_on_z0(fig)             # put on the card top plane (Z=0)
        slot_depth = uniform_fit(fig, fig_slot_w, fig_slot_h, margin=args.margin_figure)
        # place: center of left lower region
        fig.location.x = left_x_center
        fig.location.y = lower_y_center
        snap_bottom_to_base_top(fig, card)          # just touching the card
        sink_into_card(fig, card, max_fraction=1.0/3.0)
        sink_further_and_cut_protrusion(fig, card)       # Second sinking + cut
        bpy.context.view_layer.update()

        # Dynamic jig generation for the figure within its grid bounds
        if args.jigs_requested:
            master_min = (left_x_center - fig_slot_w/2.0, lower_y_center - fig_slot_h/2.0, 0.0)
            master_max = (left_x_center + fig_slot_w/2.0, lower_y_center + fig_slot_h/2.0, args.grid_height)
            jigs_to_generate = [j.strip() for j in args.jigs_requested.split(',') if j.strip()]
            for d in jigs_to_generate:
                overlap_val = args.overlap_z if 'Z' in d else (args.overlap_x if 'X' in d else args.overlap_y)
                jig_obj = generate_jig_in_place(
                    raw_model=fig,
                    master_min=master_min,
                    master_max=master_max,
                    overlap=overlap_val,
                    bottom_thickness=1.0, 
                    inflation=args.inflation_margin,
                    direction=d
                )

    # Accessories
    acc_objs = []
    acc_count = min(3, len(args.acc))
    # Y centers for 3 vertical parts: top/mid/bottom within acc column centered at acc_y_center
    start_y = acc_y_center + (acc_slot_h/2.0) - acc_cell_h/2.0
    centers_y = [ start_y - i*acc_cell_h for i in range(acc_count) ]

    for i in range(acc_count):
        path = args.acc[i]
        if not os.path.exists(path): continue
        acc = import_model_with_textures(path, f"Accessory_{i+1}")
        if not acc: continue
        apply_xforms(acc)
        if needs_roll:
            roll_about_parallel_world_x(acc, -90)
            
        center_xy(acc); rest_on_z0(acc)
        # fit inside a square cell of height acc_cell_h and width acc_slot_w
        uniform_fit(acc, acc_slot_w, acc_cell_h, margin=args.margin_accessories, target_d=slot_depth)
        # place
        acc.location.x = right_x_center
        acc.location.y = centers_y[i]
        snap_bottom_to_base_top(acc, card)          # just touching the card
        sink_into_card(acc, card, max_fraction=1.0/3.0)
        bpy.context.view_layer.update()
        acc_objs.append(acc)

    # ----------------- placement export (top-view XY) -----------------
    recs = []

    # Card (use world dims; your card is centered at origin with top on Z=0)
    c_minx, c_miny, c_maxx, c_maxy = obj_xy_aabb(card)
    recs.append(pack_xy_record(
        "Card", c_minx, c_miny, c_maxx, c_maxy,
        rot_z_rad=card.matrix_world.to_euler('XYZ').z
    ))

    # Figure
    if fig:
        f_minx, f_miny, f_maxx, f_maxy = obj_xy_aabb(fig)
        recs.append(pack_xy_record(
            "base_character", f_minx, f_miny, f_maxx, f_maxy,
            rot_z_rad=fig.matrix_world.to_euler('XYZ').z
        ))

    # Accessories
    for i, acc in enumerate(acc_objs, start=1):
        a_minx, a_miny, a_maxx, a_maxy = obj_xy_aabb(acc)
        recs.append(pack_xy_record(
            f"accessory_{i}", a_minx, a_miny, a_maxx, a_maxy,
            rot_z_rad=acc.matrix_world.to_euler('XYZ').z
        ))

    # Text group (union of title + subtitle)
    tg_minx, tg_miny, tg_maxx, tg_maxy = group_xy_aabb([title_obj, sub_obj])
    recs.append(pack_xy_record(
        "TextGroup", tg_minx, tg_miny, tg_maxx, tg_maxy,
        rot_z_rad=text_group.matrix_world.to_euler('XYZ').z
    ))

    # Meta (use post-padding W/H so they match actual layout space)
    meta = {
        "job_id": args.job_id,
        "units": "mm",
        "card": {
            "W": float(args.card_width),
            "H": float(args.card_height),
            "card_thickness": float(args.card_thickness),
            "upper_ratio": float(args.upper_ratio),
            "padding_card": float(args.padding_card),
        },
        "slots": {
            "figure": {"w": float(fig_slot_w), "h": float(fig_slot_h)},
            "accessories": {"w": float(acc_slot_w), "h": float(acc_slot_h)},
            "text_strip": {"h": float(args.card_height/5.0)}
        }
    }

    # File path (default or user-specified)
    layout_path = os.path.join(args.middir, args.model_name_seed + f"_layout.json")
    write_layout_json(layout_path, meta, recs)

    # ----------------- export -----------------
    ensure_outdir(args.outdir)
    ensure_middir(args.middir)
    
    print(f"Rendering scene with texture")    
    render_path = os.path.join(args.middir, args.model_name_seed + f"_scene_render.png")
    render_scene_ortho(
        output_path=render_path,
        res_x=args.render_resx,
        res_y=args.render_resy
    )

#def someMore():
    group_png = os.path.join(args.middir, f"TextGroup.png")

    # diagnose_text_group_front(text_group, px=1600, margin=0.08)
    # render_text_group_front_png(text_group, group_png, px=1600, margin=0.08, color=(1,0,0,1))

    # --- Optional: Export Jigs individually ---
    # if args.jigs_requested:
    #     jigs_to_export = [j.strip() for j in args.jigs_requested.split(',') if j.strip()]
    #     for d in jigs_to_export:
    #         jig_name = f"Jig_{d}"
    #         if jig_name in bpy.data.objects:
    #             bpy.ops.object.select_all(action='DESELECT')
    #             jig_obj = bpy.data.objects[jig_name]
    #             jig_obj.select_set(True)
    #             bpy.context.view_layer.objects.active = jig_obj
    #             jig_stl_path = os.path.join(args.outdir, f"{args.model_name_seed}_{jig_name}.stl")
    #             bpy.ops.export_mesh.stl(filepath=jig_stl_path, use_selection=True)

    blend_path = os.path.join(args.outdir, args.model_name_seed + f"_model.blend")
    stl_path = os.path.join(args.outdir, args.model_name_seed + f"_model.stl")

    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"[OK] Blend: {blend_path}")
    
    # Save combined STL of all meshes (card + models)
    export_scene_as_stl(stl_path)
    print(f"[OK] STL: {stl_path}")



    print("[DONE]")


if __name__ == "__main__":
    main()