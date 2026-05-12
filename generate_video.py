#!/usr/bin/env python3
"""Video Bot English v4"""

import sys,os,json,time,requests,subprocess,re,struct,math,hashlib
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

GEMINI_API_KEY        = os.environ["GEMINI_API_KEY"]
YOUTUBE_CLIENT_ID     = os.environ["YOUTUBE_CLIENT_ID"]
YOUTUBE_CLIENT_SECRET = os.environ["YOUTUBE_CLIENT_SECRET"]
YOUTUBE_REFRESH_TOKEN = os.environ["YOUTUBE_REFRESH_TOKEN"]
TELEGRAM_BOT_TOKEN    = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID      = os.environ["TELEGRAM_CHAT_ID"]

WORK = Path("./output")
WORK.mkdir(exist_ok=True)

GEMINI_MODELS = [
    ("gemini-2.5-flash","v1beta"),
    ("gemini-2.0-flash","v1"),
    ("gemini-2.0-flash-lite","v1"),
]

def tg(msg, emoji=""):
    text = f"{emoji} {msg}".strip()
    try:
        requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id":TELEGRAM_CHAT_ID,"text":text,"parse_mode":"HTML"},timeout=10)
    except: pass
    print(text)

def tg_photo(path, caption):
    try:
        with open(path,"rb") as f:
            requests.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto",
                data={"chat_id":TELEGRAM_CHAT_ID,"caption":caption,"parse_mode":"HTML"},
                files={"photo":f},timeout=30)
    except: pass

def parse_command(cmd):
    p = [x.strip() for x in cmd.strip().split(",")]
    if len(p) != 6:
        raise ValueError("Format: Topic,Music,Minutes,Images,DD.MM.YYYY,HH:MM")
    topic, music_hint, dur, imgs, date_s, time_s = p
    pub = datetime.strptime(f"{date_s} {time_s}","%d.%m.%Y %H:%M")
    return {
        "topic": topic,
        "music_hint": music_hint.strip().lower(),
        "duration": int(dur),
        "img_count": int(imgs),
        "publish_dt": pub,
        "publish_iso": pub.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    }

def gemini(prompt, max_tokens=8192):
    for model,api in GEMINI_MODELS:
        url = f"https://generativelanguage.googleapis.com/{api}/models/{model}:generateContent"
        headers = {"Content-Type":"application/json","x-goog-api-key":GEMINI_API_KEY}
        body = {"contents":[{"parts":[{"text":prompt}]}],
                "generationConfig":{"temperature":0.7,"maxOutputTokens":max_tokens}}
        for attempt in range(3):
            try:
                r = requests.post(url,headers=headers,json=body,timeout=120)
                if r.status_code == 200:
                    c = r.json().get("candidates",[])
                    if c:
                        t = c[0].get("content",{}).get("parts",[{}])[0].get("text","").strip()
                        if t: return t,model
                    time.sleep(8)
                elif r.status_code == 429:
                    wait = 30 + attempt * 20
                    tg(f"{model} rate limit, {wait}s bekleniyor...","⏳")
                    time.sleep(wait)
                elif r.status_code == 503:
                    time.sleep(15); break
                else:
                    tg(f"{model}: {r.json().get('error',{}).get('message','')[:50]}","⚠"); break
            except requests.Timeout:
                time.sleep(15)
    raise Exception("No Gemini model responded")

def parse_json(raw):
    raw = re.sub(r"```json\s*|```\s*","",raw).strip()
    try: return json.loads(raw)
    except: pass
    s=raw.find("{"); e=raw.rfind("}")+1
    if s!=-1 and e>s:
        seg=raw[s:e]
        try: return json.loads(seg)
        except: pass
    data={}
    for key,pat in [("title",r'"title"\s*:\s*"([^"]{1,120})"'),
                    ("description",r'"description"\s*:\s*"([^"]{1,800})"'),
                    ("thumbnail_text",r'"thumbnail_text"\s*:\s*"([^"]{1,50})"')]:
        m=re.search(pat,raw)
        if m: data[key]=m.group(1)
    tm=re.search(r'"tags"\s*:\s*\[(.*?)\]',raw,re.DOTALL)
    if tm: data["tags"]=re.findall(r'"([^"]+)"',tm.group(1))
    if "title" in data: return data
    raise Exception(f"JSON parse failed: {raw[:60]}")

