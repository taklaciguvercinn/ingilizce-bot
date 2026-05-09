#!/usr/bin/env python3
"""Video Bot English v3"""

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
        for _ in range(2):
            try:
                r = requests.post(url,headers=headers,json=body,timeout=90)
                if r.status_code == 200:
                    c = r.json().get("candidates",[])
                    if c:
                        t = c[0].get("content",{}).get("parts",[{}])[0].get("text","").strip()
                        if t: return t,model
                    time.sleep(5)
                elif r.status_code == 429: time.sleep(15)
                elif r.status_code == 503: break
                else:
                    err = r.json().get("error",{}).get("message","")[:50]
                    tg(f"{model}: {err}","⚠"); break
            except requests.Timeout: time.sleep(10)
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
        try: return json.loads(re.sub(r"(?<=[^\s{,:\[])'(?=[^\s},:!'\]])", "",seg))
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

# ─── CONTENT ─────────────────────────────────────────────────────────────────
def generate_content(topic, duration, img_count):
    tg(f"Generating content for '{topic}'...","📚")
    word_target = duration * 150

    location_map = {
        "great wall": ["Great Wall of China ancient stone watchtower mountain mist","Ming dynasty fortress dramatic clouds","ancient Chinese battlefield landscape epic lighting"],
        "ottoman": ["Ottoman Empire palace architecture golden era","Constantinople Byzantine cityscape dramatic","Ottoman army fortress medieval stone"],
        "egypt": ["ancient Egyptian pyramid Giza desert sunrise","Egyptian temple hieroglyphics stone dramatic","Nile river ancient civilization golden light"],
        "viking": ["Viking longship stormy ocean dramatic","Norse village wooden houses snow landscape","Scandinavian fjord epic landscape"],
        "roman": ["ancient Roman Colosseum architecture epic","Roman legionnaire fortress dramatic lighting","ancient Rome Forum ruins golden hour"],
        "napoleon": ["Napoleonic battlefield epic landscape","French Empire palace architecture dramatic","19th century European fortress dramatic"],
        "hitler": ["World War 2 battlefield dramatic landscape","ruins of war dramatic moody atmosphere","wartime bunker dramatic cinematic"],
        "space": ["deep space nebula galaxy ultra detailed","space station orbit Earth dramatic lighting","cosmos cinematic dramatic"],
        "nature": ["tropical rainforest waterfall dramatic light","mountain glacier landscape epic dramatic","ocean waves cliffs cinematic dramatic"],
        "world war": ["World War battlefield dramatic landscape","military fortress ruins dramatic atmosphere","wartime landscape dramatic moody"],
    }

    k = topic.lower()
    found = []
    for key,imgs in location_map.items():
        if key in k: found = imgs; break
    if not found:
        found = [
            f"{topic} dramatic landscape ancient architecture no people cinematic 8k",
            f"{topic} historical ruins dramatic lighting epic cinematic no people",
            f"{topic} epic environment wide shot dramatic clouds cinematic",
            f"{topic} mystical ancient site atmospheric dramatic no people",
        ]

    prompts = []
    for i in range(img_count):
        base = found[i % len(found)]
        if i % 3 == 1: base += ", golden hour warm light, wide angle"
        elif i % 3 == 2: base += ", aerial view dramatic clouds, cinematic"
        prompts.append(base)

    meta = {
        "title": f"{topic}: The Untold Story! 🏛️",
        "description": f"Discover the incredible story of {topic} in this comprehensive documentary. #documentary #history #{topic.replace(' ','')}",
        "tags": [topic,"documentary","history","youtube","education","mystery","ancient","epic"],
        "image_prompts": prompts,
        "thumbnail_text": topic.upper()[:15],
        "thumbnail_prompt": f"{topic} epic dramatic cinematic no text no people",
        "color": "#1a1a2e"
    }

    tg("Optimizing SEO...","📋")
    try:
        p1 = f"""YouTube documentary about: {topic}. Duration: {duration} minutes.
Return only this JSON (no apostrophes in values):
{{"title":"engaging title max 60 chars with emoji","description":"400 char description with #hashtags","tags":["tag1","tag2","tag3","tag4","tag5","tag6","tag7","tag8"],"thumbnail_text":"MAX 3 WORDS"}}"""
        raw,model = gemini(p1,max_tokens=512)
        mini = parse_json(raw)
        for k2 in ["title","description","tags","thumbnail_text"]:
            if mini.get(k2): meta[k2] = mini[k2]
        tg(f"SEO ready ({model}): <b>{meta['title']}</b>","✅")
    except:
        tg("SEO using defaults","⚠")

    tg(f"Writing script ({word_target} words)...","📝")
    p2 = f"""You are a professional documentary narrator. Write a script about: {topic}

STRICT RULES:
- Write ONLY the narration text, nothing else
- No scene directions, no music cues, no [brackets], no stage directions
- No "Narrator:", no headers, no bullet points
- Write approximately {word_target} words
- Style: National Geographic documentary - engaging, dramatic, informative
- Pure flowing prose paragraphs only

Begin the {topic} documentary narration now:"""

    script = ""
    for _ in range(4):
        try:
            raw,model = gemini(p2,max_tokens=8192)
            raw = re.sub(r'\[.*?\]','',raw,flags=re.DOTALL)
            raw = re.sub(r'\(.*?music.*?\)','',raw,flags=re.IGNORECASE|re.DOTALL)
            raw = re.sub(r'Narrator\s*:','',raw,flags=re.IGNORECASE)
            raw = re.sub(r'^\*+\s*|^#+\s.*$','',raw,flags=re.MULTILINE)
            raw = re.sub(r'\n{3,}','\n\n',raw).strip()
            if len(raw.split()) > 200:
                script = raw
                tg(f"Script ready ({model}): <b>{len(raw.split())} words</b>","✅")
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
    repo_root = Path(os.environ.get("GITHUB_WORKSPACE", "."))
    all_mp3 = list(repo_root.glob("*.mp3"))

    if not all_mp3:
        tg("No MP3 files in repo!","⚠")
        return _synth_music_fallback(topic, duration_sec)

    def clean(s):
        return re.sub(r"[^a-z0-9]","",s.lower())

    chosen = None

    if music_hint:
        hint_clean = clean(music_hint)
        for mp3 in all_mp3:
            if hint_clean in clean(mp3.name):
                chosen = mp3; break
        if not chosen:
            tg(f"Hint '{music_hint}' not found, using category...","⚠")

    if not chosen:
        k = topic.lower()
        if any(x in k for x in ["war","battle","viking","roman","ottoman","medieval","napoleon","soldier","crusade","hitler"]):
            cat_tag = "war"
        elif any(x in k for x in ["egypt","ancient","greek","sumerian","babylon","pharaoh","rome","persia"]):
            cat_tag = "ancient"
        elif any(x in k for x in ["space","technology","ai","future","science","robot","digital"]):
            cat_tag = "space"
        elif any(x in k for x in ["mystery","secret","conspiracy","paranormal","dark","unknown"]):
            cat_tag = "mystery"
        else:
            cat_tag = None

        if cat_tag:
            matches = [m for m in all_mp3 if cat_tag in m.name.lower()]
            if matches:
                seed = int(hashlib.md5(topic.encode()).hexdigest()[:8],16)
                chosen = matches[seed % len(matches)]

    if not chosen:
        seed = int(hashlib.md5(topic.encode()).hexdigest()[:8],16)
        chosen = all_mp3[seed % len(all_mp3)]
        tg(f"Random music: {chosen.name}","⚠")

    tg(f"Music: <b>{chosen.name}</b> ({chosen.stat().st_size//1024}KB)","✅")
    return str(chosen)

