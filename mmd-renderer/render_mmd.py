"""
MMD Headless Renderer with Genshin Shader v2.2.1 by Ben Ayers
Usage:
  blender -b -P render_mmd.py -- <model.pmx> <motion.vmd> <camera.vmd|none> <audio.wav> <output.mp4> [duration|auto] [bg.mp4|none] [facial.vmd|none] [brightness] [contrast] [saturation] [physics on|off] [genshin_blend|auto|off] [outline on|off]
"""

import bpy
import sys
import os
import math
import time
import mathutils
from datetime import datetime

render_start_time = time.time()
print(f"[TIME] Script start: {datetime.now().strftime('%H:%M:%S')}")

# === Parse args ===
argv = sys.argv
argv = argv[argv.index("--") + 1:] if "--" in argv else []

if len(argv) < 5:
    print("ERROR: Butuh minimum 5 arg: model.pmx motion.vmd camera.vmd|none audio.wav output.mp4")
    sys.exit(1)

model_path   = os.path.abspath(argv[0])
motion_path  = os.path.abspath(argv[1])
camera_path  = argv[2]
audio_path   = os.path.abspath(argv[3])
output_path  = os.path.abspath(argv[4])
duration_arg = argv[5] if len(argv) > 5 else "auto"
bg_video_arg = argv[6] if len(argv) > 6 else "none"
facial_arg   = argv[7] if len(argv) > 7 else "none"
char_brightness = float(argv[8]) if len(argv) > 8 else 1.0
char_contrast   = float(argv[9]) if len(argv) > 9 else 0.0
char_saturation = float(argv[10]) if len(argv) > 10 else 1.0
keep_physics    = (argv[11].lower() == "on") if len(argv) > 11 else True
# Genshin Shader blend file path ('auto' = default path, 'off' = skip)
genshin_arg     = argv[12] if len(argv) > 12 else "auto"
outline_enabled = (argv[13].lower() == "on") if len(argv) > 13 else True
# Auto-trim intro: potong frame intro/idle sebelum karakter mulai bergerak
auto_trim       = (argv[14].lower() == "on") if len(argv) > 14 else True
trim_buffer     = int(argv[15]) if len(argv) > 15 else 3  # frame buffer sebelum motion start

# Resolve genshin blend path
if genshin_arg.lower() == "auto":
    # Default: cari di parent dir script ini, atau via env var GENSHIN_SHADER_BLEND
    genshin_blend = os.environ.get(
        "GENSHIN_SHADER_BLEND",
        str(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "_genshin_shader.blend"))
    )
elif genshin_arg.lower() == "off":
    genshin_blend = None
else:
    genshin_blend = os.path.abspath(genshin_arg)

use_genshin = genshin_blend is not None and os.path.exists(genshin_blend)

auto_duration = duration_arg.lower() == "auto"
duration_sec = 0 if auto_duration else int(duration_arg)

use_custom_camera = camera_path.lower() != "none"
if use_custom_camera:
    camera_path = os.path.abspath(camera_path)
use_bg_video = bg_video_arg.lower() != "none"
if use_bg_video:
    bg_video_path = os.path.abspath(bg_video_arg)
use_facial = facial_arg.lower() != "none"
if use_facial:
    facial_path = os.path.abspath(facial_arg)

# === AUTO-DETECT camera & facial di folder motion (fix AI halusinasi) ===
# Kalau camera="none" tapi folder motion ada Camera.vmd / Cam.vmd → pakai itu
# Kalau facial="none" tapi folder motion ada Facial.vmd / Face.vmd → pakai itu
motion_dir = os.path.dirname(motion_path)
if not use_custom_camera:
    for cam_name in ['Camera.vmd', 'camera.vmd', 'Cam.vmd', 'CAM.vmd', 'Cam Fullscreen.vmd']:
        candidate = os.path.join(motion_dir, cam_name)
        if os.path.isfile(candidate):
            print(f"[AUTO-DETECT] Camera.vmd ditemukan di folder motion: {candidate}")
            camera_path = os.path.abspath(candidate)
            use_custom_camera = True
            break
if not use_facial:
    for fac_name in ['Facial.vmd', 'facial.vmd', 'Face.vmd', 'face.vmd', 'Expression.vmd']:
        candidate = os.path.join(motion_dir, fac_name)
        if os.path.isfile(candidate):
            print(f"[AUTO-DETECT] Facial.vmd ditemukan di folder motion: {candidate}")
            facial_path = os.path.abspath(candidate)
            use_facial = True
            break

