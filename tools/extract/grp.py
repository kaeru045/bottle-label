import pikepdf, pypdfium2 as pdfium, zlib, sys
from PIL import Image, ImageDraw
SRC='def.pdf'
pdf=pikepdf.open(SRC); del pdf.Root['/OCProperties']; pdf.save('allon_src.pdf')
L=pikepdf.open('allon_src.pdf'); ops=pikepdf.parse_content_stream(L.pages[0])
PAINT={'f','F','f*','S','s','B','B*','b','b*','sh','Do','Tj','TJ',"'",'"'}
a0,b0=int(sys.argv[1]),int(sys.argv[2]); crop=tuple(map(int,sys.argv[3].split(',')))
d=0; G=[]
for i in range(a0,b0):
    s=str(ops[i][1])
    if s=='q':
        if d==0: st=i
        d+=1
    elif s=='Q':
        d-=1
        if d==0: G.append((st,i+1))
    elif d==0 and s in PAINT: G.append((i,i+1))
print(len(G))
tiles=[]
for (a,b) in G:
    new=[pikepdf.ContentStreamInstruction([],pikepdf.Operator('n')) if (not(a<=i<b) and str(op) in PAINT) else pikepdf.ContentStreamInstruction(o,op) for i,(o,op) in enumerate(ops)]
    L.pages[0].Contents=L.make_stream(pikepdf.unparse_content_stream(new)); L.save('g.pdf')
    tiles.append(pdfium.PdfDocument('g.pdf')[0].render(scale=1.5,fill_color=(255,0,255,255)).to_pil().convert('RGB').crop(crop))
cols=8; W=crop[2]-crop[0]; H=crop[3]-crop[1]
sh=Image.new('RGB',(cols*W,((len(tiles)+cols-1)//cols)*(H+16)),'white'); dr=ImageDraw.Draw(sh)
for i,t in enumerate(tiles): x=(i%cols)*W; y=(i//cols)*(H+16); sh.paste(t,(x,y+16)); dr.text((x+3,y+2),f'{i}:{G[i][0]}',fill='black')
sh.save(sys.argv[4])