def _synth_music_fallback(topic, duration_sec):
    wav = WORK/"music.wav"; mp3 = WORK/"music.mp3"
    seed_val = int(hashlib.md5(topic.encode()).hexdigest()[:8],16) % 1000
    kategoriler = [
        {"base":[130,164,196,261,87],"amps":[0.20,0.16,0.12,0.07,0.18],"chords":[1.0,1.12,1.25,1.06],"dur":7,"label":"cinematic_1"},
        {"base":[138,174,207,277,92],"amps":[0.18,0.15,0.13,0.08,0.17],"chords":[1.0,1.19,1.06,1.12],"dur":6,"label":"cinematic_2"},
    ]; bpm = 70
    cfg = kategoriler[seed_val % len(kategoriler)]
    base_freqs,amps,chords,chord_dur,label = cfg["base"],cfg["amps"],cfg["chords"],cfg["dur"],cfg["label"]
    sr=44100; dur=int(min(duration_sec+30,7200)); n=sr*dur; fade=sr*3
    beat_period=int(sr*60/bpm); beat_env_len=int(sr*0.20)
    def smooth_env(pos,length):
        if pos>=length: return 0.0
        return math.sin(math.pi*pos/length)**2
    try:
        with open(wav,'wb') as f:
            dsize=n*2
            f.write(b'RIFF'); f.write(struct.pack('<I',36+dsize))
            f.write(b'WAVEfmt '); f.write(struct.pack('<I',16))
            f.write(struct.pack('<H',1)); f.write(struct.pack('<H',1))
            f.write(struct.pack('<I',sr)); f.write(struct.pack('<I',sr*2))
            f.write(struct.pack('<H',2)); f.write(struct.pack('<H',16))
            f.write(b'data'); f.write(struct.pack('<I',dsize))
            for start in range(0,n,sr):
                end=min(start+sr,n); buf=[]
                for i in range(start,end):
                    t=i/sr
                    chord_idx=int(t/chord_dur)%len(chords); chord_pos=t%chord_dur
                    if chord_pos<0.5:
                        prev=(chord_idx-1)%len(chords); bl=chord_pos/0.5
                        mul=chords[prev]*(1-bl)+chords[chord_idx]*bl
                    else: mul=chords[chord_idx]
                    v=sum(a*math.sin(2*math.pi*fr*mul*t) for a,fr in zip(amps,base_freqs))
                    v+=amps[0]*0.08*math.sin(2*math.pi*base_freqs[0]*mul*3*t)
                    v+=0.10*smooth_env(i%beat_period,beat_env_len)*math.sin(2*math.pi*70*mul*t)
                    v*=(1+0.02*math.sin(2*math.pi*0.15*t))
                    if i<fade: v*=i/fade
                    elif i>n-fade: v*=(n-i)/fade
                    buf.append(struct.pack('<h',int(max(-0.85,min(0.85,v))*32767)))
                f.write(b''.join(buf))
        r=subprocess.run(["ffmpeg","-y","-i",str(wav),"-af","volume=2.0,highpass=f=40,lowpass=f=8000",
            "-c:a","mp3","-b:a","128k",str(mp3)],capture_output=True,text=True,timeout=180)
        if r.returncode==0 and mp3.exists(): return str(mp3)
    except: pass
    return ""

