#!/usr/bin/env python3
"""Render an X post and its playing video to an MP4."""
import argparse
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
import cairosvg

BG = (0, 0, 0)
WHITE = (231, 233, 234)
MUTED = (113, 118, 123)
BORDER = (47, 51, 54)
BLUE = (29, 155, 240)
FONT_DIR = Path(__file__).resolve().parent / 'fonts'


def get_json(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def get_metadata(url, tweet_id):
    try:
        data = get_json(f'https://api.fxtwitter.com/status/{tweet_id}')
        tweet = data['tweet']
        author = tweet['author']
        return {
            'text': tweet['text'], 'name': author['name'],
            'handle': author['screen_name'], 'avatar': author.get('avatar_url'),
            'verified': author.get('verification', {}).get('verified') is True,
            'created_at': tweet.get('created_at'),
            'replies': tweet.get('replies', 0), 'retweets': tweet.get('retweets', 0),
            'likes': tweet.get('likes', 0), 'views': tweet.get('views', 0),
            'bookmarks': tweet.get('bookmarks', 0),
        }
    except Exception as exc:
        print(f'Profile metadata unavailable ({exc}); using yt-dlp data.', file=sys.stderr)
        raw = subprocess.check_output(['yt-dlp', '--dump-single-json', '--skip-download', url], text=True)
        data = json.loads(raw)
        return {
            'text': re.sub(r'\s+https://t\.co/\S+$', '', data.get('description', '')),
            'name': data.get('uploader', ''), 'handle': data.get('uploader_id', ''),
            'avatar': None, 'verified': False, 'created_at': None,
            'replies': data.get('comment_count', 0), 'retweets': data.get('repost_count', 0),
            'likes': data.get('like_count', 0), 'views': data.get('view_count', 0),
            'bookmarks': 0,
        }


def font(size, bold=False):
    path = FONT_DIR / ('chirp-bold.ttf' if bold else 'chirp-regular.ttf')
    return ImageFont.truetype(path, size, layout_engine=ImageFont.Layout.RAQM)


def compact(value):
    value = int(value or 0)
    if value >= 1000000:
        return f'{value / 1000000:.1f}M'
    if value >= 1000:
        amount = value / 1000
        return f'{amount:.0f}K' if amount < 10 else f'{amount:.1f}K'
    return f'{value:,}'


def wrap(draw, text, face, max_width):
    lines = []
    for paragraph in text.split('\n'):
        line = ''
        for word in paragraph.split():
            candidate = f'{line} {word}'.strip()
            if line and draw.textlength(candidate, font=face, features=['kern', 'liga']) > max_width:
                lines.append(line)
                line = word
            else:
                line = candidate
        lines.append(line)
    return lines


ICON_DIR = Path(__file__).resolve().parent / 'icons'


def icon(canvas, kind, x, y, size=21):
    png = cairosvg.svg2png(url=str(ICON_DIR / f'{kind}.svg'), output_width=size*3, output_height=size*3)
    image = Image.open(io.BytesIO(png)).convert('RGBA').resize((size,size), Image.Resampling.LANCZOS)
    canvas.paste(image, (x,y), image)


def video_mask(width, height, dest, radius=14):
    scale = 4
    mask = Image.new('L', (width * scale, height * scale), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, width * scale - 1, height * scale - 1),
        radius=radius * scale, fill=255,
    )
    mask.resize((width, height), Image.Resampling.LANCZOS).save(dest)


