#!/usr/bin/env python3
"""Fault-isolated Unity AssetBundle probe. One bad serialized object cannot hide the rest."""
import argparse, collections, csv, json, pathlib, shutil, subprocess, sys, traceback

SCENE_TYPES=("GameObject","Transform","RectTransform","Canvas","CanvasRenderer","CanvasGroup","MonoBehaviour","MeshFilter","MeshRenderer","SkinnedMeshRenderer","Animator","SpriteRenderer","AudioSource","AudioListener","Camera","ParticleSystem","ParticleSystemRenderer","Light","TrailRenderer","LineRenderer","Rigidbody","BoxCollider","SphereCollider","CapsuleCollider","MeshCollider","CharacterController","LODGroup","Animation","PrefabInstance","PrefabModification","PropertyModification","Image","RawImage","Button","Text","TextMeshProUGUI","TextMeshPro","CanvasScaler","GraphicRaycaster","EventSystem","StandaloneInputModule","InputSystemUIInputModule","ScrollRect","Slider","Toggle","Scrollbar","Mask","RectMask2D","HorizontalLayoutGroup","VerticalLayoutGroup","GridLayoutGroup","LayoutElement","ContentSizeFitter","AspectRatioFitter","Outline","Shadow","InputField","Dropdown","ToggleGroup","Selectable")
ASSET_TYPES=("Mesh","Texture2D","Sprite","AudioClip","Material","AnimationClip","AnimatorController","Avatar","MonoScript")
ALL_TYPES=SCENE_TYPES+ASSET_TYPES

FIELDS={
 "GameObject":["m_Component","m_IsActive","m_Layer","m_Tag","m_Name","m_PrefabInstance","m_PrefabAsset","m_CorrespondingSourceObject"],
 "Transform":["m_GameObject","m_Father","m_Children","m_LocalPosition","m_LocalRotation","m_LocalScale"],
 "RectTransform":["m_GameObject","m_Father","m_Children","m_LocalPosition","m_LocalRotation","m_LocalScale","m_AnchorMin","m_AnchorMax","m_AnchoredPosition","m_AnchoredPosition3D","m_SizeDelta","m_Pivot"],
 "Canvas":["m_GameObject","m_Enabled","m_RenderMode","m_Camera","m_SortingOrder","m_TargetDisplay"],
 "CanvasRenderer":["m_GameObject","m_CullTransparentMesh"],
 "CanvasGroup":["m_GameObject","m_Enabled","m_Alpha","m_Interactable","m_BlocksRaycasts"],
 "MonoBehaviour":["m_GameObject","m_Enabled","m_Script"],
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
 "Image":["m_GameObject","m_Enabled","m_Sprite","m_Color","m_Material","m_RaycastTarget","m_Type","m_FillMethod","m_FillAmount","m_FillCenter","m_FillClockwise","m_FillOrigin","m_UseSpriteMesh","m_PreserveAspect","m_Maskable"],
 "RawImage":["m_GameObject","m_Enabled","m_Texture","m_Color","m_RaycastTarget","m_UVRect","m_Maskable"],
 "Button":["m_GameObject","m_Enabled","m_Interactable","m_Transition","m_Colors","m_SpriteState","m_AnimationTriggers","m_TargetGraphic","m_OnClick"],
 "Text":["m_GameObject","m_Enabled","m_Text","m_Font","m_FontSize","m_FontStyle","m_Color","m_Alignment","m_HorizontalOverflow","m_VerticalOverflow","m_RichText"],
 "TextMeshProUGUI":["m_GameObject","m_Enabled","m_text","m_fontSize","m_fontAsset","m_color","m_alignment","m_enableAutoSizing"],
 "CanvasScaler":["m_GameObject","m_Enabled","m_UiScaleMode","m_ReferencePixelsPerUnit","m_ScaleFactor","m_ReferenceResolution","m_ScreenMatchMode","m_MatchWidthOrHeight"],
 "GraphicRaycaster":["m_GameObject","m_Enabled","m_IgnoreReversedGraphics","m_BlockingObjects","m_BlockingMask"],
 "Material":["m_Name","m_Shader","m_SavedProperties","m_CustomRenderQueue"],
 "Mesh":["m_Name","m_VertexData","m_BindPose","m_BoneNameHashes","m_RootBoneNameHash","m_BonesAABB","m_SubMeshes","m_IndexBuffer","m_Channels","m_StreamData","m_CompressedMesh"],
 "MonoScript":["m_Name","m_ClassName","m_Namespace","m_AssemblyName"],
 "Sprite":["m_Name","m_Rect","m_Pivot","m_Border","m_RD","m_Texture"],
 "ParticleSystem":["m_GameObject","m_Enabled","lengthInSec","looping","prewarm","playOnAwake","simulationSpace","startDelay","startLifetime","startSpeed","startSize","startColor","gravityModifier","maxParticles","emission","shape","sizeOverLifetime","colorOverLifetime"],
 "ParticleSystemRenderer":["m_GameObject","m_Enabled","m_Materials","m_RenderMode","m_SortingFudge"],
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
 "AnimationClip":["m_Name","m_Legacy","m_Compressed","m_UseHighQualityCurve","m_RotationCurves","m_PositionCurves","m_ScaleCurves","m_FloatCurves","m_PPtrCurves","m_Events","m_MuscleClip","m_ClipBindingConstant","m_AnimationClipSettings","m_SampleRate"],
 "AnimatorController":["m_Name","m_AnimatorLayers","m_AnimatorParameters","m_Controller","m_AnimationClips","m_ClipArray"],
 "Avatar":["m_Name","m_Avatar","m_TOS"]
}