RES_X = 1080
RES_Y = 1920
FPS = 60
MOTION_SOURCE_FPS = 30
total_frames = 0 if auto_duration else duration_sec * FPS

print(f"[INFO] Model:    {model_path}")
print(f"[INFO] Motion:   {motion_path}")
print(f"[INFO] Camera:   {camera_path if use_custom_camera else 'DEFAULT'}")
print(f"[INFO] Audio:    {audio_path}")
print(f"[INFO] BG Video: {bg_video_path if use_bg_video else 'NONE'}")
print(f"[INFO] Facial:   {facial_path if use_facial else 'NONE'}")
print(f"[INFO] Tone:     brightness={char_brightness} contrast={char_contrast} saturation={char_saturation}")
print(f"[INFO] Physics:  {'ON' if keep_physics else 'OFF'}")
print(f"[INFO] Genshin:  {genshin_blend if use_genshin else 'OFF (fallback default materials)'}")
print(f"[INFO] Outline:  {'ON' if outline_enabled else 'OFF'}")
print(f"[INFO] AutoTrim: {'ON (buffer ' + str(trim_buffer) + ' frame)' if auto_trim else 'OFF'}")
if auto_duration:
    print(f"[INFO] Render:   {RES_X}x{RES_Y} @ {FPS}fps, AUTO-detect")
else:
    print(f"[INFO] Render:   {RES_X}x{RES_Y} @ {FPS}fps, {duration_sec}s = {total_frames} frames")

# === Clean scene ===
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

# === Append Genshin Shader node groups (sebelum import model) ===
genshin_node_group = None
outline_node_group = None
rim_light_group = None

if use_genshin:
    print(f"[STEP] Appending Genshin Shader node groups from {genshin_blend}...")
    with bpy.data.libraries.load(genshin_blend, link=False) as (data_from, data_to):
        wanted_groups = ['Genshin Shader v2.2', 'Outline',
                         'Genshin Rim Light v2.2 (Beta)', 'Face Lightmap Mapping v2.1',
                         'Auto Smooth']
        data_to.node_groups = [n for n in data_from.node_groups if n in wanted_groups]

    for ng in bpy.data.node_groups:
        if ng.name == 'Genshin Shader v2.2' or ng.name.startswith('Genshin Shader v2.2'):
            genshin_node_group = ng
        elif ng.name == 'Outline':
            outline_node_group = ng
        elif 'Rim Light' in ng.name:
            rim_light_group = ng

    print(f"[INFO] Genshin shader node group loaded: {genshin_node_group.name if genshin_node_group else 'FAILED'}")

# === Import PMX ===
print("[STEP] Importing PMX model...")
bpy.ops.mmd_tools.import_model(filepath=model_path, types={'MESH', 'ARMATURE', 'MORPHS'}, scale=0.08)

mmd_root = None
for obj in bpy.context.scene.objects:
    if obj.mmd_type == 'ROOT':
        mmd_root = obj
        break
if mmd_root is None:
    print("ERROR: MMD root tidak ketemu")
    sys.exit(1)

# Pre-validate mesh
for obj in bpy.data.objects:
    if obj.type == 'MESH':
        try:
            obj.data.validate(verbose=False, clean_customdata=False)
        except Exception:
            pass

if not keep_physics:
    print("[STEP] Disabling MMD physics...")
    for obj in list(bpy.data.objects):
        if obj.mmd_type in ('RIGID_GRP_OBJ', 'JOINT_GRP_OBJ'):
            obj.hide_viewport = True
            obj.hide_render = True
    if bpy.context.scene.rigidbody_world:
        bpy.context.scene.rigidbody_world.enabled = False

# === Import Motion ===
print("[STEP] Importing motion VMD...")
bpy.ops.object.select_all(action='DESELECT')
mmd_root.select_set(True)
for child in mmd_root.children_recursive:
    child.select_set(True)
bpy.context.view_layer.objects.active = mmd_root
bpy.ops.mmd_tools.import_vmd(filepath=motion_path, scale=0.08, bone_mapper='PMX')

