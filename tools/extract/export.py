exec(open('common.py').read())
import os, glob
out='/home/claude/tool/'
for f in glob.glob(out+'ov-*.png')+glob.glob(out+'tag-*.png'): os.remove(f)
P=[[367.104,0,0,260.536,-13.196,25.222],[367.104,0,0,260.536,309.28,26.11],[367.104,0,0,260.536,-57.817,26.11],[476.082,0,0,337.879,36.987,470.333],
   [106.88,0,0,75.854,396.28,43.838],[0,-90.441,62.42,0,419.576,135.52],[143.03,0,0,101.513,381.014,42.977]]
B=np.load('base_B.npy'); A=np.load('base_A.npy'); U=np.load('base_U.npy'); H,W,_=B.shape
yy,xx=np.mgrid[0:H,0:W]; xp=(xx+0.5)/S; yp=PH-(yy+0.5)/S
def classify(Bv,Av,Uv,cands,ox=0,oy=0):
    h,w,_=Bv.shape; T=(Av-Bv)[...,0].astype(float); m=T>0
    if len(cands)==1: return np.clip(T,0,255).astype(np.uint8), np.where(m,cands[0]+1,0).astype(np.uint8)
    uc=np.where(m,(Uv[...,0]-Bv[...,0])/np.maximum(T,1),0); vc=np.where(m,(Uv[...,1]-Bv[...,1])/np.maximum(T,1),0)
    X=xp[oy:oy+h,ox:ox+w]; Y=yp[oy:oy+h,ox:ox+w]; best=np.full(T.shape,1e9); idx=np.zeros(T.shape,np.uint8)
    for k in cands:
        a,b,c,d,e,f=P[k]; det=a*d-b*c; u=(d*(X-e)-c*(Y-f))/det; v=1-(-b*(X-e)+a*(Y-f))/det
        err=np.abs(u-uc)+np.abs(v-vc); ok=m&(err<best); best[ok]=err[ok]; idx[ok]=k+1
    print('err',np.median(best[m&(T>64)]))
    return np.clip(T,0,255).astype(np.uint8), idx
T,idx=classify(B,A,U,[0,1,2,3])
Image.fromarray(B.astype(np.uint8)).save(out+'base.jpg',quality=90)
mp=np.zeros((H,W,3),np.uint8); mp[...,0]=T; mp[...,1]=idx; Image.fromarray(mp).save(out+'map.png',optimize=True)
meta={'ov':{},'tags':{},'place':P}
for k in ['tagbody','square']:
    b=np.load(f'{k}_B.npy'); a=np.load(f'{k}_A.npy'); u=np.load(f'{k}_U.npy')
    d=np.maximum(np.abs(b-B).max(2),np.abs(a-A).max(2)); ys,xs=np.where(d>0); x0,y0,x1,y1=xs.min(),ys.min(),xs.max()+1,ys.max()+1
    t,ix=classify(b[y0:y1,x0:x1],a[y0:y1,x0:x1],u[y0:y1,x0:x1],[4] if k=='tagbody' else [5],x0,y0)
    Image.fromarray(b[y0:y1,x0:x1].astype(np.uint8)).save(out+f'tag-{k}.png',optimize=True)
    m=np.zeros((y1-y0,x1-x0,3),np.uint8); m[...,0]=t; m[...,1]=ix; Image.fromarray(m).save(out+f'tag-{k}-t.png',optimize=True)
    meta['tags'][k]=[int(x0),int(y0)]
# ハート：形（透明度）だけ使い、中身はデザインを入れる
o=np.load('ov_heart.npy'); al=o[...,3].astype(float)/255; ys,xs=np.where(o[...,3]>0); x0,y0,x1,y1=xs.min(),ys.min(),xs.max()+1,ys.max()+1
a=al[y0:y1,x0:x1]; bp=B[y0:y1,x0:x1].astype(float)*(1-a[...,None])
Image.fromarray(np.clip(bp,0,255).astype(np.uint8)).save(out+'tag-heart.png',optimize=True)
m=np.zeros((y1-y0,x1-x0,3),np.uint8); m[...,0]=np.round(a*255); m[...,1]=np.where(a>0,7,0); Image.fromarray(m).save(out+'tag-heart-t.png',optimize=True)
meta['tags']['heart']=[int(x0),int(y0)]
for k in ['nashi','tagseal_white','tagseal_black','tagseal_pink','nk_white','nk_black','nk_silver','nk_gold','nk_ophicus',
          'sl_cl_silver','sl_cl_gold','sl_cl_white','sl_cl_black','sl_sample','sl_hide','sl_lx_green','sl_lx_white','sl_lx_black','sl_lx_gold','sl_lx_silver',
          'deco_neck','deco_chira','ribbon','note']:
    o=np.load(f'ov_{k}.npy'); ys,xs=np.where(o[...,3]>0); x0,y0,x1,y1=xs.min(),ys.min(),xs.max()+1,ys.max()+1
    Image.fromarray(o[y0:y1,x0:x1]).save(out+f'ov-{k}.png',optimize=True); meta['ov'][k]=[int(x0),int(y0)]
json.dump(meta,open('meta.json','w')); print(json.dumps(meta))