def safe(s):
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in str(s))[:150]

def write_json(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,separators=(",",":")),encoding="utf-8")

def manifest(bundle_path,out):
    import UnityPy
    env=UnityPy.load(str(bundle_path))
    rows=[]
    for obj in env.objects:
        try:
            rows.append({"path_id":str(obj.path_id),"type":obj.type.name,"byte_size":int(getattr(obj,"byte_size",0) or 0),
                         "assets_file":str(getattr(getattr(obj,"assets_file",None),"name",""))})
        except Exception:
            continue
    write_json(out/"manifest.json",rows)
    print("MANIFEST_READY",len(rows),flush=True)

def worker(bundle_path,out,types_filter,path_ids):
    import UnityPy
    import unity_asset_audit as audit
    env=UnityPy.load(str(bundle_path))
    type_set=set(types_filter); id_set=set(path_ids)
    rows=[]; counts=collections.Counter(); errors=0
    (out/"meshes").mkdir(parents=True,exist_ok=True)
    (out/"textures").mkdir(parents=True,exist_ok=True)
    (out/"audio").mkdir(parents=True,exist_ok=True)
    for obj in env.objects:
        pid=str(obj.path_id); typ=obj.type.name
        if type_set and typ not in type_set: continue
        if id_set and pid not in id_set: continue
        try:
            data=obj.read()
            name=str(getattr(data,"m_Name","") or "")
            base=safe(f"{typ}_{name}_{pid}")
            row={"source":pathlib.Path(bundle_path).name,"path_id":pid,"type":typ,"name":name,
                 "byte_size":int(getattr(obj,"byte_size",0) or 0),
                 "external_files":audit.json_safe(getattr(getattr(obj,"assets_file",None),"externals",[]) or [])}
            if typ in FIELDS:
                row["fields"]=audit.selected_fields(data,FIELDS[typ])
            if typ in SCENE_TYPES and typ in ("MonoBehaviour","Image","RawImage","Button","Text","TextMeshProUGUI","TextMeshPro","CanvasScaler","GraphicRaycaster","EventSystem","StandaloneInputModule","InputSystemUIInputModule","ScrollRect","Slider","Toggle","Scrollbar","Mask","RectMask2D","HorizontalLayoutGroup","VerticalLayoutGroup","GridLayoutGroup","LayoutElement","ContentSizeFitter","AspectRatioFitter","Outline","Shadow","InputField","Dropdown","ToggleGroup","Selectable"):
                try: row["serialized_fields"]=audit.json_safe(obj.read_typetree())
                except Exception as e: row["typetree_error"]=str(e)[:200]
            if typ=="Mesh":
                try:
                    exported=data.export()
                    payload=exported if isinstance(exported,bytes) else str(exported).encode("utf-8")
                    target=out/"meshes"/(base+".obj");audit.save(target,payload);row["exported"]=str(target)
                except Exception as e: row["export_error"]="mesh: "+str(e)[:200]
            elif typ in ("Texture2D","Sprite"):
                if typ=="Sprite":
                    row["fields"]=audit.selected_fields(data,FIELDS["Sprite"])
                try:
                    image=data.image
                    if image:
                        target=out/"textures"/(base+".png");target.parent.mkdir(parents=True,exist_ok=True);image.save(target);row["exported"]=str(target)
                except Exception as e: row["export_error"]="image: "+str(e)[:200]
            elif typ=="AudioClip":
                try:
                    saved=[]
                    for sample_name,blob in (data.samples or {}).items():
                        ext=pathlib.Path(str(sample_name)).suffix or ".audio"
                        target=out/"audio"/(base+"_"+safe(sample_name)+ext)
                        audit.save(target,blob);saved.append(str(target))
                    if saved: row["exported"]=";".join(saved)
                except Exception as e: row["export_error"]="audio: "+str(e)[:200]
            elif typ=="Material":
                row["fields"]=audit.selected_fields(data,FIELDS["Material"])
            elif typ=="AnimationClip":
                row["fields"]=audit.selected_fields(data,FIELDS["AnimationClip"])
            elif typ=="AnimatorController":
                row["fields"]=audit.selected_fields(data,FIELDS["AnimatorController"])
            elif typ=="Avatar":
                row["fields"]=audit.selected_fields(data,FIELDS["Avatar"])
            elif typ=="MonoScript":
                row["fields"]=audit.selected_fields(data,FIELDS["MonoScript"])
            rows.append(row);counts[typ]+=1
        except Exception as e:
            errors+=1
            rows.append({"source":pathlib.Path(bundle_path).name,"path_id":pid,"type":typ,"error":str(e)[:250]})
    write_json(out/"objects.json",rows)
    write_json(out/"summary.json",{"objects":len(rows),"types":dict(counts),"errors":errors,"filters":{"types":types_filter,"path_ids":len(path_ids)}})
    print("WORKER_DONE",len(rows),dict(counts),"errors",errors,flush=True)

