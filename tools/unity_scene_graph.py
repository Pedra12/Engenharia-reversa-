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
  for k in ("component","m_Component","first","second"):
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
def main():
 import UnityPy
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
   records={}; errors=[]; counts=collections.Counter(); external_paths={}
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
     r={"source":src,"path_id":pid,"type":t,"name":str(name)[:220],"refs":[]}
     counts[t]+=1
     for f in FIELDS.get(t,()):
      for p in refs(attr(d,f)):
       fid=p["file_id"]
       target_source=src if fid==0 else (paths[fid-1] if 0 < fid <= len(paths) else "")
       r["refs"].append({"field":f,"file_id":fid,"path_id":p["path_id"],"target_source":target_source})
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
   summary={"serialized_objects_read":len(records),"types":dict(counts.most_common()),"reference_edges":len(edges),"transform_objects":len(hierarchy),"root_transform_candidates":len(roots),"errors":len(errors),"split_families":len(groups),"split_chunks":sum(map(len,groups.values())),"source_files":sorted({r["source"] for r in records.values()})}
   (OUT/"UNITY_SCENE_GRAPH.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
   (OUT/"UNITY_SCENE_GRAPH_ERRORS.json").write_text(json.dumps(errors[:5000],ensure_ascii=False,indent=2),encoding="utf-8")
   lines=["# Segunda passagem: grafo relacional Unity","",f"- Objetos lidos: **{len(records)}**",f"- Tipos: **{len(counts)}**",f"- Referências PPtr: **{len(edges)}**",f"- Transform/RectTransform: **{len(hierarchy)}**",f"- Candidatos a raízes: **{len(roots)}**",f"- Erros de leitura: **{len(errors)}**",f"- Famílias split: **{len(groups)}**",f"- Partes split: **{summary['split_chunks']}**","","## Arquivos","- UNITY_RELATIONAL_OBJECTS.csv: objetos, IDs, origem, componentes e referências.","- UNITY_REFERENCE_EDGES.csv: relações entre objetos, incluindo o arquivo externo de destino quando resolvido.","- UNITY_TRANSFORM_HIERARCHY.csv: pai/filhos e transformações locais.","- UNITY_SCENE_ROOT_CANDIDATES.csv: raízes candidatas.","- UNITY_SCENE_GRAPH.json: resumo e arquivos de origem.","- UNITY_SCENE_GRAPH_ERRORS.json: amostra de erros.","","## Limitações","- Referências PPtr externas são resolvidas usando a tabela de arquivos externos do SerializedFile quando disponível.","- Uma raiz de Transform não prova que seja uma cena jogável.","- A reconstrução exige validar materiais, colisões, recursos externos e geometria.","- Este relatório não converte cenas Unity automaticamente para Godot."]
   (OUT/"UNITY_SCENE_GRAPH.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
   print("\n".join(lines))
   print("TYPE_COUNTS",json.dumps(counts.most_common(),ensure_ascii=False))
   print("ERROR_SAMPLE",json.dumps(errors[:20],ensure_ascii=False))
if __name__=="__main__": main()