# ─── CONTENT GENERATION ──────────────────────────────────────────────────────
def generate_content(topic, duration, img_count):
    tg(f"Generating content for '{topic}'...","📚")
    word_target = duration * 170  # daha uzun script

    # Gemini'den konuya özel görsel promptları üret
    tg(f"Generating {img_count} image prompts for '{topic}'...","🎨")
    img_prompts = []
    try:
        p_img = f"""You are a visual artist. Generate exactly {img_count} unique image prompts for a documentary about: {topic}

RULES:
- Each prompt must be directly related to {topic} - specific scenes, locations, objects, events
- NO people, NO humans, NO faces, NO text in images
- Cinematic, dramatic, high quality photography style
- Each prompt on a new line, numbered 1 to {img_count}
- Keep each prompt under 100 characters
- Vary the scenes: wide shots, close-ups, aerial views, atmospheric shots

Generate {img_count} prompts now:"""
        raw, _ = gemini(p_img, max_tokens=2048)
        lines = [l.strip() for l in raw.split('\n') if l.strip()]
        for line in lines:
            line = re.sub(r'^\d+[\.\)]\s*','',line).strip()
            if len(line) > 10:
                line += ", no people, no humans, cinematic dramatic lighting 8k"
                img_prompts.append(line)
            if len(img_prompts) >= img_count:
                break
        tg(f"Got {len(img_prompts)} AI image prompts","✅")
    except Exception as e:
        tg(f"Image prompt error: {e}","⚠")

    # Yeterli prompt yoksa fallback
    while len(img_prompts) < img_count:
        i = len(img_prompts)
        img_prompts.append(f"{topic} cinematic dramatic scene {i+1}, no people, 8k atmospheric lighting")

    meta = {
        "title": f"{topic}: The Untold Story! 🏛️",
        "description": f"Discover the incredible story of {topic}. #documentary #history #{topic.replace(' ','')}",
        "tags": [topic,"documentary","history","youtube","education","mystery","ancient","epic"],
        "image_prompts": img_prompts[:img_count],
        "thumbnail_text": topic.upper()[:15],
        "thumbnail_prompt": f"{topic} epic dramatic cinematic no text no people",
        "color": "#1a1a2e"
    }

    # SEO
    tg("Optimizing SEO...","📋")
    try:
        p1 = f"""YouTube documentary about: {topic}. Duration: {duration} minutes.
Return only this JSON (no apostrophes in values):
{{"title":"engaging title max 60 chars with emoji","description":"400 char description with #hashtags","tags":["tag1","tag2","tag3","tag4","tag5","tag6","tag7","tag8"],"thumbnail_text":"MAX 3 WORDS"}}"""
        raw,model = gemini(p1,max_tokens=512)
        mini = parse_json(raw)
        for k in ["title","description","tags","thumbnail_text"]:
            if mini.get(k): meta[k] = mini[k]
        tg(f"SEO ready ({model}): <b>{meta['title']}</b>","✅")
    except:
        tg("SEO using defaults","⚠")

    # Script - uzun ve kesin
    tg(f"Writing script ({word_target} words)...","📝")
    p2 = f"""You are a professional documentary narrator for National Geographic. Write a detailed documentary script about: {topic}

CRITICAL RULES:
- You MUST write EXACTLY {word_target} words or more. Count carefully.
- Write ONLY narration text - pure flowing prose
- NO scene directions, NO [brackets], NO (parentheses), NO music notes
- NO "Narrator:", NO headers, NO bullet points, NO numbered lists
- Keep writing until you reach {word_target} words - do not stop early
- Cover the full history, background, key events, significance, and legacy of {topic}
- Style: engaging, dramatic, informative like National Geographic

Begin now and write {word_target}+ words:"""

    script = ""
    for attempt in range(4):
        try:
            raw,model = gemini(p2,max_tokens=8192)
            raw = re.sub(r'\[.*?\]','',raw,flags=re.DOTALL)
            raw = re.sub(r'\(.*?\)','',raw,flags=re.DOTALL)
            raw = re.sub(r'Narrator\s*:','',raw,flags=re.IGNORECASE)
            raw = re.sub(r'^\*+\s*|^#+\s.*$','',raw,flags=re.MULTILINE)
            raw = re.sub(r'\n{3,}','\n\n',raw).strip()
            wc = len(raw.split())
            tg(f"Script attempt {attempt+1}: {wc} words","📝")
            if wc > 300:
                script = raw
                tg(f"Script ready ({model}): <b>{wc} words</b>","✅")
                break
            time.sleep(5)
        except Exception as e:
            tg(f"Script error: {str(e)[:50]}","⚠"); time.sleep(10)

    if not script:
        script = f"{topic} is one of the most fascinating subjects in human history."

    meta["script"] = script
    tg(f"Total: <b>{len(script.split())} words</b>","📊")
    return meta