if use_facial:
    print("[STEP] Importing facial VMD...")
    bpy.ops.object.select_all(action='DESELECT')
    mmd_root.select_set(True)
    for child in mmd_root.children_recursive:
        child.select_set(True)
    bpy.context.view_layer.objects.active = mmd_root
    try:
        bpy.ops.mmd_tools.import_vmd(filepath=facial_path, scale=0.08, bone_mapper='PMX')
    except Exception as e:
        print(f"[WARN] Facial import gagal: {e}")

# === Camera ===
print("[STEP] Setting up camera...")
if use_custom_camera:
    bpy.ops.object.select_all(action='DESELECT')
    cam_data = bpy.data.cameras.new("MMDCam")
    cam_obj = bpy.data.objects.new("MMDCam", cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)
    cam_obj.select_set(True)
    bpy.context.view_layer.objects.active = cam_obj

    for op_name in ['convert_to_mmd_camera', 'add_camera']:
        if hasattr(bpy.ops.mmd_tools, op_name):
            try:
                getattr(bpy.ops.mmd_tools, op_name)()
                break
            except Exception:
                pass

    mmd_camera_root = None
    for obj in bpy.context.scene.objects:
        if obj.mmd_type == 'CAMERA':
            mmd_camera_root = obj
            break

    if mmd_camera_root:
        bpy.ops.object.select_all(action='DESELECT')
        mmd_camera_root.select_set(True)
        bpy.context.view_layer.objects.active = mmd_camera_root
        bpy.ops.mmd_tools.import_vmd(filepath=camera_path, scale=0.08)
        for child in mmd_camera_root.children_recursive:
            if child.type == 'CAMERA':
                bpy.context.scene.camera = child
                break
    else:
        cam_obj.location = (0, -10, 5)
        cam_obj.rotation_euler = (math.radians(80), 0, 0)
        bpy.context.scene.camera = cam_obj
else:
    cam_data = bpy.data.cameras.new("DefaultCam")
    cam_obj = bpy.data.objects.new("DefaultCam", cam_data)
    bpy.context.scene.collection.objects.link(cam_obj)
    # Smart camera auto-fit: calculate model bounds, position camera supaya karakter fit di portrait frame
    # Get all mesh bounds dari karakter (skip ground/shadow plane)
    min_z, max_z = float('inf'), float('-inf')
    min_y, max_y = float('inf'), float('-inf')
    min_x, max_x = float('inf'), float('-inf')
    for obj in bpy.data.objects:
        if obj.type != 'MESH' or obj.hide_render:
            continue
        if 'shadow' in obj.name.lower() or 'plane' in obj.name.lower():
            continue
        for v in obj.bound_box:
            wv = obj.matrix_world @ mathutils.Vector(v)
            min_z = min(min_z, wv.z); max_z = max(max_z, wv.z)
            min_y = min(min_y, wv.y); max_y = max(max_y, wv.y)
            min_x = min(min_x, wv.x); max_x = max(max_x, wv.x)
    if min_z == float('inf'):
        # Fallback default
        cam_obj.location = (0, -4, 1.4)
        cam_obj.rotation_euler = (math.radians(85), 0, 0)
    else:
        char_height = max_z - min_z
        char_center_z = (min_z + max_z) / 2
        # Portrait 1080x1920 aspect = 9:16. Tinggi karakter harus fill ~85% frame
        # Default camera FOV 50° → tan(25°) = 0.466
        # Untuk fill 85% portrait, distance = (char_height / 2 / 0.85) / tan(25°) * (16/9 adjust)
        target_height_fraction = 0.80
        fov_y = math.radians(50 / 2)  # half FOV
        distance = (char_height / 2 / target_height_fraction) / math.tan(fov_y)
        # Portrait aspect: extend distance dikit biar tidak crop
        distance *= 1.1
        cam_obj.location = (0, -distance, char_center_z)
        cam_obj.rotation_euler = (math.radians(90), 0, 0)  # straight horizontal
        print(f"[INFO] Auto-fit camera: char_height={char_height:.2f}m, distance={distance:.2f}m, center_z={char_center_z:.2f}m")
    bpy.context.scene.camera = cam_obj

# === Sun Light (untuk Genshin Shader Global Light Vector) ===
print("[STEP] Adding Sun light (Genshin LightVector source)...")
sun = bpy.data.lights.new(name="GenshinSun", type='SUN')
sun.energy = 1.5
sun.color = (1.0, 1.0, 1.0)
sun.use_shadow = True
sun_obj = bpy.data.objects.new("GenshinSun", sun)
bpy.context.scene.collection.objects.link(sun_obj)
sun_obj.rotation_euler = (math.radians(50), math.radians(20), math.radians(15))

