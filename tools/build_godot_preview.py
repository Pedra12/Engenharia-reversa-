#!/usr/bin/env python3
"""Build a first Godot 4 preview project from the recovered Forest scene manifest."""
import json
import pathlib
import shutil
import sys

ROOT = pathlib.Path("scene_graph")
PROJECT = pathlib.Path("godot_project")
MANIFEST = ROOT / "maps" / "lvl_forest.json"


def main():
    if not MANIFEST.exists():
        raise SystemExit("Missing Forest map manifest: " + str(MANIFEST))
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if data.get("map_root") != "lvl_forest":
        raise SystemExit("Unexpected map root in Forest manifest")

    mesh_dir = PROJECT / "assets" / "meshes"
    texture_dir = PROJECT / "assets" / "textures"
    data_dir = PROJECT / "data"
    for folder in (mesh_dir, texture_dir, data_dir):
        folder.mkdir(parents=True, exist_ok=True)

    copied_meshes = set()
    copied_textures = set()
    missing = []

    def walk(node):
        for component in node.get("components", []):
            for ref in component.get("references", []):
                obj = ref.get("exported_obj")
                if obj:
                    src = ROOT / obj
                    dst = mesh_dir / pathlib.Path(obj).name
                    if src.exists() and dst.name not in copied_meshes:
                        shutil.copy2(src, dst)
                        copied_meshes.add(dst.name)
                    elif not src.exists():
                        missing.append(str(src))
            for material in component.get("material_resources", []):
                for texture in material.get("textures", []):
                    png = texture.get("exported_png")
                    if png:
                        src = ROOT / png
                        dst = texture_dir / pathlib.Path(png).name
                        if src.exists() and dst.name not in copied_textures:
                            shutil.copy2(src, dst)
                            copied_textures.add(dst.name)
                        elif not src.exists():
                            missing.append(str(src))
        for child in node.get("children", []):
            walk(child)

    walk(data["root"])
    (data_dir / "forest.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    project_text = """config_version=5

[application]
config/name="Block Gun - Forest Reconstruction"
run/main_scene="res://main.tscn"

[display]
window/size/viewport_width=1280
window/size/viewport_height=720
window/stretch/mode="canvas_items"

[rendering]
renderer/rendering_method="gl_compatibility"
renderer/rendering_method.mobile="gl_compatibility"
textures/default_filters/use_nearest_mipmap_filter=false
environment/defaults/default_clear_color=Color(0.055, 0.075, 0.095, 1)
"""
    (PROJECT / "project.godot").write_text(project_text, encoding="utf-8")

    main_scene = """[gd_scene load_steps=2 format=3]

[ext_resource type="Script" path="res://main.gd" id="1"]

[node name="ForestReconstruction" type="Node3D"]
script = ExtResource("1")
"""
    (PROJECT / "main.tscn").write_text(main_scene, encoding="utf-8")

    gdscript = r'''extends Node3D

const MANIFEST_PATH := "res://data/forest.json"

func _ready() -> void:
    var file := FileAccess.open(MANIFEST_PATH, FileAccess.READ)
    if file == null:
        push_error("Forest manifest not found")
        return
    var parsed = JSON.parse_string(file.get_as_text())
    if not parsed is Dictionary or not parsed.has("root"):
        push_error("Forest manifest is invalid")
        return
    _build_node(parsed["root"], self)
    _create_lighting()
    _create_camera()
    _create_overlay()
    print("FOREST_SCENE_LOADED nodes=", parsed.get("node_count", 0))

func _vector3(data: Variant, fallback: Vector3) -> Vector3:
    if not data is Dictionary:
        return fallback
    return Vector3(float(data.get("x", fallback.x)), float(data.get("y", fallback.y)), float(data.get("z", fallback.z)))

func _build_node(data: Dictionary, parent: Node3D) -> void:
    var node := Node3D.new()
    node.name = String(data.get("name", "RecoveredObject")).replace("/", "_")
    parent.add_child(node)
    node.position = _vector3(data.get("position", {}), Vector3.ZERO)
    node.scale = _vector3(data.get("scale", {}), Vector3.ONE)
    var rotation_data: Dictionary = data.get("rotation", {})
    node.quaternion = Quaternion(
        float(rotation_data.get("x", 0.0)),
        float(rotation_data.get("y", 0.0)),
        float(rotation_data.get("z", 0.0)),
        float(rotation_data.get("w", 1.0))
    ).normalized()

    var mesh_path := ""
    var collider_path := ""
    var material_resources: Array = []
    for component in data.get("components", []):
        var component_type: String = String(component.get("type", ""))
        if component_type == "MeshFilter":
            mesh_path = _reference_path(component, "m_Mesh")
        elif component_type == "MeshCollider":
            collider_path = _reference_path(component, "m_Mesh")
        elif component_type == "MeshRenderer":
            material_resources = component.get("material_resources", [])

    if not mesh_path.is_empty():
        var mesh := load("res://assets/meshes/" + mesh_path.get_file()) as Mesh
        if mesh != null:
            var instance := MeshInstance3D.new()
            instance.name = "RecoveredMesh"
            instance.mesh = mesh
            var material := _make_material(material_resources)
            if material != null:
                instance.material_override = material
            node.add_child(instance)

    if not collider_path.is_empty():
        var collision_mesh := load("res://assets/meshes/" + collider_path.get_file()) as Mesh
        if collision_mesh != null:
            var shape := collision_mesh.create_trimesh_shape()
            if shape != null:
                var body := StaticBody3D.new()
                body.name = "RecoveredCollision"
                var collision := CollisionShape3D.new()
                collision.shape = shape
                body.add_child(collision)
                node.add_child(body)

    for child in data.get("children", []):
        if child is Dictionary:
            _build_node(child, node)

func _reference_path(component: Dictionary, field_name: String) -> String:
    for reference in component.get("references", []):
        if String(reference.get("field", "")) == field_name:
            return String(reference.get("exported_obj", ""))
    return ""

func _make_material(resources: Array) -> StandardMaterial3D:
    for resource in resources:
        for texture_data in resource.get("textures", []):
            var path := String(texture_data.get("exported_png", ""))
            if not path.is_empty():
                var texture := load("res://assets/textures/" + path.get_file()) as Texture2D
                if texture != null:
                    var material := StandardMaterial3D.new()
                    material.albedo_texture = texture
                    material.roughness = 0.9
                    return material
    return null

func _create_lighting() -> void:
    var environment := WorldEnvironment.new()
    var env := Environment.new()
    env.background_mode = Environment.BG_SKY
    var sky := Sky.new()
    var sky_material := ProceduralSkyMaterial.new()
    sky_material.sky_top_color = Color(0.19, 0.34, 0.52)
    sky_material.sky_horizon_color = Color(0.68, 0.76, 0.82)
    sky.sky_material = sky_material
    env.sky = sky
    env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
    env.ambient_light_color = Color(0.65, 0.70, 0.76)
    env.ambient_light_energy = 0.75
    environment.environment = env
    add_child(environment)

    var sun := DirectionalLight3D.new()
    sun.name = "PreviewSun"
    sun.rotation_degrees = Vector3(-52.0, -32.0, 0.0)
    sun.light_energy = 1.1
    add_child(sun)

func _create_camera() -> void:
    var camera := Camera3D.new()
    camera.name = "PreviewCamera"
    camera.position = Vector3(-12.0, 42.0, 76.0)
    add_child(camera)
    camera.look_at(Vector3(-50.0, 0.0, 5.0), Vector3.UP)
    camera.current = true
    camera.fov = 62.0

func _create_overlay() -> void:
    var layer := CanvasLayer.new()
    var label := Label.new()
    label.text = "BLOCK GUN | FOREST | CENA RECONSTRUIDA"
    label.position = Vector2(22, 18)
    label.add_theme_font_size_override("font_size", 22)
    label.add_theme_color_override("font_color", Color(1.0, 1.0, 1.0))
    layer.add_child(label)
    add_child(layer)
'''
    (PROJECT / "main.gd").write_text(gdscript, encoding="utf-8")

    readme = f"""# Block Gun - Forest reconstruction preview

Generated from the serialized Unity data in the reference archive.

- Source map: {data.get('map_root')}
- Source serialized file: {data.get('source_level')}
- Hierarchy nodes in manifest: {data.get('node_count')}
- OBJ mesh files copied: {len(copied_meshes)}
- PNG texture files copied: {len(copied_textures)}
- Missing referenced exports: {len(missing)}

This is a reconstruction preview, not yet a verified playable level. It loads recovered transforms, mesh references, available material textures, and mesh-collider references. Original gameplay scripts, lighting/lightmaps, navigation and any unresolved dependencies still require separate reconstruction and validation.

Open with Godot 4.4 or newer. Main scene: main.tscn.
"""
    (PROJECT / "README.md").write_text(readme, encoding="utf-8")
    print("GODOT_PROJECT", PROJECT)
    print("MAP", data.get("map_root"), "NODES", data.get("node_count"))
    print("MESHES", len(copied_meshes), "TEXTURES", len(copied_textures), "MISSING", len(missing))
    if missing:
        print("MISSING_SAMPLE", json.dumps(missing[:30]))
    if not copied_meshes:
        raise SystemExit("No Forest meshes were copied; refusing to create an empty preview")


if __name__ == "__main__":
    main()
