#!/usr/bin/env python3
"""Reconstrói arquivos Unity divididos em .splitN e extrai objetos via UnityPy."""
import zipfile, pathlib, tempfile, json, csv, re, collections, os, hashlib, base64
from pathlib import PurePosixPath
ARCHIVE=pathlib.Path("blockgun.zip")
OUT=pathlib.Path("unity_audit"); OUT.mkdir(exist_ok=True)
EXPORT=OUT/"exported"; EXPORT.mkdir(exist_ok=True)
rows=[]; errors=[]; counts=collections.Counter(); previews=[]
skin_records=[]; animation_records=[]; controller_records=[]; avatar_records=[]; scene_records=[]; library_rows=[]
DATA_PREFIX="resources/assets/bin/Data/"

def safe(s):
    s=re.sub(r"[^A-Za-z0-9._-]+","_",str(s or "unnamed")).strip("._")
    return (s or "unnamed")[:90]
def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data)

def assetfile_label(af):
    for owner in (af,getattr(af,"file",None) if af is not None else None):
        if owner is None: continue
        for attr in ("name","path","file_name","filename"):
            try:
                value=getattr(owner,attr,None)
                if isinstance(value,str) and value and value!="<SerializedFile>":
                    return value
            except Exception: pass
    return str(af or "")
def source_label(obj):
    return assetfile_label(getattr(obj,"assets_file",None))
def json_safe(value, depth=0):
    if depth > 10:
        return str(value)
    if value is None or isinstance(value,(str,int,float,bool)):
        return value
    if isinstance(value,bytes):
        if len(value) <= 16 * 1024 * 1024:
            return {"byte_length":len(value),"base64":base64.b64encode(value).decode("ascii")}
        return {"byte_length":len(value),"base64_omitted":True}
    if isinstance(value,(list,tuple)):
        return [json_safe(v,depth+1) for v in value]
    if isinstance(value,dict):
        return {str(k):json_safe(v,depth+1) for k,v in value.items()}
    if hasattr(value,"m_FileID") and hasattr(value,"m_PathID"):
        target=assetfile_label(getattr(value,"assetsfile",None))
        return {"m_FileID":int(getattr(value,"m_FileID",0) or 0),"m_PathID":int(getattr(value,"m_PathID",0) or 0),
                "target_source":target}
    cls_name=value.__class__.__name__
    vector_fields={"Vector2f":("x","y"),"Vector3f":("x","y","z"),"Vector4f":("x","y","z","w"),
                   "Quaternionf":("x","y","z","w"),"Quaternion":("x","y","z","w")}
    if cls_name in vector_fields:
        out={}
        for axis in vector_fields[cls_name]:
            actual=axis if hasattr(value,axis) else axis.upper()
            try: out[axis]=float(getattr(value,actual))
            except Exception: pass
        if out: return out
    if cls_name=="ColorRGBA":
        return {k:float(getattr(value,k)) for k in ("r","g","b","a") if hasattr(value,k)}
    if all(hasattr(value,f"e{i}{j}") for i in range(4) for j in range(4)):
        return {"matrix4x4":[[float(getattr(value,f"e{i}{j}")) for j in range(4)] for i in range(4)]}
    if hasattr(value,"component"):
        return {"component":json_safe(getattr(value,"component"),depth+1)}
    cls=value.__class__.__name__
    if cls=="VertexData":
        data=getattr(value,"m_DataSize",b"") or b""
        channels=[]
        for ch in (getattr(value,"m_Channels",[]) or []):
            channels.append({k:int(getattr(ch,k,0) or 0) for k in ("stream","offset","format","dimension")})
        return {"type":"VertexData","m_VertexCount":int(getattr(value,"m_VertexCount",0) or 0),
                "m_Channels":channels,"m_DataSize":json_safe(data,depth+1)}
    if cls=="BoneWeights4":
        return {"weight":json_safe(getattr(value,"weight",[]),depth+1),
                "boneIndex":json_safe(getattr(value,"boneIndex",[]),depth+1)}
    if hasattr(value,"__dict__"):
        return {str(k):json_safe(v,depth+1) for k,v in vars(value).items() if k not in ("reader","assets_file")}
    slots=getattr(value.__class__,"__slots__",())
    if slots:
        if isinstance(slots,str): slots=(slots,)
        out={}
        for key in slots:
            if key in ("reader","assets_file"): continue
            try: out[str(key)]=json_safe(getattr(value,key),depth+1)
            except Exception: pass
        if out: return out
    fields=getattr(value,"_fields",())
    if fields:
        return {str(k):json_safe(getattr(value,k),depth+1) for k in fields if k not in ("reader","assets_file")}
    return str(value)