# ─── IMAGES ──────────────────────────────────────────────────────────────────
def download_image(i, prompt, total, topic=""):
    path = WORK/f"img_{i+1:02d}.jpg"
    clean = prompt[:120].replace('"','').replace("'",'')
    full_prompt = f"{clean}, no people, no humans, no cars, cinematic landscape 8k dramatic lighting"

    for attempt, seed in enumerate([i*7+42, i*13+17, i*3+99, i*19+5, i*31+11]):
        enc = quote(full_prompt[:200])
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
            full_prompt = f"{topic} landscape cinematic dramatic no people 8k"

    colors=["0x3D1C02","0x4A0E0E","0x0A1628","0x2D1B69","0x003333","0x1A3A1A","0x330033","0x1A1A00"]
    subprocess.run(["ffmpeg","-y","-f","lavfi","-i",f"color=c={colors[i%len(colors)]}:size=1920x1080:rate=1","-vframes","1","-q:v","2",str(path)],capture_output=True)
    tg(f"Image {i+1} fallback color","⚠")
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
        subprocess.run(["ffmpeg","-y","-f","lavfi","-i",f"color=c={color.replace('#','0x')}:size=1280x720:rate=1","-vframes","1",str(base)],capture_output=True)
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
    tg("Audio generated (Guy Neural)","✅")

    if sub_vtt.exists():
        vtt=sub_vtt.read_text(encoding="utf-8"); srt=[]; count=1
        for block in re.split(r'\n\n+',vtt):
            if '-->' in block:
                lines=block.strip().split('\n')
                timing=next((s for s in lines if '-->' in s),None)
                if timing:
                    timing=re.sub(r'(\d{2}:\d{2}:\d{2})\.(\d{3})',r'\1,\2',timing).strip()
                    text_lines=[s for s in lines if '-->' not in s and s.strip()
                                and not s.startswith('NOTE') and not s.strip().isdigit()]
                    if text_lines:
                        srt+=[str(count),timing]+text_lines+['']; count+=1
        sub_srt.write_text('\n'.join(srt),encoding="utf-8")

    probe=subprocess.run(["ffprobe","-v","quiet","-print_format","json","-show_format",str(rf)],capture_output=True,text=True)
    duration=float(json.loads(probe.stdout)["format"]["duration"])
    tg(f"Audio ready! Duration: <b>{duration/60:.1f} minutes</b>","✅")
    return str(rf), duration, str(sub_srt) if sub_srt.exists() else ""

