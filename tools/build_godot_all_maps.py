#!/usr/bin/env python3
"""Generate a Godot 4 project with all recovered Block Gun maps."""
import json, pathlib, shutil, re
from PIL import Image, ImageDraw, ImageChops, ImageEnhance, ImageOps
ROOT=pathlib.Path("scene_graph"); PROJECT=pathlib.Path("godot_project")
MAPS=["lvl_baghdad","lvl_assault","lvl_middle_east","lvl_resort","lvl_forest","lvl_house","lvl_india","lvl_rome","lvl_deluxe_fest"]
names={"lvl_baghdad":"Baghdad","lvl_assault":"Assalto","lvl_middle_east":"Oriente Médio","lvl_resort":"Resort","lvl_forest":"Floresta","lvl_house":"Casa","lvl_india":"Índia","lvl_rome":"Roma","lvl_deluxe_fest":"Festival Deluxe"}
def slice_obj(source:pathlib.Path,destination:pathlib.Path,first:int,count:int):
    """Keep only the Unity static-batch submeshes assigned to one renderer."""
    lines=source.read_text(encoding="utf-8",errors="replace").splitlines()
    groups=[]; preamble=[]; current=None
    for line in lines:
        if line.startswith("g "):
            if current is not None: groups.append(current)
            current=[line]
        elif line.startswith(("v ","vt ","vn ","mtllib ","o ")):
            # OBJ vertex/UV/normal tables are global and must survive submesh slicing.
            preamble.append(line)
        elif current is None:
            preamble.append(line)
        else:
            current.append(line)
    if current is not None: groups.append(current)
    # UnityPy writes a parent group containing shared vertex tables, followed by
    # one face group per static-batch submesh. Keep the global tables plus only
    # the faces assigned to this GameObject.
    usable=[g for g in groups if any(x.startswith("f ") for x in g)]
    if count<=0:
        shutil.copy2(source,destination); return False
    if not usable or first<0 or first+count>len(usable):
        raise ValueError(f"Static batch range invalid for {source.name}: first={first}, count={count}, available={len(usable)}")
    chosen=usable[first:first+count]
    if len(chosen)!=count:
        raise ValueError(f"Static batch range incomplete for {source.name}: first={first}, count={count}, selected={len(chosen)}")
    destination.write_text("\n".join(preamble+[line for group in chosen for line in group])+"\n",encoding="utf-8")
    return True

def obj_size(path:pathlib.Path):
    """Return OBJ dimensions without loading its faces into memory."""
    mins=[float("inf"),float("inf"),float("inf")]
    maxs=[float("-inf"),float("-inf"),float("-inf")]
    try:
        with path.open(errors="ignore") as src:
            for line in src:
                if line.startswith("v "):
                    try:
                        xyz=list(map(float,line.split()[1:4]))
                        for axis,value in enumerate(xyz):
                            mins[axis]=min(mins[axis],value)
                            maxs[axis]=max(maxs[axis],value)
                    except (ValueError,IndexError):
                        pass
    except OSError:
        return [0.0,0.0,0.0]
    if any(value==float("inf") for value in mins):
        return [0.0,0.0,0.0]
    return [maxs[i]-mins[i] for i in range(3)]

def enhance_india_atlas(source:pathlib.Path,destination:pathlib.Path):
    """Bake subtle surface variation into an India-only atlas copy (no runtime shader)."""
    with Image.open(source) as opened:
        image=opened.convert("RGBA")
    rgb=image.convert("RGB")
    channels=rgb.split()
    hi=ImageChops.lighter(ImageChops.lighter(channels[0],channels[1]),channels[2])
    lo=ImageChops.darker(ImageChops.darker(channels[0],channels[1]),channels[2])
    saturation=ImageChops.difference(hi,lo)
    # Restrict baked contrast/grain to low-saturation concrete, stone and plaster.
    neutral_mask=ImageOps.invert(saturation).point(lambda value: max(0,min(255,(value-18)*2)))
    contrasted=ImageEnhance.Contrast(rgb).enhance(1.055)
    noise=Image.effect_noise(rgb.size,22).convert("L")
    grain=ImageOps.colorize(noise,(112,105,94),(151,143,128)).convert("RGB")
    detailed=Image.blend(contrasted,grain,0.035)
    baked=Image.composite(detailed,rgb,neutral_mask)
    result=Image.merge("RGBA",(*baked.split(),image.getchannel("A")))
    result.save(destination,optimize=True)


def build_india_lightmapped_glb(obj_path:pathlib.Path,uv_path:pathlib.Path,lightmap_path:pathlib.Path,
                                 output_path:pathlib.Path,first_sub_mesh:int=0,sub_mesh_count:int=0):
    """Create a GLB with original UV0 and baked Unity lightmap in vertex colors."""
    try:
        import numpy as np
    except ImportError:
        import subprocess, sys
        subprocess.check_call([sys.executable,"-m","pip","install","--disable-pip-version-check","numpy"])
        import numpy as np
    import struct, io

    uv_data=json.loads(uv_path.read_text(encoding="utf-8"))
    uv0=np.asarray(uv_data.get("m_UV0",[]),dtype=np.float32)
    uv1=np.asarray(uv_data.get("m_UV1",[]),dtype=np.float32)
    if len(uv0)==0 or len(uv0)!=len(uv1):
        raise ValueError(f"India UV channel mismatch: {uv_path.name}")
    if np.any(uv0 < -0.001) or np.any(uv0 > 1.001) or np.any(uv1 < -0.001) or np.any(uv1 > 1.001):
        raise ValueError(f"India UV coordinates outside 0..1: {uv_path.name}")

    positions=[]; normals=[]; texcoords=[]; groups=[]; current=None
    with obj_path.open(encoding="utf-8",errors="replace") as source:
        for line in source:
            if line.startswith("v "):
                positions.append(tuple(map(float,line.split()[1:4])))
            elif line.startswith("vn "):
                normals.append(tuple(map(float,line.split()[1:4])))
            elif line.startswith("vt "):
                texcoords.append(tuple(map(float,line.split()[1:3])))
            elif line.startswith("g "):
                if current is not None: groups.append(current)
                current=[]
            elif line.startswith("f "):
                if current is None: current=[]
                face=[]
                for token in line.split()[1:]:
                    parts=token.split("/")
                    if len(parts)<3: raise ValueError(f"OBJ face lacks UV/normal: {obj_path.name}")
                    vi,ti,ni=(int(parts[0])-1,int(parts[1])-1,int(parts[2])-1)
                    if vi!=ti or vi!=ni:
                        raise ValueError(f"OBJ vertex/UV/normal ordering differs: {obj_path.name}")
                    face.append(vi)
                if len(face)<3: continue
                for i in range(1,len(face)-1): current.append((face[0],face[i],face[i+1]))
    if current is not None: groups.append(current)
    if len(positions)!=len(uv0) or len(normals)!=len(uv0) or len(texcoords)!=len(uv0):
        raise ValueError(f"India mesh/UV vertex counts differ: {obj_path.name}")
    usable=[group for group in groups if group]
    if sub_mesh_count>0:
        if first_sub_mesh<0 or first_sub_mesh+sub_mesh_count>len(usable):
            raise ValueError(f"India static batch range invalid: first={first_sub_mesh}, count={sub_mesh_count}, groups={len(usable)}")
        selected=usable[first_sub_mesh:first_sub_mesh+sub_mesh_count]
    else:
        selected=usable
    if not selected or any(not group for group in selected):
        raise ValueError(f"No India render submeshes selected: {obj_path.name}")

    with Image.open(lightmap_path) as lm_image:
        lightmap=np.asarray(lm_image.convert("RGB"),dtype=np.float32)/255.0
    height,width=lightmap.shape[:2]
    px=np.clip(uv1[:,0]*(width-1),0,width-1)
    py=np.clip((1.0-uv1[:,1])*(height-1),0,height-1)
    x0=np.floor(px).astype(np.int32); y0=np.floor(py).astype(np.int32)
    x1=np.minimum(x0+1,width-1); y1=np.minimum(y0+1,height-1)
    fx=(px-x0)[:,None]; fy=(py-y0)[:,None]
    c00=lightmap[y0,x0]; c10=lightmap[y0,x1]
    c01=lightmap[y1,x0]; c11=lightmap[y1,x1]
    sampled=c00*(1-fx)*(1-fy)+c10*fx*(1-fy)+c01*(1-fx)*fy+c11*fx*fy
    # Unity full-HDR lightmap decode is RGB * 2. Vertex colors preserve the
    # shadowing while clamping to the representable 0..1 color range.
    colors=np.clip(sampled*2.0,0.0,1.0)
    colors=np.concatenate((colors,np.ones((len(colors),1),dtype=np.float32)),axis=1)

    used=sorted({int(index) for group in selected for face in group for index in face})
    remap={old:new for new,old in enumerate(used)}
    pos=np.asarray(positions,dtype=np.float32)[used]
    nrm=np.asarray(normals,dtype=np.float32)[used]
    tex=np.asarray(texcoords,dtype=np.float32)[used]
    col=colors[used]
    if not np.isfinite(pos).all() or not np.isfinite(nrm).all() or not np.isfinite(tex).all() or not np.isfinite(col).all():
        raise ValueError(f"Non-finite India mesh data: {obj_path.name}")

    binary=bytearray(); views=[]; accessors=[]
    def add_view(raw,target):
        while len(binary)%4: binary.append(0)
        offset=len(binary); binary.extend(raw)
        view={"buffer":0,"byteOffset":offset,"byteLength":len(raw)}
        if target is not None: view["target"]=target
        views.append(view); return len(views)-1
    def add_accessor(view,component_type,count,kind,minimum=None,maximum=None,normalized=False):
        item={"bufferView":view,"componentType":component_type,"count":count,"type":kind}
        if minimum is not None: item["min"]=minimum
        if maximum is not None: item["max"]=maximum
        if normalized: item["normalized"]=True
        accessors.append(item); return len(accessors)-1

    pos_view=add_view(pos.astype("<f4").tobytes(),34962)
    pos_acc=add_accessor(pos_view,5126,len(pos),"VEC3",pos.min(axis=0).tolist(),pos.max(axis=0).tolist())
    nrm_view=add_view(nrm.astype("<f4").tobytes(),34962)
    nrm_acc=add_accessor(nrm_view,5126,len(nrm),"VEC3")
    tex_view=add_view(tex.astype("<f4").tobytes(),34962)
    tex_acc=add_accessor(tex_view,5126,len(tex),"VEC2")
    col_view=add_view(col.astype("<f4").tobytes(),34962)
    col_acc=add_accessor(col_view,5126,len(col),"VEC4")
    primitives=[]
    triangle_count=0
    for group in selected:
        indices=np.asarray([remap[int(index)] for face in group for index in face],dtype=np.uint32)
        if len(indices)==0: continue
        index_view=add_view(indices.astype("<u4").tobytes(),34963)
        index_acc=add_accessor(index_view,5125,len(indices),"SCALAR",int(indices.min()),int(indices.max()))
        primitives.append({"attributes":{"POSITION":pos_acc,"NORMAL":nrm_acc,"TEXCOORD_0":tex_acc,"COLOR_0":col_acc},"indices":index_acc,"material":0,"mode":4})
        triangle_count+=len(indices)//3
    if not primitives: raise ValueError(f"No India GLB primitives generated: {obj_path.name}")

    white=io.BytesIO()
    Image.new("RGBA",(1,1),(255,255,255,255)).save(white,format="PNG")
    white_view=add_view(white.getvalue(),None)
    gltf={"asset":{"version":"2.0","generator":"BlockGun India offline lightmap baker"},
          "scene":0,"scenes":[{"nodes":[0]}],"nodes":[{"mesh":0}],
          "meshes":[{"primitives":primitives}],
          "images":[{"bufferView":white_view,"mimeType":"image/png"}],
          "textures":[{"source":0}],
          "materials":[{"name":"India baked lightmap vertex colors","pbrMetallicRoughness":{"baseColorFactor":[1.0,1.0,1.0,1.0],"baseColorTexture":{"index":0},"metallicFactor":0.0,"roughnessFactor":1.0}}],
          "buffers":[{"byteLength":len(binary)}],"bufferViews":views,"accessors":accessors}
    json_chunk=json.dumps(gltf,separators=(",",":"),ensure_ascii=False).encode("utf-8")
    while len(json_chunk)%4: json_chunk+=b" "
    while len(binary)%4: binary.append(0)
    total=12+8+len(json_chunk)+8+len(binary)
    with output_path.open("wb") as out:
        out.write(struct.pack("<4sII",b"glTF",2,total))
        out.write(struct.pack("<I4s",len(json_chunk),b"JSON")); out.write(json_chunk)
        out.write(struct.pack("<I4s",len(binary),b"BIN\x00")); out.write(binary)
    print(f"INDIA_LIGHTMAP_GLB_OK mesh={obj_path.name} vertices={len(used)} triangles={triangle_count} primitives={len(primitives)} lightmap={lightmap_path.name} output={output_path.name}")
    return {"file":output_path.name,"vertices":len(used),"triangles":triangle_count,"primitives":len(primitives)}