# === GENSHIN SHADER: Setup LightVector + AOVs (replicate Init_GenshinShader) ===
if use_genshin:
    print("[STEP] Initializing Genshin Shader LightVector + AOVs...")
    view_layer = bpy.context.view_layer

    # Add LightVector & LightColorTint properties
    bpy.types.ViewLayer.LightVector = bpy.props.FloatVectorProperty(name="LightVector")
    view_layer.LightVector = (0.0, 0.0, 0.0)
    bpy.types.ViewLayer.LightColorTint = bpy.props.FloatVectorProperty(name="LightColorTint")
    view_layer.LightColorTint = (1.0, 1.0, 1.0)

    # Drivers: rotation
    for idx in range(3):
        view_layer.driver_remove('["LightVector"]', idx)
        d = view_layer.driver_add('["LightVector"]', idx).driver
        v = d.variables.new()
        v.name = 'rotation_euler'
        v.targets[0].id = sun_obj
        v.targets[0].data_path = f"rotation_euler[{idx}]"
        d.expression = "rotation_euler % (2*pi)"

    # Drivers: color tint
    for idx in range(3):
        view_layer.driver_remove('["LightColorTint"]', idx)
        d = view_layer.driver_add('["LightColorTint"]', idx).driver
        v = d.variables.new()
        v.name = 'color'
        v.targets[0].id_type = "LIGHT"
        v.targets[0].id = sun
        v.targets[0].data_path = f'color[{idx}]'
        d.expression = "color"

    # AOVs untuk Rim Light compositor
    for aov_name in ['GSDepth', 'GSFlood']:
        if aov_name not in [a.name for a in view_layer.aovs]:
            aov = view_layer.aovs.add()
            aov.name = aov_name
            aov.type = "COLOR"
    print("[INFO] Genshin Shader initialized (LightVector + AOVs)")

# === Apply Genshin Shader ke setiap material MMD ===
def apply_genshin_shader_to_material(mat):
    """Wrap material existing dengan Genshin Shader node group.
    Diffuse texture jadi Base Color input, alpha → Opacity Mask."""
    if not mat or not mat.use_nodes or genshin_node_group is None:
        return False

    nt = mat.node_tree

    # Cari diffuse image
    diffuse_image = None
    diffuse_color = (0.8, 0.8, 0.8, 1.0)
    for node in nt.nodes:
        if node.type == 'TEX_IMAGE' and node.image and diffuse_image is None:
            n = node.image.name.lower()
            if 'toon' not in n and 'sph' not in n and 'spa' not in n and 'normal' not in n and '_s.' not in n:
                diffuse_image = node.image
        if node.type == 'BSDF_PRINCIPLED':
            try:
                diffuse_color = tuple(node.inputs['Base Color'].default_value)
            except Exception:
                pass

    # Clear existing nodes
    for node in list(nt.nodes):
        nt.nodes.remove(node)

    output = nt.nodes.new('ShaderNodeOutputMaterial')

    # Genshin Shader node group
    shader = nt.nodes.new('ShaderNodeGroup')
    shader.node_tree = genshin_node_group

    # Base color source
    if diffuse_image:
        tex = nt.nodes.new('ShaderNodeTexImage')
        tex.image = diffuse_image
        nt.links.new(tex.outputs['Color'], shader.inputs['Base Color'])
        # Opacity Mask kalau ada
        if 'Opacity Mask' in shader.inputs:
            nt.links.new(tex.outputs['Alpha'], shader.inputs['Opacity Mask'])
    else:
        try:
            shader.inputs['Base Color'].default_value = diffuse_color
        except Exception:
            pass

    # Konfigurasi default Genshin shader supaya hidup
    try:
        shader.inputs['Use Global Light Vector (See Script)'].default_value = True
        shader.inputs['Tint Strength'].default_value = 0.0
        shader.inputs['Roughness'].default_value = 0.5
        shader.inputs['Metallic'].default_value = 0.0
        shader.inputs['Specular Intensity'].default_value = 0.3
        shader.inputs['Specular Size'].default_value = 0.4
        shader.inputs['Global Brightness'].default_value = 1.0
        shader.inputs['Backface Culling'].default_value = False
        shader.inputs['Emission Strength'].default_value = 0.0
        # Shadow zone
        shader.inputs['Shadow Color'].default_value = (0.7, 0.65, 0.78, 1.0)
        shader.inputs['Transition'].default_value = 0.05  # smooth transition
        shader.inputs['Position'].default_value = 0.5
        shader.inputs['Hardness'].default_value = 0.5
    except KeyError as e:
        print(f"[WARN] Genshin input missing: {e}")

    nt.links.new(shader.outputs[0], output.inputs['Surface'])

    mat.blend_method = 'HASHED'
    mat.shadow_method = 'HASHED'
    mat.use_backface_culling = False
    return True

