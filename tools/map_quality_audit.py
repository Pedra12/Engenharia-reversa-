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
def obj_surface_features(path,scale_y=1.0):
 p=GRAPH/path
 if not p.exists(): return {"missing":True,"bounds":None,"horizontal_levels":[],"stair_geometry_candidate":False}
 vertices=[]; faces=[]
 try:
  with p.open(errors="ignore") as src:
   for line in src:
    if line.startswith("v "):
     try: vertices.append(tuple(map(float,line.split()[1:4])))
     except (ValueError,IndexError): pass
    elif line.startswith("f "):
     ids=[]
     for token in line.split()[1:]:
      try: ids.append(int(token.split("/")[0])-1)
      except ValueError: pass
     if len(ids)>=3: faces.append(ids[:3])
 except OSError: return {"missing":True,"bounds":None,"horizontal_levels":[],"stair_geometry_candidate":False}
 if not vertices: return {"missing":False,"bounds":None,"horizontal_levels":[],"stair_geometry_candidate":False}
 bounds={axis:[min(v[i] for v in vertices),max(v[i] for v in vertices)] for i,axis in enumerate(("x","y","z"))}
 bounds["y"]=[bounds["y"][0]*abs(scale_y),bounds["y"][1]*abs(scale_y)]
 levels=collections.Counter()
 for ids in faces:
  if any(i<0 or i>=len(vertices) for i in ids): continue
  a,b,c=(vertices[i] for i in ids)
  ux,uy,uz=(b[i]-a[i] for i in range(3)); vx,vy,vz=(c[i]-a[i] for i in range(3))
  nx=uy*vz-uz*vy; ny=uz*vx-ux*vz; nz=ux*vy-uy*vx
  norm=(nx*nx+ny*ny+nz*nz)**0.5
  if norm>1e-9 and abs(ny)/norm>=0.96:
   levels[round(((a[1]+b[1]+c[1])/3)*abs(scale_y),3)]+=1
 tread_levels=sorted((y,n) for y,n in levels.items() if n>=3)
 sequence=[]; best=[]
 for item in tread_levels:
  if sequence and 0.07 <= item[0]-sequence[-1][0] <= 0.30: sequence.append(item)
  else:
   if len(sequence)>len(best): best=sequence
   sequence=[item]
 if len(sequence)>len(best): best=sequence
 return {"missing":False,"bounds":bounds,"horizontal_levels":[{"y":y,"triangles":n} for y,n in sorted(levels.items(),key=lambda q:-q[1])[:30]],"stair_geometry_candidate":len(best)>=3,"candidate_tread_sequence":[{"y":y,"triangles":n} for y,n in best] if len(best)>=3 else []}


