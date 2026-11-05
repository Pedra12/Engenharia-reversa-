#!/usr/bin/env python3
"""Reconstrói arquivos Unity divididos em .splitN e extrai objetos via UnityPy."""
import zipfile, pathlib, tempfile, json, csv, re, collections, os, hashlib
from pathlib import PurePosixPath
ARCHIVE=pathlib.Path("blockgun.zip")
OUT=pathlib.Path("unity_audit"); OUT.mkdir(exist_ok=True)
EXPORT=OUT/"exported"; EXPORT.mkdir(exist_ok=True)
rows=[]; errors=[]; counts=collections.Counter(); previews=[]
skin_records=[]; animation_records=[]; controller_records=[]; avatar_records=[]; library_rows=[]
DATA_PREFIX="resources/assets/bin/Data/"

def safe(s):
    s=re.sub(r"[^A-Za-z0-9._-]+","_",str(s or "unnamed")).strip("._")
    return (s or "unnamed")[:90]
def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data)

def json_safe(value, depth=0):
    if depth > 10:
        return str(value)
    if value is None or isinstance(value,(str,int,float,bool)):
        return value
    if isinstance(value,bytes):
        return {"byte_length":len(value)}
    if isinstance(value,(list,tuple)):
        return [json_safe(v,depth+1) for v in value]
    if isinstance(value,dict):
        return {str(k):json_safe(v,depth+1) for k,v in value.items()}
    if hasattr(value,"__dict__"):
        return {str(k):json_safe(v,depth+1) for k,v in vars(value).items() if k not in ("reader","assets_file")}
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
            # Also parse already-extracted Unity bundle containers, if present.
            bundle_names=[n for n in names if n.startswith("unity/assets/") and n.lower().endswith((".bundle",".unity3d",".assetbundle"))]
            for n in bundle_names:
                dest=root/("bundles"/PurePosixPath(n).name)
                dest.parent.mkdir(parents=True,exist_ok=True)
                with z.open(n) as src, open(dest,"wb") as out:
                    while True:
                        b=src.read(1024*1024)
                        if not b: break
                        out.write(b)
            print("REASSEMBLED",len(assembled),"BUNDLES",len(bundle_names))
            env=UnityPy.load(str(root))
            objects=list(env.objects)
            print("UNITY_OBJECTS",len(objects))
            for idx,obj in enumerate(objects):
                typ=getattr(obj.type,"name",str(obj.type))
                try:
                    data=obj.read()
                    name=getattr(data,"m_Name","") or getattr(data,"name","") or ""
                    pid=getattr(obj,"path_id",idx)
                    source=str(getattr(obj,"assets_file",None) or "")
                    row={"source":source[:220],"path_id":str(pid),"type":typ,"name":str(name)[:250],"status":"metadata"}
                    counts[typ]+=1
                    base=safe(pathlib.Path(source).stem)+"_"+safe(typ)+"_"+safe(name or pid)
                    if typ=="Mesh" and (str(name).startswith("sk_char_") or str(name) in ("sk_gloves","sk_bomb_fp")):
                        skin_records.append({"source":source,"path_id":str(pid),"name":str(name),
                          "fields":selected_fields(data,["m_Vertices","m_Normals","m_UV0","m_Skin","m_BindPose","m_BoneNameHashes","m_RootBoneNameHash","m_SubMeshes"])})
                    elif typ=="AnimationClip":
                        animation_records.append({"source":source,"path_id":str(pid),"name":str(name),
                          "fields":selected_fields(data,["m_SampleRate","m_Legacy","m_Compressed","m_UseHighQualityCurve","m_RotationCurves","m_PositionCurves","m_ScaleCurves","m_FloatCurves","m_PPtrCurves","m_MuscleClip","m_ClipBindingConstant","m_AnimationClipSettings"])})
                    elif typ=="AnimatorController":
                        controller_records.append({"source":source,"path_id":str(pid),"name":str(name),
                          "fields":selected_fields(data,["m_AnimatorLayers","m_AnimatorParameters","m_Controller"])})
                    elif typ=="Avatar":
                        avatar_records.append({"source":source,"path_id":str(pid),"name":str(name),
                          "fields":selected_fields(data,["m_Avatar","m_TOS","m_Name"])})
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
                    elif typ=="Material":
                        # Preserve serialized Unity material settings instead of guessing
                        # colors/textures/shaders later in the Godot conversion.
                        material_fields=selected_fields(data,[
                            "m_Name","m_Shader","m_SavedProperties","m_CustomRenderQueue",
                            "m_EnableInstancing","m_DoubleSidedGI","m_ValidKeywords",
                            "m_InvalidKeywords","m_LightmapFlags","m_Flags"
                        ])
                        row["material_data"]=json.dumps(material_fields,ensure_ascii=False)[:12000]
                        try:
                            shader=getattr(data,"m_Shader",None)
                            row["shader_path_id"]=str(getattr(shader,"path_id","") or "")
                        except Exception: pass
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
    (OUT/"UNITY_SKINNING_DATA.json").write_text(json.dumps(skin_records,ensure_ascii=False,indent=2),encoding="utf-8")
    (OUT/"UNITY_ANIMATION_DATA.json").write_text(json.dumps(animation_records,ensure_ascii=False,indent=2),encoding="utf-8")
    (OUT/"UNITY_ANIMATOR_DATA.json").write_text(json.dumps({"controllers":controller_records,"avatars":avatar_records},ensure_ascii=False,indent=2),encoding="utf-8")
    with open(OUT/"GAMEPLAY_ASSET_LIBRARY.csv","w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=["category","original_path","exported_path","size_bytes","sha256"]); w.writeheader(); w.writerows(library_rows)
    print("GAMEPLAY_LIBRARY",len(library_rows),"SKINNED_MESHES",len(skin_records),"ANIMATION_CLIPS",len(animation_records),"CONTROLLERS",len(controller_records),"AVATARS",len(avatar_records))
    with open(OUT/"UNITY_OBJECT_CATALOG.csv","w",newline="",encoding="utf-8") as f:
        fields=sorted({k for r in rows for k in r}); w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    summary={"input_zip_bytes":ARCHIVE.stat().st_size,"split_families_reassembled":len(assembled),
      "split_sources":sum(x[2] for x in assembled),"bundle_files":len(bundle_names),
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
      "- Bundles Unity adicionais: **%s**"%len(bundle_names),
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
