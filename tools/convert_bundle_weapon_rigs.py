#!/usr/bin/env python3
"""Recover the original first-person UMP45 + hands rig from the Addressables bundle."""
import argparse, base64, collections, json, pathlib, struct, sys

from convert_unity_rigs import (
    FORMAT_SIZE, align16, decode_skin, parse_obj, position3, quat_godot,
    bindpose_godot, transform_record, vec3
)

def load_objects(bundle_dir):
    p = bundle_dir / "objects.json"
    if not p.is_file():
        raise SystemExit("Bundle objects.json missing: " + str(p))
    records = json.loads(p.read_text(encoding="utf-8"))
    return records, {str(o.get("path_id")): o for o in records}

def transform_component(go, byid):
    for c in go.get("fields", {}).get("m_Component", []):
        obj = byid.get(str(c.get("component", {}).get("m_PathID")))
        if obj and obj.get("type") == "Transform":
            return obj
    return None

def path_for(go, byid, gos, seen=None):
    if not go:
        return ""
    seen = seen or set()
    gid = str(go.get("path_id"))
    if gid in seen:
        return str(go.get("name", ""))
    seen.add(gid)
    tr = transform_component(go, byid)
    if not tr:
        return str(go.get("name", ""))
    father = str(tr.get("fields", {}).get("m_Father", {}).get("m_PathID", "0"))
    parent = None
    if father != "0":
        parent_tr = byid.get(father)
        if parent_tr:
            parent_gid = str(parent_tr.get("fields", {}).get("m_GameObject", {}).get("m_PathID", ""))
            parent = gos.get(parent_gid)
    prefix = path_for(parent, byid, gos, seen) if parent else ""
    return (prefix + "/" if prefix else "") + str(go.get("name", ""))

def find_go(name, gos, byid, prefix=None):
    matches = []
    for go in gos.values():
        if go.get("name") != name:
            continue
        path = path_for(go, byid, gos)
        if prefix is None or path.startswith(prefix):
            matches.append((go, path))
    if len(matches) != 1:
        raise SystemExit(f"Expected one GameObject {name!r} under {prefix!r}, found {len(matches)}: {[p for _,p in matches[:8]]}")
    return matches[0][0]

def get_renderer(go, byid):
    for c in go.get("fields", {}).get("m_Component", []):
        obj = byid.get(str(c.get("component", {}).get("m_PathID")))
        if obj and obj.get("type") == "SkinnedMeshRenderer":
            return obj
    raise SystemExit("SkinnedMeshRenderer missing on " + str(go.get("name")))

def transform_by_id(path_id, byid):
    obj = byid.get(str(path_id))
    if not obj or obj.get("type") != "Transform":
        raise SystemExit("Transform reference missing: " + str(path_id))
    return obj

def transform_parent(tr, byid):
    parent_id = str(tr.get("fields", {}).get("m_Father", {}).get("m_PathID", "0"))
    if parent_id == "0":
        return None
    return transform_by_id(parent_id, byid)

def material_texture(material, byid):
    fields = material.get("fields", {})
    envs = fields.get("m_SavedProperties", {}).get("m_TexEnvs", []) or []
    for wanted in ("_MainTex", "_BaseMap"):
        for key, value in envs:
            if key == wanted:
                tid = str(value.get("m_Texture", {}).get("m_PathID", "0"))
                if tid != "0":
                    return byid.get(tid)
    return None

def texture_resource_path(texture, bundle_dir, bundle_name, audit):
    if not texture:
        return ""
    tid = str(texture.get("path_id"))
    candidates = list((bundle_dir / "textures").glob("*_" + tid + ".png"))
    if candidates:
        return "res://assets/unity_original/bundle_assets/" + bundle_name + "/textures/" + candidates[0].name
    candidates = list((audit / "exported" / "textures").glob("*_" + tid + ".png"))
    if candidates:
        return "res://assets/unity_original/textures/" + candidates[0].name
    return ""

def find_audio_path(sound_name, bundle_dir, bundle_name, audit):
    if not sound_name:
        return ""
    for folder, prefix in (
        (bundle_dir / "audio", "res://assets/unity_original/bundle_assets/" + bundle_name + "/audio/"),
        (audit / "exported" / "audio", "res://assets/unity_original/audio/")
    ):
        if folder.is_dir():
            hits = sorted(p for p in folder.iterdir() if sound_name.lower() in p.name.lower())
            if hits:
                return prefix + hits[0].name
    return ""

