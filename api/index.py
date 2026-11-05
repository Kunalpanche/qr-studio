import base64, io, re
from datetime import datetime
from typing import Literal
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
import qrcode
from qrcode.constants import ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q, ERROR_CORRECT_H
from PIL import Image, ImageDraw

app = FastAPI(title="QR Studio")
MAX_CONTENT = 2950
CORRECTION = {"L": ERROR_CORRECT_L, "M": ERROR_CORRECT_M, "Q": ERROR_CORRECT_Q, "H": ERROR_CORRECT_H}

class QRRequest(BaseModel):
    content: str = Field(min_length=1, max_length=MAX_CONTENT)
    format: Literal['png','svg','pdf'] = 'png'
    size: int = Field(default=512, ge=128, le=2048)
    foreground: str = '#101828'
    background: str = '#ffffff'
    transparent: bool = False
    gradient: str | None = None
    pattern: Literal['square','rounded','dots'] = 'square'
    margin: int = Field(default=4, ge=0, le=12)
    correction: Literal['L','M','Q','H'] = 'M'
    logo: str | None = None
    logo_size: int = Field(default=18, ge=8, le=26)

def color(value):
    if not re.fullmatch(r'#[0-9a-fA-F]{6}', value): raise HTTPException(422, 'Colors must be 6-digit HEX values.')
    return tuple(int(value[i:i+2],16) for i in (1,3,5))

def matrix_for(req):
    if len(req.content.strip()) > MAX_CONTENT: raise HTTPException(422, 'Content is too long for a reliable QR code.')
    qr = qrcode.QRCode(version=None, error_correction=CORRECTION[req.correction], box_size=10, border=req.margin)
    try: qr.add_data(req.content.strip()); qr.make(fit=True)
    except Exception: raise HTTPException(422, 'Could not encode this content.')
    return qr.get_matrix()

def render(req):
    fg, bg = color(req.foreground), color(req.background)
    end = color(req.gradient) if req.gradient else fg
    grid = matrix_for(req); n = len(grid); scale = req.size / n
    mode = 'RGBA'; canvas = Image.new(mode, (req.size, req.size), (0,0,0,0) if req.transparent else (*bg,255)); draw = ImageDraw.Draw(canvas)
    for y,row in enumerate(grid):
      for x,on in enumerate(row):
       if not on: continue
       t = (x+y)/(2*max(n-1,1)); c = tuple(round(fg[i]*(1-t)+end[i]*t) for i in range(3)) + (255,)
       box=(round(x*scale),round(y*scale),round((x+1)*scale),round((y+1)*scale))
       if req.pattern == 'dots': draw.ellipse(box, fill=c)
       elif req.pattern == 'rounded': draw.rounded_rectangle(box, radius=max(1,scale*.28), fill=c)
       else: draw.rectangle(box, fill=c)
    if req.logo:
      try:
       raw = req.logo.split(',',1)[-1]; data=base64.b64decode(raw, validate=True)
       if len(data)>1_500_000: raise ValueError()
       # Pillow handles PNG/JPEG. SVG artwork stays vector-native in SVG export;
       # bitmap/PDF rendering needs an optional CairoSVG installation on Windows.
       if data.lstrip().startswith(b'<svg') or b'<svg' in data[:500]:
         try:
           import cairosvg
           data = cairosvg.svg2png(bytestring=data, output_width=512, output_height=512)
         except (ImportError, OSError):
           raise HTTPException(422, 'SVG logos are supported in SVG downloads. For PNG/PDF, use PNG/JPG or install CairoSVG with its Windows Cairo runtime.')
       logo=Image.open(io.BytesIO(data)).convert('RGBA'); logo.thumbnail((req.size*req.logo_size//100,)*2)
       pad=max(8,req.size//50); side=max(logo.size)+pad*2; x=(req.size-side)//2; y=x
       draw.rounded_rectangle((x,y,x+side,y+side),radius=side//8,fill=(255,255,255,255))
       canvas.alpha_composite(logo, ((req.size-logo.width)//2,(req.size-logo.height)//2))
      except Exception: raise HTTPException(422, 'The logo must be a valid PNG, JPG, or SVG under 1.5 MB.')
    return canvas, grid

def svg(req, grid):
    fg, bg = req.foreground, 'none' if req.transparent else req.background; n=len(grid); cells=[]
    gradient = f'<linearGradient id="g" x2="1" y2="1"><stop stop-color="{fg}"/><stop offset="1" stop-color="{req.gradient}"/></linearGradient>' if req.gradient else ''
    fill='url(#g)' if req.gradient else fg
    for y,row in enumerate(grid):
      for x,on in enumerate(row):
       if on:
        if req.pattern=='dots': cells.append(f'<circle cx="{x+.5}" cy="{y+.5}" r=".5"/>')
        elif req.pattern=='rounded': cells.append(f'<rect x="{x}" y="{y}" width="1" height="1" rx=".25"/>')
        else: cells.append(f'<path d="M{x} {y}h1v1h-1z"/>')
    logo = ''
    if req.logo:
      # Preserve the original uploaded artwork in vector output where the browser supports it.
      safe = req.logo.replace('&', '&amp;').replace('"', '&quot;').replace('<', '&lt;')
      side = n * req.logo_size / 100 + 2
      pos = (n-side)/2
      logo = f'<rect x="{pos}" y="{pos}" width="{side}" height="{side}" rx="1" fill="white"/><image href="{safe}" x="{pos+1}" y="{pos+1}" width="{side-2}" height="{side-2}" preserveAspectRatio="xMidYMid meet"/>'
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" shape-rendering="crispEdges"><defs>{gradient}</defs><rect width="100%" height="100%" fill="{bg}"/><g fill="{fill}">{"".join(cells)}</g>{logo}</svg>'

@app.get('/api/health')
def health(): return {'ok':True}

@app.post('/api/generate')
def generate(req: QRRequest):
    image, grid = render(req)
    if req.format == 'svg': return Response(svg(req,grid),media_type='image/svg+xml', headers={'Content-Disposition':'attachment; filename="qr-studio.svg"'})
    output=io.BytesIO()
    if req.format == 'pdf':
      # PDF has no alpha channel; retain a clean white paper background for print.
      paper = Image.new('RGB', image.size, 'white'); paper.paste(image, mask=image.getchannel('A'))
      paper.save(output,'PDF',resolution=300.0); mime='application/pdf'; name='qr-studio.pdf'
    else: image.save(output,'PNG',dpi=(300,300)); mime='image/png'; name='qr-studio.png'
    return Response(output.getvalue(),media_type=mime,headers={'Content-Disposition':f'attachment; filename="{name}"'})
