#!/usr/bin/env python3
import csv,hashlib,json,pathlib,re,zipfile
A=pathlib.Path("blockgun.zip"); B=pathlib.Path("unity_audit"); O=B/"combat_deep"; O.mkdir(parents=True,exist_ok=True)
EXPECTED="e3e3cc4afac58236657240cc8c403fb56c9b02c9f8efa3b77bcc6044b1b480c0"
def load(p):
 p=pathlib.Path(p); return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
def save(n,x): (O/n).write_text(json.dumps(x,ensure_ascii=False,indent=2),encoding="utf-8")
def hud():
 rec=load(B/"UNITY_SCENE_OBJECTS.json"); idx={(o.get("source"),str(o.get("path_id"))):o for o in rec}
 gos={(o.get("source"),str(o.get("path_id"))):o for o in rec if o.get("type")=="GameObject"}
 trs={(o.get("source"),str(o.get("path_id"))):o for o in rec if o.get("type") in ("Transform","RectTransform")}
 pat=re.compile(r"WindowPlayer|Joystick|button_fire|aim_button|jump_button|reload_button|Crosshair|SniperScope|AimAssistance|AutoAiming|AimFire|TouchControl|ControlsManager|DamageRadar|BulletTraces|Health|bar_health|WeaponArea|WeaponNameArea|WeaponCount|SpawnPointManager|CoverPointManager|FollowCamerasManager|AutoShooting|GenericSpawn|BlueSpawn|YellowSpawn|AllSpawn|SpawnPoint|Attacker Point|DefenderPoints|NeutralPoints",re.I)
 rows=[]
 for (src,gid),g in gos.items():
  if src not in ("level3","level5","level6") or not pat.search(g.get("name","")): continue
  tr=None; comps=[]
  for c in g.get("fields",{}).get("m_Component",[]):
   cid=str(c.get("component",{}).get("m_PathID")); o=idx.get((src,cid))
   if not o: continue
   if o.get("type") in ("Transform","RectTransform"): tr=o
   elif o.get("type")=="MonoBehaviour": comps.append("MonoBehaviour:"+str(o.get("fields",{}).get("m_Script",{}).get("m_PathID","?")))
   else: comps.append(o.get("type"))
  f=(tr or {}).get("fields",{}); pid=str(f.get("m_Father",{}).get("m_PathID","0")); parent=""
  if pid!="0":
   pt=trs.get((src,pid))
   if pt: parent=gos.get((src,str(pt.get("fields",{}).get("m_GameObject",{}).get("m_PathID",""))),{}).get("name","")
  rows.append({"source":src,"id":gid,"name":g.get("name"),"active":g.get("fields",{}).get("m_IsActive",True),"parent_id":pid,"parent_name":parent,"local_position":f.get("m_LocalPosition"),"anchored_position":f.get("m_AnchoredPosition"),"size_delta":f.get("m_SizeDelta"),"anchor_min":f.get("m_AnchorMin"),"anchor_max":f.get("m_AnchorMax"),"components":comps})
 rows.sort(key=lambda x:(x["source"],x["name"],x["id"])); save("GAMEPLAY_HUD_AND_SCENE_CONTROLS.json",rows)
 with (O/"GAMEPLAY_HUD_AND_SCENE_CONTROLS.csv").open("w",newline="",encoding="utf-8") as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ["source","name"]); w.writeheader()
  for r in rows: w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()})
 return rows
