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
    var explore=Button.new()
    explore.text="ENTRAR NO MAPA"
    explore.position=Vector2(280,104)
    explore.custom_minimum_size=Vector2(190,42)
    explore.pressed.connect(_toggle_walk_mode)
    menu.add_child(explore)
    jump_button=Button.new()
    jump_button.text="PULAR"
    jump_button.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_RIGHT)
    jump_button.position=Vector2(-150,-130)
    jump_button.custom_minimum_size=Vector2(120,64)
    jump_button.visible=false
    jump_button.pressed.connect(_request_jump)
    menu.add_child(jump_button)
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
        if typ=="MeshFilter" or typ=="SkinnedMeshRenderer":
            meshpath=_ref(c,"m_Mesh")
        elif typ=="MeshCollider":
            colpath=_ref(c,"m_Mesh")
        elif typ=="MeshRenderer" or typ=="SkinnedMeshRenderer":
            mats=c.get("material_resources",[])
    # House map has one anomalous collider mesh with bounds hundreds of Unity units
    # across. It is not the visible house shell and makes the map appear clipped.
    # Keep its renderer mesh for display; retain collider mesh only for physics below.
    var renderpath=colpath if colpath!="" else meshpath
    if id=="lvl_house" and String(d.get("name",""))=="sm_house_o1":
        renderpath=meshpath
    if renderpath!="":
        var mesh=load("res://assets/meshes/"+renderpath.get_file()) as Mesh
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
    capsule.radius=0.36
    capsule.height=1.75
    var collision=CollisionShape3D.new()
    collision.shape=capsule
    collision.position.y=0.9
    player.add_child(collision)
    walk_camera=Camera3D.new()
    walk_camera.position=Vector3(0,1.55,0)
    walk_camera.fov=75.0
    player.add_child(walk_camera)
    walk_camera.current=true
    player.global_position=camera_pivot.global_position+Vector3(0,maxf(5.0,camera_distance*0.04),0)
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
    map_label.text="MODO MAPA | ARRASTE PARA EXPLORAR"
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
    player.velocity.x=direction.x*5.0
    player.velocity.z=direction.z*5.0
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
    readme="# Block Gun | Explorador 3D de mapas\n\nAPK de visualização técnica dos nove mapas recuperados do Unity. A câmera enquadra automaticamente a geometria encontrada; arraste com um dedo para orbitar e use pinça para aproximar ou afastar. O botão reenquadra o mapa.\n\nAinda não contém personagem, bots ou gameplay. A completude de cada cenário depende dos modelos e texturas que puderam ser recuperados do arquivo original.\n"
    (PROJECT/"README.md").write_text(readme,encoding="utf-8")
    print("GODOT_ALL_MAPS",len(catalog),"MESHES",len(all_meshes),"TEXTURES",len(all_textures))
    for m in catalog: print(m)
if __name__=="__main__": main()