def render_frame(meta, video_width, video_height, dest, width=632):
    canvas_width = width + 88
    margin = 60
    content = canvas_width - margin*2
    media_h = round(content * video_height / video_width)
    body = font(22)
    name_font = font(20, True)
    handle_font = font(18)
    measure = ImageDraw.Draw(Image.new('RGB', (1, 1)))
    text_lines = wrap(measure, meta['text'], body, content)
    text_h = len(text_lines)*29
    card_h = 78 + text_h + 18 + media_h + 72 + 48
    height = max(canvas_width, card_h + 48)
    canvas = Image.new('RGB', (canvas_width, height), BG)
    draw = ImageDraw.Draw(canvas)
    top = max(24, (height-card_h)//2)
    draw.line((margin-16, 0, margin-16, height), fill=BORDER)
    draw.line((canvas_width-margin+15, 0, canvas_width-margin+15, height), fill=BORDER)
    avatar_x, avatar_y = margin, top
    try:
        avatar_url = meta['avatar'].replace('_200x200.', '_400x400.').replace('_normal.', '_400x400.')
        raw = None
        for url in dict.fromkeys((avatar_url, meta['avatar'])):
            try:
                req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
                raw = urllib.request.urlopen(req, timeout=15).read()
                break
            except Exception:
                continue
        if raw is None:
            raise ValueError('Avatar image is unavailable')
        avatar = Image.open(io.BytesIO(raw)).convert('RGBA').resize((192,192), Image.Resampling.LANCZOS)
        mask = Image.new('L', (192,192))
        ImageDraw.Draw(mask).ellipse((0,0,191,191), fill=255)
        avatar.putalpha(mask)
        avatar = avatar.resize((48,48), Image.Resampling.LANCZOS)
        canvas.paste(avatar,(avatar_x,avatar_y),avatar)
    except Exception:
        draw.ellipse((avatar_x,avatar_y,avatar_x+48,avatar_y+48),fill=(47,51,54))
    name_x = avatar_x+60
    draw.text((name_x,top+1),meta['name'],font=name_font,fill=WHITE,features=['kern', 'liga'])
    name_width = draw.textlength(meta['name'],font=name_font,features=['kern', 'liga'])
    if meta['verified']:
        vx = name_x + name_width + 6
        icon(canvas,'verified',round(vx),top+4,size=19)
    draw.text((name_x,top+27),'@'+meta['handle'],font=handle_font,fill=MUTED,features=['kern', 'liga'])
    icon(canvas,'more',canvas_width-margin-22,top+4,size=22)
    text_y = top+72
    for line in text_lines:
        draw.text((margin,text_y),line,font=body,fill=WHITE,features=['kern', 'liga'])
        text_y += 29
    media_y = text_y+18
    media_box=(margin,media_y,margin+content,media_y+media_h)
    footer_y=media_y+media_h+24
    if meta.get('created_at'):
        try:
            date=datetime.strptime(meta['created_at'],'%a %b %d %H:%M:%S %z %Y')
            stamp=date.astimezone(ZoneInfo('America/New_York')).strftime('%-I:%M %p · %b %-d, %Y')
            if meta.get('views'):
                stamp += f' · {compact(meta["views"])} Views'
            draw.text((margin,footer_y),stamp,font=font(16),fill=MUTED,features=['kern', 'liga'])
        except ValueError: pass
    draw.line((margin,footer_y+31,margin+content,footer_y+31),fill=BORDER)
    row_y=footer_y+47
    actions=[('reply','replies'),('repost','retweets'),('like','likes'),('bookmark','bookmarks'),('share',None)]
    for index,(glyph,key) in enumerate(actions):
        x=margin+index*(content-22)//4
        icon(canvas,glyph,x,row_y)
        if key and meta.get(key):
            draw.text((x+27,row_y+1),compact(meta[key]),font=font(15),fill=MUTED,features=['kern', 'liga'])
    crop_top = max(0, top - 24)
    crop_bottom = min(height, row_y + 21 + 24)
    if (crop_bottom - crop_top) % 2:
        crop_bottom += 1 if crop_bottom < height else -1
    crop_left = margin - 16
    canvas.crop((crop_left, crop_top, crop_left + width, crop_bottom)).save(dest)
    return tuple(value - (crop_left if index % 2 == 0 else crop_top)
                 for index, value in enumerate(media_box))


def probe(path):
    data=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(path)],text=True))
    video=next(s for s in data['streams'] if s['codec_type']=='video')
    return video['width'],video['height'],any(s['codec_type']=='audio' for s in data['streams'])


def main():
    parser=argparse.ArgumentParser(description='Render an X video post as an MP4 with the original audio.')
    parser.add_argument('url',help='x.com or twitter.com status URL')
    parser.add_argument('-o','--output',type=Path,help='Output MP4 path (default: username-ID.mp4)')
    parser.add_argument('--cookies-from-browser',choices=['chrome','firefox','safari'],help='Use local browser cookies for yt-dlp')
    parser.add_argument('--cookies-file',type=Path,help='Netscape-format cookie file exported from a browser')
    parser.add_argument('--width',type=int,default=632,help='Output width in pixels (default: 632)')
    args=parser.parse_args()
    match=re.search(r'https?://(?:www\.|mobile\.)?(?:x|twitter)\.com/([^/?#]+)/status/(\d+)',args.url)
    if not match: parser.error('Enter an x.com or twitter.com status URL.')
    if args.width < 552 or args.width % 2: parser.error('--width must be even and at least 552.')
    for exe in ('yt-dlp','ffmpeg','ffprobe'):
        if not shutil.which(exe): parser.error(f'{exe} is required and was not found in PATH.')
    tweet_id=match.group(2)
    meta=get_metadata(args.url,tweet_id)
    username=meta['handle'].lstrip('@')
    if not re.fullmatch(r'[A-Za-z0-9_]{1,15}',username):
        username=match.group(1)
    output=args.output or Path(f'{username}-{tweet_id}.mp4')
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='tweet-to-video-') as tmp:
        tmp=Path(tmp)
        source=tmp/'source.mp4'
        command=['yt-dlp','--no-playlist','-f','bv*+ba/b','--merge-output-format','mp4','-o',str(tmp/'source.%(ext)s')]
        if args.cookies_from_browser: command += ['--cookies-from-browser',args.cookies_from_browser]
        if args.cookies_file: command += ['--cookies',str(args.cookies_file)]
        subprocess.run(command+[args.url],check=True)
        if not source.exists(): raise RuntimeError('yt-dlp did not produce an MP4.')
        video_w,video_h,has_audio=probe(source)
        if not has_audio: print('Warning: source video has no audio stream.',file=sys.stderr)
        frame=tmp/'frame.png'
        left,top,right,bottom=render_frame(meta,video_w,video_h,frame,args.width)
        mask=tmp/'mask.png'
        video_mask(right-left,bottom-top,mask)
        # Give the moving video a real alpha mask before placing it on the post.
        overlay=(f'[0:v]scale={right-left}:{bottom-top}:flags=lanczos,format=rgba[v];'
                 f'[2:v]format=gray[m];[v][m]alphamerge[clipped];'
                 f'[1:v][clipped]overlay={left}:{top}:shortest=1:format=auto[out]')
        cmd=['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(source),
             '-loop','1','-framerate','30','-i',str(frame),
             '-loop','1','-framerate','30','-i',str(mask),
             '-filter_complex',overlay,'-map','[out]']
        if has_audio: cmd += ['-map','0:a:0','-c:a','aac','-b:a','192k']
        cmd += ['-c:v','libx264','-preset','medium','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart','-shortest',str(output)]
        subprocess.run(cmd,check=True)
    print(output.resolve())


if __name__=='__main__':
    main()