def decode_rigid_or_blended_skin(fields):
    vd = fields["m_VertexData"]
    count = int(vd["m_VertexCount"])
    blob = base64.b64decode(vd["m_DataSize"]["base64"])
    channels = vd["m_Channels"]
    strides = {}
    for ch in channels:
        dim = int(ch.get("dimension", 0) or 0)
        if dim <= 0:
            continue
        size = FORMAT_SIZE[int(ch["format"])] * dim
        stream = int(ch["stream"])
        strides[stream] = max(strides.get(stream, 0), int(ch["offset"]) + size)
    offsets = {}
    cursor = 0
    for stream in sorted(strides):
        cursor = align16(cursor)
        offsets[stream] = cursor
        cursor += strides[stream] * count
    if cursor > len(blob):
        raise ValueError(f"vertex data truncated: expected {cursor}, got {len(blob)}")
    wc, ic = channels[12], channels[13]
    wd, idim = int(wc.get("dimension", 0)), int(ic.get("dimension", 0))
    if idim < 1:
        raise ValueError("bone index channel missing")
    if wd < 1 and idim != 1:
        raise ValueError("unsupported rigid skinning: expected one bone index per vertex")
    weights, indices = [], []
    for vi in range(count):
        io = offsets[int(ic["stream"])] + vi * strides[int(ic["stream"])] + int(ic["offset"])
        b = list(struct.unpack_from("<" + "I" * idim, blob, io))
        if wd < 1:
            w = [1.0, 0.0, 0.0, 0.0]
            b = (b + [0] * 4)[:4]
        else:
            wo = offsets[int(wc["stream"])] + vi * strides[int(wc["stream"])] + int(wc["offset"])
            w = list(struct.unpack_from("<" + "f" * wd, blob, wo))
            w = (w + [0.0] * 4)[:4]
            b = (b + [0] * 4)[:4]
            total = sum(w)
            if total > 1e-8:
                w = [x / total for x in w]
            else:
                w = [1.0, 0.0, 0.0, 0.0]
                b = [0, 0, 0, 0]
        weights.append(w)
        indices.append(b)
    return count, weights, indices

def build_bones(renderer, mesh_fields, byid):
    bone_ptrs = renderer.get("fields", {}).get("m_Bones", []) or []
    hashes = [int(x) for x in mesh_fields.get("m_BoneNameHashes", [])]
    if len(bone_ptrs) != len(hashes) or not bone_ptrs:
        raise ValueError("SkinnedMeshRenderer bone list and mesh bone hashes differ")
    transform_ids = [str(x.get("m_PathID")) for x in bone_ptrs]
    index_by_id = {tid: i for i, tid in enumerate(transform_ids)}
    bones = []
    for i, tid in enumerate(transform_ids):
        tr = transform_by_id(tid, byid)
        f = tr.get("fields", {})
        goid = str(f.get("m_GameObject", {}).get("m_PathID", ""))
        go = byid.get(goid, {})
        father = str(f.get("m_Father", {}).get("m_PathID", "0"))
        bones.append({
            "name": str(go.get("name", "bone_" + str(i))),
            "hash": hashes[i],
            "parent": index_by_id.get(father, -1),
            "position": position3(f.get("m_LocalPosition")),
            "rotation": quat_godot(f.get("m_LocalRotation")),
            "scale": vec3(f.get("m_LocalScale"), (1, 1, 1))
        })
    return bones, transform_ids

def build_mesh_entry(go, renderer, byid, bundle_dir, bundle_name, audit, bones):
    mesh_id = str(renderer.get("fields", {}).get("m_Mesh", {}).get("m_PathID", "0"))
    mesh = byid.get(mesh_id)
    if not mesh or mesh.get("type") != "Mesh":
        raise SystemExit("Mesh object missing for " + str(go.get("name")))
    mesh_fields = mesh["fields"]
    obj_hits = sorted((bundle_dir / "meshes").glob("Mesh_" + str(mesh.get("name")) + "_" + mesh_id + ".obj"))
    if not obj_hits:
        raise SystemExit("Bundle OBJ missing for " + str(mesh.get("name")) + " id " + mesh_id)
    count, weights, bone_indices = decode_rigid_or_blended_skin(mesh_fields)
    for row, weight_row in zip(bone_indices, weights):
        for b, w in zip(row, weight_row):
            if w > 1e-6 and b >= len(bones):
                raise ValueError(f"{mesh.get('name')}: weighted vertex bone index {b} exceeds {len(bones)}")
    surfaces = parse_obj(obj_hits[0], weights, bone_indices, count)
    tr = transform_component(go, byid)
    mats = renderer.get("fields", {}).get("m_Materials", []) or []
    texture_paths = []
    for material_ptr in mats:
        material = byid.get(str(material_ptr.get("m_PathID")))
        texture = material_texture(material, byid) if material else None
        if not texture:
            # The original UMP material has an empty texture PPtr in this dump;
            # the matching named source texture is still present in the same bundle.
            fallback = "UMP_45_Diffuse" if mesh.get("name") == "UMP_45" else "Hands texture_+"
            texture = next((o for o in byid.values() if o.get("type") == "Texture2D" and o.get("name") == fallback), None)
        texture_paths.append(texture_resource_path(texture, bundle_dir, bundle_name, audit))
    max_index = max((int(s.get("material_index", 0)) for s in surfaces), default=0)
    if len(texture_paths) <= max_index:
        texture_paths += [""] * (max_index + 1 - len(texture_paths))
    return {
        "name": str(mesh.get("name")),
        "vertex_count": count,
        "mesh_transform": transform_record(tr),
        "bind_poses": [bindpose_godot(x) for x in mesh_fields.get("m_BindPose", [])],
        "mesh_bone_to_avatar": list(range(len(bones))),
        "surfaces": surfaces,
        "textures": texture_paths,
        "source_obj": str(obj_hits[0].name),
        "material_names": [
            str(byid.get(str(m.get("m_PathID")), {}).get("name", ""))
            for m in mats
        ]
    }