# ─── MUSIC ───────────────────────────────────────────────────────────────────
def generate_music(topic, duration_sec, music_hint=""):
    tg("Loading music...","🎵")
    repo_root = Path(os.environ.get("GITHUB_WORKSPACE","."))
    all_mp3 = list(repo_root.glob("*.mp3"))
    if not all_mp3:
        tg("No MP3 in repo!","⚠"); return _synth_fallback(topic, duration_sec)

    def clean(s): return re.sub(r"[^a-z0-9]","",s.lower())
    chosen = None

    if music_hint:
        hc = clean(music_hint)
        for mp3 in all_mp3:
            if hc in clean(mp3.name): chosen = mp3; break
        if not chosen: tg(f"Hint '{music_hint}' not found, using category...","⚠")

    if not chosen:
        k = topic.lower()
        cat = None
        if any(x in k for x in ["war","battle","viking","roman","ottoman","napoleon","soldier","crusade","hitler","military"]): cat="war"
        elif any(x in k for x in ["egypt","ancient","greek","babylon","pharaoh","rome","persia","mystery","ghost","celeste","ship"]): cat="mystery"
        elif any(x in k for x in ["space","technology","ai","future","science","robot","digital"]): cat="space"
        elif any(x in k for x in ["nature","ocean","forest","animal","wildlife","earth"]): cat="nature"
        if cat:
            matches = [m for m in all_mp3 if cat in m.name.lower()]
            if matches:
                seed = int(hashlib.md5(topic.encode()).hexdigest()[:8],16)
                chosen = matches[seed % len(matches)]

    if not chosen:
        seed = int(hashlib.md5(topic.encode()).hexdigest()[:8],16)
        chosen = all_mp3[seed % len(all_mp3)]
        tg(f"Random music: {chosen.name}","⚠")

    tg(f"Music: <b>{chosen.name}</b> ({chosen.stat().st_size//1024}KB)","✅")
    return str(chosen)

def _synth_fallback(topic, duration_sec):
    wav=WORK/"music.wav"; mp3=WORK/"music.mp3"
    sr=44100; dur=int(min(duration_sec+30,7200)); n=sr*dur; fade=sr*3
    try:
        with open(wav,'wb') as f:
            dsize=n*2
            f.write(b'RIFF'); f.write(struct.pack('<I',36+dsize))
            f.write(b'WAVEfmt '); f.write(struct.pack('<I',16))
            f.write(struct.pack('<H',1)); f.write(struct.pack('<H',1))
            f.write(struct.pack('<I',sr)); f.write(struct.pack('<I',sr*2))
            f.write(struct.pack('<H',2)); f.write(struct.pack('<H',16))
            f.write(b'data'); f.write(struct.pack('<I',dsize))
            freqs=[130,164,196,261,87]; amps=[0.20,0.16,0.12,0.07,0.18]
            for start in range(0,n,sr):
                end=min(start+sr,n); buf=[]
                for i in range(start,end):
                    t=i/sr; v=sum(a*math.sin(2*math.pi*fr*t) for a,fr in zip(amps,freqs))
                    if i<fade: v*=i/fade
                    elif i>n-fade: v*=(n-i)/fade
                    buf.append(struct.pack('<h',int(max(-0.85,min(0.85,v))*32767)))
                f.write(b''.join(buf))
        r=subprocess.run(["ffmpeg","-y","-i",str(wav),"-af","volume=2.0",
            "-c:a","mp3","-b:a","128k",str(mp3)],capture_output=True,timeout=180)
        if r.returncode==0 and mp3.exists(): return str(mp3)
    except: pass
    return ""

