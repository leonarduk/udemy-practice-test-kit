# TODO: course title

Source for a Udemy video course. Lectures are Marp Markdown: the slides are
the visible content, and each slide's HTML comment is the narration script.
The pipeline is [udemy-practice-test-kit](https://github.com/leonarduk/udemy-practice-test-kit)'s
`ptkit video`.

## Build

Needs Python 3.11+, Node (Marp runs via `npx`), ffmpeg, and Chrome or Edge
(Marp uses it to render PNGs).

```bash
pip install -r requirements-dev.txt
ptkit video check                    # script problems, durations, recordings left
ptkit video build --engine silent    # free preview: slides + timing, no voice
ptkit video script 01-01             # the reading script for one lecture
ptkit video build                    # final MP4 + VTT per lecture into build/
```

Upload `build/<lecture>.mp4` as the lecture video and `build/<lecture>.vtt` as
its English captions.