def selected_fields(data, names):
    out={}
    for name in names:
        if hasattr(data,name):
            try: out[name]=json_safe(getattr(data,name))
            except Exception as e: out[name]={"error":str(e)[:200]}
    return out
def main():
    import UnityPy
    from PIL import Image, ImageDraw
    with zipfile.ZipFile(ARCHIVE) as z:
        names=set(z.namelist())
        data_names=[n for n in names if n.startswith(DATA_PREFIX) and not n.endswith("/")]
        # APK decompiler split large Unity serialized files into numbered 1 MiB pieces.
        # Reassemble each family in numeric order and keep resource sidecars beside it.
        groups=collections.defaultdict(list)
        for n in data_names:
            rel=n[len(DATA_PREFIX):]
            m=re.match(r"^(.*?)(?:\.split)(\d+)$",rel)
            if m: groups[m.group(1)].append((int(m.group(2)),n))
        with tempfile.TemporaryDirectory(prefix="blockgun_unity_") as td:
            root=pathlib.Path(td)
            assembled=[]
            for base,parts in groups.items():
                dest=root/base
                dest.parent.mkdir(parents=True,exist_ok=True)
                with open(dest,"wb") as out:
                    for idx,n in sorted(parts):
                        with z.open(n) as src:
                            while True:
                                b=src.read(1024*1024)
                                if not b: break
                                out.write(b)
                assembled.append((base,dest,len(parts)))
            # Copy resource sidecars and standalone Unity metadata files.
            for n in data_names:
                rel=n[len(DATA_PREFIX):]
                if rel.endswith((".resource",".ress")) or rel in ("globalgamemanagers","globalgamemanagers.assets"):
                    dest=root/rel; dest.parent.mkdir(parents=True,exist_ok=True)
                    with z.open(n) as src, open(dest,"wb") as out:
                        while True:
                            b=src.read(1024*1024)
                            if not b: break
                            out.write(b)
            # Copy valid UnityFS/UnityWeb/UnityRaw bundles outside the base asset root.
            # They are probed one-by-one later; bulk-loading unrelated Android files can crash UnityPy.
            bundle_exts=(".bundle",".unity3d",".assetbundle",".ab")
            bundle_markers=("/aa/android/","/assetbundles/","/streamingassets/")
            bundle_manifest=[]
            for n in sorted(x for x in names if not x.endswith("/")):
                low=n.lower()
                explicit=low.endswith(bundle_exts)
                if not explicit and not any(marker in low for marker in bundle_markers):
                    continue
                try:
                    with z.open(n) as src: header=src.read(32)
                except Exception: continue
                magic=next((m.decode("ascii") for m in (b"UnityFS",b"UnityWeb",b"UnityRaw",b"UnityArchive",b"CAB-") if header.startswith(m)), "")
                if not explicit and not magic:
                    continue
                rel=PurePosixPath(n)
                dest=OUT/"bundle_candidates"/(safe(rel.parent.name)+"_"+safe(rel.name))
                dest.parent.mkdir(parents=True,exist_ok=True)
                with z.open(n) as src, open(dest,"wb") as out:
                    total=0
                    while True:
                        b=src.read(1024*1024)
                        if not b: break
                        out.write(b); total+=len(b)
                bundle_manifest.append({"archive_path":n,"extracted_path":str(dest.relative_to(OUT)),"size":total,"magic":magic or "extension"})
            with open(OUT/"ARCHIVE_BUNDLE_CANDIDATES.csv","w",newline="",encoding="utf-8") as fh:
                w=csv.DictWriter(fh,fieldnames=["archive_path","extracted_path","size","magic"]);w.writeheader();w.writerows(bundle_manifest)
            print("REASSEMBLED",len(assembled),"BUNDLE_CANDIDATES",len(bundle_manifest),"BUNDLE_BYTES",sum(x["size"] for x in bundle_manifest))
            for entry in bundle_manifest: print("BUNDLE_CANDIDATE",entry)
            env=UnityPy.load(str(root))
            objects=list(env.objects)
            print("UNITY_OBJECTS",len(objects))
            for idx,obj in enumerate(objects):
                typ=getattr(obj.type,"name",str(obj.type))
                try:
                    data=obj.read()
                    name=getattr(data,"m_Name","") or getattr(data,"name","") or ""
                    pid=getattr(obj,"path_id",idx)
                    source=source_label(obj)
                    row={"source":source[:220],"path_id":str(pid),"type":typ,"name":str(name)[:250],"status":"metadata"}
                    counts[typ]+=1
                    base=safe(pathlib.Path(source).stem)+"_"+safe(typ)+"_"+safe(name or pid)
                    if typ=="Mesh" and (str(name).startswith("sk_char_") or str(name) in ("sk_gloves","sk_bomb_fp")):
                        skin_records.append({"source":source,"path_id":str(pid),"name":str(name),
                          "external_files":json_safe(getattr(getattr(obj,"assets_file",None),"externals",[]) or []),
                          "fields":selected_fields(data,["m_Vertices","m_Normals","m_UV0","m_UV1","m_Skin","m_BindPose","m_BoneNameHashes","m_RootBoneNameHash","m_SubMeshes","m_Indices","m_VertexData","m_CompressedMesh"])})
                    elif typ=="AnimationClip":
                        animation_records.append({"source":source,"path_id":str(pid),"name":str(name),
                          "fields":selected_fields(data,["m_SampleRate","m_Legacy","m_Compressed","m_UseHighQualityCurve","m_RotationCurves","m_PositionCurves","m_ScaleCurves","m_FloatCurves","m_PPtrCurves","m_MuscleClip","m_ClipBindingConstant","m_AnimationClipSettings"])})
                    elif typ=="AnimatorController":
                        controller_records.append({"source":source,"path_id":str(pid),"name":str(name),
                          "fields":selected_fields(data,["m_AnimatorLayers","m_AnimatorParameters","m_Controller","m_AnimationClips","m_ClipArray","m_ClipCount","m_MotionSet","m_ClipIDArray"])})
                    elif typ=="Avatar":
                        avatar_records.append({"source":source,"path_id":str(pid),"name":str(name),
                          "fields":selected_fields(data,["m_Avatar","m_TOS","m_Name"])})
                    scene_types=("GameObject","Transform","RectTransform","Canvas","CanvasRenderer","CanvasGroup","MonoBehaviour","MeshFilter","MeshRenderer","SkinnedMeshRenderer","Animator","SpriteRenderer","AudioSource","Camera","PrefabInstance","PrefabModification","PropertyModification")
                    if typ in scene_types:
                        fields_by_type={
                          "GameObject":["m_Component","m_IsActive","m_Layer","m_Tag","m_Name","m_PrefabInstance","m_PrefabAsset","m_CorrespondingSourceObject","m_PrefabInternal","m_PrefabParentObject"],
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
                          "AudioSource":["m_GameObject","m_Enabled","m_audioClip","m_Volume","m_Pitch","m_Loop","m_PlayOnAwake"],
                          "Camera":["m_GameObject","m_Enabled","m_FieldOfView","m_NearClipPlane","m_FarClipPlane"],
                          "PrefabInstance":["m_SourcePrefab","m_Modification","m_RemovedComponents","m_AddedComponents","m_TransformParent"],
                          "PrefabModification":["m_Target","m_PropertyPath","m_Value","m_ObjectReference"],
                          "PropertyModification":["target","propertyPath","value","objectReference"]
                        }
                        record={"source":source,"path_id":str(pid),"type":typ,"name":str(name)[:250],
                                "external_files":json_safe(getattr(getattr(obj,"assets_file",None),"externals",[]) or []),
                                "fields":selected_fields(data,fields_by_type.get(typ,[]))}
                        if typ=="MonoBehaviour":
                            try: record["serialized_fields"]=json_safe(obj.read_typetree())
                            except Exception as e: record["typetree_error"]=str(e)[:200]
                        scene_records.append(record)
                    if typ in ("Texture2D","Sprite"):
                        try:
                            im=data.image
                            if im:
                                target=EXPORT/"textures"/(base+".png")
                                target.parent.mkdir(parents=True,exist_ok=True); im.save(target)
                                row["exported"]=str(target)
                                if len(previews)<300:
                                    thumb=im.convert("RGB"); thumb.thumbnail((180,120))
                                    previews.append((thumb.copy(),str(name or pid)[:42]))
                        except Exception as e: row["export_error"]="image: "+str(e)[:250]
                    elif typ=="Mesh":
                        try:
                            result=data.export()
                            payload=result if isinstance(result,bytes) else str(result).encode("utf-8")
                            target=EXPORT/"meshes"/(base+".obj"); save(target,payload)
                            row["exported"]=str(target)
                        except Exception as e: row["export_error"]="mesh: "+str(e)[:250]
                    elif typ=="AudioClip":
                        try:
                            samples=data.samples; saved=[]
                            for sn,blob in (samples or {}).items():
                                target=EXPORT/"audio"/(base+"_"+safe(sn)+(PurePosixPath(str(sn)).suffix or ".audio"))
                                save(target,blob); saved.append(str(target))
                            if saved: row["exported"]=";".join(saved)
                        except Exception as e: row["export_error"]="audio: "+str(e)[:250]
                    elif typ in ("GameObject","Prefab","Transform","Animator","AnimationClip","RuntimeAnimatorController","Material","Shader","MeshRenderer","SkinnedMeshRenderer","TerrainData"):
                        for attr in ("m_IsActive","m_Tag","m_Layer","m_LocalPosition","m_LocalScale","m_LocalRotation","m_Enabled","m_AnimationType"):
                            if hasattr(data,attr):
                                try: row[attr]=str(getattr(data,attr))[:300]
                                except Exception: pass
                    rows.append(row)
                except Exception as e:
                    errors.append("object "+str(getattr(obj,"path_id",idx))+": "+str(e)[:250])
    # Preserve a curated, traceable library of gameplay assets and source stubs.
    source_assets=OUT/"source_assets"
    source_scripts=OUT/"source_scripts"
    script_names=[
      "GameManager.cs","GameModeBase.cs","GameModeData.cs","TeamDeathMatchMode.cs",
      "PlayerController.cs","PlayerInstantiationData.cs","PlayerUIController.cs","PhotonPlayerInput.cs",
      "PhotonPlayerCharacter.cs","PhotonAIInput.cs","PhotonAICharacter.cs","BotInstantiationData.cs",
      "AIController.cs","AIBehaviorData.cs","WeaponBase.cs","Weapon.cs","WeaponLoader.cs",
      "WeaponManager.cs","WeaponAnimation.cs","LocalWeapon.cs","LocalAnimator.cs","RemoteAnimator.cs",
      "SpawnPointManager.cs","SpawnPoint.cs","Bullet.cs","BulletData.cs","Projectile.cs","PhotonHealth.cs",
      "DamageIndicator.cs","InputManager.cs","Crosshair.cs","WindowMainMenu.cs","MainMenuTutorialController.cs",
      "TutorialController.cs","InGameInputController.cs","WindowGameMode.cs","WindowLobby.cs",
      "DialogMatchResult.cs","FollowCamerasManager.cs","CameraIdentity.cs"
    ]
    # Reopen the source archive: the earlier Unity parsing context has already closed it.
    with zipfile.ZipFile(ARCHIVE) as source_zip:
        for n in names:
            base_name=PurePosixPath(n).name
            if n.startswith("unity/scripts/csharp/") and base_name in script_names:
                dest=source_scripts/PurePosixPath(n).relative_to("unity/scripts/csharp")
                blob=source_zip.read(n); save(dest,blob)
                library_rows.append({"category":"script_stub","original_path":n,"exported_path":str(dest),"size_bytes":len(blob),"sha256":hashlib.sha256(blob).hexdigest()})
    model_tokens=("sk_char_","m4a1_1.obj","AK_47_2.obj","MP5_794","AWP_2.obj","M249_2.obj","Desert_Eagle_2.obj","M1014_3.obj","Famas_4.obj","P90_1.obj","UMP_45_2.obj")
    texture_tokens=("SimpleMilitary_Soldier01_Black","AK_47_Diffuse","M4A1_Diffuse","MP5_Diffuse","AWP_Diffuse","M249_Diffuse","Desert_Eagle_Diffuse","M1014_Diffuse","Famas_Diffuse","P90_Diffuse","UMP_45_Diffuse","ui_icon_weapon_m4a1","ui_icon_weapon_ak_47","ui_icon_weapon_awp","ui_icon_weapon_mp5")
    audio_tokens=("bg_menu_hazmob","bg_matchStart","bg_start_round","btn_start","ak47_fire","m4a1_fire","mp5_fire","awp_fire","reload","jump","footstep","footsteps","bullet_")
    with zipfile.ZipFile(ARCHIVE) as source_zip:
        for n in sorted(names):
            if n.startswith("unity/assets/meshes/") and n.lower().endswith(".obj") and any(t.lower() in PurePosixPath(n).name.lower() for t in model_tokens):
                dest=source_assets/"meshes"/PurePosixPath(n).name
            elif n.startswith(("unity/assets/textures/","unity/assets/sprites/")) and n.lower().endswith((".png",".jpg",".jpeg")) and any(t.lower() in PurePosixPath(n).name.lower() for t in texture_tokens):
                dest=source_assets/("sprites" if "/sprites/" in n else "textures")/PurePosixPath(n).name
            elif n.startswith("unity/assets/audio/") and n.lower().endswith((".wav",".ogg",".mp3")) and any(t.lower() in PurePosixPath(n).name.lower() for t in audio_tokens):
                dest=source_assets/"audio"/PurePosixPath(n).name
            else:
                continue
            blob=source_zip.read(n); save(dest,blob)
            library_rows.append({"category":dest.parent.name,"original_path":n,"exported_path":str(dest),"size_bytes":len(blob),"sha256":hashlib.sha256(blob).hexdigest()})
    # Preserve the exact renderer, mesh, armature and bone Transform hierarchy for every recovered skinned mesh.
    catalog_by_key={(r.get("source",""),str(r.get("path_id",""))):r for r in rows}
    transform_by_key={(r.get("source",""),str(r.get("path_id",""))):r for r in scene_records if r.get("type") in ("Transform","RectTransform")}
    gameobject_by_key={(r.get("source",""),str(r.get("path_id",""))):r for r in scene_records if r.get("type")=="GameObject"}
    transform_by_go={}
    for tr in transform_by_key.values():
        gp=tr.get("fields",{}).get("m_GameObject",{})
        transform_by_go[(tr.get("source",""),str(gp.get("m_PathID","0")))]=tr
    skin_names={x.get("name","") for x in skin_records}
    def resolve_record_source(owner_source, external_files, ptr):
        if not isinstance(ptr,dict): return owner_source
        fid=int(ptr.get("m_FileID",0) or 0)
        if fid>0 and fid<=len(external_files):
            return str(external_files[fid-1].get("path",owner_source))
        return owner_source
    included_transforms={}
    included_gameobjects={}
    rig_renderers=[]
    def add_transform_chain(src,pid):
        current=str(pid)
        visited=set()
        while current and current!="0" and (src,current) not in visited:
            visited.add((src,current))
            tr=transform_by_key.get((src,current))
            if not tr: break
            included_transforms[(src,current)]=tr
            gp=tr.get("fields",{}).get("m_GameObject",{})
            gsrc=resolve_record_source(src,tr.get("external_files",[]),gp)
            gid=str(gp.get("m_PathID","0"))
            go=gameobject_by_key.get((gsrc,gid))
            if go: included_gameobjects[(gsrc,gid)]=go
            father=tr.get("fields",{}).get("m_Father",{})
            src=resolve_record_source(src,tr.get("external_files",[]),father)
            current=str(father.get("m_PathID","0"))
    for smr in (r for r in scene_records if r.get("type")=="SkinnedMeshRenderer"):
        fields=smr.get("fields",{}); ext=smr.get("external_files",[])
        mesh_ptr=fields.get("m_Mesh",{})
        mesh_source=resolve_record_source(smr.get("source",""),ext,mesh_ptr)
        mesh_row=catalog_by_key.get((mesh_source,str(mesh_ptr.get("m_PathID","0"))),{})
        mesh_name=mesh_row.get("name","")
        if mesh_name not in skin_names: continue
        go_ptr=fields.get("m_GameObject",{})
        go_source=resolve_record_source(smr.get("source",""),ext,go_ptr)
        go_id=str(go_ptr.get("m_PathID","0"))
        go=gameobject_by_key.get((go_source,go_id))
        mesh_tr=transform_by_go.get((go_source,go_id))
        if mesh_tr: add_transform_chain(mesh_tr.get("source",""),mesh_tr.get("path_id","0"))
        bone_records=[]
        for bone_index,bone_ptr in enumerate(fields.get("m_Bones",[]) or []):
            bone_source=resolve_record_source(smr.get("source",""),ext,bone_ptr)
            bone_id=str(bone_ptr.get("m_PathID","0"))
            if bone_id!="0": add_transform_chain(bone_source,bone_id)
            bone_records.append({"mesh_bone_index":bone_index,"source":bone_source,"path_id":bone_id})
        root_ptr=fields.get("m_RootBone",{})
        root_source=resolve_record_source(smr.get("source",""),ext,root_ptr)
        if str(root_ptr.get("m_PathID","0"))!="0": add_transform_chain(root_source,root_ptr.get("m_PathID","0"))
        rig_renderers.append({"source":smr.get("source"),"path_id":smr.get("path_id"),"mesh_name":mesh_name,
            "mesh_source":mesh_source,"mesh_path_id":str(mesh_ptr.get("m_PathID","0")),
            "gameobject_source":go_source,"gameobject_path_id":go_id,"gameobject_name":go.get("name","") if go else "",
            "mesh_transform":mesh_tr,"bones":bone_records,"root_bone":{"source":root_source,"path_id":str(root_ptr.get("m_PathID","0"))},
            "materials":fields.get("m_Materials",[])})
    (OUT/"UNITY_RIG_HIERARCHY.json").write_text(json.dumps({"renderers":rig_renderers,
        "transforms":list(included_transforms.values()),"gameobjects":list(included_gameobjects.values())},ensure_ascii=False,indent=2),encoding="utf-8")
    # Export the complete original gameplay HUD hierarchy and exact RectTransform layout.
    hud_root=next((r for r in scene_records if r.get("type")=="GameObject" and r.get("name")=="WindowPlayer"),None)
    hud_elements=[]
    if hud_root:
        hud_source=hud_root.get("source","")
        def walk_hud(src,transform_id,parent_path="",depth=0):
            if depth>32: return
            tr=transform_by_key.get((src,str(transform_id)))
            if not tr: return
            tf=tr.get("fields",{})
            gp=tf.get("m_GameObject",{})
            gsrc=resolve_record_source(src,tr.get("external_files",[]),gp)
            gid=str(gp.get("m_PathID","0"))
            go=gameobject_by_key.get((gsrc,gid))
            if not go: return
            name=go.get("name","")
            path=(parent_path+"/"+name).strip("/")
            components=[]
            for pair in go.get("fields",{}).get("m_Component",[]) or []:
                ptr=pair.get("component",{})
                csrc=resolve_record_source(gsrc,go.get("external_files",[]),ptr)
                cid=str(ptr.get("m_PathID","0"))
                comp=next((x for x in scene_records if x.get("source")==csrc and str(x.get("path_id"))==cid),None)
                components.append({"source":csrc,"path_id":cid,"type":comp.get("type","") if comp else "",
                    "name":comp.get("name","") if comp else "","resolved":bool(comp)})
            rect={k:tf[k] for k in ("m_AnchoredPosition","m_AnchoredPosition3D","m_SizeDelta","m_AnchorMin","m_AnchorMax","m_Pivot","m_LocalPosition","m_LocalRotation","m_LocalScale") if k in tf}
            hud_elements.append({"source":gsrc,"path_id":gid,"name":name,"path":path,"parent_path":parent_path,
                "depth":depth,"active":go.get("fields",{}).get("m_IsActive",True),"layer":go.get("fields",{}).get("m_Layer",0),
                "rect":rect,"components":components})
            for child in tf.get("m_Children",[]) or []:
                csrc=resolve_record_source(src,tr.get("external_files",[]),child)
                walk_hud(csrc,child.get("m_PathID","0"),path,depth+1)
        root_transform=transform_by_go.get((hud_source,str(hud_root.get("path_id"))))
        if root_transform: walk_hud(hud_source,root_transform.get("path_id","0"))
    (OUT/"UNITY_HUD_LAYOUT.json").write_text(json.dumps({"root":"WindowPlayer","elements":hud_elements},ensure_ascii=False,indent=2),encoding="utf-8")
    (OUT/"UNITY_SKINNING_DATA.json").write_text(json.dumps(skin_records,ensure_ascii=False,indent=2),encoding="utf-8")
    (OUT/"UNITY_SCENE_OBJECTS.json").write_text(json.dumps(scene_records,ensure_ascii=False,indent=2),encoding="utf-8")
    (OUT/"UNITY_ANIMATION_DATA.json").write_text(json.dumps(animation_records,ensure_ascii=False,indent=2),encoding="utf-8")
    (OUT/"UNITY_ANIMATOR_DATA.json").write_text(json.dumps({"controllers":controller_records,"avatars":avatar_records},ensure_ascii=False,indent=2),encoding="utf-8")
    with open(OUT/"GAMEPLAY_ASSET_LIBRARY.csv","w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=["category","original_path","exported_path","size_bytes","sha256"]); w.writeheader(); w.writerows(library_rows)
    print("GAMEPLAY_LIBRARY",len(library_rows),"SKINNED_MESHES",len(skin_records),"ANIMATION_CLIPS",len(animation_records),"CONTROLLERS",len(controller_records),"AVATARS",len(avatar_records))
    with open(OUT/"UNITY_OBJECT_CATALOG.csv","w",newline="",encoding="utf-8") as f:
        fields=sorted({k for r in rows for k in r}); w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    summary={"input_zip_bytes":ARCHIVE.stat().st_size,"split_families_reassembled":len(assembled),
      "split_sources":sum(x[2] for x in assembled),"bundle_files":len(bundle_manifest),
      "objects_catalogued":len(rows),"types":dict(counts.most_common()),
      "exported_files":sum(1 for r in rows if r.get("exported")),"skinned_meshes":len(skin_records),"animation_clips":len(animation_records),"gameplay_library_files":len(library_rows),"errors_count":len(errors),"errors":errors[:500]}
    (OUT/"UNITY_ASSET_AUDIT.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    if previews:
        cols=4; cw,ch=210,155
        sheet=Image.new("RGB",(cols*cw,((len(previews)+cols-1)//cols)*ch),"white"); d=ImageDraw.Draw(sheet)
        for i,(im,label) in enumerate(previews):
            x=(i%cols)*cw; y=(i//cols)*ch; sheet.paste(im,(x+(180-im.width)//2,y)); d.text((x+5,y+123),label,fill="black")
        sheet.save(OUT/"UNITY_TEXTURE_CONTACT_SHEET.jpg",quality=88)
    lines=["# Auditoria especializada de recursos Unity - Block Gun 3D","",
      "- Famílias .split reconstruídas: **%s**"%len(assembled),
      "- Partes .split utilizadas: **%s**"%summary["split_sources"],
      "- Bundles Unity adicionais: **%s**"%len(bundle_manifest),
      "- Objetos catalogados: **%s**"%len(rows),
      "- Tipos Unity: **%s**"%len(counts),
      "- Objetos exportados: **%s**"%summary["exported_files"],
      "- Erros individuais: **%s**"%len(errors),"","## Tipos de objetos"]
    lines += ["- **%s**: %s"%(k,v) for k,v in counts.most_common()]
    lines += ["","## Exportações","- UNITY_OBJECT_CATALOG.csv: catálogo por tipo, nome, arquivo e ID.",
      "- exported/textures/: texturas e sprites PNG exportados.",
      "- exported/meshes/: malhas OBJ exportadas.",
      "- exported/audio/: amostras de áudio extraídas.",
      "- UNITY_TEXTURE_CONTACT_SHEET.jpg: prévia visual de até 300 texturas.",
      "- UNITY_ASSET_AUDIT.json: resumo e erros completos (até 500 entradas).",
      "- UNITY_SKINNING_DATA.json: pesos, bind poses e hashes de ossos dos modelos de personagem.",
      "- UNITY_ANIMATION_DATA.json: curvas e metadados dos clipes de animação.",
      "- UNITY_ANIMATOR_DATA.json: controladores e avatares recuperados.",
      "- source_scripts/: stubs C# selecionados para reconstruir o fluxo de jogo.",
      "- source_assets/: modelos, texturas e sons de gameplay selecionados.",
      "- GAMEPLAY_ASSET_LIBRARY.csv: origem, tamanho e SHA-256 de cada recurso preservado.",
      "","## Limitações","- Arquivos .split foram concatenados em ordem numérica antes da leitura.",
      "- Recursos ausentes, protegidos ou incompatíveis podem impedir a exportação de alguns objetos.",
      "- O processo não recupera o projeto Unity original nem o código-fonte C# original."]
    (OUT/"UNITY_ASSET_AUDIT.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines)); print("ERROR_SAMPLE",json.dumps(errors[:20],ensure_ascii=False))
if __name__=="__main__": main()