def bundle():
 files=list((B/"bundle_probe").glob("*/objects.json")); allgo=[]; comps=[]; scripts={}
 keys={"LocalWeapon","RemoteWeapon","WeaponAnimation","WeaponMovements","CharacterArmature","SkinnedMeshController","HitBox","Scope","AttachmentModifier","ItemAttachment","HandRigSaver","HandRigDataContainer","SpawnPoint","DropWeapon","ThrowableWeapon","ProjectileExplosion","AnimationEventsHandler","CharacterOutfit","Outfit","ArmorBase","MachinegunLocalSkill","MachinegunRemoteSkill","FlamethrowerLocalSkill","FlamethrowerRemoteSkill","TurretLocalSkill","TurretRemoteSkill","AnnihilatorLocalSkill","AnnihilatorRemoteSkill"}
 pat=re.compile(r"player|weapon|gun|shoot|fire|aim|scope|crosshair|bullet|damage|health|spawn|bot|enemy|input|joystick|touch|camera|reload|jump|animat|controller|battle|match|sight|hand|rig|model",re.I)
 for p in files:
  objs=json.loads(p.read_text(encoding="utf-8")); by={str(o.get("path_id")):o for o in objs}
  for o in objs:
   if o.get("type")=="MonoScript":
    f=o.get("fields",{}); scripts[str(o.get("path_id"))]={"class":f.get("m_ClassName",o.get("name")),"namespace":f.get("m_Namespace",""),"assembly":f.get("m_AssemblyName","")}
  gs={str(o.get("path_id")):o for o in objs if o.get("type")=="GameObject"}; ts={str(o.get("path_id")):o for o in objs if o.get("type")=="Transform"}
  def pathof(g,seen=None):
   if not g:return ""
   seen=seen or set(); gid=str(g.get("path_id"))
   if gid in seen:return g.get("name","")
   seen.add(gid); tid=next((str(c.get("component",{}).get("m_PathID")) for c in g.get("fields",{}).get("m_Component",[]) if str(c.get("component",{}).get("m_PathID")) in ts),None)
   if not tid:return g.get("name","")
   pid=str(ts[tid].get("fields",{}).get("m_Father",{}).get("m_PathID","0")); parent=None
   if pid!="0" and pid in ts:
    pg=str(ts[pid].get("fields",{}).get("m_GameObject",{}).get("m_PathID","")); parent=gs.get(pg)
   prefix=pathof(parent,seen) if parent else ""
   return (prefix+"/" if prefix else "")+g.get("name","")
  for gid,g in gs.items():
   names=[]
   for c in g.get("fields",{}).get("m_Component",[]):
    cid=str(c.get("component",{}).get("m_PathID")); ob=by.get(cid)
    if not ob:continue
    if ob.get("type")=="MonoBehaviour":
     sid=str(ob.get("fields",{}).get("m_Script",{}).get("m_PathID","")); cls=scripts.get(sid,{}).get("class","unknown"); names.append(cls)
     if cls in keys: comps.append({"bundle":p.parent.name,"gameobject_id":gid,"gameobject":g.get("name"),"path":pathof(g),"component_id":cid,"class":cls,"script_id":sid,"script":scripts.get(sid,{}),"fields":ob.get("fields",{})})
    else:names.append(ob.get("type",""))
   if pat.search(g.get("name","")) or any(n in keys for n in names): allgo.append({"bundle":p.parent.name,"id":gid,"name":g.get("name"),"path":pathof(g),"components":names})
 save("BUNDLE_GAMEPLAY_COMPONENTS.json",comps); save("BUNDLE_GAMEPLAY_GAMEOBJECTS.json",allgo); save("BUNDLE_MONOSCRIPT_CATALOG.json",scripts)
 return len(allgo),len(comps),scripts
