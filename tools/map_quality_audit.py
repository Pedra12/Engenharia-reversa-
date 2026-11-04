#!/usr/bin/env python3
"""Deep per-map audit report for recovered Unity hierarchy and Godot assets."""
import json,csv,pathlib,re,collections
ROOT=pathlib.Path("scene_graph/maps"); OUT=pathlib.Path("inventory_out")
OUT.mkdir(exist_ok=True)
PAT={
 "stairs":re.compile(r"stair|stairs|step|escad|degrau",re.I),
 "interior":re.compile(r"interior|inside|room|house|building|floor|hall|corridor|door|window|office|kitchen|bed|wall|roof|basement|loft",re.I),
 "terrain":re.compile(r"terrain|ground|floor|road|street|grass|sand|water|rock|mount|tree|forest",re.I),
}
def main():
 reports=[]; global_missing=0
 for f in sorted(ROOT.glob("*.json")):
  d=json.loads(f.read_text()); counts=collections.Counter(); stairs=[]; interiors=[]; missing=[]; collider_refs=[]; materials=set(); textures=set(); meshes=set()
  def walk(n,path=""):
   name=str(n.get("name","")); p=path+"/"+name; comps=n.get("components",[])
   counts["nodes"]+=1
   if PAT["stairs"].search(name): stairs.append(p)
   if PAT["interior"].search(name): interiors.append(p)
   for c in comps:
    typ=c.get("type",""); counts[typ]+=1
    for ref in c.get("references",[]):
     obj=ref.get("exported_obj")
     if obj:
      meshes.add(obj)
      if not pathlib.Path("scene_graph",obj).exists(): missing.append(obj)
     if ref.get("field")=="m_Mesh" and typ=="MeshCollider": collider_refs.append((name,ref.get("target_path_id")))
    for m in c.get("material_resources",[]):
     materials.add((m.get("source"),m.get("path_id"),m.get("name")))
     for t in m.get("textures",[]):
      textures.add(t.get("exported_png"))
      if t.get("exported_png") and not pathlib.Path("scene_graph",t["exported_png"]).exists(): missing.append(t["exported_png"])
   for ch in n.get("children",[]): walk(ch,p)
  walk(d.get("root",{}))
  report={"map":f.stem,"nodes":counts["nodes"],"meshfilters":counts["MeshFilter"],"renderers":counts["MeshRenderer"],"meshcolliders":counts["MeshCollider"],"meshes":len(meshes),"materials":len(materials),"textures":len([x for x in textures if x]),"stairs_named":len(stairs),"interior_named":len(interiors),"missing_exports":len(set(missing)),"stair_candidates":stairs[:100],"interior_candidates":interiors[:250],"missing_assets":sorted(set(missing))}
  reports.append(report); global_missing+=report["missing_exports"]
  (OUT/(f.stem+"_QUALITY_AUDIT.json")).write_text(json.dumps(report,indent=2,ensure_ascii=False))
  print("MAP_QUALITY_AUDIT",json.dumps({k:v for k,v in report.items() if not isinstance(v,list)},ensure_ascii=False))
 summary={"maps":len(reports),"missing_asset_references":global_missing,"results":reports}
 (OUT/"BLOCKGUN_MAP_QUALITY_AUDIT.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False))
 with (OUT/"BLOCKGUN_MAP_QUALITY_AUDIT.csv").open("w",newline="",encoding="utf-8") as f:
  keys=["map","nodes","meshfilters","renderers","meshcolliders","meshes","materials","textures","stairs_named","interior_named","missing_exports"]
  w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows({k:r[k] for k in keys} for r in reports)
 print("BLOCKGUN_QUALITY_AUDIT_DONE maps=",len(reports),"missing=",global_missing)
if __name__=="__main__":main()
