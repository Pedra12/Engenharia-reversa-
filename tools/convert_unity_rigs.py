#!/usr/bin/env python3
"""Rebuild original Unity skinned meshes and Avatar skeletons for Godot 4."""
import argparse, base64, json, math, pathlib, re, struct, sys
from collections import OrderedDict

FORMAT_SIZE={0:4,1:2,2:1,3:1,4:2,5:2,6:1,7:1,8:2,9:2,10:4,11:4}

def read_json(path):
    return json.loads(pathlib.Path(path).read_text(encoding="utf-8"))

def align16(v):
    return (v+15)//16*16

def decode_skin(fields):
    vd=fields["m_VertexData"]; count=int(vd["m_VertexCount"])
    blob=base64.b64decode(vd["m_DataSize"]["base64"])
    channels=vd["m_Channels"]
    strides={}
    for ch in channels:
        dim=int(ch.get("dimension",0) or 0)
        if dim<=0: continue
        size=FORMAT_SIZE[int(ch["format"])]*dim
        stream=int(ch["stream"])
        strides[stream]=max(strides.get(stream,0),int(ch["offset"])+size)
    offsets={}; cursor=0
    for stream in sorted(strides):
        cursor=align16(cursor); offsets[stream]=cursor; cursor+=strides[stream]*count
    if cursor>len(blob):
        raise ValueError(f"vertex data truncated: expected {cursor}, got {len(blob)}")
    wc,ic=channels[12],channels[13]
    if int(wc.get("dimension",0))<1 or int(ic.get("dimension",0))<1:
        raise ValueError("blend weights or indices channels missing")
    weights=[]; indices=[]
    for vi in range(count):
        wo=offsets[int(wc["stream"])]+vi*strides[int(wc["stream"])]+int(wc["offset"])
        io=offsets[int(ic["stream"])]+vi*strides[int(ic["stream"])]+int(ic["offset"])
        wd=int(wc["dimension"]); idim=int(ic["dimension"])
        w=list(struct.unpack_from("<"+"f"*wd,blob,wo))
        b=list(struct.unpack_from("<"+"I"*idim,blob,io))
        w=(w+[0.0]*4)[:4]; b=(b+[0]*4)[:4]
        total=sum(w)
        if total>1e-8: w=[x/total for x in w]
        else: w=[1.0,0.0,0.0,0.0]; b=[0,0,0,0]
        weights.append(w); indices.append(b)
    return count,weights,indices

def obj_index(raw, length):
    n=int(raw)
    return n-1 if n>0 else length+n

def parse_obj(path,weights,bone_indices,expected_vertices):
    positions=[]; uvs=[]; normals=[]
    surfaces=OrderedDict(); group="default"
    for line in pathlib.Path(path).read_text(encoding="utf-8",errors="replace").splitlines():
        line=line.strip()
        if not line or line.startswith("#"): continue
        if line.startswith("v "):
            p=line.split(); positions.append([float(x) for x in p[1:4]])
        elif line.startswith("vt "):
            p=line.split(); uvs.append([float(x) for x in p[1:3]])
        elif line.startswith("vn "):
            p=line.split(); normals.append([float(x) for x in p[1:4]])
        elif line.startswith("g "):
            group=line[2:].strip() or "default"
        elif line.startswith("f "):
            tokens=line.split()[1:]
            if len(tokens)<3: continue
            surfaces.setdefault(group,[])
            verts=[]
            for token in tokens:
                parts=token.split("/")
                vi=obj_index(parts[0],len(positions))
                ti=obj_index(parts[1],len(uvs)) if len(parts)>1 and parts[1] else -1
                ni=obj_index(parts[2],len(normals)) if len(parts)>2 and parts[2] else -1
                verts.append((vi,ti,ni))
            for i in range(1,len(verts)-1):
                surfaces[group].append((verts[0],verts[i],verts[i+1]))
    if len(positions)!=expected_vertices:
        raise ValueError(f"OBJ vertex count {len(positions)} != Unity vertex count {expected_vertices}")
    out=[]
    for group_name,triangles in surfaces.items():
        local=OrderedDict(); verts=[]; nrm=[]; uv=[]; bones=[]; wts=[]; indices=[]
        for tri in triangles:
            for key in tri:
                if key not in local:
                    local[key]=len(verts); vi,ti,ni=key
                    verts.append(positions[vi])
                    nrm.append(normals[ni] if 0<=ni<len(normals) else [0.0,1.0,0.0])
                    uv.append(uvs[ti] if 0<=ti<len(uvs) else [0.0,0.0])
                    bones.append(bone_indices[vi]); wts.append(weights[vi])
                indices.append(local[key])
        m=re.search(r"_(\d+)$",group_name)
        material_index=int(m.group(1)) if m else len(out)
        out.append({"group":group_name,"material_index":material_index,"vertices":verts,"normals":nrm,"uvs":uv,"bones":bones,"weights":wts,"indices":indices})
    if not out: raise ValueError("OBJ has no triangle surfaces")
    return out

