"""Music bed + SFX on the beat grid -> brag-output/brag.mp4 (video from
brag-output/work/video_silent.mp4). The music and SFX come from the
/brag skill install (~/.claude/skills/brag/assets). Levels are measured
afterwards (ebur128): -16.7 LUFS integrated."""

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "brag-output"
WORK = OUT / "work"
SKILL = Path.home() / ".claude" / "skills" / "brag" / "assets"
MUSIC = SKILL / "music" / "happy-beats-business-moves-vol-11-by-ende-dot-app.mp3"
SFX = SKILL / "sfx"
DURATION = 21.6

# (time s, file, gain) — see ../brag-plan.md
CUES = [
    (1.60, "interface/switch_006.ogg", 0.9),          # the word drops out
    (3.70, "impact/impactSoft_medium_001.ogg", 1.0),  # title lands
    (6.86, "casino/card-slide-1.ogg", 0.55),           # queue window slides
    (6.86, "interface/click_003.ogg", 0.6),            # chips
    (7.38, "interface/click_003.ogg", 0.6),
    (7.91, "interface/click_003.ogg", 0.6),
    (8.96, "interface/drop_002.ogg", 0.8),             # toast
    (10.54, "casino/card-slide-1.ogg", 0.55),          # review window
    (12.12, "interface/click_003.ogg", 1.0),           # THE click
    (13.70, "casino/card-slide-1.ogg", 0.55),          # add-url dialog
    (13.70, "interface/click_003.ogg", 0.45),          # host chips
    (14.22, "interface/click_003.ogg", 0.45),
    (14.76, "interface/click_003.ogg", 0.45),
    (15.28, "interface/click_003.ogg", 0.45),
    (16.34, "impact/impactSoft_medium_004.ogg", 0.8),  # «Всё на вашем компьютере»
    (18.96, "impact/impactBell_heavy_003.ogg", 0.7),   # outro
]

inputs = ["-i", str(WORK / "video_silent.mp4"), "-i", str(MUSIC)]
for _, name, _ in CUES:
    inputs += ["-i", str(SFX / name)]

# music: -14.8 LUFS integrated on its own; sit it a little under that
# and fade over the last 1.3 s. SFX: mono-ish, short; pre-delayed.
chains = [f"[1:a]atrim=0:{DURATION},aresample=48000,"
          f"afade=t=in:st=0:d=0.3,afade=t=out:st={DURATION - 1.3}:d=1.3,"
          f"volume=0.72[music]"]
labels = ["[music]"]
for i, (t, _, gain) in enumerate(CUES):
    ms = int(round(t * 1000))
    chains.append(f"[{i + 2}:a]aresample=48000,aformat=channel_layouts=stereo,"
                  f"volume={gain:.2f},adelay={ms}|{ms}[s{i}]")
    labels.append(f"[s{i}]")
chains.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0:"
              f"duration=first:dropout_transition=0,"
              f"alimiter=limit=0.89:attack=3:release=60[aout]")

cmd = ["ffmpeg", "-y", "-v", "error", *inputs,
       "-filter_complex", ";".join(chains),
       "-map", "0:v", "-map", "[aout]", "-c:v", "copy",
       "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
       "-movflags", "+faststart", "-shortest", str(OUT / "brag.mp4")]
subprocess.run(cmd, check=True)
print("mixed ->", OUT / "brag.mp4")