# ─── IMAGES ──────────────────────────────────────────────────────────────────
def download_image(i, prompt, total, topic=""):
    path = WORK/f"img_{i+1:02d}.jpg"
    for attempt, seed in enumerate([i*7+42, i*13+17, i*3+99, i*19+5, i*31+11]):
        enc = quote(prompt[:200])
        url = f"https://image.pollinations.ai/prompt/{enc}?width=1920&height=1080&seed={seed}&nologo=true&model=flux"
        try:
            r = requests.get(url,timeout=120)
            if r.status_code==200 and len(r.content)>10000 and r.content[:2]==b'\xff\xd8':
                path.write_bytes(r.content)
                tg(f"Image {i+1}/{total} ✓","🖼")
                time.sleep(4)
                return str(path)
            if r.status_code==429: time.sleep(45)
            else: time.sleep(10)
        except: time.sleep(10)
        if attempt == 1:
            prompt = f"{topic} cinematic dramatic landscape no people 8k"

    colors=["0x3D1C02","0x4A0E0E","0x0A1628","0x2D1B69","0x003333","0x1A3A1A","0x330033","0x1A1A00"]
    subprocess.run(["ffmpeg","-y","-f","lavfi","-i",f"color=c={colors[i%len(colors)]}:size=1920x1080:rate=1",
        "-vframes","1","-q:v","2",str(path)],capture_output=True)
    tg(f"Image {i+1} fallback","⚠")
    return str(path)

def generate_images(prompts, topic=""):
    n = len(prompts)
    tg(f"Generating {n} images...","🎨")
    return [download_image(i,p,n,topic) for i,p in enumerate(prompts)]

# ─── THUMBNAIL ───────────────────────────────────────────────────────────────
def generate_thumbnail(prompt, text, color, topic):
    tg("Generating thumbnail...","🖼")
    enc=quote(f"{prompt}, youtube thumbnail dramatic vibrant no text no people")
    url=f"https://image.pollinations.ai/prompt/{enc}?width=1280&height=720&seed=777&nologo=true&model=flux"
    base=WORK/"thumb_base.jpg"; final=WORK/"thumbnail.jpg"
    for _ in range(3):
        try:
            r=requests.get(url,timeout=60)
            if r.status_code==200 and len(r.content)>5000 and r.content[:2]==b'\xff\xd8':
                base.write_bytes(r.content); break
            time.sleep(10)
        except: time.sleep(10)
    else:
        subprocess.run(["ffmpeg","-y","-f","lavfi","-i",
            f"color=c={color.replace('#','0x')}:size=1280x720:rate=1",
            "-vframes","1",str(base)],capture_output=True)
    m=text.upper()[:25].replace("'","").replace(":","\\:")
    k=topic.upper()[:20].replace("'","").replace(":","\\:")
    fs=80 if len(m)<=10 else 60 if len(m)<=18 else 44
    vf=(f"drawbox=x=0:y=ih*0.58:w=iw:h=ih*0.42:color=black@0.72:t=fill,"
        f"drawtext=text='{m}':fontsize={fs}:fontcolor=black@0.4:x=(w-text_w)/2+2:y=h*0.62+2:font=DejaVu Sans:style=Bold,"
        f"drawtext=text='{m}':fontsize={fs}:fontcolor=white:x=(w-text_w)/2:y=h*0.62:font=DejaVu Sans:style=Bold,"
        f"drawtext=text='{k}':fontsize=30:fontcolor=yellow:x=20:y=20:font=DejaVu Sans:style=Bold")
    r=subprocess.run(["ffmpeg","-y","-i",str(base),"-vf",vf,"-q:v","2",str(final)],capture_output=True)
    if r.returncode!=0 or not final.exists(): subprocess.run(["cp",str(base),str(final)])
    if final.exists(): tg_photo(str(final),f"Thumbnail: {m}")
    tg("Thumbnail ready!","✅")
    return str(final)

