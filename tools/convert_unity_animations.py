#!/usr/bin/env python3
"""Convert original Unity Humanoid muscle clips into Godot Skeleton3D bone poses."""
import argparse, bisect, json, math, pathlib, struct

def v3(v, fields="xyz"):
    return [float(v.get(k,0.0)) for k in fields]

def q4(v):
    return [float(v.get(k,0.0)) for k in "xyzw"]

def qmul(a,b):
    ax,ay,az,aw=a; bx,by,bz,bw=b
    return [aw*bx+bw*ax+ay*bz-az*by,
            aw*by+bw*ay+az*bx-ax*bz,
            aw*bz+bw*az+ax*by-ay*bx,
            aw*bw-ax*bx-ay*by-az*bz]

def qinv(q):
    d=sum(x*x for x in q)
    if d<1e-12: return [0.0,0.0,0.0,1.0]
    return [-q[0]/d,-q[1]/d,-q[2]/d,q[3]/d]

def qnorm(q):
    d=math.sqrt(sum(x*x for x in q))
    if d<1e-12: return [0.0,0.0,0.0,1.0]
    return [x/d for x in q]

def axis_angle(vec):
    angle=math.sqrt(sum(x*x for x in vec))
    if angle<1e-10: return [vec[0]*0.5,vec[1]*0.5,vec[2]*0.5,1.0]
    s=math.sin(angle*0.5)/angle
    return [vec[0]*s,vec[1]*s,vec[2]*s,math.cos(angle*0.5)]

def muscle_axes():
    axes={"spine_01.x":(2,1,0),"spine_02.x":(5,4,3),"spine_03.x":(8,7,6),
          "neck.x":(11,10,9),"head.x":(14,13,12)}
    for side,leg,arm,hand in (("l",21,37,55),("r",29,46,75)):
        axes.update({
            f"thigh_stretch.{side}":(leg+2,leg+1,leg),
            f"leg_stretch.{side}":(leg+4,-1,leg+3),
            f"foot.{side}":(-1,leg+6,leg+5),
            f"toes_01.{side}":(-1,-1,leg+7),
            f"shoulder.{side}":(-1,arm+1,arm),
            f"arm_stretch.{side}":(arm+4,arm+3,arm+2),
            f"forearm_stretch.{side}":(arm+6,-1,arm+5),
            f"hand.{side}":(-1,arm+8,arm+7)
        })
        for finger,offset in zip(("thumb","index","middle","ring","pinky"),range(0,20,4)):
            i=hand+offset
            axes[f"c_{finger}1.{side}"]=(-1,i+1,i)
            axes[f"c_{finger}2.{side}"]=(-1,-1,i+2)
            axes[f"c_{finger}3.{side}"]=(-1,-1,i+3)
    return axes

BONE_AXIS={
 "spine_01":"spine_01.x","spine_03":"spine_03.x","head":"head.x",
 "thigh_l":"thigh_stretch.l","calf_l":"leg_stretch.l","foot_l":"foot.l",
 "upperarm_l":"arm_stretch.l","lowerarm_l":"forearm_stretch.l","hand_l":"hand.l",
 "thigh_r":"thigh_stretch.r","calf_r":"leg_stretch.r","foot_r":"foot.r",
 "upperarm_r":"arm_stretch.r","lowerarm_r":"forearm_stretch.r","hand_r":"hand.r"
}