def curve_keys(curve, kind):
    out = []
    data = curve.get("curve", {}).get("m_Curve", []) or []
    for key in data:
        value = key.get("value")
        if kind == "position":
            value = position3(value)
        else:
            value = quat_godot(value)
        out.append({"time": float(key.get("time", 0.0)), "value": value})
    return out

def build_animations(objects, audit, bundle_dir, bundle_name):
    clips = {}
    audio_names = {"ump45_fire", "smg_mag_out_0", "smg_mag_in_0", "smg_bolt_back_0", "smg_bolt_forward_0", "cloth_0"}
    for obj in objects:
        if obj.get("type") != "AnimationClip" or "UMP_45_armature" not in str(obj.get("name", "")):
            continue
        name = str(obj.get("name", ""))
        low = name.lower()
        key = next((k for k in ("fire", "idle", "reload", "deploy") if k in low), "")
        if not key:
            continue
        fields = obj.get("fields", {})
        settings = fields.get("m_AnimationClipSettings", {}) or {}
        pos_curves = []
        for c in fields.get("m_PositionCurves", []) or []:
            pos_curves.append({"path": c.get("path", ""), "keys": curve_keys(c, "position")})
        rot_curves = []
        for c in fields.get("m_RotationCurves", []) or []:
            rot_curves.append({"path": c.get("path", ""), "keys": curve_keys(c, "rotation")})
        events = []
        for e in fields.get("m_Events", []) or []:
            data = str(e.get("data", ""))
            if data:
                audio_names.add(data)
            events.append({
                "time": float(e.get("time", 0.0)),
                "function": str(e.get("functionName", "")),
                "data": data,
                "sound_path": find_audio_path(data, bundle_dir, bundle_name, audit)
            })
        start = float(settings.get("m_StartTime", 0.0))
        stop = float(settings.get("m_StopTime", 0.0))
        max_time = max(
            [k["time"] for c in pos_curves for k in c["keys"]] +
            [k["time"] for c in rot_curves for k in c["keys"]] +
            [e["time"] for e in events] + [0.0]
        )
        duration = max(stop - start, max_time)
        clips[key.title()] = {
            "source_name": name,
            "path_id": obj.get("path_id"),
            "sample_rate": float(fields.get("m_SampleRate", 60.0)),
            "duration": duration,
            "loop": bool(settings.get("m_LoopTime", False)),
            "position_curves": pos_curves,
            "rotation_curves": rot_curves,
            "events": events
        }
    sounds = {}
    for name in sorted(audio_names):
        path = find_audio_path(name, bundle_dir, bundle_name, audit)
        if path:
            sounds[name] = path
    return clips, sounds