def run_child(bundle_path, out, mode, types=(), ids=()):
    cmd=[sys.executable,__file__,"--"+mode,str(bundle_path),str(out)]
    if types: cmd += ["--types",",".join(types)]
    if ids: cmd += ["--ids",",".join(ids)]
    return subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)

def merge_worker(worker_dir,final_dir,all_rows):
    obj=worker_dir/"objects.json"
    if obj.exists():
        try:
            rows=json.loads(obj.read_text(encoding="utf-8"))
            for row in rows:
                if row.get("exported"):
                    mapped=[]
                    for raw in str(row["exported"]).split(";"):
                        p=pathlib.Path(raw)
                        kind=p.parent.name
                        mapped.append(str(final_dir/kind/p.name))
                    row["exported"]=";".join(mapped)
            all_rows.extend(rows)
        except Exception: pass
    for kind in ("meshes","textures","audio"):
        src=worker_dir/kind;dst=final_dir/kind
        if src.exists():
            dst.mkdir(parents=True,exist_ok=True)
            for file in src.iterdir():
                target=dst/file.name
                if not target.exists(): shutil.copy2(file,target)
    shutil.rmtree(worker_dir,ignore_errors=True)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--manifest",nargs=2)
    ap.add_argument("--worker",nargs=2)
    ap.add_argument("--types",default="")
    ap.add_argument("--ids",default="")
    ap.add_argument("bundles_pos",nargs="?")
    ap.add_argument("out_pos",nargs="?")
    ap.add_argument("--bundles",default="unity_audit")
    ap.add_argument("--out",default="unity_audit/bundle_probe")
    args=ap.parse_args()
    if args.manifest:
        manifest(pathlib.Path(args.manifest[0]),pathlib.Path(args.manifest[1]));return
    if args.worker:
        worker(pathlib.Path(args.worker[0]),pathlib.Path(args.worker[1]),[x for x in args.types.split(",") if x],[x for x in args.ids.split(",") if x]);return
    root=pathlib.Path(args.bundles_pos or args.bundles);out=pathlib.Path(args.out_pos or args.out);out.mkdir(parents=True,exist_ok=True)
    candidates=[p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in (".bundle",".bund",".assetbundle")]
    summary=[]
    for bundle in candidates:
        bundle_name=safe(bundle.name);final_dir=out/bundle_name;final_dir.mkdir(parents=True,exist_ok=True)
        manifest_dir=out/("_manifest_"+bundle_name);manifest_dir.mkdir(parents=True,exist_ok=True)
        m=run_child(bundle,manifest_dir,"manifest")
        if m.returncode!=0 or not (manifest_dir/"manifest.json").exists():
            summary.append({"bundle":bundle.name,"size":bundle.stat().st_size,"returncode":m.returncode,"status":"manifest_failed","objects":0,"types":{},"stderr":m.stdout[-500:]})
            (out/"failed_bundles").mkdir(parents=True,exist_ok=True)
            shutil.copy2(bundle,out/"failed_bundles"/bundle.name);continue
        manifest_rows=json.loads((manifest_dir/"manifest.json").read_text(encoding="utf-8"))
        by_type=collections.defaultdict(list)
        for row in manifest_rows:
            if row["type"] in ALL_TYPES: by_type[row["type"]].append(row["path_id"])
        groups=[
            [t for t in SCENE_TYPES if by_type.get(t)],
            [t for t in ASSET_TYPES if by_type.get(t)]
        ]
        all_rows=[];failed_types=[];worker_logs=[]
        def process_type(typ,ids):
            label=safe(typ+"_"+str(len(worker_logs)))
            worker_dir=final_dir/("_worker_"+label);worker_dir.mkdir(parents=True,exist_ok=True)
            # Keep large path-ID lists out of argv; a type-only pass is safe and
            # falls back to bisection if one serialized object crashes UnityPy.
            worker_ids=ids if len(ids)<=1000 else []
            result=run_child(bundle,worker_dir,"worker",[typ],worker_ids)
            worker_logs.append({"type":typ,"ids":len(ids),"returncode":result.returncode,"log":result.stdout[-1000:]})
            if result.returncode==0 and (worker_dir/"objects.json").exists():
                merge_worker(worker_dir,final_dir,all_rows);return
            if len(ids)>1:
                mid=len(ids)//2
                process_type(typ,ids[:mid]);process_type(typ,ids[mid:])
            else:
                failed_types.append({"type":typ,"path_id":ids[0] if ids else "","returncode":result.returncode,"log":result.stdout[-500:]})
        # Run each Unity object type independently. If a native decoder crashes on one object,
        # recursively bisect only that type until all safe objects have been recovered.
        for typ,ids in by_type.items():
            process_type(typ,ids)
        write_json(final_dir/"objects.json",all_rows)
        shutil.rmtree(manifest_dir,ignore_errors=True)
        counts=collections.Counter(x.get("type","") for x in all_rows)
        write_json(final_dir/"summary.json",{"objects":len(all_rows),"types":dict(counts),"failed_objects":failed_types,"manifest_objects":len(manifest_rows)})
        write_json(final_dir/"worker_logs.json",worker_logs)
        if not all_rows:
            (out/"failed_bundles").mkdir(parents=True,exist_ok=True)
            shutil.copy2(bundle,out/"failed_bundles"/bundle.name)
        summary.append({"bundle":bundle.name,"size":bundle.stat().st_size,"returncode":0,"status":"partial" if failed_types else "ok","objects":len(all_rows),"types":dict(counts),"failed":len(failed_types),"stderr":""})
    with (out/"bundle_probe_summary.csv").open("w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=["bundle","size","returncode","status","objects","types","failed","stderr"]);writer.writeheader()
        for row in summary:
            row["types"]=json.dumps(row.get("types",{}),ensure_ascii=False)
            writer.writerow(row)
    print("BUNDLE_PROBE_READY",[(x["bundle"],x["status"],x["objects"],x.get("failed",0)) for x in summary],flush=True)

if __name__=="__main__":
    main()
