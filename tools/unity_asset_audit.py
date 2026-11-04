#!/usr/bin/env python3
"""Reconstrói arquivos Unity divididos em .splitN e extrai objetos via UnityPy."""
import zipfile, pathlib, tempfile, json, csv, re, collections, os
from pathlib import PurePosixPath
ARCHIVE=pathlib.Path("blockgun.zip")
OUT=pathlib.Path("unity_audit"); OUT.mkdir(exist_ok=True)
EXPORT=OUT/"exported"; EXPORT.mkdir(exist_ok=True)
rows=[]; errors=[]; counts=collections.Counter(); previews=[]
DATA_PREFIX="resources/assets/bin/Data/"

def safe(s):
    s=re.sub(r"[^A-Za-z0-9._-]+","_",str(s or "unnamed")).strip("._")
    return (s or "unnamed")[:90]
def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(data)

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
    with open(OUT/"UNITY_OBJECT_CATALOG.csv","w",newline="",encoding="utf-8") as f:
        fields=sorted({k for r in rows for k in r}); w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    summary={"input_zip_bytes":ARCHIVE.stat().st_size,"split_families_reassembled":len(assembled),
      "split_sources":sum(x[2] for x in assembled),"bundle_files":len(bundle_names),
      "objects_catalogued":len(rows),"types":dict(counts.most_common()),
      "exported_files":sum(1 for r in rows if r.get("exported")),"errors_count":len(errors),"errors":errors[:500]}
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
      "","## Limitações","- Arquivos .split foram concatenados em ordem numérica antes da leitura.",
      "- Recursos ausentes, protegidos ou incompatíveis podem impedir a exportação de alguns objetos.",
      "- O processo não recupera o projeto Unity original nem o código-fonte C# original."]
    (OUT/"UNITY_ASSET_AUDIT.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines)); print("ERROR_SAMPLE",json.dumps(errors[:20],ensure_ascii=False))
if __name__=="__main__": main()
