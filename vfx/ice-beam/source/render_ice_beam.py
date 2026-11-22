"""Pixel-art Ice Beam: gathering frost, white/cyan beam, growing ice, shatter."""
from pathlib import Path
import concurrent.futures,json,math,sys
import numpy as np
from PIL import Image,ImageDraw,ImageFilter

ROOT=Path(__file__).resolve().parent
C=json.loads((ROOT/'ice-beam-controls.json').read_text())
W,H=320,205
FPS=int(C['framesPerSecond']);END=float(C['endSeconds']);COUNT=round(END*FPS)+1;COLS=8;ROWS=math.ceil(COUNT/COLS)
CHARGE=float(C['chargeStartSeconds']);START=float(C['beamStartSeconds']);TRAVEL=float(C['travelSeconds']);EMIT_END=float(C['emitEndSeconds'])
HIT=START+TRAVEL;LAST_HIT=EMIT_END+TRAVEL;GROW=float(C['iceGrowthSeconds']);HOLD=float(C['iceHoldSeconds'])
BREAK=float(C['shatterSeconds']);SHARD_LIFE=float(C['shardLifetimeSeconds'])
if not (FPS>0 and 0<=CHARGE<START<EMIT_END and TRAVEL>0 and GROW>0 and HOLD>=0 and LAST_HIT<BREAK and BREAK+SHARD_LIFE<END and 1<=int(C.get('crystalClusterCount',3))<=6 and 3<=int(C.get('crystalsPerCluster',7))<=12):raise ValueError('Invalid Ice Beam controls')
FOCAL,OFFSET,CAMERA_Y,HORIZON=122.,2.6,2.89,81.5
FAR=np.array([2.66,10.64]);NEAR=np.array([-1.40,1.03])
SPRITES=[Image.open(ROOT/'far.png').convert('RGBA'),Image.open(ROOT/'near.png').convert('RGBA')]
ICE=np.array([(55,113,170),(78,160,203),(119,207,229),(173,234,247),(218,250,255),(250,255,255)])

def ease(a,b,x):
    q=np.clip((x-a)/(b-a),0,1);return q*q*(3-2*q)

def project(p):
    p=np.asarray(p,dtype=float);k=FOCAL/np.maximum(p[...,2]+OFFSET,.45)
    return np.stack((W/2+p[...,0]*k,HORIZON+(CAMERA_Y-p[...,1])*k),axis=-1)

def floor_project(x,z):return project(np.array([x,0.,z]))

def layer(z):return 0 if z>FAR[1]+.06 else (1 if z>NEAR[1]+.06 else 2)

