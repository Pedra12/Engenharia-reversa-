#!/usr/bin/env python3
"""Generate a Godot 4 project with all recovered Block Gun maps."""
import json, pathlib, shutil
ROOT=pathlib.Path("scene_graph"); PROJECT=pathlib.Path("godot_project")
MAPS=["lvl_baghdad","lvl_assault","lvl_middle_east","lvl_resort","lvl_forest","lvl_house","lvl_india","lvl_rome","lvl_deluxe_fest"]
names={"lvl_baghdad":"Baghdad","lvl_assault":"Assalto","lvl_middle_east":"Oriente Médio","lvl_resort":"Resort","lvl_forest":"Floresta","lvl_house":"Casa","lvl_india":"Índia","lvl_rome":"Roma","lvl_deluxe_fest":"Festival Deluxe"}
def main():
    data_dir=PROJECT/"data"; meshes=PROJECT/"assets"/"meshes"; textures=PROJECT/"assets"/"textures"
    for p in (data_dir,meshes,textures): p.mkdir(parents=True,exist_ok=True)
    all_meshes=set(); all_textures=set(); catalog=[]
    for mapid in MAPS:
        path=ROOT/"maps"/(mapid+".json")
        if not path.exists(): raise SystemExit("Manifest missing: "+str(path))
        d=json.loads(path.read_text(encoding="utf-8")); copied=set(); tex=set(); missing=[]
        def walk(n):
            for c in n.get("components",[]):
                for r in c.get("references",[]):
                    obj=r.get("exported_obj")
                    if obj:
                        src=ROOT/obj; dst=meshes/pathlib.Path(obj).name
                        if src.exists():
                            if dst.name not in all_meshes: shutil.copy2(src,dst); all_meshes.add(dst.name)
                            copied.add(dst.name)
                        else: missing.append(obj)
                for m in c.get("material_resources",[]):
                    for t in m.get("textures",[]):
                        png=t.get("exported_png")
                        if png:
                            src=ROOT/png; dst=textures/pathlib.Path(png).name
                            if src.exists():
                                if dst.name not in all_textures: shutil.copy2(src,dst); all_textures.add(dst.name)
                                tex.add(dst.name)
                            else: missing.append(png)
            for ch in n.get("children",[]): walk(ch)
        walk(d["root"])
        (data_dir/(mapid+".json")).write_text(json.dumps(d,ensure_ascii=False),encoding="utf-8")
        catalog.append({"id":mapid,"name":names[mapid],"nodes":d.get("node_count",0),"meshes":len(copied),"textures":len(tex),"missing":len(missing)})
    (data_dir/"maps.json").write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding="utf-8")
    (PROJECT/"project.godot").write_text('''config_version=5
[application]
config/name="Block Gun - Mapas Recuperados"
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
exclude_filter=""
export_path="build/BlockGunMapsPreview.apk"
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
package/unique_name="com.pedra12.blockgunmaps"
package/name="Block Gun Map Preview"
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
var camera_pivot:Node3D
var camera:Camera3D
var camera_distance:float=80.0
var touch_points:Dictionary={}
var pinch_distance:float=0.0
var dragging_mouse:bool=false
var map_label:Label
func _ready():
    _lighting()
    _make_menu()
    print("BLOCKGUN_MAPS_READY count=",MAPS.size())
func _make_menu():
    var layer=CanvasLayer.new()
    add_child(layer)
    menu=Control.new()
    menu.mouse_filter=Control.MOUSE_FILTER_IGNORE
    menu.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
    layer.add_child(menu)
    var panel=PanelContainer.new()
    panel.position=Vector2(16,58)
    panel.size=Vector2(250,560)
    menu.add_child(panel)
    var box=VBoxContainer.new()
    box.add_theme_constant_override("separation",6)
    panel.add_child(box)
    var title=Label.new()
    title.text="BLOCK GUN | MAPAS"
    title.add_theme_font_size_override("font_size",21)
    box.add_child(title)
    for i in range(MAPS.size()):
        var b=Button.new()
        b.text=TITLES[i]
        b.custom_minimum_size.y=43
        b.pressed.connect(_load_map.bind(MAPS[i],TITLES[i]))
        box.add_child(b)
    var info=Label.new()
    info.text="Arraste para girar\nPinça para aproximar/afastar"
    box.add_child(info)
    map_label=Label.new()
    map_label.position=Vector2(280,18)
    map_label.add_theme_font_size_override("font_size",20)
    menu.add_child(map_label)
    var reset=Button.new()
    reset.text="REENQUADRAR MAPA"
    reset.position=Vector2(280,54)
    reset.custom_minimum_size=Vector2(190,42)
    reset.pressed.connect(_fit_camera)
    menu.add_child(reset)
func _load_map(id:String,title:String):
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
    _build_node(d.root,world)
    _create_camera()
    _fit_camera()
    map_label.text="MAPA: "+title.to_upper()+" | ARRASTE PARA EXPLORAR"
    print("MAP_LOADED ",id," nodes=",d.get("node_count",0)," meshes=",_count_meshes(world))
func _build_node(d:Dictionary,parent:Node3D):
    var n=Node3D.new()
    n.name=String(d.get("name","Recovered")).replace("/","_")
    parent.add_child(n)
    n.position=_v(d.get("position",{}),Vector3.ZERO)
    n.scale=_v(d.get("scale",{}),Vector3.ONE)
    var q=d.get("rotation",{})
    n.quaternion=Quaternion(float(q.get("x",0)),float(q.get("y",0)),float(q.get("z",0)),float(q.get("w",1))).normalized()
    var meshpath=""
    var colpath=""
    var mats=[]
    for c in d.get("components",[]):
        var typ=String(c.get("type",""))
        if typ=="MeshFilter":
            meshpath=_ref(c,"m_Mesh")
        elif typ=="MeshCollider":
            colpath=_ref(c,"m_Mesh")
        elif typ=="MeshRenderer":
            mats=c.get("material_resources",[])
    if meshpath!="":
        var mesh=load("res://assets/meshes/"+meshpath.get_file()) as Mesh
        if mesh:
            var mi=MeshInstance3D.new()
            mi.mesh=mesh
            mi.material_override=_mat(mats)
            n.add_child(mi)
    if colpath!="":
        var cm=load("res://assets/meshes/"+colpath.get_file()) as Mesh
        if cm:
            var body=StaticBody3D.new()
            var cs=CollisionShape3D.new()
            cs.shape=cm.create_trimesh_shape()
            body.add_child(cs)
            n.add_child(body)
    for ch in d.get("children",[]):
        _build_node(ch,n)
func _ref(c:Dictionary,key:String)->String:
    for r in c.get("references",[]):
        if String(r.get("field",""))==key:
            return String(r.get("exported_obj",""))
    return ""
func _v(x:Variant,fb:Vector3)->Vector3:
    if x is Dictionary:
        return Vector3(float(x.get("x",fb.x)),float(x.get("y",fb.y)),float(x.get("z",fb.z)))
    return fb
func _mat(ms:Array):
    for m in ms:
        for t in m.get("textures",[]):
            var p=String(t.get("exported_png",""))
            if p!="":
                var tx=load("res://assets/textures/"+p.get_file()) as Texture2D
                if tx:
                    var sm=StandardMaterial3D.new()
                    sm.albedo_texture=tx
                    sm.roughness=.9
                    return sm
    return null
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
        camera_pivot.global_position=bounds.get_center()
        var s=bounds.size
        var largest=max(s.x,max(s.y,s.z))
        camera_distance=max(12.0,largest*1.65)
        if largest<0.01:
            camera_distance=80.0
    camera_pivot.rotation=Vector3(deg_to_rad(-32.0),deg_to_rad(35.0),0)
    camera.position=Vector3(0,0,camera_distance)
    print("CAMERA_FIT distance=",camera_distance," bounds_found=",found)
func _count_meshes(root:Node)->int:
    var total=0
    for item in root.find_children("*","MeshInstance3D",true,false):
        if item is MeshInstance3D and item.mesh:
            total+=1
    return total
func _unhandled_input(event):
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
        if touch_points.has(event.index):
            touch_points[event.index]=event.position
        if touch_points.size()>=2:
            var pts=touch_points.values()
            var now=pts[0].distance_to(pts[1])
            if pinch_distance>0.0:
                camera_distance=clamp(camera_distance*pinch_distance/max(now,1.0),5.0,5000.0)
                camera.position=Vector3(0,0,camera_distance)
            pinch_distance=now
        else:
            _orbit(event.relative)
    elif event is InputEventMouseButton:
        if event.button_index==MOUSE_BUTTON_LEFT:
            dragging_mouse=event.pressed
        elif event.pressed and event.button_index==MOUSE_BUTTON_WHEEL_UP:
            _zoom(0.88)
        elif event.pressed and event.button_index==MOUSE_BUTTON_WHEEL_DOWN:
            _zoom(1.14)
    elif event is InputEventMouseMotion and dragging_mouse:
        _orbit(event.relative)
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
    readme="# Block Gun | Explorador 3D de mapas\n\nAPK de visualização técnica dos nove mapas recuperados do Unity. A câmera enquadra automaticamente a geometria encontrada; arraste com um dedo para orbitar e use pinça para aproximar ou afastar. O botão reenquadra o mapa.\n\nAinda não contém personagem, bots ou gameplay. A completude de cada cenário depende dos modelos e texturas que puderam ser recuperados do arquivo original.\n"
    (PROJECT/"README.md").write_text(readme,encoding="utf-8")
    print("GODOT_ALL_MAPS",len(catalog),"MESHES",len(all_meshes),"TEXTURES",len(all_textures))
    for m in catalog: print(m)
if __name__=="__main__": main()
