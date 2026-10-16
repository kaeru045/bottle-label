import pikepdf, zlib, numpy as np, pypdfium2 as pdfium, json
from PIL import Image
SRC='/home/claude/fmt4/all.pdf'; S=300/72; PH=841.89
src=pikepdf.open(SRC); OPS=pikepdf.parse_content_stream(src.pages[0]); N=len(OPS)
DESIGN=(113,0)
def groups(a,b):
    d=0;G=[]
    for i in range(a,b):
        s=str(OPS[i][1])
        if s=='q':
            if d==0: st=i
            d+=1
        elif s=='Q':
            d-=1
            if d==0: G.append((st,i+1))
    return G
NG=groups(4590,4660)
blocks=json.load(open('/home/claude/fmt4/blocks.json')); B12=json.load(open('/home/claude/fmt4/b12.json'))
def blk(i,j): return [(blocks[k][0],blocks[k][1]) for k in range(i,j+1)]
R={'bg':[(0,104)],'nashi':[(104,109)],'design':[(4483,4590)],
 'tagbody':[(114,407)],'tagseal_white':[(407,1766)],'tagseal_black':[(2059,3418)],'tagseal_pink':[(3418,3456)],
 'square':[(3456,4434)],'square_img':[(4456,4478)],'heart':[(4478,4483)],
 'nk_white':NG[0:2],'nk_black':NG[3:5],'nk_silver':NG[5:7],'nk_gold':NG[7:9],'nk_ophicus':[(4642,4662)],
 'sl_cl_silver':blk(0,2),'sl_cl_gold':blk(3,5),'sl_cl_white':blk(6,8),'sl_cl_black':blk(9,11),
 'sl_sample':[tuple(g) for g in B12[0:3]],'sl_hide':[tuple(g) for g in B12[3:6]],'sl_lx_green':[tuple(g) for g in B12[6:10]],
 'sl_lx_white':blk(13,15),'sl_lx_black':blk(16,18),'sl_lx_gold':blk(19,21),'sl_lx_silver':blk(22,24),
 'deco_neck':[(108675,108691)],'deco_chira':[(108691,108844)],'ribbon':[(108844,108850)],'note':[(108850,N)]}
PAINT={'f','F','f*','S','s','B','B*','b','b*','sh','Do','Tj','TJ',"'",'"'}
def render(on, fill=None, transparent=False, tag='x'):
    pdf=pikepdf.open(SRC); pg=pdf.pages[0]
    im=pdf.get_object(DESIGN); W,H=int(im.Width),int(im.Height)
    arr=(fill(W,H) if fill else np.zeros((H,W,3))).astype(np.uint8)
    im.write(zlib.compress(arr.tobytes(),6),filter=pikepdf.Name.FlateDecode)
    im.ColorSpace=pikepdf.Name.DeviceRGB; im.BitsPerComponent=8
    for k in ['/Decode','/DecodeParms','/SMask','/Intent']:
        if k in im: del im[k]
    keep=np.zeros(N,bool)
    for k in on:
        for a,b in R[k]: keep[a:b]=True
    new=[pikepdf.ContentStreamInstruction([],pikepdf.Operator('n')) if (not keep[i] and str(op) in PAINT) else pikepdf.ContentStreamInstruction(o,op) for i,(o,op) in enumerate(OPS)]
    pg.Contents=pdf.make_stream(pikepdf.unparse_content_stream(new)); pdf.save(f'tmp_{tag}.pdf')
    page=pdfium.PdfDocument(f'tmp_{tag}.pdf')[0]
    if transparent: return np.asarray(page.render(scale=S,fill_color=(0,0,0,0)).to_pil().convert('RGBA'))
    return np.asarray(page.render(scale=S).to_pil().convert('RGB')).astype(np.int16)
black=lambda W,H: np.zeros((H,W,3)); white=lambda W,H: np.full((H,W,3),255)
def uv(W,H):
    a=np.zeros((H,W,3)); a[...,0]=np.linspace(0,255,W)[None,:]; a[...,1]=np.linspace(0,255,H)[:,None]; return a
