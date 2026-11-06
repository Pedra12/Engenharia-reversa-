#!/usr/bin/env python3
"""Probe Unity Addressables bundles in isolated processes so one bad bundle cannot kill the main audit."""
import csv, json, pathlib, subprocess, sys, collections, shutil, traceback
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import unity_asset_audit as audit

SCENE_TYPES=("GameObject","Transform","RectTransform","Canvas","CanvasRenderer","CanvasGroup","MonoBehaviour","MeshFilter","MeshRenderer","SkinnedMeshRenderer","Animator","SpriteRenderer","AudioSource","AudioListener","Camera","ParticleSystem","ParticleSystemRenderer","Light","TrailRenderer","LineRenderer","Rigidbody","BoxCollider","SphereCollider","CapsuleCollider","MeshCollider","CharacterController","LODGroup","Animation","PrefabInstance","PrefabModification","PropertyModification")
FIELDS={
 "GameObject":["m_Component","m_IsActive","m_Layer","m_Tag","m_Name","m_PrefabInstance","m_PrefabAsset","m_CorrespondingSourceObject"],
 "Transform":["m_GameObject","m_Father","m_Children","m_LocalPosition","m_LocalRotation","m_LocalScale","m_PrefabInstance","m_PrefabAsset","m_CorrespondingSourceObject"],
 "RectTransform":["m_GameObject","m_Father","m_Children","m_LocalPosition","m_LocalRotation","m_LocalScale","m_AnchorMin","m_AnchorMax","m_AnchoredPosition","m_AnchoredPosition3D","m_SizeDelta","m_Pivot","m_PrefabInstance","m_PrefabAsset","m_CorrespondingSourceObject"],
 "Canvas":["m_GameObject","m_Enabled","m_RenderMode","m_Camera","m_SortingOrder","m_TargetDisplay"],
 "CanvasRenderer":["m_GameObject","m_CullTransparentMesh"],
 "CanvasGroup":["m_GameObject","m_Enabled","m_Alpha","m_Interactable","m_BlocksRaycasts"],
 "MonoBehaviour":["m_GameObject","m_Enabled","m_Script","m_PrefabInstance","m_PrefabAsset","m_CorrespondingSourceObject"],
 "MeshFilter":["m_GameObject","m_Mesh"],
 "MeshRenderer":["m_GameObject","m_Enabled","m_Materials"],
 "SkinnedMeshRenderer":["m_GameObject","m_Enabled","m_Materials","m_Mesh","m_Bones","m_RootBone","m_LocalAABB"],
 "Animator":["m_GameObject","m_Enabled","m_Avatar","m_Controller","m_ApplyRootMotion","m_UpdateMode","m_CullingMode"],
 "SpriteRenderer":["m_GameObject","m_Enabled","m_Sprite","m_Color"],
 "AudioSource":["m_GameObject","m_Enabled","m_audioClip","m_Volume","m_Pitch","m_Loop","m_PlayOnAwake","m_Spatialize","m_SpatialBlend"],
 "AudioListener":["m_GameObject","m_Enabled"],
 "Camera":["m_GameObject","m_Enabled","m_FieldOfView","m_NearClipPlane","m_FarClipPlane"],
 "ParticleSystem":["m_GameObject","m_Enabled","lengthInSec","looping","prewarm","playOnAwake","moveWithTransform","simulationSpace","scalingMode","startDelay","startLifetime","startSpeed","startSize","startColor","gravityModifier","maxParticles","emission","shape","sizeOverLifetime","colorOverLifetime"],
 "ParticleSystemRenderer":["m_GameObject","m_Enabled","m_Materials","m_RenderMode","m_SortingFudge","m_MinParticleSize","m_MaxParticleSize"],
 "Light":["m_GameObject","m_Enabled","m_Type","m_Color","m_Intensity","m_Range","m_SpotAngle"],
 "TrailRenderer":["m_GameObject","m_Enabled","m_Time","m_StartWidth","m_EndWidth","m_Materials"],
 "LineRenderer":["m_GameObject","m_Enabled","m_PositionCount","m_StartWidth","m_EndWidth","m_Materials"],
 "Rigidbody":["m_GameObject","m_Mass","m_Drag","m_AngularDrag","m_UseGravity","m_IsKinematic"],
 "BoxCollider":["m_GameObject","m_Enabled","m_IsTrigger","m_Center","m_Size"],
 "SphereCollider":["m_GameObject","m_Enabled","m_IsTrigger","m_Center","m_Radius"],
 "CapsuleCollider":["m_GameObject","m_Enabled","m_IsTrigger","m_Center","m_Radius","m_Height","m_Direction"],
 "MeshCollider":["m_GameObject","m_Enabled","m_IsTrigger","m_Convex","m_Mesh"],
 "CharacterController":["m_GameObject","m_Enabled","m_Center","m_Radius","m_Height","m_SlopeLimit","m_StepOffset"],
 "LODGroup":["m_GameObject","m_Enabled","m_LODs","m_Size","m_LocalReferencePoint"],
 "Animation":["m_GameObject","m_Enabled","m_Animations","m_Clip"],
 "PrefabInstance":["m_SourcePrefab","m_Modification","m_RemovedComponents","m_AddedComponents","m_TransformParent"],
 "PrefabModification":["m_Target","m_PropertyPath","m_Value","m_ObjectReference"],
 "PropertyModification":["target","propertyPath","value","objectReference"]
}

