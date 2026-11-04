#!/usr/bin/env python3
"""Deep per-map audit: hierarchy, collision refs, exported geometry and missing assets."""
import json,csv,pathlib,re,collections
ROOT=pathlib.Path("scene_graph/maps"); GRAPH=pathlib.Path("scene_graph"); OUT=pathlib.Path("inventory_out")
OUT.mkdir(exist_ok=True)
PAT={"stairs":re.compile(r"stair|stairs|step|escad|degrau|ladder",re.I),
     "interior":re.compile(r"interior|inside|room|house|building|floor|hall|corridor|door|window|office|kitchen|bed|wall|roof|basement|loft",re.I)}
def obj_stats(path):
 p=GRAPH/path
 if not p.exists(): return {"missing":True,"vertices":0,"faces":0}
 v=fc=0
 try:
  with p.open(errors="ignore") as src:
   for line in src:
    if line.startswith("v "): v+=1
    elif line.startswith("f "): fc+=1
 except OSError: return {"missing":True,"vertices":0,"faces":0}
 return {"missing":False,"vertices":v,"faces":fc}
def main():
 reports=[]; global_missing=0
 for f in sorted(ROOT.glob("*.json")):
  d=json.loads(f.read_text()); counts=collections.Counter(); stairs=[]; interiors=[]; missing=[]; colliders=[]; materials=set(); textures=set(); meshrefs=set(); geometry={}
  def walk(n,path=""):
   name=str(n.get("name","")); p=path+"/"+name; comps=n.get("components",[]); counts["nodes"]+=1
   if PAT["stairs"].search(name): stairs.append(p)
   if PAT["interior"].search(name): interiors.append(p)
   for c in comps:
    typ=c.get("type",""); counts[typ]+=1
    for ref in c.get("references",[]):
     obj=ref.get("exported_obj")
     if obj:
      meshrefs.add(obj)
      if ref.get("field")=="m_Mesh" and typ=="MeshCollider": colliders.append({"node":name,"mesh":obj,"stats":obj_stats(obj)})
      if not (GRAPH/obj).exists(): missing.append(obj)
     png=ref.get("exported_png")
     if png:
      textures.add(png)
      if not (GRAPH/png).exists(): missing.append(png)
    for m in c.get("material_resources",[]):
     materials.add((m.get("source"),m.get("path_id"),m.get("name")))
     for t in m.get("textures",[]):
      png=t.get("exported_png")
      if png:
       textures.add(png)
       if not (GRAPH/png).exists(): missing.append(png)
   for ch in n.get("children",[]): walk(ch,p)
  walk(d.get("root",{}))
  # Include all level-specific combined geometry exported for this map, not only named hierarchy nodes.
  level=d.get("source_level","")
  level_meshes=sorted(str(p.relative_to(GRAPH)) for p in (GRAPH/"exported_meshes").glob(level+"__*.obj")) if (GRAPH/"exported_meshes").exists() else []
  for obj in level_meshes: geometry[obj]=obj_stats(obj)
  report={"map":f.stem,"unity_level":level,"nodes":counts["nodes"],"meshfilters":counts["MeshFilter"],"renderers":counts["MeshRenderer"],"meshcolliders":counts["MeshCollider"],"referenced_meshes":len(meshrefs),"level_combined_meshes":len(level_meshes),"level_vertices":sum(x["vertices"] for x in geometry.values()),"level_faces":sum(x["faces"] for x in geometry.values()),"materials":len(materials),"textures":len([x for x in textures if x]),"stairs_named":len(stairs),"interior_named":len(interiors),"missing_exports":len(set(missing)),"stair_candidates":stairs[:100],"interior_candidates":interiors[:250],"collider_meshes":colliders,"geometry_files":geometry,"missing_assets":sorted(set(missing))}
  reports.append(report); global_missing+=report["missing_exports"]
  (OUT/(f.stem+"_QUALITY_AUDIT.json")).write_text(json.dumps(report,indent=2,ensure_ascii=False))
  print("MAP_QUALITY_AUDIT",json.dumps({k:v for k,v in report.items() if not isinstance(v,(list,dict))},ensure_ascii=False))
 summary={"maps":len(reports),"missing_asset_references":global_missing,"results":reports}
 (OUT/"BLOCKGUN_MAP_QUALITY_AUDIT.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False))
 keys=["map","unity_level","nodes","meshfilters","renderers","meshcolliders","referenced_meshes","level_combined_meshes","level_vertices","level_faces","materials","textures","stairs_named","interior_named","missing_exports"]
 with (OUT/"BLOCKGUN_MAP_QUALITY_AUDIT.csv").open("w",newline="",encoding="utf-8") as f:
  w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows({k:r[k] for k in keys} for r in reports)
 print("BLOCKGUN_QUALITY_AUDIT_DONE maps=",len(reports),"missing=",global_missing)
if __name__=="__main__":main()
