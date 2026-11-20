"""Layered pixel-art Hydro Pump: aimed water column and turbulent impact."""
from pathlib import Path
import concurrent.futures,json,math,sys
import numpy as np
from PIL import Image,ImageDraw

ROOT=Path(__file__).resolve().parent
C=json.loads((ROOT/'hydro-controls.json').read_text())
W,H=320,205
FPS=int(C['framesPerSecond']);END=float(C['endSeconds']);COUNT=round(END*FPS)+1;COLS=8;ROWS=math.ceil(COUNT/COLS)
START=float(C['streamStartSeconds']);TRAVEL=float(C['travelSeconds']);EMIT_END=float(C['emitEndSeconds'])
CHARGE_START=float(C.get('chargeStartSeconds',.05))
HIT=START+TRAVEL;LAST_HIT=EMIT_END+TRAVEL;SHEET_LIFE=float(C['impactSheetLifetimeSeconds']);POOL_CLEAR=float(C['poolClearSeconds'])
if not (FPS>0 and 0<=CHARGE_START<START<EMIT_END and TRAVEL>0 and SHEET_LIFE>0 and LAST_HIT<POOL_CLEAR<=END):
    raise ValueError('Invalid Hydro Pump timing controls')
if not (0<float(C['streamRadiusFraction']) and 0<float(C['streamBodyOpacity'])<=1 and 0<float(C.get('foamRingSpacing',.14))<=1 and 0<float(C.get('foamRingThickness',.12)) and 0<float(C.get('sourceFoamRadiusMultiplier',1.08))):
    raise ValueError('Invalid Hydro Pump water or foam controls')
FOCAL,OFFSET,CAMERA_Y,HORIZON=122.,2.6,2.89,81.5
FAR=np.array([2.66,10.64]);NEAR=np.array([-1.40,1.03])
SPRITES=[Image.open(ROOT/'far.png').convert('RGBA'),Image.open(ROOT/'near.png').convert('RGBA')]
BODY=np.array([(22,77,118),(23,111,159),(22,140,181),(32,167,196),(59,193,211),(111,220,227)])
FOAM=np.array([(109,187,202),(172,221,227),(219,244,241),(249,255,250)])
SY,SX=np.indices((H,W),dtype=float);SCALE=np.maximum(SY-HORIZON,1)/CAMERA_Y;WX=(SX-W/2)/SCALE;WZ=FOCAL/SCALE-OFFSET

def ease(a,b,x):
    p=np.clip((x-a)/(b-a),0,1);return p*p*(3-2*p)

def project(points):
    p=np.asarray(points,dtype=float);scale=FOCAL/np.maximum(p[...,2]+OFFSET,.45)
    return np.stack((W/2+p[...,0]*scale,HORIZON+(CAMERA_Y-p[...,1])*scale),axis=-1)

def floor_project(x,z):
    k=FOCAL/np.maximum(z+OFFSET,.45);return W/2+x*k,HORIZON+CAMERA_Y*k

def layer(z):
    return 0 if z>FAR[1]+.06 else (1 if z>NEAR[1]+.06 else 2)

