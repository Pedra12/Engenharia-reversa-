#!/usr/bin/env python3
import os, json, csv, gzip, zipfile, tarfile, io, collections, subprocess, tempfile, pathlib, re
MAX_DEPTH=10
MAX_MEMBER=1024*1024*1024
MAX_TOTAL=6*1024*1024*1024
total_nested=0
rows=[]
archives=[]
errors=[]
exts=collections.Counter()
cats=collections.Counter()
folders=collections.Counter()
def ext(p):
    return pathlib.PurePosixPath(p).suffix.lower() or "[sem extensão]"
def category(e,p):
    groups={
      "Modelos 3D":(".obj",".fbx",".gltf",".glb",".blend",".dae",".3ds",".stl",".ply"),
      "Mapas/cenas":(".unity",".scene",".map",".terrain",".prefab"),
      "Animações/rig":(".anim",".controller",".bvh",".skeleton",".avatar"),
      "Texturas/imagens":(".png",".jpg",".jpeg",".tga",".psd",".webp",".bmp",".dds",".ktx",".astc",".pvr"),
      "Áudio":(".wav",".mp3",".ogg",".flac",".aiff",".m4a"),
      "Vídeo":(".mp4",".webm",".mov",".avi",".mkv"),
      "Código/scripts":(".cs",".java",".kt",".smali",".js",".ts",".py",".gd",".shader",".hlsl",".glsl",".cpp",".c",".h"),
      "Bibliotecas":(".dll",".so",".a",".dylib",".aar",".jar"),
      "Fontes":(".ttf",".otf",".woff",".woff2"),
      "Dados/configuração":(".json",".xml",".yaml",".yml",".ini",".cfg",".txt",".csv",".db",".sqlite",".proto"),
      "Pacotes/compactados":(".zip",".7z",".rar",".tar",".gz",".bz2",".xz",".apk",".aab",".obb",".xapk",".bundle",".unity3d")
    }
    for k,v in groups.items():
        if e in v:return k
    return "Outros"
def add(p,size,source,depth):
    e=ext(p); exts[e]+=1; cats[category(e,p)]+=1
    folders["/".join(p.split("/")[:-1]) or "[raiz]"]+=1
    rows.append((p,size,e,category(e,p),source,depth))
def isarc(name,head):
    return name.lower().endswith((".zip",".apk",".aab",".obb",".xapk",".jar",".aar",".war",".7z",".rar",".tar",".gz",".bz2",".xz",".unity3d",".bundle")) or head.startswith((b"PK\x03\x04",b"PK\x05\x06",b"\x1f\x8b",b"BZh",b"\xfd7zXZ\x00",b"7z\xbc\xaf\x27\x1c",b"Rar!\x1a\x07"))
def scan(data,label,depth):
    global total_nested
    if depth>MAX_DEPTH: errors.append("Profundidade máxima: "+label); return
    if len(data)>MAX_MEMBER: errors.append("Membro acima de 1 GiB: "+label); return
    total_nested+=len(data)
    if total_nested>MAX_TOTAL: errors.append("Limite global de 6 GiB de expansão atingido"); return
    bio=io.BytesIO(data)
    try:
      if zipfile.is_zipfile(bio):
        z=zipfile.ZipFile(bio); infos=z.infolist()
        archives.append((label,"ZIP",depth,len(infos),len(data)))
        for i in infos:
          if i.is_dir(): continue
          p=label+"!/"+i.filename; add(p,i.file_size,"membro ZIP",depth)
          if i.file_size<=MAX_MEMBER:
            try:
              with z.open(i) as f: h=f.read(16)
              if isarc(i.filename,h):
                with z.open(i) as f: scan(f.read(),p,depth+1)
            except Exception as e: errors.append(p+": "+str(e)[:200])
        return
    except Exception as e: errors.append("ZIP "+label+": "+str(e)[:200])
    bio.seek(0)
    try:
      if tarfile.is_tarfile(bio):
        bio.seek(0); t=tarfile.open(fileobj=bio,mode="r:*"); ms=t.getmembers()
        archives.append((label,"TAR",depth,len(ms),len(data)))
        for m in ms:
          if not m.isfile():continue
          p=label+"!/"+m.name; add(p,m.size,"membro TAR",depth)
          if m.size<=MAX_MEMBER:
            f=t.extractfile(m)
            if f:
              b=f.read()
              if isarc(m.name,b[:16]):scan(b,p,depth+1)
        return
    except Exception as e: errors.append("TAR "+label+": "+str(e)[:200])
    try:
      raw=None; kind=None
      if data[:2]==b"\x1f\x8b":
        import gzip as g; raw=g.decompress(data); kind="GZIP"
      elif data[:3]==b"BZh":
        import bz2; raw=bz2.decompress(data); kind="BZIP2"
      elif data[:6]==b"\xfd7zXZ\x00":
        import lzma; raw=lzma.decompress(data); kind="XZ"
      if raw is not None:
        archives.append((label,kind,depth,1,len(data)))
        add(label+"!/[conteúdo descompactado]",len(raw),"fluxo descompactado",depth)
        if isarc("",raw[:16]):scan(raw,label+"!/[conteúdo descompactado]",depth+1)
    except Exception as e: errors.append("Descompactação "+label+": "+str(e)[:200])
