"""Concept illustration only: all numerical heights are explicitly synthetic."""
from pathlib import Path
import os, json
ROOT = Path(__file__).resolve().parent
os.environ['MPLCONFIGDIR'] = str(ROOT / 'build/mpl_cache')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import numpy as np

plt.rcParams.update({'font.sans-serif':['Microsoft YaHei'], 'axes.unicode_minus':False,
                     'font.size':17, 'text.color':'#243446', 'axes.labelcolor':'#243446'})
x = np.linspace(0,28,113)
y = np.linspace(0,3,65)
X,Y = np.meshgrid(x,y)
def surface(x,y):
    return (.08 + .92*np.exp(-((x-7)/3.0)**2-((y-.55)/.4)**2)
            + .7*np.exp(-((x-13)/3.6)**2-((y-1.5)/.42)**2)
            + 1.16*np.exp(-((x-18)/3.1)**2-((y-2.43)/.36)**2)
            + .64*np.exp(-((x-25)/3.4)**2-((y-2.18)/.5)**2))
Z=surface(X,Y)
fig=plt.figure(figsize=(11.2,7.2),facecolor='#FAFAFA')
ax=fig.add_axes([.005,.03,.99,.91],projection='3d',facecolor='#FAFAFA')
blue=LinearSegmentedColormap.from_list('history',['#E3EDF5','#8EB5D4','#4472C4','#0D3745'])
gold=LinearSegmentedColormap.from_list('future',['#F8EAD2','#E6BB77','#B67B2C'])
ax.plot_surface(X,Y,np.where(X<=21,Z,np.nan),cmap=blue,vmin=0,vmax=1.25,
                linewidth=.14,edgecolor='#EDF3F7',antialiased=True,alpha=.96,rcount=65,ccount=90)
ax.plot_surface(X,Y,np.where(X>=21,Z,np.nan),cmap=gold,vmin=0,vmax=1.05,
                linewidth=.15,edgecolor='#F5E4C6',antialiased=True,alpha=.9,rcount=65,ccount=45)
ax.contour(X,Y,Z,zdir='z',offset=-.22,levels=[.18,.3,.45,.6,.8,1.0],
           colors=['#B4C9DD','#96B5D2','#789EC3','#5C86B3','#4472C4','#0D3745'],linewidths=1.1)
ax.plot([21,21],[0,3],[-.215,-.215],color='#B67B2C',linestyle='--',linewidth=2)
px=np.array([7,13,18]);py=np.array([.55,1.5,2.43]);pz=surface(px,py)+.05
ax.plot(px,py,pz,color='#243446',linestyle='--',linewidth=2.6,marker='o',markersize=6)
for i in range(3):
    ax.text(px[i],py[i],pz[i]+.075,chr(65+i),fontsize=19,fontweight='bold',color='#0D3745')
ax.view_init(elev=28,azim=-64)
ax.set_box_aspect((2.45,1.15,.88))
ax.set_xlim(0,28);ax.set_ylim(0,3);ax.set_zlim(-.22,1.42)
ax.set_xticks([0,7,14,21,28]);ax.set_yticks([.55,1.5,2.43]);ax.set_yticklabels(['议题1','议题2','议题3'])
ax.set_zticks([0,.5,1.0]);ax.tick_params(labelsize=14,pad=0)
ax.set_xlabel('相对时间 / 日',labelpad=10,fontsize=18)
ax.set_zlabel('归一化热度',labelpad=7,fontsize=16)
for axis in (ax.xaxis,ax.yaxis,ax.zaxis):
    axis.pane.fill=False
    axis.pane.set_edgecolor('#E2E7ED')
    axis._axinfo['grid'].update({'color':'#DDE3EB','linewidth':.55})
fig.text(.06,.94,'观测区域示意',color='#4472C4',fontsize=20,fontweight='bold')
fig.text(.70,.94,'预测区域示意',color='#B67B2C',fontsize=20,fontweight='bold')
fig.text(.14,.035,'虚线 A—B—C：待核验的关系示意；议题轴仅作类别排布',fontsize=15,color='#64748B')
(ROOT/'images').mkdir(exist_ok=True)
fig.savefig(ROOT/'images/terrain_concept.png',dpi=210,facecolor=fig.get_facecolor())
plt.close(fig)
(ROOT/'evidence/terrain_concept.json').write_text(json.dumps({
    'type':'synthetic_design_illustration','implemented_in_frontend':False,
    'event_data':False,'axes':['relative_day','topic_category_layout','synthetic_normalized_heat'],
    'history_forecast_boundary_day':21,'relation':'hypothetical_unverified_links',
    'purpose':'Explain planned trace, forecast, contour and evidence-navigation integration',
    'source_script':'plot_terrain.py'},ensure_ascii=False,indent=2),encoding='utf-8')
print('Saved synthetic terrain design illustration; not an implemented UI or event result.')