# ─── MUSIC MIX ───────────────────────────────────────────────────────────────
def mix_audio(narration, music, duration):
    if not music:
        tg("No music path","⚠"); return narration
    music_path = Path(music)
    if not music_path.exists():
        tg(f"Music file not found: {music}","⚠"); return narration
    tg(f"Music file size: {music_path.stat().st_size//1024}KB","🎚")
    try:
        pb=subprocess.run(["ffprobe","-v","quiet","-print_format","json","-show_format",str(music_path)],capture_output=True,text=True)
        ms=float(json.loads(pb.stdout)["format"]["duration"])
        if ms<3: tg("Music too short","⚠"); return narration
        tg(f"Mixing audio + music ({ms:.0f}s)...","🎚")
    except Exception as e:
        tg(f"ffprobe error: {e}","⚠"); return narration

    mixed=WORK/"mixed.mp3"
    cmd=["ffmpeg","-y",
         "-i",narration,
         "-stream_loop","-1","-i",str(music_path),
         "-filter_complex",
         "[0:a]aformat=sample_rates=44100:channel_layouts=stereo[a1];"
         "[1:a]aformat=sample_rates=44100:channel_layouts=stereo,volume=0.20[a2];"
         "[a1][a2]amix=inputs=2:duration=first:weights=1 0.6[aout]",
         "-map","[aout]",
         "-c:a","libmp3lame","-b:a","192k",
         "-t",str(int(duration)+2),
         str(mixed)]
    r=subprocess.run(cmd,capture_output=True,text=True,timeout=600)
    if r.returncode==0 and mixed.exists() and mixed.stat().st_size>50000:
        tg(f"Music mixed! ({mixed.stat().st_size//1024}KB)","✅")
        return str(mixed)
    tg(f"Mix failed: {r.stderr[-80:]}","⚠")
    return narration

