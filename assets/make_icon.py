from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter

out_dir = Path('assets')
out_dir.mkdir(exist_ok=True)
size = 1024
img = Image.new('RGBA', (size, size), (0,0,0,0))
draw = ImageDraw.Draw(img)

# Background gradient
base = Image.new('RGBA', (size, size), (0,0,0,0))
bd = ImageDraw.Draw(base)
for y in range(size):
    t = y / (size - 1)
    r = int(54 + (18 - 54) * t)
    g = int(182 + (104 - 182) * t)
    b = int(255 + (170 - 255) * t)
    bd.line([(0, y), (size, y)], fill=(r, g, b, 255))

mask = Image.new('L', (size, size), 0)
md = ImageDraw.Draw(mask)
md.rounded_rectangle((64, 64, size-64, size-64), radius=220, fill=255)
img = Image.composite(base, img, mask)

# soft glow
shadow = Image.new('RGBA', (size, size), (0,0,0,0))
sd = ImageDraw.Draw(shadow)
sd.rounded_rectangle((88, 88, size-88, size-88), radius=200, fill=(255,255,255,48))
shadow = shadow.filter(ImageFilter.GaussianBlur(28))
img = Image.alpha_composite(img, shadow)

draw = ImageDraw.Draw(img)

# inner panel
panel = (170, 210, size-170, size-220)
draw.rounded_rectangle(panel, radius=120, fill=(15, 38, 70, 235), outline=(255,255,255,90), width=8)

# grid cells representing multiple tools
cells = [
    ((220, 265, 455, 500), (101, 204, 255, 255)),
    ((570, 265, 805, 500), (72, 230, 181, 255)),
    ((220, 560, 455, 795), (255, 179, 71, 255)),
    ((570, 560, 805, 795), (255, 99, 132, 255)),
]
for rect, color in cells:
    draw.rounded_rectangle(rect, radius=56, fill=(255,255,255,28), outline=(255,255,255,80), width=5)
    cx = (rect[0] + rect[2]) // 2
    cy = (rect[1] + rect[3]) // 2
    # icon-specific
    if color[0] == 101:  # image
        draw.rectangle((cx-55, cy-38, cx+55, cy+38), outline=color, width=12)
        draw.polygon([(cx-48, cy+30), (cx-8, cy-12), (cx+20, cy+18), (cx+48, cy-22), (cx+48, cy+30)], fill=color)
        draw.ellipse((cx-28, cy-24, cx-2, cy+2), fill=(255,255,255,230))
    elif color[1] == 230:  # pdf/doc
        draw.rounded_rectangle((cx-50, cy-62, cx+34, cy+62), radius=16, fill=(255,255,255,230))
        draw.polygon([(cx+34, cy-62), (cx+34, cy-14), (cx-10, cy-14)], fill=(180, 244, 220, 255))
        for i in range(3):
            y = cy - 20 + i*24
            draw.line((cx-26, y, cx+12, y), fill=color, width=10)
    elif color[0] == 255 and color[1] == 179:  # upload/download/cloud
        draw.ellipse((cx-56, cy-20, cx+8, cy+34), fill=color)
        draw.ellipse((cx-10, cy-52, cx+56, cy+24), fill=color)
        draw.rectangle((cx-52, cy, cx+56, cy+44), fill=color)
        draw.polygon([(cx+2, cy-36), (cx+2, cy+6), (cx-22, cy+6), (cx+22, cy+44), (cx+66, cy+6), (cx+38, cy+6), (cx+38, cy-36)], fill=(255,255,255,230))
    else:  # play/media
        draw.ellipse((cx-64, cy-64, cx+64, cy+64), outline=color, width=14)
        draw.polygon([(cx-18, cy-34), (cx-18, cy+34), (cx+42, cy)], fill=color)

# center badge with wrench
badge = (410, 410, 614, 614)
draw.ellipse(badge, fill=(255,255,255,240), outline=(15,38,70,90), width=6)
# wrench
wcx, wcy = 512, 512
draw.rounded_rectangle((wcx-18, wcy-84, wcx+18, wcy+58), radius=18, fill=(19, 91, 214, 255))
draw.polygon([(wcx-56,wcy-70),(wcx-18,wcy-88),(wcx+8,wcy-64),(wcx-30,wcy-44)], fill=(19, 91, 214, 255))
draw.ellipse((wcx-72, wcy-104, wcx-18, wcy-50), outline=(19, 91, 214, 255), width=18)
draw.ellipse((wcx-8, wcy+40, wcx+44, wcy+92), fill=(19, 91, 214, 255))

png_path = out_dir / 'tool_app_icon.png'
ico_path = out_dir / 'tool_app_icon.ico'
img.save(png_path)
img.save(ico_path, sizes=[(256,256), (128,128), (64,64), (48,48), (32,32), (16,16)])
print(png_path)
print(ico_path)