def single(bundle_path,outdir):
    import UnityPy
    from PIL import Image
    bundle_path=pathlib.Path(bundle_path); outdir=pathlib.Path(outdir)
    for sub in ("meshes","textures","audio"): (outdir/sub).mkdir(parents=True,exist_ok=True)
    env=UnityPy.load(str(bundle_path))
    objects=list(env.objects)
    records=[]; counts=collections.Counter(); errors=[]
    for idx,obj in enumerate(objects):
        typ=getattr(obj.type,"name",str(obj.type))
        try:
            data=obj.read()
            name=getattr(data,"m_Name","") or getattr(data,"name","") or ""
            pid=str(getattr(obj,"path_id",idx)); source=audit.source_label(obj)
            row={"source":source,"path_id":pid,"type":typ,"name":str(name)[:250]}
            counts[typ]+=1
            if typ in SCENE_TYPES:
                row["external_files"]=audit.json_safe(getattr(getattr(obj,"assets_file",None),"externals",[]) or [])
                row["fields"]=audit.selected_fields(data,FIELDS.get(typ,[]))
                if typ=="MonoBehaviour":
                    try: row["serialized_fields"]=audit.json_safe(obj.read_typetree())
                    except Exception as e: row["typetree_error"]=str(e)[:200]
            elif typ=="Mesh":
                try:
                    blob=data.export(); blob=blob if isinstance(blob,bytes) else str(blob).encode("utf-8")
                    target=outdir/"meshes"/(audit.safe(name or pid)+".obj"); audit.save(target,blob); row["exported"]=str(target)
                except Exception as e: row["export_error"]=str(e)[:250]
            elif typ in ("Texture2D","Sprite"):
                if typ=="Sprite":
                    row["fields"]=audit.selected_fields(data,["m_Name","m_Rect","m_Pivot","m_Border","m_RD","m_Texture"])
                try:
                    im=data.image
                    if im:
                        target=outdir/"textures"/(audit.safe(name or pid)+".png"); im.save(target); row["exported"]=str(target)
                except Exception as e: row["export_error"]=str(e)[:250]
            elif typ=="AudioClip":
                try:
                    samples=data.samples
                    saved=[]
                    for sn,blob in (samples or {}).items():
                        target=outdir/"audio"/(audit.safe(name or pid)+"_"+audit.safe(sn)+".audio")
                        audit.save(target,blob); saved.append(str(target))
                    if saved: row["exported"]=saved
                except Exception as e: row["export_error"]=str(e)[:250]
            elif typ=="AnimationClip":
                row["fields"]=audit.selected_fields(data,["m_SampleRate","m_MuscleClip","m_ClipBindingConstant","m_AnimationClipSettings"])
            elif typ=="AnimatorController":
                row["fields"]=audit.selected_fields(data,["m_AnimatorLayers","m_AnimatorParameters","m_Controller"])
            elif typ=="Avatar":
                row["fields"]=audit.selected_fields(data,["m_Avatar","m_TOS","m_Name"])
            elif typ=="Material":
                row["fields"]=audit.selected_fields(data,["m_Name","m_Shader","m_SavedProperties","m_CustomRenderQueue"])
            elif typ=="MonoScript":
                row["fields"]=audit.selected_fields(data,["m_Name","m_ClassName","m_Namespace","m_AssemblyName"])
            records.append(row)
        except Exception as e:
            errors.append({"path_id":str(getattr(obj,"path_id",idx)),"type":typ,"error":str(e)[:250]})
    outdir.mkdir(parents=True,exist_ok=True)
    (outdir/"objects.json").write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding="utf-8")
    summary={"bundle":str(bundle_path.name),"objects":len(records),"types":dict(counts.most_common()),"errors":errors[:100]}
    (outdir/"summary.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=False))

def main():
    if len(sys.argv)>=2 and sys.argv[1]=="--single":
        single(sys.argv[2],sys.argv[3]); return
    if len(sys.argv)<3:
        raise SystemExit("usage: unity_bundle_probe.py <bundle_candidates_dir> <output_dir>")
    source=pathlib.Path(sys.argv[1]); output=pathlib.Path(sys.argv[2]); output.mkdir(parents=True,exist_ok=True)
    candidates=sorted(p for p in source.iterdir() if p.is_file())
    results=[]
    for p in candidates:
        if p.stat().st_size<4096:
            results.append({"bundle":p.name,"size":p.stat().st_size,"returncode":0,"status":"skipped_tiny"}); continue
        dest=output/audit.safe(p.stem)
        try:
            r=subprocess.run([sys.executable,str(pathlib.Path(__file__).resolve()),"--single",str(p),str(dest)],capture_output=True,text=True,timeout=240)
            summary={}
            try: summary=json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {}
            except Exception: pass
            results.append({"bundle":p.name,"size":p.stat().st_size,"returncode":r.returncode,"status":"ok" if r.returncode==0 else "isolated_failure","objects":summary.get("objects",0),"types":json.dumps(summary.get("types",{}),ensure_ascii=False),"stderr":r.stderr[-1500:]})
            if r.returncode!=0:
                failed=output/"failed_bundles"; failed.mkdir(exist_ok=True); shutil.copy2(p,failed/p.name)
        except subprocess.TimeoutExpired as e:
            results.append({"bundle":p.name,"size":p.stat().st_size,"returncode":124,"status":"timeout","stderr":str(e)[:1500]})
            failed=output/"failed_bundles"; failed.mkdir(exist_ok=True); shutil.copy2(p,failed/p.name)
    with open(output/"bundle_probe_summary.csv","w",newline="",encoding="utf-8") as f:
        fields=["bundle","size","returncode","status","objects","types","stderr"]
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(results)
    print(json.dumps({"bundles":len(candidates),"successful":sum(x["status"]=="ok" for x in results),"failed":sum(x["status"] in ("isolated_failure","timeout") for x in results)},ensure_ascii=False))

if __name__=="__main__":
    main()
