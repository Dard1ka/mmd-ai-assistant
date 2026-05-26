# MMD Renderer (Blender CLI)

Headless Blender script untuk render video MMD dari command line.

## Run

```bash
blender -b -P render_mmd.py -- \
  "path/to/model.pmx" \
  "path/to/motion.vmd" \
  "path/to/camera.vmd" \
  "path/to/audio.wav" \
  "output.mp4" \
  auto \
  "path/to/bg.mp4" \
  "path/to/facial.vmd" \
  1.0 0.0 1.0 \
  on auto on on 3
```

## Arguments (16 positional)

| # | Argument | Default | Description |
|---|----------|---------|-------------|
| 1 | model.pmx | required | Model PMX file |
| 2 | motion.vmd | required | Body motion VMD |
| 3 | camera.vmd or "none" | required | Camera motion (auto-detected if "none") |
| 4 | audio.wav/.mp3 | required | Audio track |
| 5 | output.mp4 | required | Output MP4 path |
| 6 | duration | `auto` | "auto" or seconds (e.g., 15) |
| 7 | bg_video.mp4 or "none" | required | Background video/image |
| 8 | facial.vmd or "none" | required | Facial expression VMD |
| 9 | brightness | 1.0 | Tone adjustment |
| 10 | contrast | 0.0 | Tone adjustment |
| 11 | saturation | 1.0 | Tone adjustment |
| 12 | physics | `on` | Enable cloth/rigid body physics |
| 13 | genshin_blend | `auto` | Path to Genshin Shader blend |
| 14 | outline | `on` | Anime outline toggle |
| 15 | auto_trim | `on` | Skip idle intro frames |
| 16 | trim_buffer | 3 | Frames before motion start |

## Features

- **mmd_tools plugin** untuk import PMX + VMD
- **Genshin Shader v2.2.1** integration (anime cel-shading)
- **Auto-detect** Camera.vmd & Facial.vmd di folder motion (defense vs AI hallucination)
- **Shadow catcher** plane untuk bayangan karakter
- **Auto-trim** intro frames (skip T-pose idle start)
- **Smart camera auto-fit** kalau Camera.vmd missing — calc bounding box character
- **Color Management Standard** view transform (anime-friendly)
- **Time remap** 30fps motion → 60fps render
- **Output**: 1080x1920 portrait, H264 + AAC, MP4

## Dependencies

- **Blender 3.6 LTS** (must be in PATH as `blender`)
- **mmd_tools** plugin ([GitHub](https://github.com/MMD-Blender/blender_mmd_tools))
- **Genshin Shader v2.2.1** by Ben Ayers (commercial, optional)
- **ffmpeg** (bundled with Blender)

## Notes

Script tested on Windows 10/11 with Blender 3.6.23. Render time approximately 0.3-0.5s per frame on RTX 3060 / equivalent GPU.