if use_genshin and genshin_node_group:
    print("[STEP] Applying Genshin Shader ke semua materials...")
    applied = 0
    for mat in bpy.data.materials:
        # Skip material yang dari Genshin Shader sendiri (Outline, Text, dll)
        if mat.name in ['Text', 'Platform', 'Outline', 'Default Material'] or 'GenshinMaterial' in mat.name or 'DemoHead' in mat.name:
            continue
        if apply_genshin_shader_to_material(mat):
            applied += 1
    print(f"[INFO] {applied} materials di-shade pakai Genshin Shader v2.2")

# === Shadow Catcher Plane (untuk bayangan karakter di "lantai") ===
print("[STEP] Adding shadow catcher plane...")
import bmesh
shadow_mesh = bpy.data.meshes.new("ShadowCatcher")
shadow_obj = bpy.data.objects.new("ShadowCatcher", shadow_mesh)
bpy.context.scene.collection.objects.link(shadow_obj)
bm = bmesh.new()
bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=15)
bm.to_mesh(shadow_mesh)
bm.free()
shadow_obj.location = (0, 0, 0)  # di Z=0 (floor level)

# Shadow catcher material: transparent except where light is blocked (shadow zone)
shadow_mat = bpy.data.materials.new("ShadowCatchMat")
shadow_mat.use_nodes = True
shadow_mat.blend_method = 'BLEND'
shadow_mat.shadow_method = 'NONE'  # plane itself tidak cast shadow
shadow_mat.use_backface_culling = False
nt = shadow_mat.node_tree
for n in list(nt.nodes):
    nt.nodes.remove(n)

# Build: Diffuse → ShaderToRGB → Invert (shadow=1, light=0) → Multiply by intensity
# Use sebagai Fac di MixShader: Transparent (lit) / Black Emission (shadow)
output = nt.nodes.new('ShaderNodeOutputMaterial')
diffuse_lit = nt.nodes.new('ShaderNodeBsdfDiffuse')
diffuse_lit.inputs['Color'].default_value = (1, 1, 1, 1)
shader_rgb = nt.nodes.new('ShaderNodeShaderToRGB')
invert_node = nt.nodes.new('ShaderNodeInvert')
intensity_mult = nt.nodes.new('ShaderNodeMath')
intensity_mult.operation = 'MULTIPLY'
intensity_mult.inputs[1].default_value = 0.6  # darkness 0.0-1.0 (0.6 = bayangan medium-dark)

shadow_emit = nt.nodes.new('ShaderNodeEmission')
shadow_emit.inputs['Color'].default_value = (0, 0, 0, 1)  # black shadow
shadow_emit.inputs['Strength'].default_value = 1.0
transparent_lit = nt.nodes.new('ShaderNodeBsdfTransparent')
mix_shader = nt.nodes.new('ShaderNodeMixShader')

nt.links.new(diffuse_lit.outputs['BSDF'], shader_rgb.inputs[0])
nt.links.new(shader_rgb.outputs['Color'], invert_node.inputs['Color'])
nt.links.new(invert_node.outputs['Color'], intensity_mult.inputs[0])
nt.links.new(intensity_mult.outputs[0], mix_shader.inputs['Fac'])
nt.links.new(transparent_lit.outputs['BSDF'], mix_shader.inputs[1])  # lit area = transparent
nt.links.new(shadow_emit.outputs['Emission'], mix_shader.inputs[2])  # shadow area = black
nt.links.new(mix_shader.outputs['Shader'], output.inputs['Surface'])

shadow_obj.data.materials.append(shadow_mat)
print("[INFO] Shadow catcher plane added")

