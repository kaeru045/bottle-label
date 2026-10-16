import pikepdf, json
pdf=pikepdf.open('/home/claude/fmt4/nooc.pdf'); ops=pikepdf.parse_content_stream(pdf.pages[0])
d=0;G=[]
for i in range(4660,108675):
    s=str(ops[i][1])
    if s=='q':
        if d==0: st=i
        d+=1
    elif s=='Q':
        d-=1
        if d==0: G.append((st,i+1))
L=[b-a for a,b in G]
starts=[i for i in range(len(L)-3) if L[i:i+4]==[7,24,12,86]]
# 後半のパターン
starts2=[i for i in range(len(L)-3) if L[i:i+3]==[17,18,24] or L[i:i+3]==[7,18,24] or (L[i:i+4]==[4,4,4,4] and (i==0 or L[i-1]!=4))]
print(starts, starts2)
allst=sorted(set(starts+starts2))
blocks=[]
for j,s in enumerate(allst):
    e=allst[j+1] if j+1<len(allst) else len(G)
    blocks.append((G[s][0],G[e-1][1],s,e))
print(len(blocks)); json.dump(blocks,open('blocks.json','w'))