# ─── AUDIO ───────────────────────────────────────────────────────────────────
def generate_audio(script):
    tg("Generating English narration...","🎙")
    sf=WORK/"script.txt"; rf=WORK/"audio_raw.mp3"
    sub_vtt=WORK/"subtitles.vtt"; sub_srt=WORK/"subtitles.srt"
    sf.write_text(script,encoding="utf-8")
    r=subprocess.run(["edge-tts","--voice","en-US-GuyNeural",
        "--file",str(sf),"--write-media",str(rf),
        "--write-subtitles",str(sub_vtt)],
        capture_output=True,text=True,timeout=600)
    if r.returncode!=0 or not rf.exists():
        raise Exception(f"TTS failed: {r.stderr[-80:]}")
    tg("Audio generated","✅")
    if sub_vtt.exists():
        vtt=sub_vtt.read_text(encoding="utf-8"); srt=[]; count=1
        for block in re.split(r'\n\n+',vtt):
            if '-->' in block:
                lines=block.strip().split('\n')
                timing=next((s for s in lines if '-->' in s),None)
                if timing:
                    timing=re.sub(r'(\d{2}:\d{2}:\d{2})\.(\d{3})',r'\1,\2',timing).strip()
                    tlines=[s for s in lines if '-->' not in s and s.strip()
                             and not s.startswith('NOTE') and not s.strip().isdigit()]
                    if tlines: srt+=[str(count),timing]+tlines+['']; count+=1
        sub_srt.write_text('\n'.join(srt),encoding="utf-8")
    probe=subprocess.run(["ffprobe","-v","quiet","-print_format","json","-show_format",str(rf)],
        capture_output=True,text=True)
    duration=float(json.loads(probe.stdout)["format"]["duration"])
    tg(f"Audio ready! Duration: <b>{duration/60:.1f} minutes</b>","✅")
    return str(rf), duration, str(sub_srt) if sub_srt.exists() else ""

# ─── MUSIC MIX ───────────────────────────────────────────────────────────────
def mix_audio(narration, music, duration):
    if not music: tg("No music","⚠"); return narration
    mp = Path(music)
    if not mp.exists(): tg(f"Music not found: {music}","⚠"); return narration
    tg(f"Music size: {mp.stat().st_size//1024}KB","🎚")
    try:
        pb=subprocess.run(["ffprobe","-v","quiet","-print_format","json","-show_format",str(mp)],
            capture_output=True,text=True)
        ms=float(json.loads(pb.stdout)["format"]["duration"])
        if ms<3: tg("Music too short","⚠"); return narration
        tg(f"Mixing ({ms:.0f}s music)...","🎚")
    except Exception as e:
        tg(f"ffprobe error: {e}","⚠"); return narration
    mixed=WORK/"mixed.mp3"
    cmd=["ffmpeg","-y","-i",narration,"-stream_loop","-1","-i",str(mp),
         "-filter_complex",
         "[0:a]aformat=sample_rates=44100:channel_layouts=stereo[a1];"
         "[1:a]aformat=sample_rates=44100:channel_layouts=stereo,volume=0.20[a2];"
         "[a1][a2]amix=inputs=2:duration=first:weights=1 0.6[aout]",
         "-map","[aout]","-c:a","libmp3lame","-b:a","192k",
         "-t",str(int(duration)+2),str(mixed)]
    r=subprocess.run(cmd,capture_output=True,text=True,timeout=600)
    if r.returncode==0 and mixed.exists() and mixed.stat().st_size>50000:
        tg(f"Music mixed! ({mixed.stat().st_size//1024}KB)","✅")
        return str(mixed)
    tg(f"Mix failed: {r.stderr[-60:]}","⚠")
    return narration