def main():
    data_dir=PROJECT/"data"; meshes=PROJECT/"assets"/"meshes"; textures=PROJECT/"assets"/"textures"
    combat_assets=PROJECT/"assets"/"combat_source"
    reference_dir=PROJECT/"reference"
    for p in (data_dir,meshes,textures,combat_assets,reference_dir): p.mkdir(parents=True,exist_ok=True)
    source_assets=pathlib.Path("unity_audit")/"source_assets"
    if not source_assets.is_dir():
        raise SystemExit("Recovered gameplay asset library missing: "+str(source_assets))
    shutil.copytree(source_assets,combat_assets,dirs_exist_ok=True)
    combat_files=list(combat_assets.rglob("*"))
    required=[
        combat_assets/"meshes"/"sk_char_sold_male_01_7088991893364766669.obj",
        combat_assets/"meshes"/"UMP_45_2.obj",
        combat_assets/"textures"/"SimpleMilitary_Soldier01_Black_-6561600483854028127.png",
        combat_assets/"textures"/"UMP_45_Diffuse_-7805003812694618604.png"
    ]
    missing_required=[str(p) for p in required if not p.is_file()]
    if missing_required:
        raise SystemExit("Required original combat assets missing: "+", ".join(missing_required))
    shutil.copytree(pathlib.Path("combat"),PROJECT/"combat",dirs_exist_ok=True)
    for ref_name in ("source_scripts","UNITY_ANIMATION_DATA.json","UNITY_ANIMATOR_DATA.json","UNITY_SKINNING_DATA.json","GAMEPLAY_ASSET_LIBRARY.csv"):
        source=pathlib.Path("unity_audit")/ref_name
        if source.is_dir():
            shutil.copytree(source,reference_dir/"unity_scripts",dirs_exist_ok=True)
        elif source.is_file():
            shutil.copy2(source,reference_dir/source.name)
    print("COMBAT_SOURCE_ASSETS",sum(1 for p in combat_files if p.is_file()))
    # A real app icon prevents Godot's Android exporter from emitting the
    # missing-project-icon error on every build.
    icon=Image.new("RGBA",(512,512),(8,18,32,255)); draw=ImageDraw.Draw(icon)
    draw.rounded_rectangle((36,36,476,476),radius=92,fill=(12,43,68,255),outline=(54,190,235,255),width=18)
    draw.polygon([(125,365),(195,125),(270,125),(387,365),(302,365),(278,300),(213,300),(190,365)],fill=(230,245,250,255))
    draw.rectangle((228,235,263,270),fill=(54,190,235,255))
    icon.save(PROJECT/"icon.png")
    all_meshes=set(); all_textures=set(); catalog=[]
    for mapid in MAPS:
        path=ROOT/"maps"/(mapid+".json")
        if not path.exists(): raise SystemExit("Manifest missing: "+str(path))
        d=json.loads(path.read_text(encoding="utf-8")); copied=set(); tex=set(); missing=[]
        india_lightmap_bakes=[]
        def walk(n):
            meshpath=""; colpath=""; mats=[]; batch=None; lightmap_index=None
            for comp in n.get("components",[]):
                typ=comp.get("type","")
                if typ in ("MeshFilter","SkinnedMeshRenderer"):
                    for ref in comp.get("references",[]):
                        if ref.get("field")=="m_Mesh": meshpath=ref.get("exported_obj") or meshpath
                elif typ=="MeshCollider":
                    for ref in comp.get("references",[]):
                        if ref.get("field")=="m_Mesh": colpath=ref.get("exported_obj") or colpath
                elif typ=="MeshRenderer":
                    mats=comp.get("material_resources",[])
                    batch=comp.get("static_batch_info")
                    lightmap_index=comp.get("m_LightmapIndex")
                for material in comp.get("material_resources",[]):
                    for texture in material.get("textures",[]):
                        png=texture.get("exported_png")
                        if png:
                            src=ROOT/png
                            original_name=pathlib.Path(png).name
                            india_atlas=(mapid=="lvl_india" and original_name=="sharedassets1.assets__65__t_atlas_environment.png")
                            output_name=("india_detail_"+original_name) if india_atlas else original_name
                            dst=textures/output_name
                            if src.exists():
                                if dst.name not in all_textures:
                                    if india_atlas: enhance_india_atlas(src,dst)
                                    else: shutil.copy2(src,dst)
                                    all_textures.add(dst.name)
                                if india_atlas:
                                    texture["exported_png"]=output_name
                                tex.add(dst.name)
                            else: missing.append(png)
            def copy_mesh(obj,kind):
                if not obj: return ""
                src=ROOT/obj
                if not src.exists():
                    missing.append(obj); return ""
                base=pathlib.Path(obj).name
                first=int((batch or {}).get("first_sub_mesh") or 0)
                count=int((batch or {}).get("sub_mesh_count") or 0)
                if kind=="render" and count>0:
                    tid=str(n.get("transform_path_id",n.get("name","node")))
                    dst=meshes/f"{mapid}_{tid}_{base}"
                    if not dst.exists(): slice_obj(src,dst,first,count)
                else:
                    dst=meshes/base
                    if dst.name not in all_meshes: shutil.copy2(src,dst)
                all_meshes.add(dst.name); copied.add(dst.name)
                return dst.name
            n["godot_render_obj"]=copy_mesh(meshpath or colpath,"render")
            static_batched=bool(batch and int(batch.get("sub_mesh_count") or 0)>0)
            # When a static-batched renderer and MeshCollider reference the same
            # combined Unity mesh, both must use the same sliced world-space OBJ.
            # Reusing the full collider mesh under the original transform makes
            # one map collider cover unrelated geometry and trap the player.
            if static_batched and colpath and colpath==meshpath:
                n["godot_collider_obj"]=n["godot_render_obj"]
                n["godot_static_batched_collider"]=True
            else:
                n["godot_collider_obj"]=copy_mesh(colpath,"collider")
                n["godot_static_batched_collider"]=False
            # Bake India's original Unity lightmap offline into a dedicated
            # atlas copy for each renderer. This avoids runtime shaders and
            # prevents different overlapping UV islands from contaminating each other.
            if mapid=="lvl_india" and lightmap_index is not None and meshpath:
                lm_index=int(lightmap_index)
                lm_names={
                    0:"sharedassets7.assets__3__lvl_gameplay_india_LM0_final.png",
                    1:"sharedassets7.assets__4__lvl_gameplay_india_LMA1_final.png"
                }
                lightmap_path=ROOT/"exported_textures"/lm_names.get(lm_index,"")
                uv_name=pathlib.Path(meshpath).stem+".uv.json"
                uv_path=ROOT/"uv_channels"/uv_name
                source_obj=ROOT/meshpath
                if lm_index not in lm_names or not lightmap_path.exists() or not uv_path.exists() or not source_obj.exists():
                    raise SystemExit(f"India lightmap inputs missing for {n.get('name')}: index={lm_index}, mesh={meshpath}")
                first=int((batch or {}).get("first_sub_mesh") or 0)
                count=int((batch or {}).get("sub_mesh_count") or 0)
                tid=str(n.get("transform_path_id",n.get("name","node")))
                glb_name=f"india_lightmapped_{tid}.glb"
                glb_path=meshes/glb_name
                result=build_india_lightmapped_glb(source_obj,uv_path,lightmap_path,glb_path,first,count)
                n["godot_render_obj"]=glb_name
                n["godot_lightmap_vertex_colors"]=True
                # GLB primitives are sliced from the original Unity static-batch
                # submesh range. Preserve the original material-array offset so
                # each surface receives its matching Unity material, not mats[0].
                n["godot_material_start_index"]=first if count>0 else 0
                all_meshes.add(glb_name); copied.add(glb_name)
                india_lightmap_bakes.append({"node":n.get("name"),"lightmap_index":lm_index,**result})
            n["godot_materials"]=mats
            # Mirror the exact per-axis correction applied to CollisionShape3D
            # so geometry-based stair probes use the same world dimensions.
            render_name=n.get("godot_render_obj","")
            collider_name=n.get("godot_collider_obj","")
            visual_size=obj_size(meshes/render_name) if render_name and not render_name.endswith(".glb") else obj_size(ROOT/meshpath) if meshpath else [0.0,0.0,0.0]
            collider_size=obj_size(meshes/collider_name) if collider_name else [0.0,0.0,0.0]
            node_scale=n.get("scale") or {}
            effective_collider_size=[collider_size[i]*abs(float(node_scale.get(key,1.0) or 1.0)) for i,key in enumerate(("x","y","z"))]
            correction=[1.0,1.0,1.0]
            for axis in range(3):
                if visual_size[axis]>0.02 and effective_collider_size[axis]>visual_size[axis]*4.0:
                    correction[axis]=visual_size[axis]/effective_collider_size[axis]
            n["godot_collider_correction"]={"x":correction[0],"y":correction[1],"z":correction[2]}
            # Unity static-batched OBJ vertices are already in scene/world space.
            # Their visuals and matching colliders are attached to the map root
            # rather than applying the GameObject transform a second time.
            n["godot_static_batched"]=static_batched
            for ch in n.get("children",[]): walk(ch)
        walk(d["root"])
        (data_dir/(mapid+".json")).write_text(json.dumps(d,ensure_ascii=False),encoding="utf-8")
        catalog.append({"id":mapid,"name":names[mapid],"nodes":d.get("node_count",0),"meshes":len(copied),"textures":len(tex),"missing":len(missing),"india_lightmap_bakes":india_lightmap_bakes})
    (data_dir/"maps.json").write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding="utf-8")
    (PROJECT/"project.godot").write_text('''config_version=5
[application]
config/name="Block Gun - Mapas Recuperados"
config/icon="res://icon.png"
run/main_scene="res://main.tscn"
[display]
window/size/viewport_width=1280
window/size/viewport_height=720
window/stretch/mode="canvas_items"
[rendering]
renderer/rendering_method="gl_compatibility"
renderer/rendering_method.mobile="gl_compatibility"
textures/vram_compression/import_etc2_astc=true
environment/defaults/default_clear_color=Color(0.055, 0.075, 0.095, 1)
''',encoding="utf-8")
    (PROJECT/"export_presets.cfg").write_text("""[preset.0]
name="Android"
platform="Android"
runnable=true
dedicated_server=false
custom_features=""
export_filter="all_resources"
include_filter=""
exclude_filter="reference/*"
export_path="build/BlockGunFlorestaCombat.apk"
encryption_include_filters=""
encryption_exclude_filters=""
encrypt_pck=false
encrypt_directory=false

[preset.0.options]
custom_template/debug=""
custom_template/release=""
gradle_build/use_gradle_build=false
gradle_build/gradle_build_directory=""
gradle_build/android_source_template=""
gradle_build/compress_native_libraries=false
keystore/debug="/home/runner/.android/debug.keystore"
keystore/debug_user="androiddebugkey"
keystore/debug_password="android"
keystore/release=""
keystore/release_user=""
keystore/release_password=""
architectures/armeabi-v7a=false
architectures/arm64-v8a=true
architectures/x86=false
architectures/x86_64=false
version/code=1
version/name="1.0"
package/unique_name="com.pedra12.blockgunbattle"
package/name="Block Gun - Combate Floresta"
package/signed=true
package/app_category=2
screen/immersive_mode=true
""",encoding="utf-8")
    (PROJECT/"main.tscn").write_text('[gd_scene load_steps=2 format=3]\n\n[ext_resource type="Script" path="res://main.gd" id="1"]\n\n[node name="BlockGunMaps" type="Node3D"]\nscript = ExtResource("1")\n',encoding="utf-8")
    gd=r'''extends Node3D
const MAPS=["lvl_baghdad","lvl_assault","lvl_middle_east","lvl_resort","lvl_forest","lvl_house","lvl_india","lvl_rome","lvl_deluxe_fest"]
const TITLES=["Baghdad","Assalto","Oriente Medio","Resort","Floresta","Casa","India","Roma","Festival Deluxe"]
var world:Node3D
var menu:Control
var home_panel:PanelContainer
var selection_panel:PanelContainer
var tutorial_panel:PanelContainer
var map_actions:HBoxContainer
var camera_pivot:Node3D
var camera:Camera3D
var camera_distance:float=80.0
var touch_points:Dictionary={}
var pinch_distance:float=0.0
var dragging_mouse:bool=false
var map_label:Label
var walk_mode:=false
var player:CharacterBody3D
var walk_camera:Camera3D
var move_touch_id:=-1
var look_touch_id:=-1
var move_origin:=Vector2.ZERO
var move_vector:=Vector2.ZERO
var walk_yaw:=0.0
var walk_pitch:=0.0
var jump_button:Button
var combat_session:Node3D
func _ready():
    _lighting()
    _make_menu()
    if OS.get_cmdline_user_args().has("--audit-all-maps"):
        call_deferred("_audit_all_maps")
        return
    # Always create a real 3D scene before showing the front end.
    _load_map("lvl_forest","Floresta")
    _show_home()
    print("BLOCKGUN_BOOT_OK")
    print("BLOCKGUN_MAPS_READY count=",MAPS.size())
    if OS.get_cmdline_user_args().has("--audit-combat"):
        call_deferred("_run_combat_audit")
        return
func _make_menu():
    var layer=CanvasLayer.new()
    layer.layer=10
    add_child(layer)
    menu=Control.new()
    menu.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    menu.mouse_filter=Control.MOUSE_FILTER_IGNORE
    layer.add_child(menu)

    home_panel=PanelContainer.new()
    home_panel.position=Vector2(36,64)
    home_panel.size=Vector2(390,470)
    var home_style=StyleBoxFlat.new()
    home_style.bg_color=Color(0.025,0.045,0.075,0.94)
    home_style.border_color=Color(0.12,0.58,0.82,1)
    home_style.set_border_width_all(2)
    home_style.set_corner_radius_all(12)
    home_panel.add_theme_stylebox_override("panel",home_style)
    menu.add_child(home_panel)
    var home_box=VBoxContainer.new()
    home_box.add_theme_constant_override("separation",14)
    home_panel.add_child(home_box)
    var title=Label.new()
    title.text="BLOCK GUN"
    title.horizontal_alignment=HORIZONTAL_ALIGNMENT_CENTER
    title.add_theme_font_size_override("font_size",42)
    title.add_theme_color_override("font_color",Color(0.9,0.96,1,1))
    home_box.add_child(title)
    var subtitle=Label.new()
    subtitle.text="OPERAÇÃO ZERO  |  PROJETO INDEPENDENTE"
    subtitle.horizontal_alignment=HORIZONTAL_ALIGNMENT_CENTER
    subtitle.add_theme_font_size_override("font_size",12)
    subtitle.add_theme_color_override("font_color",Color(0.3,0.75,0.95,1))
    home_box.add_child(subtitle)
    var description=Label.new()
    description.text="Prepare-se para entrar no campo de batalha. Explore os cenários recuperados e acompanhe a evolução do projeto."
    description.autowrap_mode=TextServer.AUTOWRAP_WORD_SMART
    description.custom_minimum_size.y=62
    home_box.add_child(description)
    var play=Button.new()
    play.text="JOGAR"
    play.custom_minimum_size=Vector2(0,62)
    play.add_theme_font_size_override("font_size",24)
    play.pressed.connect(_show_map_select)
    home_box.add_child(play)
    var battle=Button.new()
    battle.text="INICIAR BATALHA | FLORESTA"
    battle.custom_minimum_size=Vector2(0,58)
    battle.add_theme_font_size_override("font_size",19)
    battle.pressed.connect(_start_combat)
    home_box.add_child(battle)
    var tutorial=Button.new()
    tutorial.text="COMO JOGAR"
    tutorial.custom_minimum_size.y=48
    tutorial.pressed.connect(_show_tutorial)
    home_box.add_child(tutorial)
    var maps=Button.new()
    maps.text="SELECIONAR CENÁRIO"
    maps.custom_minimum_size.y=48
    maps.pressed.connect(_show_map_select)
    home_box.add_child(maps)
    var version=Label.new()
    version.text="VERSÃO DE DESENVOLVIMENTO  |  BUILD EXPERIMENTAL"
    version.horizontal_alignment=HORIZONTAL_ALIGNMENT_CENTER
    version.add_theme_font_size_override("font_size",10)
    home_box.add_child(version)

    selection_panel=PanelContainer.new()
    selection_panel.position=Vector2(36,40)
    selection_panel.size=Vector2(320,620)
    selection_panel.visible=false
    menu.add_child(selection_panel)
    var select_box=VBoxContainer.new()
    select_box.add_theme_constant_override("separation",5)
    selection_panel.add_child(select_box)
    var select_title=Label.new()
    select_title.text="SELECIONE O CENÁRIO"
    select_title.add_theme_font_size_override("font_size",22)
    select_box.add_child(select_title)
    for i in range(MAPS.size()):
        var button=Button.new()
        button.text=TITLES[i]
        button.custom_minimum_size.y=43
        button.pressed.connect(_load_map.bind(MAPS[i],TITLES[i]))
        select_box.add_child(button)
    var select_info=Label.new()
    select_info.text="Escolha um cenário para abrir a prévia 3D."
    select_info.autowrap_mode=TextServer.AUTOWRAP_WORD_SMART
    select_box.add_child(select_info)
    var back=Button.new()
    back.text="VOLTAR AO MENU"
    back.custom_minimum_size.y=44
    back.pressed.connect(_show_home)
    select_box.add_child(back)

    tutorial_panel=PanelContainer.new()
    tutorial_panel.position=Vector2(36,64)
    tutorial_panel.size=Vector2(410,470)
    tutorial_panel.visible=false
    menu.add_child(tutorial_panel)
    var tutorial_box=VBoxContainer.new()
    tutorial_box.add_theme_constant_override("separation",12)
    tutorial_panel.add_child(tutorial_box)
    var tutorial_title=Label.new()
    tutorial_title.text="COMO JOGAR"
    tutorial_title.add_theme_font_size_override("font_size",28)
    tutorial_box.add_child(tutorial_title)
    var tutorial_text=Label.new()
    tutorial_text.text="1. Toque em JOGAR e escolha um cenário.\n\n2. Na prévia, arraste para girar a câmera e use dois dedos para aproximar.\n\n3. Toque em ENTRAR NO MAPA para explorar em primeira pessoa.\n\n4. No modo exploração, arraste no lado esquerdo para andar, no lado direito para olhar e use PULAR para saltar.\n\nO combate, os bots e as partidas completas ainda estão em desenvolvimento."
    tutorial_text.autowrap_mode=TextServer.AUTOWRAP_WORD_SMART
    tutorial_text.size_flags_vertical=Control.SIZE_EXPAND_FILL
    tutorial_box.add_child(tutorial_text)
    var tutorial_back=Button.new()
    tutorial_back.text="VOLTAR"
    tutorial_back.custom_minimum_size.y=48
    tutorial_back.pressed.connect(_show_home)
    tutorial_box.add_child(tutorial_back)

    map_label=Label.new()
    map_label.position=Vector2(380,18)
    map_label.add_theme_font_size_override("font_size",20)
    menu.add_child(map_label)
    map_actions=HBoxContainer.new()
    map_actions.position=Vector2(380,54)
    map_actions.add_theme_constant_override("separation",8)
    menu.add_child(map_actions)
    var reset=Button.new()
    reset.text="REENQUADRAR"
    reset.custom_minimum_size=Vector2(150,44)
    reset.pressed.connect(_fit_camera)
    map_actions.add_child(reset)
    var explore=Button.new()
    explore.text="ENTRAR NO MAPA"
    explore.custom_minimum_size=Vector2(170,44)
    explore.pressed.connect(_toggle_walk_mode)
    map_actions.add_child(explore)
    var map_menu=Button.new()
    map_menu.text="CENÁRIOS"
    map_menu.custom_minimum_size=Vector2(120,44)
    map_menu.pressed.connect(_show_map_select)
    map_actions.add_child(map_menu)
    var main_menu=Button.new()
    main_menu.text="MENU"
    main_menu.custom_minimum_size=Vector2(90,44)
    main_menu.pressed.connect(_show_home)
    map_actions.add_child(main_menu)
    map_label.visible=false
    map_actions.visible=false

    jump_button=Button.new()
    jump_button.text="PULAR"
    jump_button.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_RIGHT)
    jump_button.position=Vector2(-150,-130)
    jump_button.custom_minimum_size=Vector2(120,64)
    jump_button.visible=false
    jump_button.pressed.connect(_request_jump)
    menu.add_child(jump_button)
func _start_combat():
    if is_instance_valid(combat_session) or not is_instance_valid(world):
        return
    home_panel.visible=false
    selection_panel.visible=false
    tutorial_panel.visible=false
    map_label.visible=false
    map_actions.visible=false
    combat_session=Node3D.new()
    combat_session.name="FlorestaCombatSession"
    combat_session.set_script(load("res://combat/combat_mode.gd"))
    add_child(combat_session)
    combat_session.call_deferred("begin",world,Callable(self,"_end_combat"))
func _end_combat():
    if is_instance_valid(combat_session):
        combat_session.queue_free()
    combat_session=null
    if is_instance_valid(camera):
        camera.current=true
    _show_home()
func _run_combat_audit():
    _start_combat()
    await get_tree().create_timer(2.5).timeout
    var bot_count=world.find_children("BotSoldier_*","CharacterBody3D",true,false).size() if is_instance_valid(world) else 0
    var combat_player=combat_session.get("player") if is_instance_valid(combat_session) else null
    if is_instance_valid(combat_player) and bot_count>0:
        print("BLOCKGUN_COMBAT_AUDIT_OK bots=",bot_count)
        get_tree().quit(0)
    else:
        push_error("BLOCKGUN_COMBAT_AUDIT_FAILED player=",is_instance_valid(combat_player)," bots=",bot_count)
        get_tree().quit(1)
func _show_home():
    _stop_walk_mode()
    home_panel.visible=true
    selection_panel.visible=false
    tutorial_panel.visible=false
    map_label.visible=false
    map_actions.visible=false
func _show_map_select():
    _stop_walk_mode()
    home_panel.visible=false
    selection_panel.visible=true
    tutorial_panel.visible=false
    map_label.visible=false
    map_actions.visible=false
func _show_tutorial():
    home_panel.visible=false
    selection_panel.visible=false
    tutorial_panel.visible=true
    map_label.visible=false
    map_actions.visible=false
func _load_map(id:String,title:String):
    _stop_walk_mode()
    if world:
        world.queue_free()
    world=Node3D.new()
    world.name="Map_"+id
    add_child(world)
    var f=FileAccess.open("res://data/"+id+".json",FileAccess.READ)
    if f==null:
        push_error("Manifest missing "+id)
        return
    var d=JSON.parse_string(f.get_as_text())
    if not d is Dictionary or not d.has("root"):
        push_error("Invalid map manifest "+id)
        return
    _build_node(d.root,world,id)
    _create_camera()
    _fit_camera()
    home_panel.visible=false
    selection_panel.visible=false
    tutorial_panel.visible=false
    map_label.visible=true
    map_actions.visible=true
    map_label.text="CENÁRIO: "+title.to_upper()+" | PRÉVIA 3D"
    print("MAP_LOADED ",id," nodes=",d.get("node_count",0)," meshes=",_count_meshes(world))
func _build_node(d:Dictionary,parent:Node3D,map_id:String):
    var n=Node3D.new()
    n.name=String(d.get("name","Recovered")).replace("/","_")
    parent.add_child(n)
    n.position=_v(d.get("position",{}),Vector3.ZERO)
    # Unity's static-batched meshes are exported in world space with X already
    # reflected for Godot. Non-static meshes still use their original local
    # transforms. Apply the X-origin reflection only to maps where the recovered
    # scene contains a non-static mesh that must align with its static geometry:
    # Rome, Forest and India. The other recovered maps are fully static-batched
    # and must keep their original node transforms.
    if (map_id=="lvl_rome" or map_id=="lvl_forest" or map_id=="lvl_india") and not bool(d.get("godot_static_batched",false)):
        n.position.x=-n.position.x
    n.scale=_v(d.get("scale",{}),Vector3.ONE)
    var q=d.get("rotation",{})
    n.quaternion=Quaternion(float(q.get("x",0)),float(q.get("y",0)),float(q.get("z",0)),float(q.get("w",1))).normalized()
    var renderpath=String(d.get("godot_render_obj",""))
    var colpath=String(d.get("godot_collider_obj",""))
    var mats=d.get("godot_materials",[])
    if renderpath=="":
        renderpath=_ref_by_type(d.get("components",[]),"MeshFilter","m_Mesh")
    if renderpath=="":
        renderpath=colpath
    var render_mesh:Mesh=null
    if renderpath!="":
        var mesh_resource=load("res://assets/meshes/"+renderpath.get_file())
        if mesh_resource is Mesh:
            render_mesh=mesh_resource as Mesh
        elif mesh_resource is PackedScene:
            var imported_scene=(mesh_resource as PackedScene).instantiate()
            var imported_instances=imported_scene.find_children("*","MeshInstance3D",true,false)
            if not imported_instances.is_empty():
                var imported_instance=imported_instances[0] as MeshInstance3D
                if imported_instance:
                    render_mesh=imported_instance.mesh
            imported_scene.free()
        if render_mesh:
            var mi=MeshInstance3D.new()
            mi.mesh=render_mesh
            var visual_parent:Node3D=parent if bool(d.get("godot_static_batched",false)) else n
            visual_parent.add_child(mi)
            for surface_index in range(mi.mesh.get_surface_count()):
                if mats.size()>0:
                    var material_start=int(d.get("godot_material_start_index",0))
                    var material_index=min(material_start+surface_index,mats.size()-1)
                    var surface_material=_mat([mats[material_index]],String(d.get("name","")))
                    if surface_material:
                        if bool(d.get("godot_lightmap_vertex_colors",false)) and surface_material is StandardMaterial3D:
                            (surface_material as StandardMaterial3D).vertex_color_use_as_albedo=true
                        mi.set_surface_override_material(surface_index,surface_material)
    # Only use recovered Unity MeshCollider data, not every visible render mesh.
    # Treating trees, water, roofs and static-batched scenery as solid walls was
    # the main source of blocked movement and impossible house entrances.
    var collision_mesh:Mesh=null
    # Static-batched renderer geometry is exported as a sliced world-space mesh.
    # A separate Unity MeshCollider reference can still point to the unsliced
    # combined source mesh; using it with the GameObject transform traps players.
    var static_batched_collision=bool(d.get("godot_static_batched_collider",false)) and render_mesh!=null and colpath!=""
    if static_batched_collision:
        collision_mesh=render_mesh
    elif colpath!="":
        collision_mesh=load("res://assets/meshes/"+colpath.get_file()) as Mesh
    var object_name=String(d.get("name","")).to_lower()
    # Keep decorative background meshes visual-only. The playable ground in
    # Rome and Forest comes from the original Unity collider meshes; do not turn
    # giant backdrop geometry into an artificial floor.
    if collision_mesh==null and render_mesh and colpath=="":
        var excluded=["background","alpha","water","foliage","tree","roof"]
        var forbidden=false
        for token in excluded:
            if object_name.contains(token): forbidden=true
        var bounds=render_mesh.get_aabb().size
        var horizontal=maxf(bounds.x,bounds.z)
        # India uses a large central terrain mesh without a Unity MeshCollider.
        # It is the main walkable surface, not decorative scenery.
        if map_id=="lvl_india" and object_name=="umsh_india_s2":
            collision_mesh=render_mesh
        elif not forbidden and horizontal>8.0 and bounds.y< horizontal*0.16:
            collision_mesh=render_mesh
            print("FALLBACK_COLLIDER map=",map_id," node=",n.name," bounds=",bounds," status=AUTOGENERATED")
    # Static-batched render meshes are already in world coordinates. This
    # applies both to Unity MeshColliders that reuse the sliced render mesh and
    # to safe fallback floor meshes. Parenting them under the transformed node
    # applies the Unity transform twice and creates invisible barriers/holes.
    var collision_world_space=bool(d.get("godot_static_batched",false)) and collision_mesh!=null and collision_mesh==render_mesh
    if collision_mesh:
        var body=StaticBody3D.new()
        body.name="RecoveredUnityCollider_"+n.name
        body.collision_layer=1
        body.collision_mask=1
        var cs=CollisionShape3D.new()
        cs.name="RecoveredTriangleCollision"
        cs.shape=collision_mesh.create_trimesh_shape()
        # Some shared-asset collider meshes are exported in centimeters while
        # their scene render meshes are already in meters. Normalize per axis.
        if render_mesh:
            var visual_size=render_mesh.get_aabb().size
            var collider_size=collision_mesh.get_aabb().size
            var node_scale=Vector3(absf(n.scale.x),absf(n.scale.y),absf(n.scale.z))
            var effective_collider_size=collider_size*node_scale
            var correction=Vector3.ONE
            for axis in range(3):
                if visual_size[axis]>0.02 and effective_collider_size[axis]>visual_size[axis]*4.0:
                    correction[axis]=visual_size[axis]/effective_collider_size[axis]
            cs.scale=correction
        body.add_child(cs)
        var collider_parent:Node3D=parent if collision_world_space else n
        collider_parent.add_child(body)
        if not collision_world_space and bool(d.get("godot_static_batched",false)):
            # A static-batched visual is already in reflected world X, while
            # its separate Unity MeshCollider is still local to the object.
            # Mirror the node origin only for this case. Non-static-batched
            # visuals and colliders share the same local transform and need no
            # offset at all.
            if absf(n.scale.x)>0.0001:
                body.position.x=(-2.0*n.position.x)/n.scale.x
    for ch in d.get("children",[]):
        _build_node(ch,n,map_id)
func _ref(c:Dictionary,key:String)->String:
    for r in c.get("references",[]):
        if String(r.get("field",""))==key:
            return String(r.get("exported_obj",""))
    return ""
func _ref_by_type(components:Array,component_type:String,key:String)->String:
    for component in components:
        if String(component.get("type",""))==component_type:
            var path=_ref(component,key)
            if path!="": return path
    return ""
func _v(x:Variant,fb:Vector3)->Vector3:
    if x is Dictionary:
        return Vector3(float(x.get("x",fb.x)),float(x.get("y",fb.y)),float(x.get("z",fb.z)))
    return fb
func _mat(ms:Array,object_name:String="",india_detail:bool=false)->Material:
    if ms.is_empty(): return null
    var m=ms[0]
    var material_name=String(m.get("name","")).to_lower()
    var object_lower=object_name.to_lower()
    var sm=StandardMaterial3D.new()
    sm.roughness=0.88
    for t in m.get("textures",[]):
        var p=String(t.get("exported_png",""))
        if p!="":
            var tx=load("res://assets/textures/"+p.get_file()) as Texture2D
            if tx:
                sm.albedo_texture=tx
                break
    if material_name.contains("alpha") or object_lower.contains("alpha"):
        sm.transparency=BaseMaterial3D.TRANSPARENCY_ALPHA_SCISSOR
        sm.alpha_scissor_threshold=0.42
        sm.cull_mode=BaseMaterial3D.CULL_DISABLED
    if material_name.contains("water") or object_lower.contains("water"):
        sm.transparency=BaseMaterial3D.TRANSPARENCY_ALPHA
        sm.albedo_color=Color(0.28,0.58,0.72,0.58)
        sm.roughness=0.16
        sm.cull_mode=BaseMaterial3D.CULL_DISABLED
    # All map materials use preprocessed textures; no procedural India shader at runtime.
    return sm
func _create_camera():
    camera_pivot=Node3D.new()
    camera_pivot.name="ExplorerCameraPivot"
    world.add_child(camera_pivot)
    camera=Camera3D.new()
    camera.name="ExplorerCamera"
    camera.fov=65.0
    camera_pivot.add_child(camera)
    camera.current=true
func _fit_camera():
    if not world or not camera_pivot or not camera:
        return
    var found=false
    var bounds=AABB()
    for item in world.find_children("*","MeshInstance3D",true,false):
        var mi=item as MeshInstance3D
        if mi and mi.mesh:
            var transformed=mi.get_aabb() * mi.global_transform
            if not found:
                bounds=transformed
                found=true
            else:
                bounds=bounds.merge(transformed)
    if not found:
        camera_pivot.global_position=world.global_position
        camera_distance=80.0
    else:
        # For the recovered house, the physics collider for sm_house_o1 is
        # intentionally excluded from rendering above; fit to visible geometry.
        camera_pivot.global_position=bounds.get_center()
        var diagonal=maxf(bounds.size.length(),4.0)
        var half_fov=deg_to_rad(camera.fov*0.5)
        camera_distance=maxf(12.0,(diagonal*0.62)/maxf(tan(half_fov),0.1))
        camera_distance=clampf(camera_distance,12.0,5000.0)
        camera.far=maxf(10000.0,camera_distance*8.0)
    camera_pivot.rotation=Vector3(deg_to_rad(-32.0),deg_to_rad(35.0),0)
    camera.position=Vector3(0,0,camera_distance)
    print("CAMERA_FIT distance=",camera_distance," bounds_found=",found," bounds=",bounds)
func _count_meshes(root:Node)->int:
    var total=0
    for item in root.find_children("*","MeshInstance3D",true,false):
        if item is MeshInstance3D and item.mesh:
            total+=1
    return total
func _count_colliders(root:Node)->int:
    var total=0
    for item in root.find_children("*","CollisionShape3D",true,false):
        if item is CollisionShape3D and item.shape:
            total+=1
    return total
func _audit_all_maps():
    var failed=false
    for index in range(MAPS.size()):
        _load_map(MAPS[index],TITLES[index])
        await get_tree().process_frame
        var mesh_count=_count_meshes(world) if is_instance_valid(world) else 0
        var collider_count=_count_colliders(world) if is_instance_valid(world) else 0
        var manifest=JSON.parse_string(FileAccess.get_file_as_string("res://data/"+MAPS[index]+".json"))
        var expected_meshes=maxi(0,int(manifest.get("node_count",1))-1) if manifest is Dictionary else 0
        var node_count=world.get_child_count() if is_instance_valid(world) else 0
        print("MAP_AUDIT id=",MAPS[index]," meshes=",mesh_count," expected_meshes=",expected_meshes," colliders=",collider_count," root_children=",node_count)
        if MAPS[index]=="lvl_assault" and is_instance_valid(world):
            var diagnostic_count=0
            for collider_node in world.find_children("*","StaticBody3D",true,false):
                if diagnostic_count>=12: break
                print("ASSAULT_COLLIDER_DIAGNOSTIC name=",collider_node.name," position=",collider_node.global_position," scale=",collider_node.global_transform.basis.get_scale()," shapes=",collider_node.get_child_count())
                diagnostic_count+=1
        if mesh_count<expected_meshes or collider_count==0:
            failed=true
        await _start_walk_mode()
        var grounded=false
        for frame in range(90):
            await get_tree().physics_frame
            if is_instance_valid(player) and player.is_on_floor():
                grounded=true
                break
        var moved=false
        var max_displacement=0.0
        if is_instance_valid(player):
            var test_origin=player.global_position
            for direction in [Vector2(0,-1),Vector2(0,1),Vector2(1,0),Vector2(-1,0)]:
                player.global_position=test_origin
                player.velocity=Vector3.ZERO
                move_vector=direction
                for frame in range(60):
                    await get_tree().physics_frame
                var end_position=player.global_position
                var travelled=Vector2(end_position.x-test_origin.x,end_position.z-test_origin.z).length()
                max_displacement=maxf(max_displacement,travelled)
                if travelled>0.50:
                    moved=true
                if MAPS[index]=="lvl_assault":
                    var collision_name="none"
                    if player.get_slide_collision_count()>0:
                        var slide=player.get_slide_collision(0)
                        if slide.get_collider():
                            collision_name=String(slide.get_collider().name)
                    print("ASSAULT_DIRECTION_TEST direction=",direction," start=",test_origin," end=",end_position," velocity=",player.velocity," collisions=",player.get_slide_collision_count()," collider=",collision_name," travelled=",travelled)
            move_vector=Vector2.ZERO
        var stair_routes=manifest.get("stair_route_candidates",[]) if manifest is Dictionary else []
        var tested_stairs=0
        var passed_stairs=0
        for route in stair_routes:
            if not is_instance_valid(player) or not route is Dictionary:
                continue
            var route_start=route.get("start",[])
            var route_end=route.get("end",[])
            if route_start.size()<3 or route_end.size()<3:
                continue
            var start_xz=Vector3(float(route_start[0]),0.0,float(route_start[2]))
            var end_xz=Vector3(float(route_end[0]),0.0,float(route_end[2]))
            var route_delta=end_xz-start_xz
            if route_delta.length()<0.20:
                continue
            print("STAIR_PROBE_TARGET node=",route.get("node","?")," start=",start_xz," end=",end_xz)
            var stair_hit={}
            var probe_used=Vector2.ZERO
            var best_probe_distance=INF
            for ix in range(-4,5):
                for iz in range(-4,5):
                    var offset=Vector2(float(ix)*0.25,float(iz)*0.25)
                    if offset.length()>1.01:
                        continue
                    var probe=start_xz+Vector3(offset.x,0.0,offset.y)
                    var probe_y=float(route_start[1])
                    var stair_query=PhysicsRayQueryParameters3D.create(Vector3(probe.x,probe_y+2.5,probe.z),Vector3(probe.x,probe_y-2.5,probe.z))
                    stair_query.collision_mask=1
                    stair_query.hit_back_faces=true
                    stair_query.exclude=[player.get_rid()]
                    var target_collider_name="RecoveredUnityCollider_"+String(route.get("node",""))
                    for other_collider in world.find_children("*","StaticBody3D",true,false):
                        if String(other_collider.name)!=target_collider_name:
                            stair_query.exclude.append(other_collider.get_rid())
                    var candidate_hit=get_world_3d().direct_space_state.intersect_ray(stair_query)
                    if not candidate_hit.is_empty() and abs(candidate_hit.normal.dot(Vector3.UP))>0.70 and offset.length()<best_probe_distance:
                        stair_hit=candidate_hit
                        probe_used=offset
                        best_probe_distance=offset.length()
            tested_stairs+=1
            if stair_hit.is_empty():
                print("STAIR_ROUTE_AUDIT map=",MAPS[index]," node=",route.get("node","?")," hit=false predicted_start=",start_xz," predicted_end=",end_xz)
                continue
            # A valid ray hit does not guarantee enough room for the full
            # capsule. Search nearby points and accept only a grounded spawn.
            var grounded_at_start=false
            var grounded_hit={}
            var grounded_offset=Vector2.ZERO
            var start_offsets=[Vector2.ZERO,Vector2(0.25,0),Vector2(-0.25,0),Vector2(0,0.25),Vector2(0,-0.25),Vector2(0.35,0.35),Vector2(-0.35,0.35),Vector2(0.35,-0.35),Vector2(-0.35,-0.35),Vector2(0.5,0),Vector2(-0.5,0),Vector2(0,0.5),Vector2(0,-0.5)]
            var target_collider_name="RecoveredUnityCollider_"+String(route.get("node",""))
            for offset in start_offsets:
                var probe=start_xz+Vector3(offset.x,0.0,offset.y)
                var probe_y=float(route_start[1])
                var query=PhysicsRayQueryParameters3D.create(Vector3(probe.x,probe_y+2.5,probe.z),Vector3(probe.x,probe_y-2.5,probe.z))
                query.collision_mask=1
                query.hit_back_faces=true
                query.exclude=[player.get_rid()]
                for other_collider in world.find_children("*","StaticBody3D",true,false):
                    if String(other_collider.name)!=target_collider_name:
                        query.exclude.append(other_collider.get_rid())
                var candidate=get_world_3d().direct_space_state.intersect_ray(query)
                if candidate.is_empty() or candidate.normal.dot(Vector3.UP)<0.70:
                    continue
                player.global_position=candidate.position-Vector3.UP*0.025
                player.velocity=Vector3.ZERO
                for settle_frame in range(3):
                    await get_tree().physics_frame
                if player.is_on_floor():
                    grounded_at_start=true
                    grounded_hit=candidate
                    grounded_offset=offset
                    break
            if not grounded_at_start:
                print("STAIR_ROUTE_AUDIT map=",MAPS[index]," node=",route.get("node","?")," grounded_start=false no_capsule_safe_tread start=",start_xz)
                continue
            stair_hit=grounded_hit
            probe_used=grounded_offset
            var stair_start_y=player.global_position.y
            var saved_stair_yaw=walk_yaw
            var route_points:Array=route.get("waypoints",[])
            if route_points.size()<2:
                route_points=[route_start,route_end]
            for waypoint_index in range(1,route_points.size()):
                var waypoint=route_points[waypoint_index]
                var segment=Vector3(float(waypoint[0])-player.global_position.x,0.0,float(waypoint[2])-player.global_position.z)
                if segment.length()<0.05:
                    continue
                walk_yaw=atan2(-segment.normalized().x,-segment.normalized().z)
                move_vector=Vector2(0,-1)
                var segment_frames=clampi(int(ceil(segment.length()/4.5*60.0))+1,3,30)
                for frame in range(segment_frames):
                    await get_tree().physics_frame
                move_vector=Vector2.ZERO
                for frame in range(2):
                    await get_tree().physics_frame
            move_vector=Vector2.ZERO
            walk_yaw=saved_stair_yaw
            var climb_height=player.global_position.y-stair_start_y
            var passed=grounded_at_start and climb_height>=minf(0.25,float(route.get("rise",0.5))*0.45) and player.is_on_floor()
            print("STAIR_ROUTE_AUDIT map=",MAPS[index]," node=",route.get("node","?")," grounded_start=",grounded_at_start," grounded_end=",player.is_on_floor()," start=",stair_start_y," hit=",stair_hit.position," normal=",stair_hit.normal," probe_offset=",probe_used," route_delta=",route_delta," end=",player.global_position," climb_height=",climb_height," expected_rise=",route.get("rise",0.0)," passed=",passed)
            if passed:
                passed_stairs+=1
        print("STAIR_MAP_AUDIT map=",MAPS[index]," tested=",tested_stairs," passed=",passed_stairs)
        if tested_stairs==0 or passed_stairs==0:
            print("STAIR_AUDIT_WARNING map=",MAPS[index]," tested=",tested_stairs," passed=",passed_stairs," status=UNVERIFIED")
        print("MAP_WALK_AUDIT id=",MAPS[index]," grounded=",grounded," moved=",moved," max_cardinal_displacement=",max_displacement)
        if not grounded or not moved or max_displacement<0.50:
            failed=true
        _stop_walk_mode()
        await get_tree().process_frame
    if failed:
        print("BLOCKGUN_ALL_MAPS_AUDIT_FAILED")
        get_tree().quit(1)
    else:
        print("BLOCKGUN_ALL_MAPS_AUDIT_OK count=",MAPS.size())
        get_tree().quit(0)
func _unhandled_input(event):
    if walk_mode:
        _walk_input(event)
        return
    if event is InputEventScreenTouch:
        if event.pressed:
            touch_points[event.index]=event.position
            if touch_points.size()==2:
                var pts=touch_points.values()
                pinch_distance=pts[0].distance_to(pts[1])
        else:
            touch_points.erase(event.index)
            if touch_points.size()<2:
                pinch_distance=0.0
    elif event is InputEventScreenDrag:
        var old_points=touch_points.duplicate()
        if touch_points.has(event.index):
            touch_points[event.index]=event.position
        if touch_points.size()>=2:
            var pts=touch_points.values()
            var previous=old_points.values()
            var now=pts[0].distance_to(pts[1])
            var before=previous[0].distance_to(previous[1]) if previous.size()>=2 else now
            if before>1.0 and now>1.0:
                camera_distance=clampf(camera_distance*before/now,5.0,5000.0)
                camera.position=Vector3(0,0,camera_distance)
            if previous.size()>=2:
                var old_center=(previous[0]+previous[1])*0.5
                var new_center=(pts[0]+pts[1])*0.5
                _pan(new_center-old_center)
            pinch_distance=now
        elif event.position.x>get_viewport().get_visible_rect().size.x*0.38:
            _orbit(event.relative)
        else:
            _pan(event.relative)
    elif event is InputEventMouseButton:
        if event.button_index==MOUSE_BUTTON_LEFT:
            dragging_mouse=event.pressed
        elif event.pressed and event.button_index==MOUSE_BUTTON_WHEEL_UP:
            _zoom(0.88)
        elif event.pressed and event.button_index==MOUSE_BUTTON_WHEEL_DOWN:
            _zoom(1.14)
    elif event is InputEventMouseMotion and dragging_mouse:
        if event.position.x>get_viewport().get_visible_rect().size.x*0.38:
            _orbit(event.relative)
        else:
            _pan(event.relative)
func _toggle_walk_mode():
    if walk_mode:
        _stop_walk_mode()
    else:
        _start_walk_mode()
func _start_walk_mode():
    if not world or not camera_pivot or not camera:
        return
    walk_mode=true
    camera.current=false
    camera_pivot.visible=false
    player=CharacterBody3D.new()
    player.name="ExplorerPlayer"
    world.add_child(player)
    var capsule=CapsuleShape3D.new()
    capsule.radius=0.32
    capsule.height=1.75
    var collision=CollisionShape3D.new()
    collision.shape=capsule
    collision.position.y=0.9
    player.add_child(collision)
    player.motion_mode=CharacterBody3D.MOTION_MODE_GROUNDED
    player.floor_snap_length=0.72
    player.floor_max_angle=deg_to_rad(55.0)
    player.safe_margin=0.025
    player.max_slides=8
    walk_camera=Camera3D.new()
    walk_camera.position=Vector3(0,1.55,0)
    walk_camera.fov=75.0
    player.add_child(walk_camera)
    walk_camera.current=true
    player.global_position=camera_pivot.global_position+Vector3.UP*20.0
    await get_tree().physics_frame
    if is_instance_valid(player):
        var candidate_points=[camera_pivot.global_position]
        var spawn_reference=camera_pivot.global_position
        # Forest's train crosses the map center. Prefer a known open ground
        # patch away from the train when selecting the initial exploration spawn.
        if world.name=="Map_lvl_forest":
            spawn_reference=Vector3(40.0,-10.0,40.0)
            candidate_points.append(spawn_reference)
        # Probe from actual collider origins too. A map's visual bounding-box
        # center can be over a gap or background mesh rather than its playable floor.
        for collider_node in world.find_children("*","CollisionShape3D",true,false):
            if collider_node is CollisionShape3D and collider_node.shape:
                candidate_points.append(collider_node.global_position)
        var best_found=false
        var best_distance=INF
        var best_clearance=-1
        var best_floor=Vector3.ZERO
        var offsets=[]
        for x in [-8.0,0.0,8.0]:
            for z in [-8.0,0.0,8.0]:
                offsets.append(Vector3(x,0.0,z))
        var test_directions=[Vector3.FORWARD,Vector3.BACK,Vector3.LEFT,Vector3.RIGHT]
        for base_point in candidate_points:
            for offset in offsets:
                var ray_origin=base_point+offset+Vector3.UP*250.0
                var ray_query=PhysicsRayQueryParameters3D.create(ray_origin,ray_origin-Vector3.UP*600.0)
                ray_query.collision_mask=1
                ray_query.exclude=[player.get_rid()]
                var floor_hit=get_world_3d().direct_space_state.intersect_ray(ray_query)
                if floor_hit.is_empty() or floor_hit.normal.y<=0.58:
                    continue
                # The train remains part of the Forest scenery, but it must
                # never be selected as the player's initial ground spawn.
                if world.name=="Map_lvl_forest" and floor_hit.collider and String(floor_hit.collider.name)=="RecoveredUnityCollider_sm_forest_s3":
                    continue
                var candidate_transform=player.global_transform
                candidate_transform.origin=floor_hit.position+Vector3.UP*0.06
                # test_move alone does not reject a body that already starts
                # intersecting a wall/solid mesh. Query the actual capsule volume.
                var overlap_query=PhysicsShapeQueryParameters3D.new()
                overlap_query.shape=capsule
                overlap_query.transform=candidate_transform*collision.transform
                overlap_query.collision_mask=1
                overlap_query.exclude=[player.get_rid()]
                var overlaps=get_world_3d().direct_space_state.intersect_shape(overlap_query,8)
                if not overlaps.is_empty():
                    continue
                var clear_directions=0
                for direction in test_directions:
                    if not player.test_move(candidate_transform,direction*4.5):
                        clear_directions+=1
                var distance=Vector2(floor_hit.position.x-spawn_reference.x,floor_hit.position.z-spawn_reference.z).length()
                if clear_directions>best_clearance or (clear_directions==best_clearance and distance<best_distance):
                    best_clearance=clear_directions
                    best_distance=distance
                    best_floor=floor_hit.position
                    best_found=true
        if best_found:
            player.global_position=best_floor+Vector3.UP*0.06
            print("WALK_SPAWN_SURFACE point=",best_floor," distance_from_center=",best_distance," clear_directions=",best_clearance," capsule_overlaps=0")
        else:
            player.global_position=camera_pivot.global_position+Vector3.UP*8.0
            print("WALK_SPAWN_FALLBACK point=",player.global_position)
    walk_yaw=camera_pivot.rotation.y
    walk_pitch=deg_to_rad(-8.0)
    move_vector=Vector2.ZERO
    move_touch_id=-1
    look_touch_id=-1
    jump_button.visible=true
    map_label.text="MODO EXPLORAÇÃO | ESQUERDA: ANDAR | DIREITA: OLHAR"
    print("WALK_MODE_STARTED position=",player.global_position)
func _stop_walk_mode():
    if not walk_mode:
        return
    walk_mode=false
    if is_instance_valid(player):
        player.queue_free()
    player=null
    walk_camera=null
    if camera and is_instance_valid(camera):
        camera.current=true
    if camera_pivot and is_instance_valid(camera_pivot):
        camera_pivot.visible=true
    if jump_button:
        jump_button.visible=false
    move_vector=Vector2.ZERO
    map_label.text="CENÁRIO: "+String(world.name).replace("Map_","").to_upper()+" | PRÉVIA 3D"
func _request_jump():
    if walk_mode and is_instance_valid(player) and player.is_on_floor():
        player.velocity.y=6.0
func _walk_input(event):
    var screen=get_viewport().get_visible_rect().size
    if event is InputEventScreenTouch:
        if event.pressed:
            if event.position.x<screen.x*0.48 and move_touch_id==-1:
                move_touch_id=event.index
                move_origin=event.position
                move_vector=Vector2.ZERO
            elif event.position.x>=screen.x*0.48 and look_touch_id==-1:
                look_touch_id=event.index
        else:
            if event.index==move_touch_id:
                move_touch_id=-1
                move_vector=Vector2.ZERO
            if event.index==look_touch_id:
                look_touch_id=-1
    elif event is InputEventScreenDrag:
        if event.index==move_touch_id:
            var offset=event.position-move_origin
            move_vector=Vector2(clampf(offset.x/75.0,-1.0,1.0),clampf(offset.y/75.0,-1.0,1.0))
            if move_vector.length()>1.0:
                move_vector=move_vector.normalized()
        elif event.index==look_touch_id:
            walk_yaw-=event.relative.x*0.004
            walk_pitch=clampf(walk_pitch-event.relative.y*0.003,-1.15,1.15)
            if player:
                player.rotation.y=walk_yaw
                walk_camera.rotation.x=walk_pitch
    elif event is InputEventMouseMotion and Input.is_mouse_button_pressed(MOUSE_BUTTON_LEFT):
        walk_yaw-=event.relative.x*0.004
        walk_pitch=clampf(walk_pitch-event.relative.y*0.003,-1.15,1.15)
        if player:
            player.rotation.y=walk_yaw
            walk_camera.rotation.x=walk_pitch
func _physics_process(delta):
    if not walk_mode or not is_instance_valid(player):
        return
    var gravity=float(ProjectSettings.get_setting("physics/3d/default_gravity",9.8))
    if not player.is_on_floor():
        player.velocity.y-=gravity*delta
    # Screen drag upward is negative Y; camera forward in Godot is local -Z.
    var input_dir=Vector3(move_vector.x,0.0,-move_vector.y)
    var forward=Vector3(-sin(walk_yaw),0.0,-cos(walk_yaw))
    var right=Vector3(cos(walk_yaw),0.0,-sin(walk_yaw))
    var direction=(right*input_dir.x+forward*input_dir.z).normalized()
    player.velocity.x=direction.x*4.5
    player.velocity.z=direction.z*4.5
    var horizontal_motion=Vector3(player.velocity.x,0.0,player.velocity.z)*delta
    # Assisted stair traversal: when the capsule hits a riser, test safe lifts
    # and raycast the tread at the destination. This avoids requiring jump input.
    var stepped=false
    var horizontal_blocked=player.test_move(player.global_transform,horizontal_motion) if horizontal_motion.length()>0.001 else false
    if player.is_on_floor() and horizontal_motion.length()>0.001 and horizontal_blocked:
        var space=get_world_3d().direct_space_state
        for step_height in [0.18,0.26,0.34,0.44,0.56,0.70,0.85]:
            var raised=player.global_transform
            raised.origin+=Vector3.UP*step_height
            if player.test_move(player.global_transform,Vector3.UP*step_height):
                continue
            if player.test_move(raised,horizontal_motion):
                continue
            var target=raised
            target.origin+=horizontal_motion
            # Probe ahead by one tread depth. At a riser, the capsule center is
            # still over the previous tread, so a short ray only sees the old floor.
            var probe_offset=horizontal_motion.normalized()*0.38
            var probe_origin=target.origin+probe_offset
            var ray_start=probe_origin+Vector3.UP*0.22
            var ray_end=probe_origin-Vector3.UP*(step_height+0.25)
            var query=PhysicsRayQueryParameters3D.create(ray_start,ray_end)
            query.collision_mask=1
            query.exclude=[player.get_rid()]
            var hit=space.intersect_ray(query)
            if hit.is_empty() or hit.normal.dot(Vector3.UP)<0.68:
                continue
            var rise=hit.position.y-player.global_position.y
            if rise<0.03 or rise>step_height+0.18:
                continue
            var landing=target
            landing.origin.y=hit.position.y+0.06
            var overlap=PhysicsShapeQueryParameters3D.new()
            overlap.shape=player.get_child(0).shape
            overlap.transform=landing*player.get_child(0).transform
            overlap.collision_mask=1
            overlap.exclude=[player.get_rid()]
            if not space.intersect_shape(overlap,4).is_empty():
                continue
            player.global_transform=landing
            player.velocity=Vector3.ZERO
            stepped=true
            break
    player.move_and_slide()
func _pan(delta:Vector2):
    if not camera_pivot or not camera:
        return
    var right=camera_pivot.global_transform.basis.x
    var forward=-camera_pivot.global_transform.basis.z
    right.y=0.0
    forward.y=0.0
    right=right.normalized()
    forward=forward.normalized()
    var amount=camera_distance*0.0018
    camera_pivot.global_position+=(-right*delta.x+forward*delta.y)*amount
func _orbit(delta:Vector2):
    if not camera_pivot:
        return
    camera_pivot.rotation.y-=delta.x*0.008
    camera_pivot.rotation.x=clamp(camera_pivot.rotation.x-delta.y*0.006,deg_to_rad(-85),deg_to_rad(15))
func _zoom(factor:float):
    camera_distance=clamp(camera_distance*factor,5.0,5000.0)
    if camera:
        camera.position=Vector3(0,0,camera_distance)
func _lighting():
    var env=WorldEnvironment.new()
    var e=Environment.new()
    e.background_mode=Environment.BG_SKY
    var sky=Sky.new()
    var sm=ProceduralSkyMaterial.new()
    sm.sky_top_color=Color(.19,.34,.52)
    sm.sky_horizon_color=Color(.68,.76,.82)
    sky.sky_material=sm
    e.sky=sky
    e.ambient_light_source=Environment.AMBIENT_SOURCE_COLOR
    e.ambient_light_color=Color(.65,.7,.76)
    e.ambient_light_energy=.75
    env.environment=e
    add_child(env)
    var sun=DirectionalLight3D.new()
    sun.rotation_degrees=Vector3(-52,-32,0)
    sun.light_energy=1.1
    add_child(sun)
'''
    (PROJECT/"main.gd").write_text(gd,encoding="utf-8")
    readme="# Block Gun | Combate na Floresta\\n\\nProtótipo Android de combate local construído com recursos recuperados do pacote Unity: soldado, UMP45, texturas, sons e mapa Floresta. Inclui joystick, câmera por toque, mira, tiro, recarga, pulo, vida, dano, eliminações, bots e retorno após eliminação. Os dados e scripts de referência Unity permanecem em reference/ e são excluídos do APK.\\n\\nOs OBJ de personagem atualmente exportados não preservam pesos de skinning utilizáveis. A animação esquelética original exige reconstrução do rig e associação dos clips, sem substituir o personagem por um modelo genérico.\\n"
    (PROJECT/"README.md").write_text(readme,encoding="utf-8")
    print("GODOT_ALL_MAPS",len(catalog),"MESHES",len(all_meshes),"TEXTURES",len(all_textures))
    for m in catalog: print(m)
if __name__=="__main__": main()
