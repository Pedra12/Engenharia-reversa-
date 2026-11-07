#!/usr/bin/env python3
"""Recover the original level5 Unity NavMesh surface and off-mesh links."""
import argparse
import json
import math
import pathlib

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

def vec3(value, default=(0.0, 0.0, 0.0)):
    if isinstance(value, dict):
        return (float(value.get("x", default[0])), float(value.get("y", default[1])), float(value.get("z", default[2])))
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return tuple(float(x) for x in value[:3])
    return default

def quat(value):
    if isinstance(value, dict):
        return (float(value.get("x", 0)), float(value.get("y", 0)), float(value.get("z", 0)), float(value.get("w", 1)))
    if isinstance(value, (list, tuple)) and len(value) >= 4:
        return tuple(float(x) for x in value[:4])
    return (0.0, 0.0, 0.0, 1.0)

def godot_position(value, origin, rotation):
    rotated = qrotate(rotation, value)
    unity = (rotated[0] + origin[0], rotated[1] + origin[1], rotated[2] + origin[2])
    return [-unity[0], unity[1], unity[2]]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", default="unity_audit")
    ap.add_argument("--project", default="godot_project")
    args = ap.parse_args()
    source_file = pathlib.Path(args.audit) / "UNITY_SCENE_OBJECTS.json"
    if not source_file.is_file():
        raise SystemExit("UNITY_SCENE_OBJECTS.json missing: " + str(source_file))
    records = json.loads(source_file.read_text(encoding="utf-8"))

    settings_record = next((o for o in records if o.get("type") == "NavMeshSettings" and o.get("source") == "level5" and str(o.get("path_id")) == "1930"), None)
    if not settings_record:
        raise SystemExit("Original level5 NavMeshSettings (path 1930) not found")
    settings_fields = settings_record.get("fields", {})
    navmesh_ptr = settings_fields.get("m_NavMeshData", {})
    navmesh_path_id = str(navmesh_ptr.get("m_PathID", ""))
    navmesh_record = next((o for o in records if o.get("type") == "NavMeshData" and o.get("source") == "sharedassets5.assets" and str(o.get("path_id")) == navmesh_path_id), None)
    if not navmesh_record:
        raise SystemExit("NavMeshData referenced by level5 was not found: " + navmesh_path_id)

    fields = navmesh_record.get("fields", {})
    height_meshes = fields.get("m_HeightMeshes", [])
    if not height_meshes:
        raise SystemExit("Original forest NavMeshData has no height mesh")
    height_mesh = height_meshes[0]
    vertices_raw = height_mesh.get("m_Vertices", [])
    indices_raw = height_mesh.get("m_Indices", [])
    if not vertices_raw or len(indices_raw) < 3 or len(indices_raw) % 3:
        raise SystemExit("Original forest height mesh has invalid vertices or triangle indices")

    origin = vec3(fields.get("m_Position"))
    rotation = quat(fields.get("m_Rotation"))
    vertices = [godot_position(vec3(v), origin, rotation) for v in vertices_raw]
    triangles = []
    dropped = 0
    for i in range(0, len(indices_raw), 3):
        a, b, c = (int(indices_raw[i]), int(indices_raw[i + 1]), int(indices_raw[i + 2]))
        if min(a, b, c) < 0 or max(a, b, c) >= len(vertices):
            raise SystemExit("NavMesh triangle references an invalid vertex index")
        pa, pb, pc = vertices[a], vertices[b], vertices[c]
        ux, uy, uz = pb[0] - pa[0], pb[1] - pa[1], pb[2] - pa[2]
        vx, vy, vz = pc[0] - pa[0], pc[1] - pa[1], pc[2] - pa[2]
        normal_y = uz * vx - ux * vz
        area = 0.5 * math.sqrt(
            (uy * vz - uz * vy) ** 2 +
            (uz * vx - ux * vz) ** 2 +
            (ux * vy - uy * vx) ** 2
        )
        if area < 1e-8:
            dropped += 1
            continue
        if normal_y < 0:
            b, c = c, b
        triangles.append([a, b, c])

    links = []
    for link in fields.get("m_OffMeshLinks", []):
        start = godot_position(vec3(link.get("m_Start")), origin, rotation)
        end = godot_position(vec3(link.get("m_End")), origin, rotation)
        links.append({
            "start": [round(x, 6) for x in start],
            "end": [round(x, 6) for x in end],
            "radius": float(link.get("m_Radius", 0.4)),
            "area": int(link.get("m_Area", 0)),
            "direction": int(link.get("m_LinkDirection", 0)),
            "type": int(link.get("m_LinkType", 0))
        })

    build = fields.get("m_NavMeshBuildSettings", {})
    settings = {
        "agent_height": float(build.get("agentHeight", 2.0)),
        "agent_radius": float(build.get("agentRadius", 0.4)),
        "agent_slope": float(build.get("agentSlope", 60.0)),
        "agent_climb": float(build.get("agentClimb", 0.5)),
        "cell_size": float(build.get("cellSize", 0.09)),
        "tile_size": int(build.get("tileSize", 256))
    }
    source_bounds = fields.get("m_SourceBounds", {})
    center = vec3(source_bounds.get("m_Center"))
    extent = vec3(source_bounds.get("m_Extent"))
    bounds = {
        "center": [-center[0], center[1], center[2]],
        "extent": list(extent)
    }
    if len(triangles) < 1000:
        raise SystemExit("Recovered forest navigation surface unexpectedly small: " + str(len(triangles)))

    output = {
        "source_scene": "level5",
        "navmesh_source": navmesh_record.get("source"),
        "navmesh_path_id": navmesh_record.get("path_id"),
        "settings": settings,
        "bounds": bounds,
        "vertices": [[round(x, 6) for x in p] for p in vertices],
        "triangles": triangles,
        "off_mesh_links": links,
        "audit": {
            "unity_tile_count": len(fields.get("m_NavMeshTiles", [])),
            "height_mesh_count": len(height_meshes),
            "vertex_count": len(vertices),
            "triangle_count": len(triangles),
            "dropped_degenerate_triangles": dropped,
            "off_mesh_link_count": len(links)
        }
    }
    out = pathlib.Path(args.project) / "assets" / "combat_source" / "original_forest_navmesh.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(output, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
    print("ORIGINAL_FOREST_NAVMESH_READY", json.dumps(output["audit"] | {"settings": settings, "bounds_center": bounds["center"]}, ensure_ascii=False))

if __name__ == "__main__":
    main()