def _cluster_xz(points,eps=1.2,min_count=3):
 cell=eps; buckets=collections.defaultdict(list)
 for i,p in enumerate(points): buckets[(int(p[0]//cell),int(p[1]//cell))].append(i)
 unseen=set(range(len(points))); found=[]
 while unseen:
  seed=unseen.pop(); stack=[seed]; group=[seed]
  while stack:
   i=stack.pop(); x,z=points[i]; gx,gz=int(x//cell),int(z//cell)
   for dx in (-1,0,1):
    for dz in (-1,0,1):
     for j in buckets.get((gx+dx,gz+dz),[]):
      if j in unseen:
       px,pz=points[j]
       if (px-x)*(px-x)+(pz-z)*(pz-z)<=eps*eps:
        unseen.remove(j); stack.append(j); group.append(j)
  if len(group)>=min_count:
   found.append((sum(points[i][0] for i in group)/len(group),sum(points[i][1] for i in group)/len(group)))
 return found

def stair_route_candidates(mesh_path,scale,position,node_name):
 p=GRAPH/mesh_path
 if not p.exists(): return []
 sx,sy,sz=(float(scale.get(k,1.0) or 1.0) for k in ("x","y","z"))
 px,py,pz=(float(position.get(k,0.0) or 0.0) for k in ("x","y","z"))
 vertices=[]; faces=[]
 try:
  with p.open(errors="ignore") as src:
   for line in src:
    if line.startswith("v "):
     try:
      x,y,z=map(float,line.split()[1:4]); vertices.append((x*sx,y*sy,z*sz))
     except (ValueError,IndexError): pass
    elif line.startswith("f "):
     ids=[]
     for token in line.split()[1:]:
      try: ids.append(int(token.split("/")[0])-1)
      except ValueError: pass
     if len(ids)>=3: faces.append(ids[:3])
 except OSError: return []
 if not vertices or not faces: return []
 levels=collections.defaultdict(list)
 for ids in faces:
  if any(i<0 or i>=len(vertices) for i in ids): continue
  a,b,c=(vertices[i] for i in ids)
  ux,uy,uz=(b[i]-a[i] for i in range(3)); vx,vy,vz=(c[i]-a[i] for i in range(3))
  nx=uy*vz-uz*vy; ny=uz*vx-ux*vz; nz=ux*vy-uy*vx
  norm=(nx*nx+ny*ny+nz*nz)**0.5
  if norm<1e-9 or abs(ny)/norm<0.96: continue
  y=round((a[1]+b[1]+c[1])/3,3)
  levels[y].append(((a[0]+b[0]+c[0])/3,(a[2]+b[2]+c[2])/3))
 nodes=[]
 for y,points in sorted(levels.items()):
  for xz in _cluster_xz(points):
   nodes.append((y,xz))
 if len(nodes)<3: return []
 best_paths=[[i] for i in range(len(nodes))]
 for j,(yj,xj) in enumerate(nodes):
  for i in range(j):
   yi,xi=nodes[i]; dy=yj-yi
   if dy<0.07 or dy>0.32: continue
   if (xj[0]-xi[0])**2+(xj[1]-xi[1])**2>1.6**2: continue
   if len(best_paths[i])+1>len(best_paths[j]):
    best_paths[j]=best_paths[i]+[j]
 best_path=max(best_paths,key=len)
 if len(best_path)<3: return []
 y0,(x0,z0)=nodes[best_path[0]]; y1,(x1,z1)=nodes[best_path[-1]]
 # UnityPy's local collider mesh aligns with the static-batch render mesh
 # after reflecting the GameObject's X translation into Godot coordinates.
 start=[x0-px,y0+py,z0+pz]; end=[x1-px,y1+py,z1+pz]
 distance=((end[0]-start[0])**2+(end[2]-start[2])**2)**0.5
 rise=end[1]-start[1]
 if not (0.18<=distance<=2.0 and 0.15<=rise<=1.6): return []
 return [{"node":node_name,"steps":len(best_path),"start":start,"end":end,"horizontal_distance":distance,"rise":rise}]

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
      if ref.get("field")=="m_Mesh" and typ=="MeshCollider":
       scale_y=float((n.get("scale") or {}).get("y",1.0) or 1.0)
       colliders.append({"node":name,"mesh":obj,"scale_y":scale_y,"scale":n.get("scale") or {},"position":n.get("position") or {},"stats":obj_stats(obj),"surface_features":obj_surface_features(obj,scale_y)})
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
  stair_routes=[]
  for c in colliders:
   stair_routes.extend(stair_route_candidates(c["mesh"],c["scale"],c["position"],c["node"]))
  stair_routes.sort(key=lambda r:(r["steps"],r["rise"],-abs(r["horizontal_distance"]-1.0)),reverse=True)
  report={"map":f.stem,"unity_level":level,"stair_route_candidates":stair_routes,"nodes":counts["nodes"],"meshfilters":counts["MeshFilter"],"renderers":counts["MeshRenderer"],"meshcolliders":counts["MeshCollider"],"referenced_meshes":len(meshrefs),"level_combined_meshes":len(level_meshes),"level_vertices":sum(x["vertices"] for x in geometry.values()),"level_faces":sum(x["faces"] for x in geometry.values()),"materials":len(materials),"textures":len([x for x in textures if x]),"stairs_named":len(stairs),"interior_named":len(interiors),"missing_exports":len(set(missing)),"stair_candidates":stairs[:100],"stair_geometry_candidates":[{"node":c["node"],"mesh":c["mesh"],"scale_y":c["scale_y"],"treads":c["surface_features"]["candidate_tread_sequence"]} for c in colliders if c["surface_features"]["stair_geometry_candidate"]],"interior_candidates":interiors[:250],"collider_meshes":colliders,"geometry_files":geometry,"missing_assets":sorted(set(missing))}
  reports.append(report); global_missing+=report["missing_exports"]
  (OUT/(f.stem+"_QUALITY_AUDIT.json")).write_text(json.dumps(report,indent=2,ensure_ascii=False))
  godot_manifest=pathlib.Path("godot_project/data")/(f.stem+".json")
  if godot_manifest.exists():
   godot_data=json.loads(godot_manifest.read_text())
   godot_data["stair_route_candidates"]=stair_routes
   godot_manifest.write_text(json.dumps(godot_data,ensure_ascii=False),encoding="utf-8")
  print("MAP_QUALITY_AUDIT",json.dumps({k:v for k,v in report.items() if not isinstance(v,(list,dict))},ensure_ascii=False))
 summary={"maps":len(reports),"missing_asset_references":global_missing,"results":reports}
 (OUT/"BLOCKGUN_MAP_QUALITY_AUDIT.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False))
 keys=["map","unity_level","nodes","meshfilters","renderers","meshcolliders","referenced_meshes","level_combined_meshes","level_vertices","level_faces","materials","textures","stairs_named","interior_named","missing_exports"]
 with (OUT/"BLOCKGUN_MAP_QUALITY_AUDIT.csv").open("w",newline="",encoding="utf-8") as f:
  w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows({k:r[k] for k in keys} for r in reports)
 print("BLOCKGUN_QUALITY_AUDIT_DONE maps=",len(reports),"missing=",global_missing)
if __name__=="__main__":main()