def sample_curves(fields,times):
    muscle=fields["m_MuscleClip"]; clip=muscle["m_Clip"]["data"]
    stream,dense,constant=(clip[k] for k in ("m_StreamedClip","m_DenseClip","m_ConstantClip"))
    ns=int(stream.get("curveCount",0)); nd=int(dense.get("m_CurveCount",0)); const=constant.get("data",[])
    total=ns+nd+len(const)
    bindings=fields.get("m_ClipBindingConstant",{}).get("genericBindings",[])
    if total!=len(bindings):
        raise ValueError(f"curve/binding mismatch {total} != {len(bindings)}")
    out=[[0.0]*total for _ in times]
    if ns:
        raw=struct.pack("<"+"I"*len(stream["data"]),*stream["data"])
        cursor=0; keys=[[] for _ in range(ns)]
        while cursor<len(raw):
            tm,count=struct.unpack_from("<fi",raw,cursor);cursor+=8
            for _ in range(count):
                index,a,b,c,value=struct.unpack_from("<i4f",raw,cursor);cursor+=20
                if 0<=index<ns and math.isfinite(tm):
                    keys[index].append((tm,(a,b,c,value)))
        for curve_index,curve_keys in enumerate(keys):
            if not curve_keys: continue
            stamps=[x[0] for x in curve_keys]
            for frame,t in enumerate(times):
                k=max(0,bisect.bisect_right(stamps,t)-1)
                start,(a,b,c,value)=curve_keys[k]
                dt=max(0.0,t-start)
                out[frame][curve_index]=((a*dt+b)*dt+c)*dt+value
    if nd:
        values=dense.get("m_SampleArray",[])
        frames=int(dense.get("m_FrameCount",0))
        rate=float(dense.get("m_SampleRate",0) or fields.get("m_SampleRate",30) or 30)
        begin=float(dense.get("m_BeginTime",0.0))
        if frames and len(values)>=frames*nd:
            sample_times=[begin+i/rate for i in range(frames)]
            for frame,t in enumerate(times):
                if t<=sample_times[0]: lo=hi=0;alpha=0.0
                elif t>=sample_times[-1]: lo=hi=frames-1;alpha=0.0
                else:
                    lo=max(0,bisect.bisect_right(sample_times,t)-1);hi=min(frames-1,lo+1)
                    alpha=(t-sample_times[lo])/(sample_times[hi]-sample_times[lo]) if hi!=lo else 0.0
                base=frame*total+ns
                for ci in range(nd):
                    a=float(values[lo*nd+ci]);b=float(values[hi*nd+ci])
                    out[frame][ns+ci]=a+(b-a)*alpha
    for frame in range(len(times)):
        for ci,value in enumerate(const):
            out[frame][ns+nd+ci]=float(value)
    human=[]
    for curves in out:
        row=[0.0]*137
        row[13]=1.0
        for i,binding in enumerate(bindings):
            if int(binding.get("typeID",-1))!=95 or int(binding.get("customType",-1))!=8:
                raise ValueError("clip contains non-humanoid binding")
            attr=int(binding["attribute"])
            if 0<=attr<len(row): row[attr]=curves[i]
        human.append(row)
    return human

