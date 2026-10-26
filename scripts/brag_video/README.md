# The site's video (docs/assets/brag.mp4)

Made with the `/brag-slim` skill (github.com/latent-spaces/brag): the
story is in `brag-plan.md`, the frames are drawn by `render.py`
(QPainter, every frame a function of time), the sound is mixed by
`mix.py`. The music and sound effects are NOT in this repo — they come
with the `/brag` skill (`~/.claude/skills/brag/assets`; install by
copying `skills/brag` from that repo). Music: Sascha Ende, ende.app,
CC BY 4.0 — keep the credit in the site footer. SFX: Kenney, CC0.

```
python scripts/render_screenshots.py          # fresh design renders (optional)
python scripts/brag_video/stage_review.py     # UI material -> brag-output/work
python scripts/brag_video/render.py stills    # check frames -> brag-output/work/stills
python scripts/brag_video/render.py video     # -> brag-output/work/video_silent.mp4
python scripts/brag_video/mix.py              # -> brag-output/brag.mp4
```

Then the poster (the settled reveal frame) baked as frame 0, from
`brag-output/`:

```
ffmpeg -y -ss 6.30 -i brag.mp4 -frames:v 1 -q:v 2 brag.jpg
ffmpeg -y -i brag.mp4 -i brag.jpg -filter_complex "[0:v][1:v]overlay=0:0:enable='eq(n,0)'[v]" -map "[v]" -map "0:a?" -c:v libx264 -crf 18 -preset slow -pix_fmt yuv420p -c:a copy -movflags +faststart brag.poster.mp4
```

Copy `brag.poster.mp4` to `docs/assets/brag.mp4` and `brag.jpg` to
`docs/assets/brag.jpg`. `brag-output/` itself is gitignored.