class IceBeam:
    def __init__(self,incoming=False):
        self.incoming=incoming;self.source,self.target=(FAR,NEAR) if incoming else (NEAR,FAR)
        self.caster=SPRITES[0 if incoming else 1];self.defender=SPRITES[1 if incoming else 0]
        self.source_height=self.caster.height*(self.source[1]+OFFSET)/FOCAL
        self.target_height=self.defender.height*(self.target[1]+OFFSET)/FOCAL
        muzzle=(-.25*self.caster.width if incoming else .42*self.caster.width)*(self.source[1]+OFFSET)/FOCAL
        self.origin=np.array([self.source[0]+muzzle,self.source_height*(.52 if incoming else .62),self.source[1]])
        self.contact=np.array([self.target[0],self.target_height*.48,self.target[1]])
        self.axis=self.contact-self.origin;self.axis/=np.linalg.norm(self.axis)
        self.side=np.array([self.axis[2],0.,-self.axis[0]]);self.side/=np.linalg.norm(self.side)
        self.up=np.cross(self.axis,self.side)
        if self.up[1]<0:self.up=-self.up
        self.camera=np.array([0.,CAMERA_Y,-OFFSET]);self.light=np.array([-.5,.8,-.6]);self.light/=np.linalg.norm(self.light)
        self.radius0=self.source_height*float(C['beamRadiusFraction']);self.radius1=self.target_height*float(C['beamRadiusFraction'])
        rng=np.random.default_rng(2511+int(incoming));self.crystals=[];self.shards=[];self.motes=[]
        self.clusters=[]
        # Each attached patch is one dense crystalline mass, with overlapping
        # roots and a shared faceted base rather than separate icicles.
        anchors=[(-.16,.56,-.07),(.17,.37,-.085),(-.015,.12,-.12),(.10,.73,-.09)]
        count=int(C.get('crystalClusterCount',3));per_cluster=int(C.get('crystalsPerCluster',7))
        for g in range(count):
            ax,ay,az=anchors[g%len(anchors)]
            base=np.array([self.target[0]+ax*self.target_height,ay*self.target_height,self.target[1]+az*self.target_height])
            born=HIT+.04+(g%4)*.055
            break_at=max(BREAK,born+.044+GROW+HOLD)+(g%3)*.035
            main=np.array([(-.28 if g==0 else .28 if g==1 else 0),.96,-.22]);main/=np.linalg.norm(main)
            self.clusters.append((base,main,born,break_at,g))
            for k in range(per_cluster):
                a=k*2*math.pi/max(1,per_cluster-1)+g*.65
                if k==0:
                    root=base;direction=main;length=self.target_height*.37;radius=self.target_height*.052
                else:
                    # Wide fans of unequal points stay visibly joined at the root.
                    root=base+np.array([math.cos(a)*.036,.012,math.sin(a)*.025])*self.target_height
                    direction=main+np.array([math.cos(a)*.85,.12*math.sin(a),math.sin(a)*.48])
                    direction/=np.linalg.norm(direction)
                    length=self.target_height*rng.uniform(.19,.32);radius=self.target_height*rng.uniform(.038,.058)
                length*=float(C.get('crystalSizeMultiplier',1.12));radius*=float(C.get('crystalSizeMultiplier',1.12))
                child_born=born+(k%3)*.022;j=g*per_cluster+k
                self.crystals.append((root,direction,length,radius,child_born,break_at,j))
                for part in range(3):
                    pos=root+direction*length*(.22+part*.25)
                    velocity=np.array([rng.uniform(-1.7,1.7),rng.uniform(1.4,3.4),rng.uniform(-1.4,1.1)])*self.target_height*.55
                    self.shards.append((break_at,pos,velocity,radius*rng.uniform(.65,1.15),rng.uniform(.52,SHARD_LIFE-.08),rng.uniform(0,6.28),j*3+part))
        for born in np.arange(HIT,LAST_HIT+.05,.045):
            for k in range(3):
                vel=(self.side*rng.uniform(-1.7,1.7)+self.up*rng.uniform(-.2,2.3)+self.axis*rng.uniform(-1.,.8))*self.target_height*.45
                self.motes.append((float(born),vel,rng.uniform(.18,.40),rng.uniform(.008,.025)*self.target_height))

    def face(self,faces,points,color):
        p=np.asarray(points);xy=project(p)
        if not np.isfinite(xy).all() or xy[:,0].max()<-5 or xy[:,0].min()>W+5 or xy[:,1].max()<-5 or xy[:,1].min()>H+5:return
        faces.append((float(np.mean(p[:,2])),[tuple(q) for q in xy],tuple(int(np.clip(v,0,255)) for v in color)))

    def prism(self,faces,base,axis,length,radius,alpha=1.,phase=0.,shoulder_fraction=.55):
        if length<=0 or alpha<=0:return
        axis=np.asarray(axis);axis=axis/np.linalg.norm(axis)
        u=np.cross(axis,np.array([0.,0.,1.]))
        if np.linalg.norm(u)<.01:u=np.cross(axis,np.array([1.,0.,0.]))
        u/=np.linalg.norm(u);v=np.cross(axis,u)
        angles=np.linspace(0,2*math.pi,7)+phase
        ring=np.array([base+(math.cos(a)*u+math.sin(a)*v)*radius for a in angles])
        shoulder=ring+axis*length*shoulder_fraction;tip=base+axis*length
        for j in range(6):
            normal=math.cos((angles[j]+angles[j+1])*.5)*u+math.sin((angles[j]+angles[j+1])*.5)*v
            shade=float(np.dot(normal,self.light));idx=int(np.digitize(shade,[-.45,-.1,.22,.6]))
            self.face(faces,[ring[j],ring[j+1],shoulder[j+1],shoulder[j]],(*ICE[idx],round(215*alpha)))
            self.face(faces,[shoulder[j],shoulder[j+1],tip],(*ICE[min(5,idx+1)],round(245*alpha)))
        self.face(faces,[tip,shoulder[0],shoulder[1]],(*ICE[5],round(255*alpha)))

    def beam(self,t,faces,glows):
        hi=min(1.,(t-START)/TRAVEL);lo=max(0.,(t-EMIT_END)/TRAVEL)
        if hi<=0 or lo>=1 or hi<=lo:return
        s=np.linspace(lo,hi,65);theta=np.linspace(0,2*math.pi,13)
        strength=float(ease(START,START+.045,t))
        centers=self.origin[None,:]+(self.contact-self.origin)[None,:]*s[:,None]
        radii=((1-s)*self.radius0+s*self.radius1)*(.92+.055*np.sin(s*65-t*32))*(.5+.5*strength)
        normals=np.cos(theta)[:,None]*self.side+np.sin(theta)[:,None]*self.up
        for shell,opacity in ((2.6,.09),(1.75,.19),(1.0,.85),(.53,1.)):
            points=centers[:,None,:]+shell*radii[:,None,None]*normals[None,:,:]
            for i in range(64):
                for j in range(12):
                    normal=(normals[j]+normals[j+1])*.5
                    if np.dot(normal,self.camera-centers[i])<0:continue
                    if shell<=.53:color=ICE[5]
                    elif shell<=1:color=ICE[3+(math.sin(s[i]*60-t*48+j*.35)>.1)]
                    else:color=ICE[2 if shell>2 else 3]
                    # Traveling brightness bands make the beam itself shimmer.
                    shine=(.5+.5*math.sin(s[i]*43-t*float(C.get('beamShimmerSpeed',21.))+j*.65))**3
                    depth=float(C.get('beamShimmerStrength',.85))
                    if shell<=.53:
                        glint=ICE[3]*(1-shine)+ICE[5]*shine
                        color=np.asarray(color)*(1-depth)+glint*depth
                    elif shell<=1.:
                        glint=ICE[2]*(.75-.65*shine)+ICE[5]*(.25+.65*shine)
                        color=np.asarray(color)*(1-depth)+glint*depth
                    self.face(faces,points[[i,i,i+1,i+1],[j,j+1,j+1,j]],(*color,255*opacity*strength))
        # Bright fine filaments ride the pale beam; no water rings.
        for k in range(3):
            phase=s*34-t*24+k*2.1
            p=centers+(np.cos(phase)[:,None]*self.side+np.sin(phase)[:,None]*self.up)*radii[:,None]*.75
            for i in range(64):
                normal=self.up*radii[i]*.08
                self.face(faces,[p[i]-normal,p[i]+normal,p[i+1]+normal,p[i+1]-normal],(*ICE[5],round(130+125*(.5+.5*math.sin(s[i]*53-t*27+k*2)))))
        if t<EMIT_END:
            self.star(glows,self.origin,self.radius0*1.7,.7*strength,t)

    def star(self,layers,pos,radius,strength,phase):
        if strength<=0:return
        x,y=project(pos);r=float(max(1.,radius*FOCAL/max(.45,pos[2]+OFFSET)));target=layers[layer(pos[2])]
        glow=Image.new('RGBA',(W,H));d=ImageDraw.Draw(glow)
        d.ellipse((x-r*2,y-r*2,x+r*2,y+r*2),fill=(*ICE[2],int(65*strength)))
        target.alpha_composite(glow.filter(ImageFilter.GaussianBlur(max(.5,r*.45))))
        d=ImageDraw.Draw(target)
        d.polygon([(x-r,y),(x-r*.25,y-r*.25),(x,y-r*1.35),(x+r*.25,y-r*.25),(x+r,y),(x+r*.25,y+r*.25),(x,y+r*1.35),(x-r*.25,y+r*.25)],fill=(*ICE[4],int(220*strength)))
        rr=r*(.30+.025*math.sin(phase*40));d.ellipse((x-rr,y-rr,x+rr,y+rr),fill=(*ICE[5],int(255*strength)))

    def gathering_rings(self,t,faces,layers):
        if not CHARGE<t<START+.09:return
        fade=1-float(ease(START,START+.09,t));height=self.source_height
        count=int(C.get('chargeRingCount',4));angles=np.linspace(0,2*math.pi,65)
        for j in range(count):
            born=CHARGE+j*.075;age=t-born;life=.26
            if not 0<age<life:continue
            p=age/life;gather=float(ease(0,1,p))
            r=height*float(C.get('chargeRingRadiusFraction',.62))*(1-gather)+self.radius0*.45
            center=self.origin-self.axis*height*.09*(1-gather)
            strength=float(ease(0,.025,age)*(1-ease(.20,life,age)))*fade
            outer_opacity=float(C.get('chargeRingOuterOpacity',.22))
            strength*=outer_opacity+(1-outer_opacity)*float(ease(.05,.90,gather))
            # Real ground/camera perspective: rings lie across the firing axis.
            for extent,alpha,color in ((.025,.28,ICE[2]),(.013,.90,ICE[4]),(.005,1.,ICE[5])):
                thickness=height*extent*(.65+.35*gather)
                for k in range(64):
                    a,b=angles[k],angles[k+1]
                    n0=math.cos(a)*self.side+math.sin(a)*self.up
                    n1=math.cos(b)*self.side+math.sin(b)*self.up
                    r0=r*(1+.015*math.sin(a*6+t*18+j));r1=r*(1+.015*math.sin(b*6+t*18+j))
                    self.face(faces,[center+n0*(r0-thickness),center+n0*(r0+thickness),center+n1*(r1+thickness),center+n1*(r1-thickness)],(*color,round(255*alpha*strength)))
            for k in range(5):
                angle=k*2*math.pi/5+j*.6+t*2.5;normal=math.cos(angle)*self.side+math.sin(angle)*self.up
                self.prism(faces,center+normal*r,-normal,height*.045,height*.008,strength,angle)

    def exaggerated_impact(self,t,faces,layers):
        if t<=HIT or t>LAST_HIT+.44:return
        height=self.target_height;age=t-HIT
        center=self.contact+np.array([0.,0.,-.085*height])
        pressure=float(ease(HIT,HIT+.035,t)*(1-ease(LAST_HIT,LAST_HIT+.16,t)))
        self.star(layers,center,height*.19,pressure*(.65+.25*math.sin(t*33)**2),t)
        # A large, very fast star-shaped icy blast marks the first strike.
        if age<.23:
            strength=float(ease(0,.018,age)*(1-ease(.075,.23,age)))
            self.star(layers,center,height*.31,strength,t)
            reach=height*float(C.get('impactBurstRadiusFraction',.72))*float(ease(0,.085,age))
            for j in range(18):
                a=j*2*math.pi/18+.12
                normal=math.cos(a)*self.side+math.sin(a)*self.up
                tangent=-math.sin(a)*self.side+math.cos(a)*self.up
                length=reach*(.66+.34*math.sin(j*2.1)**2)
                root=center+normal*height*.055;tip=center+normal*length-self.axis*height*.08
                width=height*(.018+.022*math.sin(j*3.2)**2)
                self.face(faces,[root-tangent*width,tip,root+tangent*width],(*ICE[3],round(180*strength)))
                self.face(faces,[root-tangent*width*.35,tip*.90+root*.10,root+tangent*width*.35],(*ICE[5],round(255*strength)))
        # Repeated pale frost blooms keep the beam pounding into the target.
        for born in np.arange(HIT,min(t,LAST_HIT)+1e-7,.12):
            elapsed=t-float(born);life=.36
            if not 0<elapsed<life:continue
            progress=elapsed/life;fade=float(ease(0,.025,elapsed)*(1-ease(.09,life,elapsed)))
            for j in range(5):
                a=j*2*math.pi/5+float(born)*8
                normal=math.cos(a)*self.side+math.sin(a)*self.up
                drift=height*(.07+.30*progress)
                p=center+normal*drift-self.axis*height*elapsed*.5
                x,y=project(p);scale=FOCAL/max(.45,p[2]+OFFSET)
                radius=float(height*(.055+.12*progress)*scale*float(C.get('impactFrostPlumeMultiplier',1.)))
                cloud=Image.new('RGBA',(W,H));draw=ImageDraw.Draw(cloud);theta=np.linspace(0,2*math.pi,23)
                for mult,color,opacity in ((1.35,(130,218,242),.13),(.95,(211,246,255),.23),(.55,(248,255,255),.22)):
                    lobes=1+.16*np.sin(theta*3+j+born*7)+.09*np.sin(theta*7-j)
                    xy=list(zip(x+np.cos(theta)*radius*mult*lobes,y+np.sin(theta)*radius*.75*mult*lobes))
                    puff=Image.new('RGBA',(W,H));ImageDraw.Draw(puff).polygon(xy,fill=(*color,round(255*fade*opacity)));cloud.alpha_composite(puff)
                layers[layer(p[2])].alpha_composite(cloud.filter(ImageFilter.GaussianBlur(.45)))
        # Larger pointed ice chips eject forcefully; fine white shimmer stays fine.
        for born in np.arange(HIT,min(t,LAST_HIT)+1e-7,.105):
            elapsed=t-float(born);life=.39
            if not 0<elapsed<life:continue
            strength=1-float(ease(.18,life,elapsed))
            for j in range(5):
                phase=j*2.399+float(born)*19
                velocity=(-self.axis*(.65+.3*math.sin(phase)**2)+self.side*math.sin(phase)*2.7+self.up*(.6+2.5*math.cos(phase*1.3)))*height
                p=center+velocity*elapsed+np.array([0.,-3.1*height*elapsed*elapsed,0.])
                if p[1]<.025:continue
                spin=np.array([math.sin(phase+elapsed*14),math.cos(phase+elapsed*14),.3])
                size=height*(.035+.032*math.sin(phase*2)**2)
                self.prism(faces,p,spin,size,size*.18,strength,phase)

    def charge(self,t,faces,glows):
        if not CHARGE<t<START+.09:return
        build=float(ease(CHARGE,START,t));fade=1-float(ease(START,START+.09,t))
        onset=float(ease(CHARGE,CHARGE+.055,t));height=self.source_height
        strength=onset*fade
        gather=height*float(C.get('chargeGatherRadiusFraction',.64))
        self.gathering_rings(t,faces,glows)
        # Pale frost clouds spiral inward rather than exploding away from the source.
        for j in range(14):
            stagger=(j%4)*.018
            progress=float(ease(CHARGE+stagger,START+.025,t))
            angle=j*2*math.pi/14+progress*1.4
            normal=math.cos(angle)*self.side+math.sin(angle)*self.up
            radius=gather*(.78+.22*math.sin(j*2.3)**2)*(1-progress)**.85+self.radius0*.8
            center=self.origin+normal*radius+self.axis*height*.055*math.sin(angle*2)
            x,y=project(center);scale=FOCAL/max(.45,center[2]+OFFSET)
            size=float(height*(.065+.055*build)*scale)
            alpha=float(C.get('chargeFogOpacity',.56))*strength*(.40+.60*build)
            mist=Image.new('RGBA',(W,H));draw=ImageDraw.Draw(mist)
            angles=np.linspace(0,2*math.pi,23)
            for mult,opacity,color in ((1.45,.25,(126,209,237)),(1.,.65,(189,235,250)),(.58,.8,(230,250,255))):
                lobes=1+.14*np.sin(angles*3+j+t*15)+.07*np.sin(angles*7-j)
                # The curved tangential shape stretches around the gathering core.
                tangent=angle+.7
                dx=np.cos(angles)*size*1.6*mult*lobes;dy=np.sin(angles)*size*.65*mult*lobes
                xy=list(zip(x+dx*math.cos(tangent)-dy*math.sin(tangent),y+dx*math.sin(tangent)+dy*math.cos(tangent)))
                cloud=Image.new('RGBA',(W,H));ImageDraw.Draw(cloud).polygon(xy,fill=(*color,round(255*alpha*opacity)))
                mist.alpha_composite(cloud)
            glows[layer(center[2])].alpha_composite(mist.filter(ImageFilter.GaussianBlur(.45)))
        # Staggered ice flecks accelerate along curved paths into the same source.
        count=int(C.get('chargeParticleCount',30))
        for j in range(count):
            born=CHARGE+(j%6)*.022
            if t<=born:continue
            progress=float(ease(born,START+.025,t))
            angle=j*2.399963+progress*(1.2+.3*math.sin(j))
            normal=math.cos(angle)*self.side+math.sin(angle)*self.up
            distance=gather*(.65+.35*math.sin(j*1.71)**2)*(1-progress)**.75+self.radius0*.40
            p=self.origin+normal*distance+self.axis*height*.06*math.sin(j+progress*3)
            particle_strength=fade*float(ease(born,born+.035,t))
            length=height*(.025+.018*math.sin(j*2.9)**2)
            self.prism(faces,p,-normal,length,length*.18,particle_strength,angle)
            # A short icy streak shows the convergence without a persistent ring.
            trail=normal*height*(.012+.035*build)
            self.face(faces,[p,p+trail+self.up*height*.002,p+trail-self.up*height*.002],(*ICE[3],round(150*particle_strength)))
            if j%5==0:self.star(glows,p,height*.018,particle_strength*.75,t+j)
        core_multiplier=float(C.get('chargeCoreMultiplier',1.5))
        self.star(glows,self.origin,self.radius0*(.65+2.25*build)*core_multiplier,fade*(.3+.7*build),t)
        # A dense white/cyan nucleus grows as the surrounding fog is pulled in.
        x,y=project(self.origin);scale=FOCAL/(self.origin[2]+OFFSET)
        radius=float(height*(.018+.068*build)*scale);core=Image.new('RGBA',(W,H));draw=ImageDraw.Draw(core)
        for mult,color,opacity in ((1.55,ICE[2],.30),(1.2,ICE[3],.70),(.85,ICE[5],1.)):
            rr=radius*mult*(1+.025*math.sin(t*58))
            draw.ellipse((x-rr,y-rr,x+rr,y+rr),fill=(*map(int,color),round(255*strength*opacity)))
        glows[layer(self.origin[2])].alpha_composite(core)

    def frost(self,t,faces,layers):
        age=t-HIT
        if age>0 and t<LAST_HIT+.30:
            strength=float(ease(0,.055,age)*(1-ease(LAST_HIT,LAST_HIT+.30,t)))
            self.star(layers,self.contact,self.target_height*.095,strength*.9,t)
            # A localized icy impact bloom stays close to the affected unit.
            for j in range(8):
                angle=j*math.pi/4+t*.7
                normal=math.cos(angle)*self.side+math.sin(angle)*self.up
                reach=self.target_height*(.10+.07*(.5+.5*math.sin(t*19+j)))
                pos=self.contact+normal*reach
                self.prism(faces,pos,normal,self.target_height*.07,self.target_height*.015,strength*.75,angle)
        for base,direction,born,break_at,g in self.clusters:
            growth=float(ease(born,born+GROW,t));life=1-float(ease(break_at,break_at+.045,t))
            # A broad, low faceted core unifies the roots into a single ice patch.
            self.prism(faces,base-np.array([0.,.015*self.target_height,0.]),direction,
                       self.target_height*.15*growth*float(C.get('crystalSizeMultiplier',1.12)),self.target_height*.115*math.sqrt(growth)*float(C.get('crystalSizeMultiplier',1.12)),life,g*.8)
            flank=base+np.array([(-1 if g%2 else 1)*.038,.018,-.012])*self.target_height
            self.prism(faces,flank,direction,self.target_height*.13*growth*float(C.get('crystalSizeMultiplier',1.12)),
                       self.target_height*.09*math.sqrt(growth)*float(C.get('crystalSizeMultiplier',1.12)),life,g*.8+.5)
        for base,direction,length,radius,born,break_at,j in self.crystals:
            growth=float(ease(born,born+GROW,t));life=1-float(ease(break_at,break_at+.045,t))
            self.prism(faces,base,direction,length*growth,radius*math.sqrt(growth),life,j*.7,shoulder_fraction=float(C.get('crystalTipShoulderFraction',.30)))
            if growth>.9 and t<break_at and j%3==0:
                pulse=.5+.5*math.sin(t*22+j*3)
                if pulse>.85:self.star(layers,base+direction*length,radius*.7,(pulse-.85)/.15*.7,t)
        for born,velocity,life,radius in self.motes:
            age=t-born
            if not 0<age<life:continue
            p=self.contact+velocity*age+np.array([0.,-.7*age*age,0.])
            self.prism(faces,p,velocity/np.linalg.norm(velocity),radius*2,radius*.45,1-float(ease(life*.4,life,age)),born*19)

    def freezing_fog(self,t,layers):
        # Wisps are born only where the beam has already passed, then peel off
        # and keep drifting after the beam's tail has moved on.
        lifetime=float(C.get('fogLifetimeSeconds',.58));opacity=float(C.get('fogOpacity',.42))
        fog=[Image.new('RGBA',(W,H)) for _ in range(3)]
        for j,sample in enumerate(np.linspace(.04,.98,10)):
            height=(1-sample)*self.source_height+sample*self.target_height
            beam_center=self.origin+(self.contact-self.origin)*sample
            first=START+sample*TRAVEL
            for born in np.arange(first,min(t,EMIT_END+sample*TRAVEL)+1e-7,.085):
                age=t-float(born)
                if not 0<age<lifetime:continue
                phase=j*2.37+float(born)*17;side=1 if (j+round(born/.085))%2 else -1
                normal=self.side*side
                p=beam_center+normal*height*(.015+.12*age+.24*age**.7)*(.65+.35*math.sin(phase*1.7)**2)
                p+=self.up*height*(.025*math.sin(phase)+.22*age+.20*age**.7*math.cos(phase+age*5))
                p+=self.axis*height*age*.26
                scale=FOCAL/max(.45,p[2]+OFFSET);radius=height*float(C.get('fogRadiusFraction',.11))*(.36+1.1*age/lifetime)*scale
                alpha=float(ease(0,.065,age)*(1-ease(.19,lifetime,age)))*opacity
                if alpha<.003:continue
                x,y=project(p);heading=project(p+self.axis)-np.array([x,y]);heading/=max(.001,np.linalg.norm(heading));cross=np.array([-heading[1],heading[0]])
                # Long, uneven curls keep the fog wispy rather than spherical smoke.
                a=np.linspace(0,2*math.pi,25);lobe=1+.17*np.sin(a*3+phase)+.09*np.sin(a*7-phase-age*5)
                for size,strength,color in ((1.25,.32,(136,215,240)),(.95,.66,(197,239,251)),(.59,.73,(235,252,255))):
                    xy=np.array([x,y])+heading[None,:]*(np.cos(a)*radius*(1.15+.20*math.sin(phase))*lobe*size)[:,None]+cross[None,:]*(np.sin(a)*radius*.70*lobe*size)[:,None]
                    cloud=Image.new('RGBA',(W,H));ImageDraw.Draw(cloud).polygon([tuple(v) for v in xy],fill=(*color,round(255*alpha*strength)))
                    fog[layer(p[2])].alpha_composite(cloud)
                # A narrow curling lip highlights only part of a drifting wisp.
                arc=np.linspace(-.25,math.pi*.78,13)
                curl=np.array([x,y])+heading[None,:]*(np.cos(arc)*radius*.95)[:,None]+cross[None,:]*(np.sin(arc)*radius*.40)[:,None]
                cloud=Image.new('RGBA',(W,H));ImageDraw.Draw(cloud).line([tuple(v) for v in curl],fill=(225,250,255,round(255*alpha*.50)),width=1)
                fog[layer(p[2])].alpha_composite(cloud)
        for target,mist in zip(layers,fog):target.alpha_composite(mist.filter(ImageFilter.GaussianBlur(.45)))

    def fragments(self,t,faces,layers):
        for born,pos,velocity,radius,life,phase,j in self.shards:
            age=t-born
            if not 0<age<life:continue
            outward=pos-self.contact;outward=outward.copy();outward[1]*=.55
            outward/=max(1e-6,np.linalg.norm(outward))
            kick=velocity*float(C.get('shatterSpeedMultiplier',2.0))+outward*self.target_height*float(C.get('shatterOutwardKickFraction',.45))
            kick[1]=max(self.target_height*.35,kick[1])
            kick[2]=velocity[2]+outward[2]*self.target_height*float(C.get('shatterDepthKickFraction',.10))
            p=pos+kick*age+np.array([0.,-3.6*self.target_height*age*age,0.])
            if p[1]<.015:continue
            alpha=1-float(ease(life*.60,life,age))
            axis=np.array([math.sin(phase+age*12),math.cos(phase+age*12),.45*math.sin(phase+age*9)])
            self.prism(faces,p,axis,radius*2.7,radius*.65,alpha,phase+age*7)
        # Brief radial glints make the actual break legible without a full-screen flash.
        for j in range(7):
            age=t-(BREAK+j*.006)
            if not 0<age<.15:continue
            angle=j*2*math.pi/7;normal=math.cos(angle)*self.side+math.sin(angle)*self.up
            p=self.contact+normal*self.target_height*(.12+age*1.2)
            self.star(layers,p,self.target_height*.024,(1-age/.15)*.7,t)

    def white_glint(self,layers,pos,radius,strength,phase):
        if strength<=0 or pos[1]<.012:return
        x,y=project(pos)
        if x<-3 or x>W+3 or y<-3 or y>H+3:return
        r=float(max(.28,radius*FOCAL/max(.45,pos[2]+OFFSET)*float(C.get('sparkleSizeMultiplier',.40))))
        # Each small grain smoothly dims and brightens at its own phase.
        pulse=(.5+.5*math.sin(phase*float(C.get('sparkleShimmerRate',.55))))**3
        shimmer=.12+.88*pulse
        alpha=float(np.clip(strength,0,1))*shimmer
        particle=Image.new('RGBA',(W,H));draw=ImageDraw.Draw(particle)
        ix,iy=round(float(x)),round(float(y))
        # Mostly single-pixel pinpoints; the rare peak adds one tiny white ray.
        draw.point((ix,iy),fill=(255,255,255,round(255*alpha)))
        if pulse>.91 and r>.46:
            draw.point((ix,iy-1),fill=(240,253,255,round(100*alpha)))
            if r>.68:draw.point((ix+1,iy),fill=(255,255,255,round(75*alpha)))
        layers[layer(pos[2])].alpha_composite(particle)

    def sparkling_frost(self,t,layers):
        # Bright snow-like glints converge on the same muzzle as the gathering fog.
        if CHARGE<t<START+.09:
            fade=1-float(ease(START,START+.09,t));count=int(C.get('chargeWhiteSparkleCount',22))
            gather=self.source_height*float(C.get('chargeGatherRadiusFraction',.64))
            for j in range(count):
                born=CHARGE+(j%5)*.023
                if t<=born:continue
                p=float(ease(born,START+.015,t));angle=j*2.399963+p*1.55
                normal=math.cos(angle)*self.side+math.sin(angle)*self.up
                radius=gather*(.72+.28*math.sin(j*2.1)**2)*(1-p)**.78+self.radius0*.2
                center=self.origin+normal*radius+self.axis*self.source_height*.04*math.sin(j+p*2)
                strength=fade*float(ease(born,born+.025,t))
                self.white_glint(layers,center,self.source_height*(.009+.009*math.sin(j*1.8)**2),strength,t*26+j*1.7)
        lifetime=float(C.get('sparkleLifetimeSeconds',.58))
        # The beam sheds sparkling frozen droplets along its entire traveled path.
        spacing=float(C.get('beamSparkleSpacingSeconds',.13))
        for j,sample in enumerate(np.linspace(.08,.98,9)):
            local_height=(1-sample)*self.source_height+sample*self.target_height
            first=START+sample*TRAVEL+(j%3)*.018
            for born in np.arange(first,min(t,EMIT_END+sample*TRAVEL)+1e-7,spacing):
                age=t-float(born);life=lifetime*(.78+.22*math.sin(j+born*11)**2)
                if not 0<age<life:continue
                center=self.origin+(self.contact-self.origin)*sample
                center+=self.axis*local_height*.16*age+self.side*local_height*(.04*math.sin(j+born*23)+.12*math.sin(j*2+born)*age)
                center+=np.array([0.,-local_height*(.055*age+1.5*age*age),0.])
                strength=float(ease(0,.025,age)*(1-ease(life*.62,life,age)))
                size=local_height*(.010+.010*math.sin(j*2+born*31)**2)
                self.white_glint(layers,center,size,strength,t*24+j+born*13)
        # Continuous white ricochets start on the target surface only while struck.
        interval=float(C.get('impactSparkleSpacingSeconds',.075))
        for born in np.arange(HIT,min(t,LAST_HIT)+1e-7,interval):
            age=t-float(born)
            for j in range(int(C.get('impactSparklesPerBurst',7))):
                phase=j*2.39+float(born)*29;life=lifetime*(.80+.20*math.sin(phase*2)**2)
                if not 0<age<life:continue
                velocity=(-self.axis*(.45+.16*math.sin(phase)**2)+self.side*math.sin(phase)*1.12+self.up*(.52+.72*math.cos(phase*1.7)**2))*self.target_height*float(C.get('impactSparkleSpeedMultiplier',2.15))
                p=self.contact+np.array([0.,0.,-.075*self.target_height])+self.side*self.target_height*.045*math.sin(phase*3)
                p+=velocity*age+np.array([0.,-2.7*self.target_height*age*age,0.])
                strength=float(ease(0,.020,age)*(1-ease(life*.65,life,age)))
                size=self.target_height*(.013+.010*math.sin(phase*1.3)**2)
                self.white_glint(layers,p,size,strength,t*30+phase)

    def impact_atmosphere(self,t,layers):
        if t<=HIT or t>LAST_HIT+.48:return
        height=self.target_height;center=self.contact+np.array([0.,0.,-.11*height])
        pressure=float(ease(HIT,HIT+.045,t)*(1-ease(LAST_HIT,LAST_HIT+.20,t)))
        # Sustained light shafts breathe and move independently from the first blast.
        count=int(C.get('impactLightRayCount',10))
        for j in range(count):
            angle=j*2*math.pi/count+.13*math.sin(t*2.4+j*1.7)
            normal=math.cos(angle)*self.side+math.sin(angle)*self.up
            tangent=-math.sin(angle)*self.side+math.cos(angle)*self.up
            pulse=.45+.55*(.5+.5*math.sin(t*8+j*2.13))**2
            reach=height*float(C.get('impactLightRayReachFraction',.78))*(.60+.40*pulse)
            width=height*(.012+.025*pulse)
            for glow,alpha,color in ((2.2,.20,(139,220,246)),(1.,.72,(233,250,255)),(.30,.95,(255,255,255))):
                for step in range(5):
                    u=step/5;v=(step+1)/5
                    root=center+normal*(height*.035+u*reach)
                    tip=center+normal*(height*.035+v*reach)
                    wr=width*glow*(1-u);wt=width*glow*(1-v)
                    xy=project([root-tangent*wr,root+tangent*wr,tip+tangent*wt,tip-tangent*wt])
                    light=Image.new('RGBA',(W,H))
                    strength=pressure*pulse*(1-(u+v)*.5)**1.4
                    ImageDraw.Draw(light).polygon([tuple(p) for p in xy],fill=(*color,round(255*alpha*strength)))
                    z=float((root[2]+tip[2])*.5)
                    layers[layer(z)].alpha_composite(light)
        # Foreground freezing vapor is centered on the exact contact point.
        # It rolls away in uneven lobes and lingers briefly after emission ends.
        for born in np.arange(HIT,min(t,LAST_HIT)+1e-7,.105):
            age=t-float(born);life=.46
            if not 0<age<life:continue
            progress=age/life
            fade=float(ease(0,.035,age)*(1-ease(.12,life,age)))
            for j in range(4):
                angle=j*math.pi/2+float(born)*7.5
                normal=math.cos(angle)*self.side+math.sin(angle)*self.up
                p=center+normal*height*(.025+.18*progress)
                p-=self.axis*height*age*.30
                p+=np.array([0.,height*(.09*age-.12*age*age),0.])
                x,y=project(p);scale=FOCAL/max(.45,p[2]+OFFSET)
                r=float(height*(.065+.14*progress)*scale)
                theta=np.linspace(0,2*math.pi,25);lobes=1+.18*np.sin(theta*3+j+born*9)+.08*np.sin(theta*7-j-age*4)
                mist=Image.new('RGBA',(W,H))
                opacity=float(C.get('impactFogOpacity',.58))*fade
                for size,color,strength in ((1.45,(142,222,244),.18),(1.,(207,243,254),.42),(.52,(243,253,255),.35)):
                    xy=list(zip(x+np.cos(theta)*r*size*lobes,y+np.sin(theta)*r*.8*size*lobes))
                    puff=Image.new('RGBA',(W,H));ImageDraw.Draw(puff).polygon(xy,fill=(*color,round(255*opacity*strength)))
                    mist.alpha_composite(puff)
                layers[layer(p[2])].alpha_composite(mist.filter(ImageFilter.GaussianBlur(.60)))

    def shatter_atmosphere(self,t,layers):
        height=self.target_height;fog_life=float(C.get('shatterFogLifetimeSeconds',.52))
        for base,direction,_,broken,g in self.clusters:
            age=t-broken
            if not 0<age<max(fog_life,.58):continue
            center=base+direction*height*.13+np.array([0.,0.,-.025*height])
            if age<fog_life:
                fade=float(ease(0,.025,age)*(1-ease(.14,fog_life,age)))
                # Frost bursts from the individual ice patch, then rolls outward.
                for j in range(5):
                    angle=j*2*math.pi/5+g*.7
                    normal=math.cos(angle)*self.side+math.sin(angle)*self.up
                    p=center+normal*height*(.02+.47*age)-self.axis*height*.20*age
                    p[1]+=height*.12*age
                    x,y=project(p);scale=FOCAL/max(.45,p[2]+OFFSET)
                    r=float(height*(.055+.25*age/fog_life)*scale)
                    theta=np.linspace(0,2*math.pi,25);lobes=1+.18*np.sin(theta*3+j+g)+.08*np.sin(theta*7-age*5-j)
                    mist=Image.new('RGBA',(W,H));opacity=fade*float(C.get('shatterFogOpacity',.64))
                    for size,color,strength in ((1.4,(140,217,242),.16),(1.,(209,245,253),.40),(.50,(247,255,255),.32)):
                        xy=list(zip(x+np.cos(theta)*r*size*lobes,y+np.sin(theta)*r*.75*size*lobes))
                        puff=Image.new('RGBA',(W,H));ImageDraw.Draw(puff).polygon(xy,fill=(*color,round(255*opacity*strength)));mist.alpha_composite(puff)
                    layers[layer(p[2])].alpha_composite(mist.filter(ImageFilter.GaussianBlur(.55)))
            # Fine white shimmer flies out with the larger shattered ice pieces.
            for j in range(int(C.get('shatterSparklesPerCluster',20))):
                phase=j*2.399963+g*1.8;life=.43+.15*math.sin(phase*1.7)**2
                if age>=life:continue
                velocity=(self.side*math.cos(phase)*1.9+self.up*(.6+1.8*math.sin(phase)) +self.axis*math.sin(phase*2.3)*.8)*height
                p=center+velocity*age+np.array([0.,-2.5*height*age*age,0.])
                strength=float(ease(0,.018,age)*(1-ease(life*.60,life,age)))
                self.white_glint(layers,p,height*(.012+.009*math.sin(phase*3)**2),strength,t*32+phase)

    def brilliant_beam_core(self,t,layers):
        hi=min(1.,(t-START)/TRAVEL);lo=max(0.,(t-EMIT_END)/TRAVEL)
        if hi<=0 or lo>=1 or hi<=lo:return
        strength=float(ease(START,START+.045,t))
        s=np.linspace(lo,hi,81);centers=self.origin[None,:]+(self.contact-self.origin)[None,:]*s[:,None]
        radii=((1-s)*self.radius0+s*self.radius1)*(.92+.055*np.sin(s*65-t*32))*(.5+.5*strength)
        speed=float(C.get('beamCoreShimmerSpeed',26.))
        pulse=(.5+.5*np.sin(s*49-t*speed))**3
        # A thin, saturated white spine stays bright; traveling highlights pulse
        # its width and corona so the center visibly shimmers without strobing out.
        widths=radii*float(C.get('beamCoreRadiusFraction',.42))*(.70+.30*pulse)
        view=self.camera[None,:]-centers;view/=np.linalg.norm(view,axis=1)[:,None]
        cross=np.cross(np.broadcast_to(self.axis,view.shape),view);cross/=np.linalg.norm(cross,axis=1)[:,None]
        for scale,base_alpha,shine_alpha in ((2.4,35,55),(1.55,95,65),(1.,248,7)):
            for i in range(80):
                points=[centers[i]-cross[i]*widths[i]*scale,centers[i]+cross[i]*widths[i]*scale,centers[i+1]+cross[i+1]*widths[i+1]*scale,centers[i+1]-cross[i+1]*widths[i+1]*scale]
                xy=project(points);highlight=float((pulse[i]+pulse[i+1])*.5)
                alpha=round((base_alpha+shine_alpha*highlight)*strength)
                color=(round(245+10*highlight),round(253+2*highlight),255) if scale==1. else (233,252,255)
                light=Image.new('RGBA',(W,H));ImageDraw.Draw(light).polygon([tuple(p) for p in xy],fill=(*color,alpha))
                layers[layer(float((centers[i,2]+centers[i+1,2])*.5))].alpha_composite(light)

    def effect(self,t):
        layers=[Image.new('RGBA',(W,H)) for _ in range(3)]
        self.freezing_fog(t,layers)
        faces=[];self.charge(t,faces,layers);self.beam(t,faces,layers);self.frost(t,faces,layers);self.fragments(t,faces,layers);self.exaggerated_impact(t,faces,layers)
        draws=[ImageDraw.Draw(im,'RGBA') for im in layers]
        for z,xy,color in sorted(faces,key=lambda x:x[0],reverse=True):
            index=layer(z)
            if color[3]>=255:draws[index].polygon(xy,fill=color);continue
            x0=max(0,math.floor(min(p[0] for p in xy)));y0=max(0,math.floor(min(p[1] for p in xy)))
            x1=min(W,math.ceil(max(p[0] for p in xy))+1);y1=min(H,math.ceil(max(p[1] for p in xy))+1)
            if x1<=x0 or y1<=y0:continue
            tile=Image.new('RGBA',(x1-x0,y1-y0));ImageDraw.Draw(tile).polygon([(x-x0,y-y0) for x,y in xy],fill=color)
            layers[index].alpha_composite(tile,(x0,y0))
        self.brilliant_beam_core(t,layers)
        self.impact_atmosphere(t,layers)
        self.shatter_atmosphere(t,layers)
        self.sparkling_frost(t,layers)
        return layers

    def preview(self,t,layers,bg):
        out=bg.copy()
        for i,(position,sprite) in enumerate(zip((FAR,NEAR),SPRITES)):
            out.alpha_composite(layers[i].resize((640,410),Image.Resampling.NEAREST))
            px,py=np.rint(floor_project(*position)).astype(int)
            shadow=Image.new('RGBA',(W,H));ImageDraw.Draw(shadow).ellipse((px-sprite.width*.34,py-2,px+sprite.width*.34,py+3),fill=(41,28,47,95))
            out.alpha_composite(shadow.resize((640,410),Image.Resampling.NEAREST))
            hit=t-HIT;target=np.array_equal(position,self.target)
            shake=round(math.sin(hit*85)*1.3*(1-float(ease(.05,.25,hit)))) if target and hit>0 else 0
            out.alpha_composite(sprite.resize((sprite.width*2,sprite.height*2),Image.Resampling.NEAREST),(2*(px-sprite.width//2+shake),2*(py-sprite.height)))
        out.alpha_composite(layers[2].resize((640,410),Image.Resampling.NEAREST))
        return out.convert('RGB')

def render(incoming):
    name='incoming' if incoming else 'outgoing';fx=IceBeam(incoming);folder=ROOT/name;folder.mkdir(exist_ok=True)
    bg=Image.open(ROOT/'arena.png').convert('RGBA');atlases=[Image.new('RGBA',(W*COLS,H*ROWS)) for _ in range(3)]
    for i in range(COUNT):
        t=i/FPS;layers=fx.effect(t);fx.preview(t,layers,bg).save(folder/f'{i:03d}.png')
        for atlas,im in zip(atlases,layers):atlas.paste(im,(i%COLS*W,i//COLS*H))
    assets=ROOT/'assets';assets.mkdir(exist_ok=True)
    for atlas,scope in zip(atlases,('behind','between','front')):atlas.save(assets/f'ice-beam-{name}-{scope}.png',optimize=True)
    return name

if __name__=='__main__':
    with concurrent.futures.ProcessPoolExecutor(max_workers=2) as ex:
        for name in ex.map(render,(False,True)):print('Rendered '+name,flush=True)
    timing={'spriteFrame':{'width':W,'height':H},'previewStage':{'width':640,'height':410},'displayScale':2,'sampling':'nearest','framesPerSecond':FPS,'frameDurationMs':round(1000/FPS),'frameCount':COUNT,'durationMs':round(1000*COUNT/FPS),'loop':False,'atlas':{'columns':COLS,'rows':ROWS,'order':'row-major'},'anchor':{'x':0,'y':0},'beatsMs':{'chargeStarts':round(CHARGE*1000),'beamStarts':round(START*1000),'targetImpact':round(HIT*1000),'emissionEnds':round(EMIT_END*1000),'lastBeamHits':round(LAST_HIT*1000),'iceShatters':round(BREAK*1000),'fragmentsClearBy':round((max(BREAK,HIT+.04+.165+GROW+HOLD)+.07+SHARD_LIFE)*1000)},'crystalClusterCount':int(C.get('crystalClusterCount',3)),'crystalsPerCluster':int(C.get('crystalsPerCluster',7)),'compositingOrder':['stage','behind','far battler','between','near battler','front']}
    for key,name in (('playerAttack','outgoing'),('opponentAttack','incoming')):timing[key]={scope:f'ice-beam-{name}-{scope}.png' for scope in ('behind','between','front')}
    (ROOT/'assets/ice-beam-timing.json').write_text(json.dumps(timing,indent=2)+'\n')