def convert_clip(record,avatar_fields,full_index,full_pose,human_skeleton,human_fields):
    fields=record["fields"]; mc=fields.get("m_MuscleClip")
    if not mc or not fields.get("m_ClipBindingConstant",{}).get("genericBindings"):
        return None
    start=float(mc.get("m_StartTime",0.0)); stop=float(mc.get("m_StopTime",0.0))
    duration=max(0.0,stop-start)
    fps=30.0; count=max(2,int(math.ceil(duration*fps))+1)
    times=[start+(stop-start)*i/(count-1) for i in range(count)]
    curves=sample_curves(fields,times)
    human=human_fields
    skeleton=human["m_Skeleton"]["data"]
    nodes=skeleton["m_Node"]; ids=skeleton["m_ID"]
    tos={int(k):str(v) for k,v in avatar_fields.get("m_TOS",[])}
    rest=human["m_SkeletonPose"]["data"]["m_X"][1:]
    root_x=human.get("m_RootX",{})
    ref_q=q4(root_x.get("q",{"x":0,"y":0,"z":0,"w":1}))
    muscle_map=muscle_axes()
    frames=[]
    for row in curves:
        body_q=qnorm(row[10:14])
        body_delta=qmul(body_q,qinv(ref_q))
        rotations=[]
        for bi in range(len(ids)-1):
            hash_id=int(ids[bi+1]); full_bone=full_index.get(hash_id)
            if full_bone is None: continue
            bone_path=tos.get(hash_id,"")
            bone_name=bone_path.split("/")[-1] if bone_path else ""
            rest_q=q4(full_pose[full_bone].get("q",{"x":0,"y":0,"z":0,"w":1}))
            if bi==0:
                absolute=qmul(body_delta,rest_q)
            elif bone_name in BONE_AXIS:
                axis_id=int(nodes[bi+1].get("m_AxesId",-1))
                if axis_id<0:
                    absolute=rest_q
                else:
                    ax=skeleton["m_AxesArray"][axis_id]
                    muscle_indices=muscle_map[BONE_AXIS[bone_name]]
                    muscle=[row[42+i] if i>=0 else 0.0 for i in muscle_indices]
                    mn=ax["m_Limit"]["m_Min"]; mx=ax["m_Limit"]["m_Max"]; sign=ax["m_Sgn"]
                    angles=[]
                    for axis,value in zip("xyz",muscle):
                        limit=float(mx[axis]) if value>=0 else -float(mn[axis])
                        angles.append(value*limit*float(sign[axis]))
                    swing=axis_angle([0.0,angles[1],angles[2]])
                    twist=axis_angle([angles[0],0.0,0.0])
                    pre=q4(ax["m_PreQ"]); post=q4(ax["m_PostQ"])
                    absolute=qmul(qmul(qmul(pre,swing),twist),qinv(post))
            else:
                absolute=rest_q
            pose_delta=qnorm(qmul(qinv(rest_q),qnorm(absolute)))
            rotations.append([full_bone,*pose_delta])
        frames.append(rotations)
    settings=fields.get("m_AnimationClipSettings",{})
    loop=bool(settings.get("m_LoopTime",mc.get("m_LoopTime",False)))
    return {"name":record.get("name",""),"source":record.get("source",""),"path_id":record.get("path_id"),
            "fps":fps,"duration":duration,"loop":loop,"frames":frames}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--audit",default="unity_audit")
    ap.add_argument("--project",default="godot_project")
    args=ap.parse_args()
    audit=pathlib.Path(args.audit); project=pathlib.Path(args.project)
    clips= json.loads((audit/"UNITY_ANIMATION_DATA.json").read_text(encoding="utf-8"))
    animator=json.loads((audit/"UNITY_ANIMATOR_DATA.json").read_text(encoding="utf-8"))
    avatar=next(x for x in animator["avatars"] if x["name"]=="Character_BitGunAvatar")
    af=avatar["fields"]; av=af["m_Avatar"]; human=av["m_Human"]["data"]
    full_ids=av["m_AvatarSkeleton"]["data"]["m_ID"]
    full_pose=av["m_AvatarSkeletonPose"]["data"]["m_X"]
    full_index={int(h):i for i,h in enumerate(full_ids)}
    converted=[]; skipped=[]; used_names={}
    for record in clips:
        try:
            item=convert_clip(record,af,full_index,full_pose,human,human)
            if item is None:
                skipped.append({"name":record.get("name"),"reason":"no humanoid muscle bindings"});continue
            base=item["name"]; used_names[base]=used_names.get(base,0)+1
            if used_names[base]>1: item["key"]=f"{base}__{record.get('path_id')}"
            else: item["key"]=base
            converted.append(item)
        except Exception as e:
            skipped.append({"name":record.get("name"),"path_id":record.get("path_id"),"reason":str(e)[:300]})
    aliases={}
    for key in ("front_walk","front_run","jump_loop","Fire","Reload","Hit Reaction","Rifle_Idle_gun_down","Idle","zoom_idle"):
        match=next((x["key"] for x in converted if x["name"]==key),None)
        if match: aliases[key]=match
    out=project/"assets"/"combat_source"/"original_animations.json"
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps({"avatar":"Character_BitGunAvatar","aliases":aliases,"clips":converted},separators=(",",":"),ensure_ascii=False),encoding="utf-8")
    report={"converted":len(converted),"skipped":len(skipped),"aliases":aliases,"clips":[{"name":x["name"],"key":x["key"],"frames":len(x["frames"]),"duration":x["duration"]} for x in converted],"skipped_examples":skipped[:40]}
    (out.parent/"original_animations_report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print("ORIGINAL_ANIMATIONS_READY",report["converted"],"clips; skipped",report["skipped"],"aliases",aliases)

if __name__=="__main__":
    main()