# === Audio ===
print("[STEP] Adding audio...")
if not bpy.context.scene.sequence_editor:
    bpy.context.scene.sequence_editor_create()
bpy.context.scene.sequence_editor.sequences.new_sound(
    name="bgm", filepath=audio_path, channel=1, frame_start=1
)

# === Render settings ===
print("[STEP] Configuring render...")
scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x = RES_X
scene.render.resolution_y = RES_Y
scene.render.resolution_percentage = 100
scene.render.fps = FPS
scene.render.frame_map_old = MOTION_SOURCE_FPS
scene.render.frame_map_new = FPS
scene.frame_start = 1

# Color Management: Standard (anime-friendly, bukan AGX/Filmic)
scene.view_settings.view_transform = 'Standard'
scene.view_settings.look = 'None'
scene.view_settings.exposure = 0.0
scene.view_settings.gamma = 1.0
print("[INFO] Color Management: Standard view transform")

# Auto-detect durasi
if auto_duration:
    max_motion_frame = 1
    for obj in bpy.data.objects:
        if obj.animation_data and obj.animation_data.action:
            try:
                end_f = int(obj.animation_data.action.frame_range[1])
                if end_f > max_motion_frame:
                    max_motion_frame = end_f
            except Exception:
                pass
        if obj.type == 'MESH' and obj.data.shape_keys:
            sk = obj.data.shape_keys
            if sk.animation_data and sk.animation_data.action:
                try:
                    end_f = int(sk.animation_data.action.frame_range[1])
                    if end_f > max_motion_frame:
                        max_motion_frame = end_f
                except Exception:
                    pass
    total_frames = int(max_motion_frame * (FPS / MOTION_SOURCE_FPS))
    duration_sec = total_frames / FPS
    print(f"[INFO] Auto-detected: {max_motion_frame} src frames → {total_frames} render frames ({duration_sec:.2f}s)")

scene.frame_end = total_frames

# === AUTO-TRIM: Detect frame dimana karakter mulai bergerak (skip intro/idle) ===
def find_motion_start_source_frame():
    """Cek fcurves di armature, find earliest keyframe dengan perubahan signifikan.
    Returns frame number di source FPS (30fps timeline)."""
    arm = None
    for obj in bpy.data.objects:
        if obj.type == 'ARMATURE' and obj.animation_data and obj.animation_data.action:
            arm = obj
            break
    if not arm:
        return 1

    action = arm.animation_data.action
    rotation_threshold = 0.08   # radians (~4.5 derajat)
    location_threshold = 0.05   # meters
    earliest = None

    for fcurve in action.fcurves:
        if 'rotation' in fcurve.data_path:
            threshold = rotation_threshold
        elif 'location' in fcurve.data_path:
            threshold = location_threshold
        else:
            continue
        kfs = fcurve.keyframe_points
        if len(kfs) < 2:
            continue
        first_val = kfs[0].co[1]
        for kf in kfs[1:]:
            if abs(kf.co[1] - first_val) > threshold:
                fnum = kf.co[0]
                if earliest is None or fnum < earliest:
                    earliest = fnum
                break
    return int(earliest) if earliest is not None else 1


if auto_trim:
    motion_start_src = find_motion_start_source_frame()
    # Convert source frame → render frame (frame_map remap)
    motion_start_render = int(motion_start_src * (FPS / MOTION_SOURCE_FPS))
    # Buffer beberapa frame sebelum motion start (smoother intro)
    trimmed_start = max(1, motion_start_render - trim_buffer)

    if trimmed_start > 1:
        old_start = scene.frame_start
        scene.frame_start = trimmed_start

        # Shift audio strip supaya audio mulai dari awal pas frame_start
        try:
            for strip in bpy.context.scene.sequence_editor.sequences:
                if strip.type == 'SOUND':
                    strip.frame_start = trimmed_start
        except Exception:
            pass

        skipped_frames = trimmed_start - old_start
        skipped_sec = skipped_frames / FPS
        print(f"[AUTO-TRIM] Motion start detected at source frame {motion_start_src} → render frame {motion_start_render}")
        print(f"[AUTO-TRIM] Skipping {skipped_frames} intro frames ({skipped_sec:.2f}s)")
        print(f"[AUTO-TRIM] Render now: frame {scene.frame_start} → {scene.frame_end} ({(scene.frame_end - scene.frame_start + 1)} frames)")
    else:
        print("[AUTO-TRIM] No intro detected, motion starts at frame 1")