def vec3(v,default=(0,0,0)):
    if isinstance(v,dict): return [float(v.get("x",0)),float(v.get("y",0)),float(v.get("z",0))]
    if isinstance(v,(list,tuple)): return [float(x) for x in v[:3]]
    return list(default)

def quat(v):
    if isinstance(v,dict): return [float(v.get("x",0)),float(v.get("y",0)),float(v.get("z",0)),float(v.get("w",1))]
    if isinstance(v,(list,tuple)): return [float(x) for x in v[:4]]
    return [0,0,0,1]

def position3(v,default=(0,0,0)):
    out=vec3(v,default)
    out[0]=-out[0]
    return out

def quat_godot(v):
    q=quat(v)
    return [q[0],-q[1],-q[2],q[3]]

def bindpose_godot(value):
    matrix=value.get("matrix4x4",value) if isinstance(value,dict) else value
    if isinstance(matrix,(list,tuple)) and len(matrix)==16 and not isinstance(matrix[0],(list,tuple)):
        matrix=[matrix[i:i+4] for i in range(0,16,4)]
    if not isinstance(matrix,(list,tuple)) or len(matrix)<4:
        return matrix
    # UnityPy exports mesh vertices with X mirrored. Conjugate inverse-bind
    # matrices by the same reflection S=diag(-1,1,1,1): M_godot = S*M_unity*S.
    result=[]
    for i in range(4):
        row=[]
        for j in range(4):
            sign=(-1.0 if i==0 else 1.0)*(-1.0 if j==0 else 1.0)
            row.append(float(matrix[i][j])*sign)
        result.append(row)
    return result

def transform_record(rec):
    if not rec: return {"position":[0,0,0],"rotation":[0,0,0,1],"scale":[1,1,1],"name":""}
    f=rec.get("fields",{})
    return {"position":position3(f.get("m_LocalPosition")),"rotation":quat_godot(f.get("m_LocalRotation")),
            "scale":vec3(f.get("m_LocalScale",(1,1,1)),(1,1,1)),
            "name":rec.get("name",""),"path_id":rec.get("path_id"),"source":rec.get("source")}