def main():
    top=pathlib.Path("blockgun.zip")
    with zipfile.ZipFile(top) as z:
      for i in z.infolist():
        if i.is_dir():continue
        add(i.filename,i.file_size,"ZIP principal",0)
        try:
          with z.open(i) as f:h=f.read(16)
          if isarc(i.filename,h):
            with z.open(i) as f:scan(f.read(),i.filename,1)
        except Exception as e:errors.append(i.filename+": "+str(e)[:200])
    # List 7z/RAR archives where the 7-Zip command supports the format.
    for p,size,e,cat,source,depth in list(rows):
      if "!/" in p or e not in (".7z",".rar"):continue
      try:
        with zipfile.ZipFile(top) as z:b=z.read(p)
        with tempfile.NamedTemporaryFile(suffix=e) as tf:
          tf.write(b);tf.flush()
          r=subprocess.run(["7z","l","-slt",tf.name],capture_output=True,text=True,timeout=120)
          if r.returncode in (0,1):
            items=[]
            for block in r.stdout.split("\n\n"):
              m=re.search(r"^Path = (.+)$",block,re.M); s=re.search(r"^Size = (\d+)$",block,re.M)
              if m and s and m.group(1)!=tf.name:items.append((m.group(1),int(s.group(1))))
            archives.append((p,e[1:].upper(),1,len(items),len(b)))
            for n,sz in items:add(p+"!/"+n,sz,"membro "+e,1)
          else:errors.append(p+": 7z não listou: "+r.stderr[:200])
      except Exception as e:errors.append(p+": "+str(e)[:200])
    outdir=pathlib.Path("inventory_out");outdir.mkdir(exist_ok=True)
    with gzip.open(outdir/"INVENTORY_ALL_FILES.csv.gz","wt",newline="",encoding="utf-8") as f:
      w=csv.writer(f);w.writerow(["path","size_bytes","extension","category","source","archive_depth"]);w.writerows(rows)
    with gzip.open(outdir/"ARCHIVES_RECURSIVE.csv.gz","wt",newline="",encoding="utf-8") as f:
      w=csv.writer(f);w.writerow(["archive_path","format","depth","entries","source_bytes"]);w.writerows(archives)
    report={}
    try:
      with zipfile.ZipFile(top) as z:
        p=next((n for n in z.namelist() if n.endswith("unity/assets/_report.json")),None)
        if p:
          report=json.loads(z.read(p).decode("utf-8","replace"))
          (outdir/"UNITY_EXTRACTION_REPORT.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    except Exception as e:errors.append("Relatório Unity: "+str(e))
    lines=["# Inventário recursivo completo: Block Gun 3D 2.0.3","",
      "- Arquivos indexados em todas as camadas: **%s**"%format(len(rows),","),
      "- Arquivos na raiz do ZIP: **%s**"%format(sum(1 for r in rows if r[4]=="ZIP principal"),","),
      "- Membros internos adicionados: **%s**"%format(sum(1 for r in rows if r[4]!="ZIP principal"),","),
      "- Arquivos compactados/pacotes identificados: **%s**"%format(len(archives),","),
      "- Profundidade máxima verificada: **%s**"%MAX_DEPTH,
      "- Dados lidos de conteúdo aninhado: **%s bytes**"%format(total_nested,","),
      "- ZIP original: **%s bytes**"%format(top.stat().st_size,","),"","## Categorias"]
    lines += ["- %s: %s"%(k,format(v,",")) for k,v in cats.most_common()]
    lines += ["","## Extensões"]
    lines += ["- %s: %s"%(k,format(v,",")) for k,v in exts.most_common()]
    lines += ["","## Arquivos compactados detectados"]
    lines += ["- %s | %s | nível %s | %s entradas | %s bytes"%(p,fmt,d,format(n,","),format(sz,",")) for p,fmt,d,n,sz in archives]
    lines += ["","## Pastas com mais arquivos"]
    lines += ["- %s: %s"%(p,format(n,",")) for p,n in folders.most_common(100)]
    lines += ["","## Erros ou limites encontrados"]
    lines += ["- "+e for e in errors] if errors else ["- Nenhuma falha de leitura registrada."]
    if report:
      lines += ["","## Resumo do relatório de extração Unity"]
      def walk(o,path=""):
        if isinstance(o,dict):
          for k,v in o.items():
            q=(path+"."+str(k)) if path else str(k)
            if isinstance(v,(str,int,float,bool)) or v is None:
              if any(t in q.lower() for t in ("error","fail","missing","unparsed","warning")):lines.append("- %s: %s"%(q,str(v)[:400]))
            else:walk(v,q)
        elif isinstance(o,list):
          lines.append("- %s: lista com %s itens"%(path,len(o)))
          for i,v in enumerate(o[:200]):walk(v,"%s[%s]"%(path,i))
      walk(report)
    lines += ["","## Arquivos de dados completos","- INVENTORY_ALL_FILES.csv.gz: índice de todos os caminhos, tamanhos, categorias e níveis.",
      "- ARCHIVES_RECURSIVE.csv.gz: relação de pacotes e arquivos compactados encontrados.",
      "- UNITY_EXTRACTION_REPORT.json: relatório bruto de falhas de exportação Unity, se presente."]
    (outdir/"BLOCKGUN_DEEP_INVENTORY.md").write_text("\n".join(lines)+"\n",encoding="utf-8")
    print("\n".join(lines[:220]))
    print("TOTAL_FILES",len(rows),"ARCHIVES",len(archives),"ERRORS",len(errors))
if __name__=="__main__":main()