class HydroPump:
    def __init__(self,incoming=False):
        self.incoming=incoming;self.source,self.target=(FAR,NEAR) if incoming else (NEAR,FAR)
        self.caster=SPRITES[0 if incoming else 1];self.defender=SPRITES[1 if incoming else 0]
        ground=self.target-self.source;self.direction=ground/np.linalg.norm(ground);self.across=np.array([self.direction[1],-self.direction[0]])
        source_scale=FOCAL/(self.source[1]+OFFSET);target_scale=FOCAL/(self.target[1]+OFFSET)
        self.source_height=self.caster.height/source_scale;self.target_height=self.defender.height/target_scale
        muzzle=(-.25*self.caster.width if incoming else .42*self.caster.width)/source_scale
        self.origin=np.array([self.source[0]+muzzle,self.source_height*(.52 if incoming else .62),self.source[1]])
        self.contact=np.array([self.target[0],self.target_height*.48,self.target[1]])
        self.axis=self.contact-self.origin;self.axis/=np.linalg.norm(self.axis)
        self.side=np.array([self.axis[2],0.,-self.axis[0]]);self.side/=np.linalg.norm(self.side)
        self.up=np.cross(self.axis,self.side);self.up/=np.linalg.norm(self.up)
        if self.up[1]<0:self.up=-self.up
        self.radius0=self.source_height*float(C['streamRadiusFraction']);self.radius1=self.target_height*float(C['streamRadiusFraction'])
        self.camera=np.array([0.,CAMERA_Y,-OFFSET]);self.light=np.array([-.55,.82,-.5]);self.light/=np.linalg.norm(self.light)
        self.spray=[];rng=np.random.default_rng(8731+int(incoming))
        for born in np.arange(HIT,LAST_HIT+.025,.028):
            for _ in range(4):
                velocity=(self.side*rng.uniform(-3.3,3.3)+self.up*rng.uniform(-.7,4.2)+self.axis*rng.uniform(-1.,2.2))*self.target_height*.60
                self.spray.append((float(born),velocity,rng.uniform(.32,.62),rng.uniform(.018,.045)*self.target_height))

    def pressure(self,t):
        return float(ease(HIT,HIT+.07,t)*(1-ease(LAST_HIT,LAST_HIT+.17,t)))

    def add_face(self,faces,points,color):
        p=np.asarray(points);xy=project(p)
        if not np.isfinite(xy).all():return
        if xy[:,0].max()<-4 or xy[:,0].min()>W+4 or xy[:,1].max()<-4 or xy[:,1].min()>H+4:return
        faces.append((float(np.mean(p[:,2])),[tuple(q) for q in xy],tuple(int(np.clip(v,0,255)) for v in color)))

    def charge(self,t,faces):
        # Water gathers and churns around the muzzle, then feeds into the jet.
        if not CHARGE_START<t<START+.18:return
        build=float(ease(CHARGE_START,START-.03,t))
        release=1-float(ease(START,START+.18,t))
        strength=float(ease(CHARGE_START,CHARGE_START+.08,t))*release
        radius=self.radius0*(.16+.92*build)*(1+.035*math.sin(t*43)*build)
        center=self.origin+self.axis*self.radius0*(.04+.16*build)
        angles=np.linspace(0,2*math.pi,33);latitudes=np.linspace(-math.pi/2,math.pi/2,15)
        grid=[]
        for latitude in latitudes:
            ring=[]
            for angle in angles:
                normal=math.cos(angle)*self.side+math.sin(angle)*self.up
                lobe=1+.035*math.sin(angle*5+t*23)+.025*math.sin(latitude*7-angle*3-t*31)
                ring.append(center+radius*lobe*(normal*math.cos(latitude)+self.axis*.63*math.sin(latitude)))
            grid.append(ring)
        grid=np.asarray(grid)
        for k in range(14):
            latitude=(latitudes[k]+latitudes[k+1])*.5
            for j in range(32):
                angle=(angles[j]+angles[j+1])*.5
                normal=(math.cos(angle)*self.side+math.sin(angle)*self.up)*math.cos(latitude)+self.axis*math.sin(latitude)
                middle=np.mean(grid[[k,k,k+1,k+1],[j,j+1,j+1,j]],axis=0)
                if np.dot(normal,self.camera-middle)<0:continue
                lighting=np.dot(normal,self.light)
                color=BODY[int(np.clip(round(3.1+1.2*lighting+.3*math.sin(angle*4-latitude*3-t*18)),1,5))]
                streak=1-float(ease(.07,.25,abs(math.sin(angle*3+latitude*2-t*12))))
                white=.8*streak*build
                rgb=color*(1-white)+FOAM[2+(lighting>.2)]*white
                alpha=(float(C['streamBodyOpacity'])*(1-white)+white)*strength
                self.add_face(faces,grid[[k,k,k+1,k+1],[j,j+1,j+1,j]],(*rgb,255*alpha))
        # Rounded foam billows build around the source instead of a flat flash.
        collar_center=center-self.axis*radius*.08
        self.foam_ring(faces,collar_center,radius*.96,radius*.14,strength*(.35+.65*build),t*2)
        for j in range(12):
            angle=j*2*math.pi/12+t*1.8
            normal=math.cos(angle)*self.side+math.sin(angle)*self.up
            q=collar_center+normal*radius*(.93+.05*math.sin(t*17+j*2))
            self.foam_blob(faces,q,radius*(.12+.07*build)*(.85+.15*math.sin(j*3+t*24)**2),strength*(.3+.7*build),j+t*9)
        # Small inward-moving ribbons make the charging motion visible.
        for j in range(3):
            phase=(t*3.4+j/3)%1
            rr=radius*(1.15+.65*(1-phase))
            self.foam_ring(faces,center-self.axis*radius*.15,rr,radius*.035,strength*.55*math.sin(math.pi*phase),t+j*2)

    def stream(self,t,faces):
        hi=min(1.,(t-START)/TRAVEL);lo=max(0.,(t-EMIT_END)/TRAVEL)
        if hi<=0 or lo>=1 or hi<=lo:return
        segments=max(8,round((hi-lo)*88));s=np.linspace(lo,hi,segments+1);theta=np.linspace(0,2*math.pi,33)
        centers=self.origin[None,:]+(self.contact-self.origin)[None,:]*s[:,None]
        normals=np.cos(theta)[:,None]*self.side+np.sin(theta)[:,None]*self.up
        ripple=.95+.035*np.sin(s*57-t*43)+.026*np.sin(s*109-t*66)
        radius=((1-s)*self.radius0+s*self.radius1)*ripple
        radius*=.25+.75*ease(START,START+.065,t)
        points=centers[:,None,:]+radius[:,None,None]*normals[None,:,:]
        flow=t*float(C['flowSpeed'])
        for i in range(segments):
            a=(s[i]+s[i+1])*.5
            for j in range(32):
                angle=(theta[j]+theta[j+1])*.5;normal=(normals[j]+normals[j+1])*.5
                center=centers[i]
                if np.dot(normal,self.camera-center)<0:continue
                lighting=np.dot(normal,self.light)
                variation=.24*math.sin(a*53-flow*3+angle*2)+.15*math.sin(a*99-flow*4-angle*3)
                index=int(np.clip(round(2.9+1.4*lighting+variation),0,5));color=BODY[index].astype(float)
                # Long flowing runnels, linked by irregular white arches.
                lane=angle*5+.13*math.sin(a*10-flow*.45)+.05*math.sin(a*21-flow*.8)
                streak=1-float(ease(.10,.38,abs(math.sin(lane))))
                arch=1-float(ease(.045,.17,abs(math.sin(math.pi*(a*4-flow+.25*math.cos(angle*3))))))
                broken=.45+.55*float(ease(-.3,.7,math.sin(a*33-flow*2+angle*4)))
                white=max(.95*streak,.60*arch*broken)
                color=color*(1-white)+FOAM[2+(lighting>.2)]*white
                alpha=255*(float(C['streamBodyOpacity'])*(1-white)+white)
                self.add_face(faces,points[[i,i,i+1,i+1],[j,j+1,j+1,j]],(*color,alpha))
        # Close the camera-facing end, so the stream reads as a round
        # volume of water rather than an open ribbon at the nozzle.
        for k,sign in ((0,-1),(-1,1)):
            if np.dot(self.axis*sign,self.camera-centers[k])<=0:continue
            for j in range(32):
                bright=.5+.5*math.sin(theta[j]*4+.12*math.sin(t*18))
                color=BODY[3]*(1-bright*.5)+BODY[4]*bright*.5
                self.add_face(faces,[centers[k],points[k,j],points[k,j+1]],(*color,round(255*float(C['streamBodyOpacity']))))
        # Emitted foam collars travel at the same speed as the stream.
        spacing=float(C.get('foamRingSpacing',.14));period=spacing*TRAVEL
        first=max(0,math.ceil((t-TRAVEL-START)/period))
        last=math.floor((min(t,EMIT_END)-START)/period)
        for index in range(first,last+1):
            born=START+index*period;a=(t-born)/TRAVEL
            if not lo<=a<=hi:continue
            center=self.origin+(self.contact-self.origin)*a
            r=((1-a)*self.radius0+a*self.radius1)*(.95+.035*math.sin(a*57-t*43)+.026*math.sin(a*109-t*66))
            r*=.25+.75*float(ease(START,START+.065,t))
            self.foam_ring(faces,center,r*1.035,r*float(C.get('foamRingThickness',.12)),1.,t+index)
        # Source foam hugs the actual animated jet radius, without an air gap.
        source_strength=float(ease(START,START+.07,t)*(1-ease(EMIT_END-.06,EMIT_END,t)))
        if source_strength>0:
            jet_radius=float(radius[0])
            r=jet_radius*float(C.get('sourceFoamRadiusMultiplier',1.02))
            center=self.origin+self.axis*jet_radius*.08
            # A filled, rounded foam cap thickens inward and along the jet,
            # keeping the same fitted outer footprint instead of a hollow hoop.
            radial=np.linspace(0,1,7);cap=[]
            for u in radial:
                ring=[]
                for angle in theta:
                    normal=math.cos(angle)*self.side+math.sin(angle)*self.up
                    lobe=1+.035*math.sin(angle*5+t*17)+.025*math.sin(angle*9-t*23)
                    axial=-r*(.30*(1-u*u)+.025*math.sin(angle*3+t*19)*u)
                    ring.append(center+normal*r*.94*u*lobe+self.axis*axial)
                cap.append(ring)
            cap=np.asarray(cap)
            for k in range(6):
                u=(radial[k]+radial[k+1])*.5
                for j in range(32):
                    angle=(theta[j]+theta[j+1])*.5
                    shade=.55+.25*math.sin(angle)+.14*math.sin(angle*4+t*16+u*5)
                    color=FOAM[3 if shade>.52 else 2]
                    self.add_face(faces,cap[[k,k,k+1,k+1],[j,j+1,j+1,j]],(*color,round(255*source_strength)))
            self.foam_ring(faces,center,r*.86,r*.24,source_strength,t*2)
            # Dense overlapping billows cover the center as well as the rim.
            for j in range(12):
                angle=j*2*math.pi/12
                normal=math.cos(angle)*self.side+math.sin(angle)*self.up
                p=center+normal*r*(.78+.025*math.sin(j*3-t*25))-self.axis*r*.06
                self.foam_blob(faces,p,r*(.235+.025*math.sin(j*2+t*20)**2),source_strength,j+t*12)
            for j in range(5):
                angle=j*2*math.pi/5+t*.7
                normal=math.cos(angle)*self.side+math.sin(angle)*self.up
                p=center+normal*r*.31-self.axis*r*.31
                self.foam_blob(faces,p,r*(.27+.025*math.sin(j+t*15)**2),source_strength,j+t*10)
        # Frothy advancing nose, with an open cyan center rather than a flash.
        front=centers[-1];r=radius[-1]
        if hi<1.:
            for j in range(32):
                a=theta[j];b=theta[j+1];r0=r*(1.02+.05*math.sin(j*2.3-t*28))
                n0=math.cos(a)*self.side+math.sin(a)*self.up;n1=math.cos(b)*self.side+math.sin(b)*self.up
                self.add_face(faces,[front+n0*r*.71,front+n0*r0,front+n1*r0,front+n1*r*.71],(*FOAM[3],250))

    def foam_ring(self,faces,center,radius,thickness,strength,phase):
        angles=np.linspace(0,2*math.pi,25);cross=np.linspace(0,2*math.pi,7)
        grid=[]
        for angle in angles:
            normal=math.cos(angle)*self.side+math.sin(angle)*self.up
            r=radius*(1+.075*math.sin(angle*3-phase*7)+.035*math.sin(angle*7+phase*5))
            local_thickness=thickness*(.75+.24*math.sin(angle*5+phase*3)+.12*math.sin(angle*9-phase*4))
            grid.append([center+normal*(r+local_thickness*math.cos(phi))+self.axis*local_thickness*math.sin(phi) for phi in cross])
        grid=np.asarray(grid)
        for j in range(24):
            if math.sin((angles[j]+angles[j+1])*.5*4+phase*2)<-.88:continue
            normal=math.cos((angles[j]+angles[j+1])*.5)*self.side+math.sin((angles[j]+angles[j+1])*.5)*self.up
            for k in range(6):
                phi=(cross[k]+cross[k+1])*.5
                surface=normal*math.cos(phi)+self.axis*math.sin(phi)
                middle=np.mean(grid[[j,j,j+1,j+1],[k,k+1,k+1,k]],axis=0)
                if np.dot(surface,self.camera-middle)<0:continue
                light=np.dot(surface,self.light)
                color=FOAM[int(np.digitize(light,[-.25,.10,.42]))]
                self.add_face(faces,grid[[j,j,j+1,j+1],[k,k+1,k+1,k]],(*color,round(255*strength)))

    def foam_blob(self,faces,center,radius,strength,phase):
        x,y=project(center);r=radius*FOCAL/max(.45,center[2]+OFFSET)
        if r<.45:return
        for scale,dy,color in ((1.,0.,FOAM[0]),(.92,-.10,FOAM[2]),(.72,-.24,FOAM[3])):
            a=np.linspace(0,2*math.pi,19)
            lobe=1+.07*np.sin(a*5+phase)+.04*np.sin(a*9-phase)
            xy=list(zip(x+r*scale*np.cos(a)*lobe,y+r*scale*np.sin(a)*lobe+r*dy))
            faces.append((float(center[2])-radius*.25,xy,(*map(int,color),int(255*strength))))

    def impact(self,t,faces):
        radius=self.target_height*float(C['impactRadiusFraction'])
        for born in np.arange(HIT,min(t,LAST_HIT)+1e-7,.095):
            age=t-float(born)
            if not 0<age<SHEET_LIFE:continue
            life=age/SHEET_LIFE;spread=1-math.exp(-age/.105)
            fade=float(1-ease(.62,1.,life));strength=float(ease(0,.035,age))*fade
            angles=np.linspace(0,2*math.pi,33);rows=np.linspace(0,1,9);grid=[]
            for u in rows:
                ring=[]
                for angle in angles:
                    normal=math.cos(angle)*self.side+math.sin(angle)*self.up
                    lobe=.90+.08*math.sin(angle*5+born*15)+.05*math.sin(angle*9-born*11)
                    r=radius*(.12+spread*u*lobe)
                    center=self.contact+normal*r+self.axis*(.08+.22*math.sin(u*math.pi/2))*self.target_height
                    center[1]-=(1.25*age*age+.12*u*u*life)*self.target_height
                    center[1]=max(.025,center[1]);ring.append(center)
                grid.append(ring)
            grid=np.asarray(grid)
            for k in range(8):
                u=(k+.5)/8;white=float(ease(.35,.80,u))
                for j in range(32):
                    color=BODY[3]*(1-white)+FOAM[2+(k>=6)]*white
                    self.add_face(faces,grid[[k,k,k+1,k+1],[j,j+1,j+1,j]],(*color,(.72+.28*white)*255*strength))
            for j in range(0,32,3):
                center=grid[-1,j]
                blob_radius=radius*(.11+.035*math.sin(j*2.7+born*17)**2)*(.65+.35*spread)
                self.foam_blob(faces,center,blob_radius,strength,j+born*13)

    def pool(self,t):
        result=np.zeros((H,W,4),np.uint8);age=t-HIT
        if age<=0 or t>=POOL_CLEAR:return Image.fromarray(result,'RGBA')
        buildup=1-math.exp(-age/.27);fade=1-ease(LAST_HIT+.05,POOL_CLEAR,t)
        radius=self.target_height*(.20+.43*buildup)
        center=self.target+self.direction*self.target_height*.22*buildup
        x=((WX-center[0])*self.across[0]+(WZ-center[1])*self.across[1])/radius
        z=((WX-center[0])*self.direction[0]+(WZ-center[1])*self.direction[1])/(radius*.72)
        angle=np.arctan2(z,x);dist=np.hypot(x,z);edge=dist-1-.035*np.sin(7*angle-t*4)-.02*np.sin(13*angle+t*6)
        active=(SY>HORIZON+3)&(edge<.035)
        if not active.any():return Image.fromarray(result,'RGBA')
        a=edge[active];xx=x[active];zz=z[active]
        light=.5+.25*np.sin(xx*5+zz*3-t*7)+.16*np.cos(zz*8-t*8)
        color=BODY[np.clip(np.rint(2.5+light),1,4).astype(int)].astype(float)
        rim=1-ease(.015,.085,abs(a+.025))
        cell=abs(np.cos(xx*7+.35*np.sin(zz*6-t*3))+.8*np.cos(zz*8+.3*np.sin(xx*5+t*2)))
        web=(1-ease(.06,.24,cell))*(1-ease(.08,.45,-a))
        foam=np.maximum(rim,.88*web)
        alpha=(.63*(1-foam)+foam)*float(fade)*float(ease(0,.1,age))
        rgb=color*(1-foam[:,None])+FOAM[3]*foam[:,None]
        result[:,:,:3][active]=np.rint(rgb).astype(np.uint8);result[:,:,3][active]=np.rint(255*alpha).astype(np.uint8)
        return Image.fromarray(result,'RGBA')

    def droplets(self,t,layers):
        draws=[ImageDraw.Draw(im,'RGBA') for im in layers]
        for born,velocity,life,radius in self.spray:
            age=t-born
            if not 0<age<life:continue
            p=self.contact+velocity*age+np.array([0.,-4.8*age*age,0.])
            if p[1]<.03:continue
            x,y=project(p);scale=FOCAL/max(.45,p[2]+OFFSET);r=max(.6,min(2.,radius*scale))
            alpha=int(255*(1-ease(.60*life,life,age)))
            draw=draws[layer(p[2])];draw.ellipse((x-r,y-r*.6,x+r,y+r*.6+1),fill=(*FOAM[0],alpha))
            draw.rectangle((round(x-r*.4),round(y-r*.6),round(x+r*.4),round(y)),fill=(*FOAM[3],alpha))

    def effect(self,t):
        layers=[self.pool(t),Image.new('RGBA',(W,H)),Image.new('RGBA',(W,H))]
        faces=[];self.charge(t,faces);self.stream(t,faces);self.impact(t,faces)
        draws=[ImageDraw.Draw(im,'RGBA') for im in layers]
        for z,xy,color in sorted(faces,key=lambda f:f[0],reverse=True):draws[layer(z)].polygon(xy,fill=color)
        self.droplets(t,layers)
        return layers

    def preview(self,t,layers,bg):
        out=bg.copy()
        for i,(position,sprite) in enumerate(zip((FAR,NEAR),SPRITES)):
            out.alpha_composite(layers[i].resize((640,410),Image.Resampling.NEAREST))
            px,py=floor_project(*position);px,py=round(px),round(py)
            shadow=Image.new('RGBA',(W,H));ImageDraw.Draw(shadow).ellipse((px-sprite.width*.34,py-2,px+sprite.width*.34,py+3),fill=(41,28,47,95))
            out.alpha_composite(shadow.resize((640,410),Image.Resampling.NEAREST))
            target=np.array_equal(position,self.target);hit=max(0,t-HIT)
            shake=round(1.5*math.sin(hit*90)*self.pressure(t)) if target else 0
            out.alpha_composite(sprite.resize((sprite.width*2,sprite.height*2),Image.Resampling.NEAREST),(2*(px-sprite.width//2+shake),2*(py-sprite.height)))
        out.alpha_composite(layers[2].resize((640,410),Image.Resampling.NEAREST))
        return out.convert('RGB')

def render(incoming,pilot=False):
    name='incoming' if incoming else 'outgoing';pump=HydroPump(incoming)
    folder=ROOT/name;folder.mkdir(exist_ok=True);bg=Image.open(ROOT/'arena.png').convert('RGBA')
    frames=(4,8,11,16,23,30,37,44,48) if pilot else range(COUNT)
    atlases=[Image.new('RGBA',(W*COLS,H*ROWS)) for _ in range(3)]
    for i in frames:
        t=i/FPS;layers=pump.effect(t);pump.preview(t,layers,bg).save(folder/f'{i:03d}.png')
        for atlas,im in zip(atlases,layers):atlas.paste(im,(i%COLS*W,i//COLS*H))
    if not pilot:
        assets=ROOT/'assets';assets.mkdir(exist_ok=True)
        for atlas,scope in zip(atlases,('behind','between','front')):atlas.save(assets/f'hydro-pump-{name}-{scope}.png',optimize=True)
    return name

if __name__=='__main__':
    pilot='--pilot' in sys.argv
    with concurrent.futures.ProcessPoolExecutor(max_workers=2) as ex:
        futures=[ex.submit(render,inc,pilot) for inc in (False,True)]
        for f in futures:print('Rendered '+f.result(),flush=True)
    if not pilot:
        timing={'spriteFrame':{'width':W,'height':H},'previewStage':{'width':640,'height':410},'displayScale':2,'sampling':'nearest','framesPerSecond':FPS,'frameDurationMs':round(1000/FPS),'frameCount':COUNT,'durationMs':round(1000*COUNT/FPS),'loop':False,'atlas':{'columns':COLS,'rows':ROWS,'order':'row-major'},'anchor':{'x':0,'y':0},'beatsMs':{'chargeStarts':round(1000*CHARGE_START),'streamStarts':round(1000*START),'targetImpact':round(1000*HIT),'emissionEnds':round(1000*EMIT_END),'lastWaterHits':round(1000*LAST_HIT),'groundWaterClears':round(1000*POOL_CLEAR)},'compositingOrder':['stage','behind','far battler','between','near battler','front']}
        for key,name in (('playerAttack','outgoing'),('opponentAttack','incoming')):timing[key]={scope:f'hydro-pump-{name}-{scope}.png' for scope in ('behind','between','front')}
        (ROOT/'assets/hydro-pump-timing.json').write_text(json.dumps(timing,indent=2)+'\n')