def build_rig(mesh_record,avatar_record,rig_hierarchy,mesh_path,texture_paths):
    f=mesh_record["fields"]; af=avatar_record["fields"]; av=af["m_Avatar"]
    avatar_ids=av["m_AvatarSkeleton"]["data"]["m_ID"]
    avatar_nodes=av["m_AvatarSkeleton"]["data"]["m_Node"]
    avatar_pose=av["m_AvatarSkeletonPose"]["data"]["m_X"]
    tos={int(k):str(v) for k,v in af.get("m_TOS",[])}
    id_to_index={int(h):i for i,h in enumerate(avatar_ids)}
    bones=[]
    for i,h in enumerate(avatar_ids):
        path=tos.get(int(h),"")
        short=path.split("/")[-1] if path else ("UnityRoot" if i==0 else f"bone_{i}")
        parent=int(avatar_nodes[i].get("m_ParentId",-1))
        p=avatar_pose[i]
        bones.append({"name":short,"path":path,"hash":int(h),"parent":parent,
            "position":position3(p.get("t")),"rotation":quat_godot(p.get("q")),"scale":vec3(p.get("s"),(1,1,1))})
    hashes=[int(x) for x in f.get("m_BoneNameHashes",[])]
    mesh_bone_to_avatar=[id_to_index.get(h,0) for h in hashes]
    bindposes=[]
    for bp in f.get("m_BindPose",[]):
        bindposes.append(bindpose_godot(bp))
    if len(bindposes)!=len(mesh_bone_to_avatar):
        raise ValueError(f"{mesh_record['name']}: bind pose count {len(bindposes)} != mesh bone count {len(mesh_bone_to_avatar)}")
    vertex_count,weights,bone_indices=decode_skin(f)
    for row, weight_row in zip(bone_indices,weights):
        for b,w in zip(row,weight_row):
            if w>1e-6 and b>=len(hashes):
                raise ValueError(f"{mesh_record['name']}: weighted vertex bone index {b} exceeds {len(hashes)}")
    surfaces=parse_obj(mesh_path,weights,bone_indices,vertex_count)
    renderer=next((x for x in rig_hierarchy.get("renderers",[]) if x.get("mesh_name")==mesh_record["name"]),None)
    mesh_tr=renderer.get("mesh_transform") if renderer else None
    transforms={(x.get("source"),str(x.get("path_id"))):x for x in rig_hierarchy.get("transforms",[])}
    root=renderer.get("root_bone",{}) if renderer else {}
    root_tr=transforms.get((root.get("source"),str(root.get("path_id"))))
    skeleton_tr=None
    if root_tr:
        father=root_tr.get("fields",{}).get("m_Father",{})
        src=root_tr.get("source","")
        ext=root_tr.get("external_files",[])
        fid=int(father.get("m_FileID",0) or 0)
        if fid>0 and fid<=len(ext): src=ext[fid-1].get("path",src)
        skeleton_tr=transforms.get((src,str(father.get("m_PathID","0"))))
    parent_tr=None
    if mesh_tr:
        father=mesh_tr.get("fields",{}).get("m_Father",{})
        src=mesh_tr.get("source",""); ext=mesh_tr.get("external_files",[])
        fid=int(father.get("m_FileID",0) or 0)
        if fid>0 and fid<=len(ext): src=ext[fid-1].get("path",src)
        parent_tr=transforms.get((src,str(father.get("m_PathID","0"))))
    return {"name":mesh_record["name"],"avatar":avatar_record["name"],"vertex_count":vertex_count,
        "bones":bones,"mesh_bone_to_avatar":mesh_bone_to_avatar,"bind_poses":bindposes,
        "surfaces":surfaces,"mesh_transform":transform_record(mesh_tr),
        "skeleton_transform":transform_record(skeleton_tr),"model_parent_transform":transform_record(parent_tr),
        "textures":texture_paths}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--audit",default="unity_audit")
    ap.add_argument("--project",default="godot_project")
    args=ap.parse_args()
    audit=pathlib.Path(args.audit); project=pathlib.Path(args.project)
    skin=read_json(audit/"UNITY_SKINNING_DATA.json")
    anim=read_json(audit/"UNITY_ANIMATOR_DATA.json")
    hierarchy=read_json(audit/"UNITY_RIG_HIERARCHY.json")
    avatars={x["name"]:x for x in anim["avatars"]}
    mesh_specs={
      "sk_char_sold_male_01":("Character_BitGunAvatar",["SimpleMilitary_Soldier01_Black"]),
      "sk_gloves":("sk_bomb_anim_fpAvatar",["gloves-diffuse","arm-diffuse"]),
      "sk_bomb_fp":("sk_bomb_anim_fpAvatar",[])
    }
    mesh_dir=audit/"exported"/"meshes"
    texture_dir=project/"assets"/"unity_original"/"textures"
    rigs={}
    for mesh_name,(avatar_name,texture_tokens) in mesh_specs.items():
        record=next((x for x in skin if x.get("name")==mesh_name),None)
        if not record: raise SystemExit(f"Original skin data missing: {mesh_name}")
        matches=sorted(mesh_dir.glob(f"*_Mesh_{mesh_name}.obj"))
        if not matches:
            matches=sorted((audit/"source_assets"/"meshes").glob(f"*{mesh_name}*.obj"))
        if not matches: raise SystemExit(f"Original mesh OBJ missing: {mesh_name}")
        texture_paths=[]
        for token in texture_tokens:
            candidates=sorted(texture_dir.glob(f"*{token}*.png"))
            if not candidates: candidates=sorted((audit/"exported"/"textures").glob(f"*{token}*.png"))
            if candidates: texture_paths.append(candidates[0].name)
            else: texture_paths.append("")
        rigs[mesh_name]=build_rig(record,avatars[avatar_name],hierarchy,matches[0],texture_paths)
    out=project/"assets"/"combat_source"/"original_rigs.json"
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(rigs,separators=(",",":"),ensure_ascii=False),encoding="utf-8")
    print("ORIGINAL_RIGS_READY",[(k,v["vertex_count"],len(v["bones"]),len(v["surfaces"])) for k,v in rigs.items()])

if __name__=="__main__":
    main()