def build_sockets(objects, byid, gos, prefix, bone_ids, bone_names):
    sockets = {}
    effects = []
    for go in gos.values():
        name = str(go.get("name", ""))
        if not (name.startswith("socket_") or name in ("MuzzleFlashEffect_FirstPerson", "ShellParticle_FirstPerson", "Smoke", "StartRing", "MuzzleSparks", "Puff")):
            continue
        path = path_for(go, byid, gos)
        if not path.startswith(prefix + "/"):
            continue
        tr = transform_component(go, byid)
        if not tr:
            continue
        f = tr.get("fields", {})
        father = str(f.get("m_Father", {}).get("m_PathID", "0"))
        parent_bone = bone_names[bone_ids.index(father)] if father in bone_ids else ""
        record = {
            "name": name,
            "parent_bone": parent_bone,
            "transform": transform_record(tr),
            "path": path
        }
        if name.startswith("socket_"):
            sockets[name] = record
        else:
            effects.append(record)
    return sockets, effects

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", default="unity_audit")
    ap.add_argument("--project", default="godot_project")
    args = ap.parse_args()
    audit = pathlib.Path(args.audit)
    project = pathlib.Path(args.project)
    bundle_root = audit / "bundle_probe"
    bundle_files = sorted(
        p for p in bundle_root.glob("*/objects.json")
        if p.parent.name != "failed_bundles"
    )
    if not bundle_files:
        raise SystemExit("Original Addressables bundle objects.json not found")
    selected = None
    for candidate in bundle_files:
        candidate_objects, candidate_byid = load_objects(candidate.parent)
        if any(o.get("type") == "GameObject" and o.get("name") == "p_ump_fp" for o in candidate_objects):
            selected = (candidate.parent, candidate_objects, candidate_byid)
            break
    if selected is None:
        raise SystemExit("No successful bundle contains the original p_ump_fp prefab: " + ", ".join(str(p.parent) for p in bundle_files))
    bundle_dir, objects, byid = selected
    bundle_name = bundle_dir.name
    gos = {str(o.get("path_id")): o for o in objects if o.get("type") == "GameObject"}

    fp_go = find_go("p_ump_fp", gos, byid)
    fp_path = path_for(fp_go, byid, gos)
    base_go = find_go("Local_model_base", gos, byid, fp_path)
    weapon_root_go = find_go("UMP_45_bitgun_test", gos, byid, fp_path)
    hands_go = find_go("Hands", gos, byid, fp_path)
    weapon_go = find_go("UMP_45", gos, byid, fp_path)
    hands_renderer = get_renderer(hands_go, byid)
    weapon_renderer = get_renderer(weapon_go, byid)
    weapon_mesh = byid[str(weapon_renderer["fields"]["m_Mesh"]["m_PathID"])]
    bones, bone_ids = build_bones(weapon_renderer, weapon_mesh["fields"], byid)
    hands_bones, hands_bone_ids = build_bones(hands_renderer, byid[str(hands_renderer["fields"]["m_Mesh"]["m_PathID"])]["fields"], byid)
    if bone_ids != hands_bone_ids or [b["name"] for b in bones] != [b["name"] for b in hands_bones]:
        raise SystemExit("UMP45 and Hands do not share the same original bone hierarchy")

    fp_transform = transform_component(fp_go, byid)
    base_transform = transform_component(base_go, byid)
    weapon_root_transform = transform_component(weapon_root_go, byid)
    armature_go = find_go("UMP_45_armature", gos, byid, fp_path)
    armature_transform = transform_component(armature_go, byid)
    root_bone_id = str(weapon_renderer["fields"]["m_RootBone"]["m_PathID"])
    root_bone = transform_by_id(root_bone_id, byid)
    if str(root_bone.get("fields", {}).get("m_Father", {}).get("m_PathID")) != str(armature_transform.get("path_id")):
        raise SystemExit("UMP45 skeleton root/armature hierarchy does not match original prefab")

    meshes = {
        "hands": build_mesh_entry(hands_go, hands_renderer, byid, bundle_dir, bundle_name, audit, bones),
        "weapon": build_mesh_entry(weapon_go, weapon_renderer, byid, bundle_dir, bundle_name, audit, bones)
    }
    animations, sounds = build_animations(objects, audit, bundle_dir, bundle_name)
    sockets, effects = build_sockets(objects, byid, gos, fp_path, bone_ids, [b["name"] for b in bones])

    if set(animations) != {"Fire", "Idle", "Reload", "Deploy"}:
        raise SystemExit("UMP45 original animation set incomplete: " + str(sorted(animations)))
    if len(bones) != 11 or meshes["weapon"]["vertex_count"] != 2689 or meshes["hands"]["vertex_count"] != 144:
        raise SystemExit("UMP45 original rig counts differ from the verified source layout")
    if not meshes["weapon"]["textures"][0] or not meshes["hands"]["textures"][0]:
        raise SystemExit("UMP45 or Hands original texture could not be resolved")

    output = {
        "UMP45": {
            "source_bundle": bundle_name,
            "prefab_transform": transform_record(fp_transform),
            "model_base_transform": transform_record(base_transform),
            "model_root_transform": transform_record(weapon_root_transform),
            "skeleton_transform": transform_record(armature_transform),
            "bones": bones,
            "meshes": meshes,
            "sockets": sockets,
            "effects": effects,
            "animations": animations,
            "sounds": sounds
        }
    }
    out = project / "assets" / "combat_source" / "original_weapon_rigs.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print("ORIGINAL_WEAPON_RIGS_READY", json.dumps({
        "bones": len(bones),
        "hands_vertices": meshes["hands"]["vertex_count"],
        "weapon_vertices": meshes["weapon"]["vertex_count"],
        "animations": sorted(animations),
        "sockets": sorted(sockets),
        "effects": sorted(e["name"] for e in effects),
        "sounds": sorted(sounds)
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
