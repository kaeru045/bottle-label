exec(open('common.py').read())
import time; t=time.time()
for nm,f in [('B',black),('A',white),('U',uv)]:
    np.save(f'base_{nm}.npy',render(['bg','design'],f,tag=nm)); print(nm,time.time()-t,flush=True)
for k in ['tagbody','square']:
    for nm,f in [('B',black),('A',white),('U',uv)]:
        np.save(f'{k}_{nm}.npy',render(['bg','design',k],f,tag=k+nm))
    print(k,time.time()-t,flush=True)
for k in ['nashi','tagseal_white','tagseal_black','tagseal_pink','heart','nk_white','nk_black','nk_silver','nk_gold','nk_ophicus',
          'sl_cl_silver','sl_cl_gold','sl_cl_white','sl_cl_black','sl_sample','sl_hide','sl_lx_green','sl_lx_white','sl_lx_black','sl_lx_gold','sl_lx_silver',
          'deco_neck','deco_chira','ribbon','note']:
    np.save(f'ov_{k}.npy',render([k],None,transparent=True,tag=k)); print(k,time.time()-t,flush=True)
