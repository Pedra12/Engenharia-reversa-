#!/usr/bin/env python3
"""Auditoria especializada dos objetos Unity recuperáveis do ZIP do Block Gun."""
import zipfile, pathlib, tempfile, json, csv, hashlib, re, collections, traceback
from io import BytesIO

ARCHIVE=pathlib.Path("blockgun.zip")
OUT=pathlib.Path("unity_audit")
OUT.mkdir(exist_ok=True)
EXPORT=OUT/"exported"
EXPORT.mkdir(exist_ok=True)
rows=[]
errors=[]
counts=collections.Counter()
previews=[]

def safe(s):
    s=re.sub(r"[^A-Za-z0-9._-]+","_",str(s or "unnamed")).strip("._")
    return (s or "unnamed")[:90]

def save_bytes(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(data)

def main():
    try:
        import UnityPy
    except Exception as e:
        raise SystemExit("UnityPy não instalado: "+str(e))
    try:
        from PIL import Image, ImageDraw
        pil_ok=True
    except Exception:
        pil_ok=False
    with zipfile.ZipFile(ARCHIVE) as outer:
        candidates=[]
        for info in outer.infolist():
            if info.is_dir(): continue
            n=info.filename
            low=n.lower()
            if low.startswith("unity/assets/") and (low.endswith((".assets",".bundle",".unity3d",".assetbundle",".resource",".ress"))):
                candidates.append(info)
        # Feed serialized files and bundle containers to UnityPy. Resource sidecars are retained
        # in the temp tree so UnityPy can resolve external stream data when possible.
        with tempfile.TemporaryDirectory(prefix="blockgun_unity_") as td:
            root=pathlib.Path(td)
            for info in candidates:
                dest=root/info.filename
                dest.parent.mkdir(parents=True,exist_ok=True)
                with outer.open(info) as src, open(dest,"wb") as dst:
                    while True:
                        b=src.read(1024*1024)
                        if not b: break
                        dst.write(b)
            # Group by likely Unity container, with all sidecars available in their original paths.
            for info in candidates:
                n=info.filename
                low=n.lower()
                if low.endswith((".resource",".ress")): continue
                p=root/n
                try:
                    env=UnityPy.load(str(p))
                    obj_list=list(env.objects)
                    for idx,obj in enumerate(obj_list):
                        typ=getattr(obj.type,"name",str(obj.type))
                        try:
                            data=obj.read()
                            name=getattr(data,"m_Name","") or getattr(data,"name","") or ""
                            pid=getattr(obj,"path_id",idx)
                            row={"source":n,"path_id":str(pid),"type":typ,"name":str(name)[:250],"status":"metadata"}
                            counts[typ]+=1
                            base=safe(pathlib.Path(n).stem)+"_"+safe(typ)+"_"+safe(name or pid)
                            if typ in ("Texture2D","Sprite"):
                                try:
                                    im=data.image
                                    if im:
                                        target=EXPORT/"textures"/(base+".png")
                                        target.parent.mkdir(parents=True,exist_ok=True)
                                        im.save(target)
                                        row["exported"]=str(target)
                                        if pil_ok and len(previews)<240:
                                            thumb=im.convert("RGB"); thumb.thumbnail((180,120))
                                            previews.append((thumb.copy(),str(name or pid)[:40]))
                                except Exception as e: row["export_error"]="image: "+str(e)[:250]
                            elif typ=="Mesh":
                                try:
                                    result=data.export()
                                    if isinstance(result,bytes): payload=result
                                    else: payload=str(result).encode("utf-8")
                                    target=EXPORT/"meshes"/(base+".obj")
                                    save_bytes(target,payload)
                                    row["exported"]=str(target)
                                except Exception as e: row["export_error"]="mesh: "+str(e)[:250]
                            elif typ=="AudioClip":
                                try:
                                    samples=data.samples
                                    saved=[]
                                    for sn,blob in (samples or {}).items():
                                        ext=pathlib.Path(str(sn)).suffix or ".audio"
                                        target=EXPORT/"audio"/(base+"_"+safe(sn)+ext)
                                        save_bytes(target,blob); saved.append(str(target))
                                    if saved: row["exported"]=";".join(saved)
                                except Exception as e: row["export_error"]="audio: "+str(e)[:250]
                            elif typ in ("GameObject","Prefab","Transform","Animator","AnimationClip","RuntimeAnimatorController","Material","Shader","MeshRenderer","SkinnedMeshRenderer","TerrainData"):
                                # Store useful serializable metadata, not opaque object dumps.
                                for attr in ("m_IsActive","m_Tag","m_Layer","m_LocalPosition","m_LocalScale","m_LocalRotation","m_Enabled","m_AnimationType"):
                                    if hasattr(data,attr):
                                        try: row[attr]=str(getattr(data,attr))[:300]
                                        except Exception: pass
                            rows.append(row)
                        except Exception as e:
                            errors.append(n+" object "+str(getattr(obj,"path_id",idx))+": "+str(e)[:250])
                except Exception as e:
                    errors.append(n+": "+str(e)[:350])
    with open(OUT/"UNITY_OBJECT_CATALOG.csv","w",newline="",encoding="utf-8") as f:
        fields=sorted({k for r in rows for k in r})
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    summary={"input_zip_bytes":ARCHIVE.stat().st_size,"unity_candidate_files":len(candidates),"objects_catalogued":len(rows),
             "types":dict(counts.most_common()),"exported_files":sum(1 for r in rows if r.get("exported")),
             "errors_count":len(errors),"errors":errors[:500]}
    (OUT/"UNITY_ASSET_AUDIT.json").write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding="utf-8")
    if pil_ok and previews:
        cols=4; cw,ch=210,155
        sheet=Image.new("RGB",(cols*cw,((len(previews)+cols-1)//cols)*ch),"white")
        d=ImageDraw.Draw(sheet)
        for i,(im,label) in enumerate(previews):
            x=(i%cols)*cw; y=(i//cols)*ch
            sheet.paste(im,(x+(180-im.width)//2,y))
            d.text((x+5,y+123),label,fill="black")
        sheet.save(OUT/"UNITY_TEXTURE_CONTACT_SHEET.jpg",quality=88)
    lines=["# Auditoria especializada de recursos Unity - Block Gun 3D","",
      "- Arquivos Unity examinados: **%s**"%len(candidates),
      "- Objetos catalogados: **%s**"%len(rows),
      "- Tipos Unity: **%s**"%len(counts),
      "- Objetos com exportação: **%s**"%summary["exported_files"],
      "- Erros individuais: **%s**"%len(errors),"","## Tipos de objetos"]
    lines += ["- **%s**: %s"%(k,v) for k,v in counts.most_common()]
    lines += ["","## Limitações","- A extração depende de os dados Unity estarem presentes e legíveis no APK decompilado.",
      "- Arquivos .resource/.resS são mantidos ao lado dos arquivos .assets para tentar resolver dados externos.",
      "- Objetos Shader podem falhar por diferenças de versão/formato; o relatório JSON registra cada erro.",
      "- O catálogo não recupera código-fonte C# original nem cenas editáveis completas."]
    (OUT/"UNITY_ASSET_AUDIT.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines))
    print("ERROR_SAMPLE",json.dumps(errors[:15],ensure_ascii=False))
if __name__=="__main__": main()
