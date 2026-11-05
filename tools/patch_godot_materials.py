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
                if mats.size()>0:
                    var material_start=int(d.get("godot_material_start_index",0))
                    var material_index=min(material_start+surface_index,mats.size()-1)
                    var recovered_material=_mat([mats[material_index]],String(d.get("name","")))
                    if recovered_material:
                        # Keep the imported GLB/OBJ material settings and replace
                        # only the albedo texture recovered from the exact Unity ref.
                        var embedded_material=mi.mesh.surface_get_material(surface_index)
                        if embedded_material is StandardMaterial3D and recovered_material is StandardMaterial3D:
                            var combined_material=(embedded_material as StandardMaterial3D).duplicate() as StandardMaterial3D
                            var recovered_standard=recovered_material as StandardMaterial3D
                            if recovered_standard.albedo_texture:
                                combined_material.albedo_texture=recovered_standard.albedo_texture
                            if recovered_standard.transparency!=BaseMaterial3D.TRANSPARENCY_DISABLED:
                                combined_material.transparency=recovered_standard.transparency
                            if recovered_standard.cull_mode!=BaseMaterial3D.CULL_BACK:
                                combined_material.cull_mode=recovered_standard.cull_mode
                            if bool(d.get("godot_lightmap_vertex_colors",false)):
                                combined_material.vertex_color_use_as_albedo=true
                            mi.set_surface_override_material(surface_index,combined_material)
                        else:
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
    var special_material=material_name=="m_atlas_environment_alpha" or material_name=="m_water" or material_name=="water"
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
