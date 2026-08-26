from PIL import Image, ImageDraw, ImageFont
import math

S = 2  # supersample
FR = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
FB = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
FM = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
FMB= "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"

C = dict(
  ink="#16222F", ink2="#3E5062", ink3="#6F8296", rule="#AEBCC6",
  surf="#EDF1F3", white="#FFFFFF", chip="#E3EAEE", band="#F1F5F6",
  mark="#B33224", verify="#0D6A61", warn="#8A6008", scope="#E1EEF0",
)

class D:
    def __init__(self, w, h, title=None, sub=None):
        self.w, self.h = w, h
        self.im = Image.new("RGB", (w*S, h*S), C["white"])
        self.d = ImageDraw.Draw(self.im)
        self.y0 = 0
        if title:
            self.text(38, 34, title, 27, FB, C["ink"])
            if sub: self.text(38, 70, sub, 16, FR, C["ink3"])
            self.line(38, 100, w-38, 100, C["ink"], 2)

    def f(self, size, path=FR):
        return ImageFont.truetype(path, int(size*S))

    def text(self, x, y, s, size=15, font=FR, col=None, anchor="la", spacing=1.35):
        col = col or C["ink"]
        self.d.text((x*S, y*S), s, font=self.f(size, font), fill=col, anchor=anchor)

    def tw(self, s, size=15, font=FR):
        return self.d.textlength(s, font=self.f(size, font))/S

    def line(self, x1, y1, x2, y2, col=None, wdt=1, dash=None):
        col = col or C["rule"]
        if not dash:
            self.d.line([x1*S, y1*S, x2*S, y2*S], fill=col, width=int(wdt*S))
            return
        L = math.hypot(x2-x1, y2-y1)
        if L == 0: return
        ux, uy = (x2-x1)/L, (y2-y1)/L
        on, off = dash; t = 0
        while t < L:
            e = min(t+on, L)
            self.d.line([(x1+ux*t)*S, (y1+uy*t)*S, (x1+ux*e)*S, (y1+uy*e)*S], fill=col, width=int(wdt*S))
            t = e + off

    def box(self, x, y, w, h, title=None, lines=None, kind="plain", tsize=17, lsize=13.5, pad=13):
        fill = {"plain":C["surf"], "accent":C["surf"], "verify":C["surf"],
                "band":C["band"], "white":C["white"], "chip":C["chip"]}[kind]
        edge = {"plain":C["rule"], "accent":C["mark"], "verify":C["verify"],
                "band":C["band"], "white":C["rule"], "chip":C["chip"]}[kind]
        wid  = {"plain":1, "accent":2.4, "verify":2, "band":1, "white":1, "chip":1}[kind]
        self.d.rectangle([x*S, y*S, (x+w)*S, (y+h)*S], fill=fill,
                         outline=edge, width=max(1,int(wid*S)))
        cy = y + pad
        if title:
            self.text(x+pad, cy, title, tsize, FB, C["ink"]); cy += tsize*1.42
        for ln in (lines or []):
            mono = ln.startswith("~")
            s = ln[1:] if mono else ln
            self.text(x+pad, cy, s, lsize-(1.5 if mono else 0),
                      FM if mono else FR, C["ink3"] if mono else C["ink2"])
            cy += (lsize)*1.5
        return (x, y, w, h)

    def arrow(self, pts, col=None, wdt=1.6, label=None, lsize=12, dash=None, lpos=None):
        col = col or C["ink3"]
        for i in range(len(pts)-1):
            (x1,y1),(x2,y2) = pts[i], pts[i+1]
            self.line(x1,y1,x2,y2,col,wdt,dash)
        (px,py),(qx,qy) = pts[-2], pts[-1]
        a = math.atan2(qy-py, qx-px); L=9; W=5.2
        p1 = (qx - L*math.cos(a) + W*math.sin(a), qy - L*math.sin(a) - W*math.cos(a))
        p2 = (qx - L*math.cos(a) - W*math.sin(a), qy - L*math.sin(a) + W*math.cos(a))
        self.d.polygon([(qx*S,qy*S),(p1[0]*S,p1[1]*S),(p2[0]*S,p2[1]*S)], fill=col)
        if label:
            lx, ly = lpos if lpos else ((pts[0][0]+qx)/2, (pts[0][1]+qy)/2 - 14)
            self.text(lx, ly, label, lsize, FM, col, anchor="ma")

    def tag(self, x, y, s, col=None, size=12):
        self.text(x, y, s, size, FMB, col or C["ink3"])

    def save(self, path):
        self.im.resize((self.w, self.h), Image.LANCZOS).save(path, "PNG", optimize=True)
        return path