def source():
 rows=[]; pat=re.compile(r"weapon|player|anim|shoot|fire|aim|scope|bullet|damage|health|spawn|bot|enemy|input|joystick|touch|camera|reload|jump|game.?mode|match|hitbox|outfit|rig|armor",re.I)
 with zipfile.ZipFile(A) as z:
  names=[n for n in z.namelist() if n.startswith("unity/scripts/csharp/") and n.lower().endswith(".cs")]
  for n in names:
   rel=pathlib.PurePosixPath(n).relative_to("unity/scripts/csharp"); dest=O/"csharp"/pathlib.Path(*rel.parts); dest.parent.mkdir(parents=True,exist_ok=True)
   data=z.read(n); dest.write_bytes(data); txt=data.decode("utf-8","replace")
   rows.append({"original_path":n,"exported_path":str(dest),"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest(),"classes":";".join(re.findall(r"\b(?:class|struct|interface|enum)\s+([A-Za-z_]\w*)",txt)),"namespace":(re.search(r"\bnamespace\s+([\w.]+)",txt) or [None,""])[1],"gameplay_related":bool(pat.search(n+" "+txt[:12000]))})
 with (O/"CSHARP_SOURCE_INDEX.csv").open("w",newline="",encoding="utf-8") as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ["original_path"]);w.writeheader();w.writerows(rows)
 return rows
def rig():
 r=load(B/"UNITY_RIG_HIERARCHY.json"); skins=load(B/"UNITY_SKINNING_DATA.json"); anim=load(B/"UNITY_ANIMATION_DATA.json"); ctr=load(B/"UNITY_ANIMATOR_DATA.json")
 gos={str(g.get("path_id")):g for g in r.get("gameobjects",[])}; ts={str(t.get("path_id")):t for t in r.get("transforms",[])}
 def node(tid,seen=None):
  seen=seen or set(); tid=str(tid)
  if tid in seen or tid not in ts:return None
  seen.add(tid); t=ts[tid]; f=t.get("fields",{}); gid=str(f.get("m_GameObject",{}).get("m_PathID",""))
  return {"transform_id":tid,"gameobject_id":gid,"name":gos.get(gid,{}).get("name",""),"position":f.get("m_LocalPosition"),"rotation":f.get("m_LocalRotation"),"scale":f.get("m_LocalScale"),"children":[node(c.get("m_PathID"),seen.copy()) for c in f.get("m_Children",[])]}
 roots=[node(tid) for tid,t in ts.items() if str(t.get("fields",{}).get("m_Father",{}).get("m_PathID","0"))=="0"]
 save("RIG_HIERARCHY_WITH_LOCAL_TRANSFORMS.json",roots)
 save("SKINNING_SUMMARY.json",[{"name":m.get("name"),"source":m.get("source"),"path_id":m.get("path_id"),"bind_pose_count":len(m.get("fields",{}).get("m_BindPose") or []),"bone_hash_count":len(m.get("fields",{}).get("m_BoneNameHashes") or []),"root_bone_hash":m.get("fields",{}).get("m_RootBoneNameHash")} for m in skins])
 clips=[]
 for a in anim:
  f=a.get("fields",{}); d=(((f.get("m_MuscleClip") or {}).get("m_Clip") or {}).get("data") or {}).get("m_DenseClip") or {}
  clips.append({"name":a.get("name"),"source":a.get("source"),"path_id":a.get("path_id"),"fps":f.get("m_SampleRate"),"frames":d.get("m_FrameCount"),"curves":d.get("m_CurveCount")})
 save("ANIMATION_CLIP_INDEX.json",clips); save("ANIMATOR_CONTROLLERS_FULL.json",ctr.get("controllers",[]))
 return len(roots),len(skins),len(clips),len(ctr.get("controllers",[]))
def main():
 sha=hashlib.sha256(A.read_bytes()).hexdigest()
 if sha!=EXPECTED:raise SystemExit("SHA-256 do ZIP original não confere: "+sha)
 h=hud(); ng,nc,sc=bundle(); cs=source(); nr,ns,na,nc2=rig()
 summary={"sha256":sha,"csharp_files":len(cs),"gameplay_csharp_files":sum(x["gameplay_related"] for x in cs),"mono_scripts":len(sc),"bundle_gameobjects":ng,"gameplay_components":nc,"hud_controls":len(h),"rig_roots":nr,"skinned_meshes":ns,"animation_clips":na,"animator_controllers":nc2}
 save("COMBAT_DEEP_AUDIT_SUMMARY.json",summary)
 report=["# Auditoria profunda do combate original","",f"SHA-256 verificado: {sha}",f"Arquivos C# extraídos: {len(cs)}",f"Arquivos C# ligados a gameplay: {summary['gameplay_csharp_files']}",f"MonoScripts de bundle: {len(sc)}",f"GameObjects de bundle indexados: {ng}",f"Componentes de gameplay mapeados: {nc}",f"Controles/HUD nos níveis 3, 5 e 6: {len(h)}",f"Raízes de rig: {nr}",f"Malhas skinned: {ns}",f"Clipes de animação: {na}",f"Animator Controllers: {nc2}","","Arquivos C# relacionados:"]
 report += ["- "+x["original_path"]+" :: "+x["classes"] for x in cs if x["gameplay_related"]]
 (O/"COMBAT_DEEP_AUDIT_REPORT.md").write_text("\n".join(report),encoding="utf-8")
 print("COMBAT_DEEP_AUDIT_OK",json.dumps(summary,ensure_ascii=False))
if __name__=="__main__":main()
