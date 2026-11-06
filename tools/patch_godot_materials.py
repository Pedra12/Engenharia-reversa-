#!/usr/bin/env python3
"""Apply conservative material-preservation fixes to the generated Godot project."""
from pathlib import Path

path = Path("godot_project/main.gd")
if not path.is_file():
    raise SystemExit("Generated Godot script not found: " + str(path))
source = path.read_text(encoding="utf-8")

old_loop = """            for surface_index in range(mi.mesh.get_surface_count()):
                if mats.size()>0:
                    var material_start=int(d.get("godot_material_start_index",0))
                    var material_index=min(material_start+surface_index,mats.size()-1)
                    var surface_material=_mat([mats[material_index]],String(d.get("name","")))
                    if surface_material:
                        if bool(d.get("godot_lightmap_vertex_colors",false)) and surface_material is StandardMaterial3D:
                            (surface_material as StandardMaterial3D).vertex_color_use_as_albedo=true
                        mi.set_surface_override_material(surface_index,surface_material)
"""
new_loop = """            for surface_index in range(mi.mesh.get_surface_count()):
                if mats.is_empty():
                    continue
                var material_start=int(d.get("godot_material_start_index",0))
                var material_index=material_start+surface_index
                # Never clamp an invalid Unity slot to the last material.
                # That silently paints unrelated tank/crate submeshes with wrong colors.
                if material_index<0 or material_index>=mats.size():
                    push_warning("UNITY_MATERIAL_SLOT_MISSING node="+String(d.get("name",""))+" surface="+str(surface_index)+" slot="+str(material_index)+" materials="+str(mats.size()))
                    continue
                var embedded_material=mi.mesh.surface_get_material(surface_index)
                var keep_embedded=false
                if embedded_material is StandardMaterial3D:
                    var embedded_standard=embedded_material as StandardMaterial3D
                    keep_embedded=embedded_standard.albedo_texture!=null
                    # India lightmap GLB keeps its embedded texture; only duplicate
                    # it to enable vertex-color lighting when that flag is present.
                    if keep_embedded and bool(d.get("godot_lightmap_vertex_colors",false)):
                        var lightmapped_material=embedded_standard.duplicate() as StandardMaterial3D
                        lightmapped_material.vertex_color_use_as_albedo=true
                        mi.set_surface_override_material(surface_index,lightmapped_material)
                elif embedded_material!=null:
                    keep_embedded=true
                if keep_embedded:
                    continue
                var recovered_material=_mat([mats[material_index]],String(d.get("name","")),map_id=="lvl_india")
                if recovered_material:
                    if bool(d.get("godot_lightmap_vertex_colors",false)) and recovered_material is StandardMaterial3D:
                        (recovered_material as StandardMaterial3D).vertex_color_use_as_albedo=true
                    mi.set_surface_override_material(surface_index,recovered_material)
"""
if source.count(old_loop) != 1:
    raise SystemExit(f"Expected exactly one material override loop, found {source.count(old_loop)}")
source = source.replace(old_loop, new_loop)

old_return = """    # All map materials use preprocessed textures; no procedural India shader at runtime.
    return sm
"""
new_return = """    # Do not replace a valid imported GLB/OBJ material with a generic grey
    # StandardMaterial when the Unity reference has no recovered texture.
    # Preserve only explicit special shader behavior in that case.
    var special_material=material_name=="m_atlas_environment_alpha" or material_name=="m_water" or material_name=="water" or material_name=="unlit"
    if sm.albedo_texture==null and not special_material:
        return null
    # All map materials use preprocessed textures; no procedural India shader at runtime.
    return sm
"""
if source.count(old_return) != 1:
    raise SystemExit(f"Expected exactly one _mat return block, found {source.count(old_return)}")
source = source.replace(old_return, new_return)
path.write_text(source, encoding="utf-8")
print("MATERIAL_PRESERVATION_PATCH_OK: embedded material properties retained; only recovered albedo/special shader settings override.")
