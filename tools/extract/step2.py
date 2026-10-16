exec(open('common.py').read())

np.save('sqframe.npy',render(['bg','design','square'],black,tag='sqf'))
np.save('ov_square_img.npy',render(['square_img'],None,transparent=True,tag='sqi'))
B=np.load('base_B.npy')
out='/home/claude/tool/'
o=np.load('ov_nk_ophicus.npy'); ys,xs=np.where(o[...,3]>0); x0,y0,x1,y1=xs.min(),ys.min(),xs.max()+1,ys.max()+1
Image.fromarray(o[y0:y1,x0:x1]).save(out+'ov-nk_ophicus.png',optimize=True); print('oph',x0,y0,x1)
F=np.load('sqframe.npy').astype(float); I=np.load('ov_square_img.npy'); al=I[...,3].astype(float)/255
d=np.maximum(np.abs(F-B).max(2), I[...,3]); ys,xs=np.where(d>0); x0,y0,x1,y1=xs.min(),ys.min(),xs.max()+1,ys.max()+1
a=al[y0:y1,x0:x1]; bp=F[y0:y1,x0:x1]*(1-a[...,None])
Image.fromarray(np.clip(bp,0,255).astype(np.uint8)).save(out+'tag-square.png',optimize=True)
m=np.zeros((y1-y0,x1-x0,3),np.uint8); m[...,0]=np.round(a*255); m[...,1]=np.where(a>0,6,0); Image.fromarray(m).save(out+'tag-square-t.png',optimize=True)
print('square',x0,y0)
