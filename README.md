# Tweet to video

Create an MP4 that shows a video post from X. It's equivalent to screen recording it yourself, minus the hassle.

## Install

Requires Python 3.10+, `ffmpeg`, `ffprobe`, and `yt-dlp` on `PATH`.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Run

```sh
tweettovideo https://x.com/davj/status/2045949292897022078?s=20
```

You can tweak a few options, such as the width of the output video, using flags. Type `tweettovideo -h` to see more.