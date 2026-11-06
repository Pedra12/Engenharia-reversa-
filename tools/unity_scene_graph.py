#!/usr/bin/env python3
"""Second-pass Unity serialized-object graph audit for the Block Gun archive."""
from __future__ import annotations
import collections, csv, json, pathlib, re, tempfile, zipfile

ARCHIVE = pathlib.Path("blockgun.zip")
OUT = pathlib.Path("scene_graph")
PREFIX = "resources/assets/bin/Data/"
FIELDS = {
 "GameObject": ("m_Component",),
 "Transform": ("m_GameObject","m_Father","m_Children"),
 "RectTransform": ("m_GameObject","m_Father","m_Children"),
 "MeshFilter": ("m_GameObject","m_Mesh"),
 "MeshRenderer": ("m_GameObject","m_Materials"),
 "SkinnedMeshRenderer": ("m_GameObject","m_Materials","m_Mesh","m_Bones","m_RootBone"),
 "MeshCollider": ("m_GameObject","m_Mesh","m_Material"),
 "BoxCollider": ("m_GameObject","m_Material"),
 "SphereCollider": ("m_GameObject","m_Material"),
 "CapsuleCollider": ("m_GameObject","m_Material"),
 "Animator": ("m_GameObject","m_Avatar","m_Controller"),
 "Animation": ("m_GameObject","m_Animations"),
 "Material": ("m_Shader",),
 "LightmapSettings": ("m_Lightmaps",),
 "MonoBehaviour": ("m_GameObject","m_Script"),
 "Rigidbody": ("m_GameObject",), "Light": ("m_GameObject",), "Camera": ("m_GameObject",)
}
TRANSFORMS = {"Transform","RectTransform"}

def typ(o): return getattr(getattr(o,"type",None),"name",str(getattr(o,"type","Unknown")))
def source(o):
 a=getattr(o,"assets_file",None)
 for k in ("name","filename","path"):
  v=getattr(a,k,None)
  if v: return str(v)
 return str(a or "")
def ptr(v):
 if v is None or not hasattr(v,"path_id"): return None
 try:
  p=int(v.path_id)
  return {"file_id":int(getattr(v,"file_id",0) or 0),"path_id":p} if p else None
 except Exception: return None
def refs(v):
 p=ptr(v)
 if p: return [p]
 out=[]
 if isinstance(v,(list,tuple)):
  for x in v: out.extend(refs(x))
 elif isinstance(v,dict):
  for x in v.values(): out.extend(refs(x))
 else:
  for k in ("component","m_Component","first","second","m_Texture","texture","lightmapColor","lightmapDir","shadowMask","m_Lightmaps"):
   try: x=getattr(v,k,None)
   except Exception: x=None
   if x is not None: out.extend(refs(x))
 unique={(x["file_id"],x["path_id"]):x for x in out}
 return list(unique.values())
def val(v):
 if v is None or isinstance(v,(str,int,float,bool)): return v
 if isinstance(v,(list,tuple)): return [val(x) for x in v[:16]]
 d={}
 for k in ("x","y","z","w"):
  try:
   x=getattr(v,k)
   if isinstance(x,(int,float)): d[k]=x
  except Exception: pass
 return d or str(v)[:250]
def attr(d,k):
 try: return getattr(d,k,None)
 except Exception: return None

def vec2(v, fallback):
 try:
  return {"x":float(getattr(v,"x")),"y":float(getattr(v,"y"))}
 except Exception:
  if isinstance(v,dict): return {"x":float(v.get("x",fallback["x"])),"y":float(v.get("y",fallback["y"]))}
  return dict(fallback)
def material_uv_transforms(data):
 """Extract Unity Material m_SavedProperties.m_TexEnvs scale/offset per texture slot."""
 saved=attr(data,"m_SavedProperties"); envs=attr(saved,"m_TexEnvs") or []; out=[]
 for entry in envs:
  key=attr(entry,"first"); value=attr(entry,"second")
  if value is None and isinstance(entry,(list,tuple)) and len(entry)>=2: key,value=entry[0],entry[1]
  if value is None: continue
  out.append({"property":str(key or ""), "Mscale":vec2(attr(value,"m_Scale"),{"x":1.0,"y":1.0}), "Moffset":vec2(attr(value,"m_Offset"),{"x":0.0,"y":0.0}), "texture_path_id":int(getattr(attr(value,"m_Texture"),"path_id",0) or 0)})
 return out