# ─── VIDEO ASSEMBLY ───────────────────────────────────────────────────────────
def assemble_video(images, audio, subtitle_srt, total_duration):
    tg(f"Assembling video...\n{len(images)} images | fade + flash effects\n⏳ ~{len(images)//2+5} min","🎬")

    img_dur  = total_duration / len(images)
    fps      = 30
    fade_dur = 0.6
    gecis    = ["fade","dissolve","brightness","fade","dissolve"]
    fcolors  = ["white","0x4444ff","0xff2222"]

    def make_vf(idx, dur, is_flash, fcol):
        half = max(int(dur * fps) // 2, 1)
        zoom = (
            f"scale=8000:-1,"
            f"crop="
            f"w='iw/(1.0+0.15*if(lte(n,{half}),n/{half},(2*{half}-n)/{half}))':"
            f"h='ih/(1.0+0.15*if(lte(n,{half}),n/{half},(2*{half}-n)/{half}))':"
            f"x='(iw-iw/(1.0+0.15*if(lte(n,{half}),n/{half},(2*{half}-n)/{half})))/2':"
            f"y='(ih-ih/(1.0+0.15*if(lte(n,{half}),n/{half},(2*{half}-n)/{half})))/2',"
            f"scale=1920:1080,vignette=PI/4"
        )
        if is_flash:
            return (f"{zoom},"
                    f"fade=t=in:st=0:d=0.4:color={fcol},"
                    f"fade=t=out:st={dur-0.4:.2f}:d=0.4:color={fcol},"
                    f"format=yuv420p")
        tip = gecis[idx % len(gecis)]
        fi = f"fade=t=in:st=0:d={fade_dur}"
        fo = f"fade=t=out:st={dur-fade_dur:.2f}:d={fade_dur}"
        if tip == "dissolve": fi+=":alpha=1"; fo+=":alpha=1"
        elif tip == "brightness": fi+=":color=black"; fo+=":color=black"
        return f"{zoom},{fi},{fo},format=yuv420p"

    clips = []
    for idx, img in enumerate(images):
        clip    = WORK/f"clip_{idx:02d}.mp4"
        flash   = (idx % 4 == 3)
        fcol    = fcolors[(idx // 4) % len(fcolors)]
        vf      = make_vf(idx, img_dur, flash, fcol)

        r = subprocess.run(
            ["ffmpeg","-y","-loop","1","-i",img,
             "-vf",vf,"-t",str(img_dur),
             "-c:v","libx264","-preset","fast","-crf","20",
             "-r",str(fps),str(clip)],
            capture_output=True,text=True,timeout=300)
        if r.returncode==0 and clip.exists():
            clips.append(str(clip))
            icon = ("⚡🔵" if fcol=="0x4444ff" else "⚡🔴" if fcol=="0xff2222" else "⚡⚪") if flash else "✓"
            tg(f"Clip {idx+1}/{len(images)} {icon}","🎞")
        else:
            tg(f"Clip {idx+1} failed: {r.stderr[-80:]}","⚠")

    if not clips: raise Exception("No clips generated")

    concat_list = WORK/"concat.txt"
    concat_list.write_text('\n'.join(f"file '{Path(c).resolve()}'" for c in clips))
    raw_video = WORK/"video_raw.mp4"
    r = subprocess.run(["ffmpeg","-y","-f","concat","-safe","0",
        "-i",str(concat_list.resolve()),"-c:v","copy",str(raw_video)],
        capture_output=True,text=True,timeout=3600)
    if r.returncode!=0 or not raw_video.exists():
        raise Exception(f"Concat failed: {r.stderr[-100:]}")

    final_video = WORK/"final_video.mp4"
    if subtitle_srt and os.path.exists(subtitle_srt):
        srt_esc = str(subtitle_srt).replace('\\','/').replace(':','\\:')
        vf_sub  = (f"subtitles={srt_esc}:force_style='"
                   f"FontSize=14,PrimaryColour=&H00FFFF00,"
                   f"OutlineColour=&H00000000,Outline=2,BorderStyle=1,"
                   f"Alignment=2,MarginV=30'")
        r = subprocess.run(["ffmpeg","-y","-i",str(raw_video),"-i",audio,
            "-vf",vf_sub,"-c:v","libx264","-preset","fast","-crf","20",
            "-c:a","aac","-b:a","192k","-shortest",str(final_video)],
            capture_output=True,text=True,timeout=7200)
    else:
        r = subprocess.run(["ffmpeg","-y","-i",str(raw_video),"-i",audio,
            "-c:v","copy","-c:a","aac","-b:a","192k","-shortest",str(final_video)],
            capture_output=True,text=True,timeout=7200)

    if r.returncode!=0 or not final_video.exists():
        raise Exception(f"Final video failed: {r.stderr[-100:]}")

    tg(f"Video ready! {final_video.stat().st_size//(1024*1024)}MB","✅")
    return str(final_video)

# ─── YOUTUBE ─────────────────────────────────────────────────────────────────
def get_access_token():
    r=requests.post("https://oauth2.googleapis.com/token",data={
        "client_id":YOUTUBE_CLIENT_ID,"client_secret":YOUTUBE_CLIENT_SECRET,
        "refresh_token":YOUTUBE_REFRESH_TOKEN,"grant_type":"refresh_token"},timeout=30)
    return r.json()["access_token"]

def upload_youtube(video_path, meta, publish_iso):
    tg("Uploading to YouTube...","📤")
    token = get_access_token()
    body = {"snippet":{"title":meta["title"][:100],"description":meta["description"][:5000],
                       "tags":meta["tags"][:500],"categoryId":"27",
                       "defaultLanguage":"en","defaultAudioLanguage":"en"},
            "status":{"privacyStatus":"private","publishAt":publish_iso,"selfDeclaredMadeForKids":False}}
    r=requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        headers={"Authorization":f"Bearer {token}","Content-Type":"application/json",
                 "X-Upload-Content-Type":"video/mp4"},json=body,timeout=30)
    upload_url = r.headers.get("Location","")
    if not upload_url: raise Exception(f"No upload URL: {r.text[:100]}")
    with open(video_path,"rb") as f: video_data=f.read()
    r2=requests.put(upload_url,headers={"Content-Type":"video/mp4"},data=video_data,timeout=1800)
    if r2.status_code not in [200,201]: raise Exception(f"Upload failed: {r2.text[:100]}")
    vid_id=r2.json().get("id","")
    tg(f"Uploaded! youtube.com/watch?v={vid_id}\nScheduled: {publish_iso}","🎉")
    return vid_id

def upload_thumbnail(vid_id, thumb_path):
    try:
        token=get_access_token()
        with open(thumb_path,"rb") as f: data=f.read()
        r=requests.post(f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={vid_id}",
            headers={"Authorization":f"Bearer {token}","Content-Type":"image/jpeg"},
            data=data,timeout=60)
        if r.status_code==200: tg("Thumbnail uploaded!","🖼")
    except Exception as e: tg(f"Thumbnail upload failed: {e}","⚠")

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    if len(sys.argv)<2: tg("No command","⚠"); sys.exit(1)
    cmd=" ".join(sys.argv[1:])
    tg(f"Command: <b>{cmd}</b>","🚀")
    try: params=parse_command(cmd)
    except Exception as e: tg(f"Command error: {e}","❌"); sys.exit(1)

    topic=params["topic"]; music_hint=params["music_hint"]
    duration=params["duration"]; img_count=params["img_count"]
    pub_iso=params["publish_iso"]

    tg(f"<b>{topic}</b> | {duration} min | {img_count} images\n🎵 {music_hint}\n📅 {pub_iso}","📋")
    try:
        meta        = generate_content(topic, duration, img_count)
        music       = generate_music(topic, duration*60, music_hint)
        images      = generate_images(meta["image_prompts"], topic)
        generate_thumbnail(meta["thumbnail_prompt"],meta["thumbnail_text"],meta["color"],topic)
        audio,dur,srt = generate_audio(meta["script"])
        final_audio = mix_audio(audio, music, dur)
        video       = assemble_video(images, final_audio, srt, dur)
        vid_id      = upload_youtube(video, meta, pub_iso)
        upload_thumbnail(vid_id, str(WORK/"thumbnail.jpg"))
        tg(f"✅ DONE!\nyoutube.com/watch?v={vid_id}","🎬")
    except Exception as e:
        tg(f"Fatal error: {str(e)[:200]}","❌"); sys.exit(1)

if __name__=="__main__":
    main()