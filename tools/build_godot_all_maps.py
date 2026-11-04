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
func _ready():
    _lighting()
    _make_menu()
    print("BLOCKGUN_MAPS_READY count=",MAPS.size())
func _make_menu():
    menu=Control.new(); menu.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT); add_child(menu)
    var panel=PanelContainer.new(); panel.position=Vector2(24,70); panel.size=Vector2(300,560); menu.add_child(panel)
    var box=VBoxContainer.new(); box.add_theme_constant_override("separation",8); panel.add_child(box)
    var title=Label.new(); title.text="BLOCK GUN | MAPAS"; title.add_theme_font_size_override("font_size",24); box.add_child(title)
    for i in range(MAPS.size()):
        var b=Button.new(); b.text=TITLES[i]; b.custom_minimum_size.y=45
        b.pressed.connect(_load_map.bind(MAPS[i],TITLES[i])); box.add_child(b)
    var info=Label.new(); info.text="Cenas recuperadas do Unity\nPreview técnico, sem gameplay"; box.add_child(info)
func _load_map(id:String,title:String):
    if world: world.queue_free()
    world=Node3D.new(); world.name="Map_"+id; add_child(world)
    var f=FileAccess.open("res://data/"+id+".json",FileAccess.READ)
    if f==null: push_error("Manifest missing "+id); return
    var d=JSON.parse_string(f.get_as_text()); _build_node(d.root,world)
    var camera=Camera3D.new(); camera.position=Vector3(0,60,90); world.add_child(camera); camera.look_at(Vector3.ZERO); camera.current=true
    var label=Label.new(); label.text="MAPA: "+title.to_upper()+" | CENA RECONSTRUIDA"; label.position=Vector2(350,22); label.add_theme_font_size_override("font_size",22); menu.add_child(label)
    print("MAP_LOADED ",id," nodes=",d.get("node_count",0))
func _build_node(d:Dictionary,parent:Node3D):
    var n=Node3D.new(); n.name=String(d.get("name","Recovered")).replace("/","_"); parent.add_child(n)
    n.position=_v(d.get("position",{}),Vector3.ZERO); n.scale=_v(d.get("scale",{}),Vector3.ONE)
    var q=d.get("rotation",{}); n.quaternion=Quaternion(float(q.get("x",0)),float(q.get("y",0)),float(q.get("z",0)),float(q.get("w",1))).normalized()
    var meshpath=""; var colpath=""; var mats=[]
    for c in d.get("components",[]):
        var typ=String(c.get("type",""))
        if typ=="MeshFilter": meshpath=_ref(c,"m_Mesh")
        elif typ=="MeshCollider": colpath=_ref(c,"m_Mesh")
        elif typ=="MeshRenderer": mats=c.get("material_resources",[])
    if meshpath!="":
        var mesh=load("res://assets/meshes/"+meshpath.get_file()) as Mesh
        if mesh:
            var mi=MeshInstance3D.new(); mi.mesh=mesh; mi.material_override=_mat(mats); n.add_child(mi)
    if colpath!="":
        var cm=load("res://assets/meshes/"+colpath.get_file()) as Mesh
        if cm:
            var body=StaticBody3D.new(); var cs=CollisionShape3D.new(); cs.shape=cm.create_trimesh_shape(); body.add_child(cs); n.add_child(body)
    for ch in d.get("children",[]): _build_node(ch,n)
func _ref(c:Dictionary,key:String)->String:
    for r in c.get("references",[]): 
        if String(r.get("field",""))==key: return String(r.get("exported_obj",""))
    return ""
func _v(x:Variant,fb:Vector3)->Vector3:
    if x is Dictionary:return Vector3(float(x.get("x",fb.x)),float(x.get("y",fb.y)),float(x.get("z",fb.z)))
    return fb
func _mat(ms:Array):
    for m in ms:
        for t in m.get("textures",[]):
            var p=String(t.get("exported_png",""))
            if p!="":
                var tx=load("res://assets/textures/"+p.get_file()) as Texture2D
                if tx:
                    var sm=StandardMaterial3D.new(); sm.albedo_texture=tx; sm.roughness=.9; return sm
    return null
func _lighting():
    var env=WorldEnvironment.new(); var e=Environment.new(); e.background_mode=Environment.BG_SKY
    var sky=Sky.new(); var sm=ProceduralSkyMaterial.new(); sm.sky_top_color=Color(.19,.34,.52); sm.sky_horizon_color=Color(.68,.76,.82); sky.sky_material=sm; e.sky=sky
    e.ambient_light_source=Environment.AMBIENT_SOURCE_COLOR; e.ambient_light_color=Color(.65,.7,.76); e.ambient_light_energy=.75; env.environment=e; add_child(env)
    var sun=DirectionalLight3D.new(); sun.rotation_degrees=Vector3(-52,-32,0); sun.light_energy=1.1; add_child(sun)
'''
    (PROJECT/"main.gd").write_text(gd,encoding="utf-8")
    readme="# Block Gun | Mapas recuperados\n\nPreview técnico com 9 mapas serializados recuperados do Unity. Selecione um mapa no painel esquerdo.\n\nNão contém gameplay, bots, spawn funcional ou iluminação original; valida a reconstrução de hierarquia, meshes, texturas disponíveis e colisores exportados.\n"
    (PROJECT/"README.md").write_text(readme,encoding="utf-8")
    print("GODOT_ALL_MAPS",len(catalog),"MESHES",len(all_meshes),"TEXTURES",len(all_textures))
    for m in catalog: print(m)
if __name__=="__main__": main()