def static_batch_info(d):
 v=attr(d,"m_StaticBatchInfo")
 if v is None: return None
 return {"first_sub_mesh":val(attr(v,"firstSubMesh")),"sub_mesh_count":val(attr(v,"subMeshCount")),"raw":str(v)[:300]}
def safe(s):
 return (re.sub(r"[^A-Za-z0-9._-]+","_",str(s or "unnamed")).strip("._") or "unnamed")[:100]
def main():
 import UnityPy
 from UnityPy.helpers.MeshHelper import MeshHandler
 OUT.mkdir(parents=True,exist_ok=True)
 with zipfile.ZipFile(ARCHIVE) as z:
  members=[n for n in z.namelist() if n.startswith(PREFIX) and not n.endswith("/")]
  groups=collections.defaultdict(list)
  for n in members:
   rel=n[len(PREFIX):]; m=re.match(r"^(.*)\.split(\d+)$",rel)
   if m: groups[m.group(1)].append((int(m.group(2)),n))
  with tempfile.TemporaryDirectory(prefix="blockgun_graph_") as td:
   root=pathlib.Path(td)
   for base,parts in groups.items():
    target=root/base; target.parent.mkdir(parents=True,exist_ok=True)
    with target.open("wb") as dst:
     for _,member in sorted(parts):
      with z.open(member) as src:
       while True:
        b=src.read(1024*1024)
        if not b: break
        dst.write(b)
   for member in members:
    rel=member[len(PREFIX):]
    if rel.endswith((".resource",".ress")) or rel in ("globalgamemanagers","globalgamemanagers.assets","boot.config"):
     target=root/rel; target.parent.mkdir(parents=True,exist_ok=True)
     with z.open(member) as src,target.open("wb") as dst:
      while True:
       b=src.read(1024*1024)
       if not b: break
       dst.write(b)
   env=UnityPy.load(str(root)); objects=list(env.objects)
   records={}; errors=[]; counts=collections.Counter(); external_paths={}; mesh_exports={}; texture_exports={}; uv_channel_records=[]; uv_channel_exports={}
   for i,o in enumerate(objects):
    pid=int(getattr(o,"path_id",i)); t=typ(o); src=source(o)
    try:
     af=getattr(o,"assets_file",None)
     exts=getattr(af,"externals",[]) or []
     paths=[]
     for ext in exts:
      ep=getattr(ext,"path",None) or getattr(ext,"name",None) or str(ext)
      paths.append(str(ep).replace("\\\\","/").rsplit("/",1)[-1])
     external_paths[src]=paths
     d=o.read(); name=attr(d,"m_Name") or attr(d,"name") or ""
     if t=="Texture2D":
      try:
       image=d.image
       if image:
        texture_dir=OUT/"exported_textures"; texture_dir.mkdir(parents=True,exist_ok=True)
        texture_name=f"{safe(src)}__{pid}__{safe(name or 'texture')}.png"
        image.save(texture_dir/texture_name)
        texture_exports[(src,pid)]=str(pathlib.Path("exported_textures")/texture_name)
      except Exception as texture_error:
       errors.append({"source":src,"path_id":pid,"type":t,"error":"texture export: "+str(texture_error)[:220]})
     uv_summary={}
     if t=="Mesh":
      try:
       # Unity stores modern mesh UVs in interleaved VertexData streams. MeshHandler
       # decodes those streams (and compressed meshes) before OBJ export.
       uv_payload={}
       if str(name).startswith("umsh_india_") or (str(src)=="level7" and int(pid)==1):
        handler=MeshHandler(d)
        handler.process()
        for channel in range(8):
         raw_uv=getattr(handler,f"m_UV{channel}",None)
         if raw_uv is None: continue
         uv_values=list(raw_uv)
         uv_summary[str(channel)]={"count":len(uv_values),"dimension":len(uv_values[0]) if uv_values else 0,"sample":[list(x) for x in uv_values[:4]]}
         if channel in (0,1):
          uv_payload[f"m_UV{channel}"]=[list(x) for x in uv_values]
       if uv_summary:
        uv_channel_records.append({"source":src,"path_id":pid,"name":str(name),"channels":uv_summary})
       if uv_payload:
        uv_dir=OUT/"uv_channels"; uv_dir.mkdir(parents=True,exist_ok=True)
        uv_name=f"{safe(src)}__{pid}__{safe(name or 'mesh')}.uv.json"
        (uv_dir/uv_name).write_text(json.dumps(uv_payload,separators=(",",":")),encoding="utf-8")
        uv_channel_exports[(src,pid)]=str(pathlib.Path("uv_channels")/uv_name)
       exported=d.export()
       payload=exported if isinstance(exported,bytes) else str(exported).encode("utf-8")
       mesh_dir=OUT/"exported_meshes"; mesh_dir.mkdir(parents=True,exist_ok=True)
       mesh_name=f"{safe(src)}__{pid}__{safe(name or 'mesh')}.obj"
       (mesh_dir/mesh_name).write_bytes(payload)
       mesh_exports[(src,pid)]=str(pathlib.Path("exported_meshes")/mesh_name)
      except Exception as mesh_error:
       errors.append({"source":src,"path_id":pid,"type":t,"error":"mesh export: "+str(mesh_error)[:220]})
     r={"source":src,"path_id":pid,"type":t,"name":str(name)[:220],"refs":[]}
     if t=="MeshRenderer":
      r["static_batch_info"]=static_batch_info(d)
      # Preserve Unity's baked-lighting metadata so lightmaps can be mapped
      # to the correct static-batched submesh instead of guessed by filename.
      for field in ("m_LightmapIndex","m_LightmapST","m_LightmapScaleOffset","m_LightmapTilingOffset",
                    "m_ReceiveGI","m_ReceiveShadows","m_ReflectionProbeUsage",
                    "m_LightProbeUsage","m_ScaleInLightmap","m_StitchSeams"):
       value=attr(d,field)
       if value is not None: r[field]=val(value)
     if t=="LightmapSettings":
      r["lightmap_mode"]=val(attr(d,"m_LightmapsMode"))
      r["lightmaps_count"]=len(attr(d,"m_Lightmaps") or [])
     if t=="Mesh":
      r["uv_channels"]=uv_summary
      if (src,pid) in uv_channel_exports: r["uv_channel_export"]=uv_channel_exports[(src,pid)]
     counts[t]+=1
     for f in FIELDS.get(t,()):
      for p in refs(attr(d,f)):
       fid=p["file_id"]
       target_source=src if fid==0 else (paths[fid-1] if 0 < fid <= len(paths) else "")
       r["refs"].append({"field":f,"file_id":fid,"path_id":p["path_id"],"target_source":target_source})
     if t=="Material":
      r["unity_uv_transforms"]=material_uv_transforms(d)
      saved=attr(d,"m_SavedProperties")
      for prop in ("m_TexEnvs",):
       for p in refs(attr(saved,prop)):
        fid=p["file_id"]; target_source=src if fid==0 else (paths[fid-1] if 0 < fid <= len(paths) else "")
        r["refs"].append({"field":prop,"file_id":fid,"path_id":p["path_id"],"target_source":target_source})
     if t in TRANSFORMS:
      for f in ("m_LocalPosition","m_LocalRotation","m_LocalScale"): r[f]=val(attr(d,f))
      p=refs(attr(d,"m_Father")); r["parent"]=p[0]["path_id"] if p else 0
      r["children"]=[x["path_id"] for x in refs(attr(d,"m_Children"))]
      g=refs(attr(d,"m_GameObject")); r["game_object"]=g[0]["path_id"] if g else None
     elif t=="GameObject":
      r["active"]=val(attr(d,"m_IsActive")); r["layer"]=val(attr(d,"m_Layer")); r["tag"]=val(attr(d,"m_Tag"))
      r["components"]=[x["path_id"] for x in refs(attr(d,"m_Component"))]
     elif t in ("MeshFilter","SkinnedMeshRenderer","MeshCollider"):
      m=refs(attr(d,"m_Mesh")); r["mesh_path_id"]=m[0]["path_id"] if m else None
      r["materials"]=[x["path_id"] for x in refs(attr(d,"m_Materials"))]
     records[(src,pid)]=r
    except Exception as e: errors.append({"source":src,"path_id":pid,"type":t,"error":str(e)[:250]})
   (OUT/"UNITY_UV_CHANNEL_AUDIT.json").write_text(json.dumps(uv_channel_records,ensure_ascii=False,indent=2),encoding="utf-8")
   index={(r["source"],r["path_id"]):r for r in records.values()}
   edges=[]; hierarchy=[]; roots=[]
   for r in records.values():
    for p in r["refs"]:
     target=index.get((p.get("target_source") or r["source"],p["path_id"]))
     edges.append({"source_file":r["source"],"from_path_id":r["path_id"],"from_type":r["type"],"from_name":r["name"],"field":p["field"],"file_id":p["file_id"],"to_path_id":p["path_id"],"target_source":p.get("target_source",""),"to_type":target["type"] if target else "UNRESOLVED_OR_EXTERNAL","to_name":target["name"] if target else ""})
    if r["type"] in TRANSFORMS:
     go=index.get((r["source"],r.get("game_object")))
     parent=index.get((r["source"],r.get("parent"))) if r.get("parent") else None
     item={"source":r["source"],"transform_path_id":r["path_id"],"game_object_path_id":r.get("game_object"),"name":go["name"] if go else r["name"],"parent_transform_path_id":r.get("parent",0),"parent_name":"","position":r.get("m_LocalPosition"),"rotation":r.get("m_LocalRotation"),"scale":r.get("m_LocalScale"),"component_path_ids":go.get("components",[]) if go else []}
     if parent:
      pg=index.get((r["source"],parent.get("game_object"))); item["parent_name"]=pg["name"] if pg else parent["name"]
     else: roots.append(item)
     hierarchy.append(item)
   # Build per-level manifests from recovered Transform -> GameObject -> Component links.
   map_manifests=[]
   for level in [f"level{i}" for i in range(1,10)]:
    level_transforms={int(r["path_id"]):r for r in records.values() if r["source"]==level and r["type"] in TRANSFORMS}
    level_gameobjects={int(r["path_id"]):r for r in records.values() if r["source"]==level and r["type"]=="GameObject"}
    level_components={int(r["path_id"]):r for r in records.values() if r["source"]==level and r["type"] not in TRANSFORMS and r["type"]!="GameObject"}
    map_root=next((r for r in level_transforms.values() if r.get("parent",0)==0 and (level_gameobjects.get(r.get("game_object")) or {}).get("name","").startswith("lvl_")),None)
    if not map_root: continue
    def component_info(cid):
     c=level_components.get(int(cid))
     if not c: return {"path_id":int(cid),"type":"UNKNOWN"}
     info={"path_id":int(cid),"type":c["type"],"name":c["name"],"references":[]}
     if c.get("static_batch_info") is not None: info["static_batch_info"]=c["static_batch_info"]
     for field in ("m_LightmapIndex","m_LightmapST","m_LightmapScaleOffset","m_LightmapTilingOffset",
                   "m_ReceiveGI","m_ReceiveShadows","m_ReflectionProbeUsage",
                   "m_LightProbeUsage","m_ScaleInLightmap","m_StitchSeams"):
      if field in c: info[field]=c[field]
     for ref in c.get("refs",[]):
      target_source=ref.get("target_source") or level
      entry={"field":ref["field"],"target_source":target_source,"target_path_id":ref["path_id"]}
      if ref["field"]=="m_Mesh":
       entry["exported_obj"]=mesh_exports.get((target_source,ref["path_id"]))
      info["references"].append(entry)
      if c["type"] in ("MeshRenderer","SkinnedMeshRenderer") and ref["field"]=="m_Materials":
       material=index.get((target_source,ref["path_id"]))
       if material:
        info.setdefault("material_resources",[]).append({
         "source":target_source,"path_id":ref["path_id"],"name":material["name"],
         "textures":[{"source":x.get("target_source"),"path_id":x["path_id"],"exported_png":texture_exports.get((x.get("target_source"),x["path_id"]))} for x in material.get("refs",[]) if x["field"]=="m_TexEnvs"],
         "unity_uv_transforms":material.get("unity_uv_transforms",[]),
         "shader_refs":[{"source":x.get("target_source"),"path_id":x["path_id"]} for x in material.get("refs",[]) if x["field"]=="m_Shader"]
        })
     return info
    def build_node(tid,seen):
     if tid in seen: return {"error":"cycle","transform_path_id":tid}
     seen=seen|{tid}; tr=level_transforms[tid]; go=level_gameobjects.get(tr.get("game_object"))
     node={"name":go["name"] if go else tr["name"],"transform_path_id":tid,"game_object_path_id":tr.get("game_object"),"position":tr.get("m_LocalPosition"),"rotation":tr.get("m_LocalRotation"),"scale":tr.get("m_LocalScale"),"active":go.get("active") if go else None,"layer":go.get("layer") if go else None,"tag":go.get("tag") if go else None,"components":[component_info(cid) for cid in (go.get("components",[]) if go else [])],"children":[]}
     for child_id in tr.get("children",[]):
      if int(child_id) in level_transforms: node["children"].append(build_node(int(child_id),seen))
     return node
    root_go=level_gameobjects.get(map_root.get("game_object"))
    map_name=root_go["name"] if root_go else map_root["name"]
    manifest={"source_level":level,"map_root":map_name,"root_transform_path_id":int(map_root["path_id"]),"node_count":0,"mesh_exports":sorted({v for v in mesh_exports.values()}),"root":build_node(int(map_root["path_id"]),set())}
    def count_nodes(n):
     return 1+sum(count_nodes(c) for c in n.get("children",[]))
    manifest["node_count"]=count_nodes(manifest["root"])
    map_dir=OUT/"maps"; map_dir.mkdir(parents=True,exist_ok=True)
    out_name=safe(map_name)+".json"
    (map_dir/out_name).write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    map_manifests.append({"level":level,"map":map_name,"nodes":manifest["node_count"],"file":str(pathlib.Path("maps")/out_name)})
   def write_csv(path,rows):
    rows=list(rows)
    if not rows: path.write_text("no_data\n",encoding="utf-8"); return
    keys=sorted({k for x in rows for k in x})
    with path.open("w",newline="",encoding="utf-8") as f:
     w=csv.DictWriter(f,fieldnames=keys); w.writeheader()
     for x in rows:
      w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in x.items()})
   write_csv(OUT/"UNITY_RELATIONAL_OBJECTS.csv",records.values())
   write_csv(OUT/"UNITY_REFERENCE_EDGES.csv",edges)
   write_csv(OUT/"UNITY_TRANSFORM_HIERARCHY.csv",hierarchy)
   write_csv(OUT/"UNITY_SCENE_ROOT_CANDIDATES.csv",roots)
   summary={"serialized_objects_read":len(records),"types":dict(counts.most_common()),"reference_edges":len(edges),"transform_objects":len(hierarchy),"root_transform_candidates":len(roots),"errors":len(errors),"split_families":len(groups),"split_chunks":sum(map(len,groups.values())),"exported_meshes":len(mesh_exports),"exported_textures":len(texture_exports),"map_manifests":map_manifests,"source_files":sorted({r["source"] for r in records.values()})}
   (OUT/"UNITY_SCENE_GRAPH.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
   (OUT/"UNITY_SCENE_GRAPH_ERRORS.json").write_text(json.dumps(errors[:5000],ensure_ascii=False,indent=2),encoding="utf-8")
   lines=["# Segunda passagem: grafo relacional Unity","",f"- Objetos lidos: **{len(records)}**",f"- Tipos: **{len(counts)}**",f"- Referências PPtr: **{len(edges)}**",f"- Transform/RectTransform: **{len(hierarchy)}**",f"- Candidatos a raízes: **{len(roots)}**",f"- Erros de leitura: **{len(errors)}**",f"- Famílias split: **{len(groups)}**",f"- Partes split: **{summary['split_chunks']}**","","## Arquivos","- UNITY_RELATIONAL_OBJECTS.csv: objetos, IDs, origem, componentes e referências.","- UNITY_REFERENCE_EDGES.csv: relações entre objetos, incluindo o arquivo externo de destino quando resolvido.","- UNITY_TRANSFORM_HIERARCHY.csv: pai/filhos e transformações locais.","- UNITY_SCENE_ROOT_CANDIDATES.csv: raízes candidatas.","- UNITY_SCENE_GRAPH.json: resumo e arquivos de origem.","- UNITY_SCENE_GRAPH_ERRORS.json: amostra de erros.","- maps/: manifestos hierárquicos de cada mapa identificado.","- exported_meshes/: malhas OBJ exportadas com origem e path_id únicos.","- exported_textures/: texturas PNG exportadas com origem e path_id únicos.","","## Limitações","- Referências PPtr externas são resolvidas usando a tabela de arquivos externos do SerializedFile quando disponível.","- Uma raiz de Transform não prova que seja uma cena jogável.","- A reconstrução exige validar materiais, colisões, recursos externos e geometria.","- Este relatório não converte cenas Unity automaticamente para Godot."]
   (OUT/"UNITY_SCENE_GRAPH.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
   print("\n".join(lines))
   print("TYPE_COUNTS",json.dumps(counts.most_common(),ensure_ascii=False))
   print("ERROR_SAMPLE",json.dumps(errors[:20],ensure_ascii=False))
if __name__=="__main__": main()