# ─── VIDEO ASSEMBLY ───────────────────────────────────────────────────────────
def assemble_video(images, audio, subtitle_srt, total_duration):
    tg(f"Assembling video...\n{len(images)} images | fade + flash effects\n⏳ ~{len(images)//2+5} min","🎬")

    img_dur = total_duration / len(images)
    fps = 30
    fade_dur = 0.8  # saniye - geçiş süresi

    def make_effect(idx, frames):
        effects = [
            f"zoompan=z='1.0+(0.12*on/{frames})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1920x1080:fps={fps}",
            f"zoompan=z='1.12-(0.12*on/{frames})':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1920x1080:fps={fps}",
            f"zoompan=z='1.10':x='(iw*0.05)-(iw*0.05*on/{frames})':y='ih/2-(ih/zoom/2)':d={frames}:s=1920x1080:fps={fps}",
            f"zoompan=z='1.10':x='iw*0.05*on/{frames}':y='ih/2-(ih/zoom/2)':d={frames}:s=1920x1080:fps={fps}",
            f"zoompan=z='1.10':x='iw/2-(iw/zoom/2)':y='(ih*0.04)-(ih*0.04*on/{frames})':d={frames}:s=1920x1080:fps={fps}",
            f"zoompan=z='1.10':x='iw/2-(iw/zoom/2)':y='ih*0.04*on/{frames}':d={frames}:s=1920x1080:fps={fps}",
            f"zoompan=z='1.0':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1920x1080:fps={fps}",
            f"zoompan=z='1.0+(0.10*on/{frames})':x='(iw*0.03)-(iw*0.03*on/{frames})':y='ih/2-(ih/zoom/2)':d={frames}:s=1920x1080:fps={fps}",
        ]
        return effects[idx % len(effects)]

    clips = []
    for idx, img in enumerate(images):
        clip = WORK/f"clip_{idx:02d}.mp4"
        frames = int(img_dur * fps)
        eff = make_effect(idx, frames)

        # Her 4 sahnede bir ışık parlaması efekti
        flash = (idx % 4 == 3)
        if flash:
            # Işık parlaması: ortada parlama, sonra normale dön
            vf = (f"{eff},"
                  f"vignette=PI/4,"
                  f"curves=all='0/0 0.3/0.3 0.5/1.0 0.7/0.7 1/1'[base];"
                  f"[base]fade=t=in:st=0:d=0.3:color=white,"
                  f"fade=t=out:st={img_dur-0.3:.2f}:d=0.3,"
                  f"format=yuv420p")
        else:
            vf = (f"{eff},"
                  f"vignette=PI/4,"
                  f"fade=t=in:st=0:d={fade_dur},"
                  f"fade=t=out:st={img_dur-fade_dur:.2f}:d={fade_dur},"
                  f"format=yuv420p")

        r=subprocess.run(["ffmpeg","-y","-loop","1","-i",img,
            "-vf", vf,
            "-t", str(img_dur),
            "-c:v","libx264","-preset","fast","-crf","20",
            "-r", str(fps),
            str(clip)],
            capture_output=True, text=True, timeout=300)
        if r.returncode==0 and clip.exists():
            clips.append(str(clip))
            tg(f"Clip {idx+1}/{len(images)} {'⚡' if flash else '✓'}","🎞")
        else:
            tg(f"Clip {idx+1} failed: {r.stderr[-60:]}","⚠")

    if not clips:
        raise Exception("No clips generated")

    concat_list = WORK/"concat.txt"
    concat_list.write_text('\n'.join(f"file '{Path(c).resolve()}'" for c in clips))
    raw_video = WORK/"video_raw.mp4"
    r=subprocess.run(["ffmpeg","-y","-f","concat","-safe","0",
        "-i",str(concat_list.resolve()),"-c:v","copy",str(raw_video)],
        capture_output=True,text=True,timeout=3600)
    if r.returncode!=0 or not raw_video.exists():
        raise Exception(f"Concat failed: {r.stderr[-100:]}")

    final_video = WORK/"final_video.mp4"
    if subtitle_srt and os.path.exists(subtitle_srt):
        srt_esc = str(subtitle_srt).replace('\\','/').replace(':','\\:')
        vf_sub = (f"subtitles={srt_esc}:force_style='"
                  f"FontSize=14,PrimaryColour=&H00FFFF00,"
                  f"OutlineColour=&H00000000,Outline=2,BorderStyle=1,"
                  f"Alignment=2,MarginV=30'")
        r=subprocess.run(["ffmpeg","-y","-i",str(raw_video),"-i",audio,
            "-vf",vf_sub,"-c:v","libx264","-preset","fast","-crf","20",
            "-c:a","aac","-b:a","192k","-shortest",str(final_video)],
            capture_output=True,text=True,timeout=7200)
    else:
        r=subprocess.run(["ffmpeg","-y","-i",str(raw_video),"-i",audio,
            "-c:v","copy","-c:a","aac","-b:a","192k","-shortest",str(final_video)],
            capture_output=True,text=True,timeout=7200)

    if r.returncode!=0 or not final_video.exists():
        raise Exception(f"Final video failed: {r.stderr[-100:]}")

    size_mb = final_video.stat().st_size//(1024*1024)
    tg(f"Video ready! {size_mb}MB","✅")
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
    body = {
        "snippet":{
            "title":meta["title"][:100],
            "description":meta["description"][:5000],
            "tags":meta["tags"][:500],
            "categoryId":"27",
            "defaultLanguage":"en",
            "defaultAudioLanguage":"en"
        },
        "status":{
            "privacyStatus":"private",
            "publishAt":publish_iso,
            "selfDeclaredMadeForKids":False
        }
    }
    r=requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",
        headers={"Authorization":f"Bearer {token}","Content-Type":"application/json",
                 "X-Upload-Content-Type":"video/mp4"},
        json=body,timeout=30)
    upload_url = r.headers.get("Location","")
    if not upload_url: raise Exception(f"No upload URL: {r.text[:100]}")
    with open(video_path,"rb") as f: video_data = f.read()
    r2=requests.put(upload_url,headers={"Content-Type":"video/mp4"},data=video_data,timeout=1800)
    if r2.status_code not in [200,201]: raise Exception(f"Upload failed: {r2.text[:100]}")
    vid_id = r2.json().get("id","")
    tg(f"Uploaded! youtube.com/watch?v={vid_id}\nScheduled: {publish_iso}","🎉")
    return vid_id

