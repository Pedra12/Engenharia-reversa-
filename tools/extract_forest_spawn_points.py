#!/usr/bin/env python3
"""Extract original level5 forest spawn transforms from the decompiled Unity scene."""
import argparse, json, pathlib

def qmul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (
        aw * bx + ax * bw + ay * bz - az * by,
        aw * by - ax * bz + ay * bw + az * bx,
        aw * bz + ax * by - ay * bx + az * bw,
        aw * bw - ax * bx - ay * by - az * bz
    )

def qrotate(q, v):
    x, y, z, w = q
    vx, vy, vz = v
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return (
        vx + w * tx + y * tz - z * ty,
        vy + w * ty + z * tx - x * tz,
        vz + w * tz + x * ty - y * tx
    )

def vec3(value, default):
    if isinstance(value, dict):
        return (float(value.get("x", default[0])), float(value.get("y", default[1])), float(value.get("z", default[2])))
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return (float(value[0]), float(value[1]), float(value[2]))
    return default

def quat(value):
    if isinstance(value, dict):
        return (float(value.get("x", 0)), float(value.get("y", 0)), float(value.get("z", 0)), float(value.get("w", 1)))
    if isinstance(value, (list, tuple)) and len(value) >= 4:
        return tuple(float(x) for x in value[:4])
    return (0.0, 0.0, 0.0, 1.0)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", default="unity_audit")
    ap.add_argument("--project", default="godot_project")
    args = ap.parse_args()
    audit = pathlib.Path(args.audit)
    project = pathlib.Path(args.project)
    source_file = audit / "UNITY_SCENE_OBJECTS.json"
    if not source_file.is_file():
        raise SystemExit("UNITY_SCENE_OBJECTS.json missing: " + str(source_file))
    records = json.loads(source_file.read_text(encoding="utf-8"))
    sources = sorted({str(o.get("source", "")) for o in records if "level5" in str(o.get("source", "")).lower()})
    if not sources:
        raise SystemExit("Original level5 scene not found in UNITY_SCENE_OBJECTS.json")
    source = next((s for s in sources if s.lower() == "level5"), sources[0])
    scene = [o for o in records if str(o.get("source", "")) == source]
    byid = {str(o.get("path_id")): o for o in scene}
    gos = {str(o.get("path_id")): o for o in scene if o.get("type") == "GameObject"}
    transforms = {str(o.get("path_id")): o for o in scene if o.get("type") in ("Transform", "RectTransform")}

    transform_by_go = {}
    for tid, tr in transforms.items():
        gid = str(tr.get("fields", {}).get("m_GameObject", {}).get("m_PathID", ""))
        if gid:
            transform_by_go[gid] = tid

    cache = {}
    def world_transform(tid, seen=None):
        if tid in cache:
            return cache[tid]
        seen = seen or set()
        if tid in seen:
            raise ValueError("Transform parent cycle at " + tid)
        seen.add(tid)
        tr = transforms[tid]
        f = tr.get("fields", {})
        local_pos = vec3(f.get("m_LocalPosition"), (0, 0, 0))
        local_rot = quat(f.get("m_LocalRotation"))
        local_scale = vec3(f.get("m_LocalScale"), (1, 1, 1))
        father = str(f.get("m_Father", {}).get("m_PathID", "0"))
        if father == "0" or father not in transforms:
            result = (local_pos, local_rot, local_scale)
        else:
            parent_pos, parent_rot, parent_scale = world_transform(father, seen)
            scaled = (local_pos[0] * parent_scale[0], local_pos[1] * parent_scale[1], local_pos[2] * parent_scale[2])
            rotated = qrotate(parent_rot, scaled)
            world_pos = (parent_pos[0] + rotated[0], parent_pos[1] + rotated[1], parent_pos[2] + rotated[2])
            world_rot = qmul(parent_rot, local_rot)
            world_scale = (local_scale[0] * parent_scale[0], local_scale[1] * parent_scale[1], local_scale[2] * parent_scale[2])
            result = (world_pos, world_rot, world_scale)
        cache[tid] = result
        return result

    def get_world_for_go(go):
        tid = transform_by_go.get(str(go.get("path_id")))
        if not tid:
            return None
        return world_transform(tid)

    spawn_groups = {"generic": [], "blue": [], "yellow": [], "other": []}
    map_center = None
    for gid, go in gos.items():
        name = str(go.get("fields", {}).get("m_Name", go.get("name", "")))
        lowered = name.lower()
        group = ""
        if name == "MapCenter":
            wt = get_world_for_go(go)
            if wt:
                map_center = {"name": name, "unity": list(wt[0]), "godot": [-wt[0][0], wt[0][1], wt[0][2]]}
            continue
        if name == "GenericSpawn" or name.startswith("GenericSpawn ("):
            group = "generic"
        elif name == "BlueSpawn" or name.startswith("BlueSpawn ("):
            group = "blue"
        elif name == "YellowSpawn" or name.startswith("YellowSpawn ("):
            group = "yellow"
        elif name == "SpawnPoint" or name.startswith("SpawnPoint ("):
            group = "other"
        if not group:
            continue
        wt = get_world_for_go(go)
        if not wt:
            continue
        pos = wt[0]
        spawn_groups[group].append({
            "name": name,
            "game_object_path_id": int(gid),
            "unity_position": [round(x, 6) for x in pos],
            "godot_position": [round(-pos[0], 6), round(pos[1], 6), round(pos[2], 6)]
        })

    for group in spawn_groups:
        spawn_groups[group].sort(key=lambda item: (item["name"], item["game_object_path_id"]))
    if len(spawn_groups["generic"]) < 3:
        raise SystemExit("Expected at least three original forest GenericSpawn points; found " + str(len(spawn_groups["generic"])))
    if not map_center:
        raise SystemExit("Original forest MapCenter transform not found")

    output = {
        "source_scene": source,
        "map_center": map_center,
        "spawn_groups": spawn_groups
    }
    out = project / "assets" / "combat_source" / "original_forest_spawn_points.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print("ORIGINAL_FOREST_SPAWNS_READY", json.dumps({
        "source_scene": source,
        "map_center": map_center["godot"],
        "generic": len(spawn_groups["generic"]),
        "blue": len(spawn_groups["blue"]),
        "yellow": len(spawn_groups["yellow"]),
        "other": len(spawn_groups["other"])
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