# EEVEE settings — Genshin Shader handle shading sendiri, jadi minimal post-fx
scene.eevee.taa_render_samples = 32
if use_genshin:
    scene.eevee.use_gtao = False  # Genshin shader sudah include AO logic sendiri
    scene.eevee.use_bloom = True
    scene.eevee.bloom_intensity = 0.03
    scene.eevee.use_ssr = False
else:
    scene.eevee.use_gtao = True
    scene.eevee.gtao_distance = 0.5
    scene.eevee.use_bloom = True
    scene.eevee.bloom_intensity = 0.05

# === Background Image/Video Compositor (auto-detect) ===
if use_bg_video:
    bg_ext = os.path.splitext(bg_video_path)[1].lower()
    is_video_bg = bg_ext in ('.mp4', '.mov', '.avi', '.webm', '.mkv')
    bg_type = "VIDEO" if is_video_bg else "IMAGE"
    print(f"[STEP] Setting up BG {bg_type}: {bg_video_path}")
    scene.render.film_transparent = True
    scene.use_nodes = True
    tree = scene.node_tree
    for node in tree.nodes:
        tree.nodes.remove(node)

    render_layers = tree.nodes.new('CompositorNodeRLayers')
    bg_image = bpy.data.images.load(bg_video_path)
    bg_image.source = 'MOVIE' if is_video_bg else 'FILE'

    image_node = tree.nodes.new('CompositorNodeImage')
    image_node.image = bg_image
    if is_video_bg:
        image_node.frame_duration = total_frames
        image_node.frame_start = 1
        image_node.use_auto_refresh = True

    scale_node = tree.nodes.new('CompositorNodeScale')
    scale_node.space = 'RENDER_SIZE'
    scale_node.frame_method = 'CROP'

    bright_contrast = tree.nodes.new('CompositorNodeBrightContrast')
    bright_contrast.inputs['Bright'].default_value = (char_brightness - 1.0) * 1.0
    bright_contrast.inputs['Contrast'].default_value = char_contrast

    hue_sat = tree.nodes.new('CompositorNodeHueSat')
    hue_sat.inputs['Saturation'].default_value = char_saturation

    alpha_over = tree.nodes.new('CompositorNodeAlphaOver')
    composite = tree.nodes.new('CompositorNodeComposite')

    tree.links.new(image_node.outputs['Image'], scale_node.inputs['Image'])
    tree.links.new(scale_node.outputs['Image'], alpha_over.inputs[1])
    tree.links.new(render_layers.outputs['Image'], bright_contrast.inputs['Image'])
    tree.links.new(bright_contrast.outputs['Image'], hue_sat.inputs['Image'])
    tree.links.new(hue_sat.outputs['Image'], alpha_over.inputs[2])
    tree.links.new(alpha_over.outputs['Image'], composite.inputs['Image'])

# Output MP4 + H264 + AAC
scene.render.image_settings.file_format = 'FFMPEG'
scene.render.ffmpeg.format = 'MPEG4'
scene.render.ffmpeg.codec = 'H264'
scene.render.ffmpeg.constant_rate_factor = 'MEDIUM'
scene.render.ffmpeg.audio_codec = 'AAC'
scene.render.filepath = output_path

# === RENDER ===
print(f"[STEP] Rendering {total_frames} frames at {RES_X}x{RES_Y} @ {FPS}fps...")
render_phase_start = time.time()
bpy.ops.render.render(animation=True)
render_phase_elapsed = time.time() - render_phase_start
total_elapsed = time.time() - render_start_time

def fmt_duration(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    if h > 0:
        return f"{h}j {m}m {s:.1f}d"
    if m > 0:
        return f"{m} menit {s:.1f} detik"
    return f"{s:.1f} detik"

avg_per_frame = render_phase_elapsed / total_frames if total_frames else 0

print(f"[DONE] Output saved to: {output_path}")
print(f"[TIME] Render phase    : {fmt_duration(render_phase_elapsed)}")
print(f"[TIME] Total script    : {fmt_duration(total_elapsed)}")
print(f"[TIME] Avg per frame   : {avg_per_frame:.2f} detik/frame ({total_frames} frame)")
print(f"[TIME] Finished at     : {datetime.now().strftime('%H:%M:%S')}")