def upload_thumbnail(vid_id, thumb_path):
    try:
        token = get_access_token()
        with open(thumb_path,"rb") as f: data = f.read()
        r=requests.post(f"https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId={vid_id}",
            headers={"Authorization":f"Bearer {token}","Content-Type":"image/jpeg"},
            data=data,timeout=60)
        if r.status_code==200: tg("Thumbnail uploaded!","🖼")
    except Exception as e: tg(f"Thumbnail upload failed: {e}","⚠")

# ─── MAIN ─────────────────────────────────────────────────────────────────────
def main():
    if len(sys.argv) < 2:
        tg("No command received","⚠"); sys.exit(1)
    cmd = " ".join(sys.argv[1:])
    tg(f"Command: <b>{cmd}</b>","🚀")
    try:
        params = parse_command(cmd)
    except Exception as e:
        tg(f"Command error: {e}","❌"); sys.exit(1)

    topic      = params["topic"]
    music_hint = params["music_hint"]
    duration   = params["duration"]
    img_count  = params["img_count"]
    pub_iso    = params["publish_iso"]

    tg(f"<b>{topic}</b> | {duration} min | {img_count} images\n🎵 Music: {music_hint}\n📅 {pub_iso}","📋")

    try:
        meta        = generate_content(topic, duration, img_count)
        music       = generate_music(topic, duration*60, music_hint)
        images      = generate_images(meta["image_prompts"], topic)
        generate_thumbnail(meta["thumbnail_prompt"], meta["thumbnail_text"], meta["color"], topic)
        audio, audio_dur, subtitle_srt = generate_audio(meta["script"])
        final_audio = mix_audio(audio, music, audio_dur)
        video       = assemble_video(images, final_audio, subtitle_srt, audio_dur)
        vid_id      = upload_youtube(video, meta, pub_iso)
        upload_thumbnail(vid_id, str(WORK/"thumbnail.jpg"))
        tg(f"✅ DONE!\nyoutube.com/watch?v={vid_id}","🎬")
    except Exception as e:
        tg(f"Fatal error: {str(e)[:200]}","❌"); sys.exit(1)

if __name__ == "__main__":
    main()