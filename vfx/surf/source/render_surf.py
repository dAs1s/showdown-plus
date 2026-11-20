"""Render both Surf directions and pack 320 by 205 alpha-layered frames."""
import concurrent.futures
import math
import json
from pathlib import Path
import sys

import trail_water as _trail

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
W, H = 320, 205
CONTROLS = json.loads((ROOT/"timing-controls.json").read_text())
HOLD = float(CONTROLS["columnHoldSeconds"])
RATE = float(CONTROLS["runoffPlaybackRate"])
BIAS = float(CONTROLS["earlySpreadBias"])
FPS, COLUMNS = 20, 8
WAVE_FORMATION, TRAVEL_START, IMPACT = -.055, .025, float(CONTROLS["impactSeconds"])
WAVE_RATE = float(CONTROLS.get("waveTravelRate", 1.0))
if not math.isfinite(WAVE_RATE) or WAVE_RATE < 1.:
    raise ValueError("waveTravelRate must be finite and at least 1")

def travel_beat_ms(source_time):
    """Map a pre-contact animation beat to the stage timeline."""
    return max(0,round(1000*(IMPACT+(source_time-IMPACT)/WAVE_RATE)))

if not (0 <= HOLD <= 2 and .8 <= IMPACT <= 4 and .50 <= RATE <= 3 and 0 <= BIAS <= .65):
    raise ValueError("Use the timing ranges in EDITING.md")
SURGE_PEAK = .168+.60*HOLD
SURGE_LANDING = .76+HOLD
CREST_DECAY = float(CONTROLS.get("crestDecaySeconds", .70))
if not .35 <= CREST_DECAY <= 1.1:
    raise ValueError("crestDecaySeconds must be between 0.35 and 1.1")
LIP_FALL = .50
TAIL_START=float(CONTROLS.get("waveTailStretchStartSeconds",IMPACT+CREST_DECAY))
TAIL_SOURCE_END=float(CONTROLS.get("waveTailSourceEndSeconds",IMPACT+CREST_DECAY))
TAIL_CLEAR=float(CONTROLS.get("waveTailClearSeconds",IMPACT+CREST_DECAY))
TAIL_BLEND=float(CONTROLS.get("waveTailBlendSeconds",.22))
TAIL_FADE_SECONDS=float(CONTROLS.get("waveTailFadeSeconds",.20))
CARRY_FRACTION=float(CONTROLS.get("waterCarryDistanceFraction",0.))
CARRY_EASE=float(CONTROLS.get("waterCarryEaseSeconds",.16))
MAINTAIN_MOMENTUM=bool(CONTROLS.get("waterMaintainMomentum",False))
MOMENTUM_BLEND=float(CONTROLS.get("waterMomentumBlendSeconds",.10))
MOMENTUM_OUT=float(CONTROLS.get("waterCruiseGainOutgoing",2.4))
MOMENTUM_IN=float(CONTROLS.get("waterCruiseGainIncoming",2.))
COMPENSATE_CARRY_WIDTH=bool(CONTROLS.get("waterPerspectiveWidthCompensation",False))
CARRY_WIDTH_STRENGTH=float(CONTROLS.get("waterPerspectiveWidthStrength",1.))
TRAILING_REACH=float(CONTROLS.get("waterTrailingReachCompensation",0.))
if not (math.isfinite(MOMENTUM_BLEND) and MOMENTUM_BLEND>0 and all(math.isfinite(x) and x>=1 for x in (MOMENTUM_OUT,MOMENTUM_IN))):
    raise ValueError("Invalid post-impact momentum settings")
if not (math.isfinite(CARRY_FRACTION) and CARRY_FRACTION>=0 and math.isfinite(CARRY_EASE) and CARRY_EASE>0):
    raise ValueError("Invalid shared water carry")
if not math.isfinite(TAIL_FADE_SECONDS) or TAIL_FADE_SECONDS<=0:
    raise ValueError("Wave opacity-fade duration must be finite and positive")
if not (all(math.isfinite(x) for x in (TAIL_START,TAIL_SOURCE_END,TAIL_CLEAR,TAIL_BLEND)) and IMPACT<=TAIL_START<=TAIL_SOURCE_END<=TAIL_CLEAR and TAIL_BLEND>0):
    raise ValueError("Invalid late-wave stretch timing")

def wave_tail_time(stage_time):
    """Preserve the approach and impact, then ease into slower late frames."""
    if stage_time<=TAIL_START:
        return stage_time
    span=TAIL_CLEAR-TAIL_START
    transient=TAIL_BLEND*(-math.expm1(-span/TAIL_BLEND))
    rate=(TAIL_SOURCE_END-TAIL_START-transient)/max(1e-8,span-transient)
    if not 0<rate<=1:
        raise ValueError("Late-wave stretch must retain positive playback speed")
    dt=stage_time-TAIL_START
    return TAIL_START+rate*dt+(1-rate)*TAIL_BLEND*(-math.expm1(-dt/TAIL_BLEND))

RUNOFF_DURATION = 1.112/RATE
END = max(IMPACT+RUNOFF_DURATION, IMPACT+CREST_DECAY, IMPACT+.86, 1.11+HOLD)
ORIGINAL_END = END
END = max(END,_trail.WATER_STAGE_END+_trail.DAMP_FADE)
COUNT = math.ceil(END*FPS)+1
ROWS = math.ceil(COUNT/COLUMNS)
LAUNCH_EASE = .008
POST_WIDTH_GROWTH=float(CONTROLS.get("wavePostImpactWidthGrowth",.25))
POST_WIDTH_SECONDS=float(CONTROLS.get("wavePostImpactWidthSpreadSeconds",.50))
if not (math.isfinite(POST_WIDTH_GROWTH) and POST_WIDTH_GROWTH>=0 and math.isfinite(POST_WIDTH_SECONDS) and POST_WIDTH_SECONDS>0):
    raise ValueError("Invalid post-impact wave-width controls")

def runoff_age(seconds):
    phase = min(max(seconds/RUNOFF_DURATION,0.),1.)
    return 1.112*phase*(1+BIAS*(1-phase))

CREST_SPAN = 6.3
RUNOFF_AREA = float(CONTROLS.get("runoffAreaMultiplier", 1.0))
if not math.isfinite(RUNOFF_AREA) or RUNOFF_AREA <= 0:
    raise ValueError("runoffAreaMultiplier must be positive and finite")
RUNOFF_SCALE = math.sqrt(1.20 * RUNOFF_AREA)
CURL_START, CURL_FULL = TRAVEL_START+.27*(IMPACT-TRAVEL_START), TRAVEL_START+.65*(IMPACT-TRAVEL_START)
FALL_START = IMPACT-.140
FAR = np.array([2.66, 10.64])
NEAR = np.array([-1.40, 1.03])
CAMERA_Y, HORIZON, FOCAL, OFFSET = 2.89, 81.5, 122, 2.6
SY, SX = np.indices((H, W), dtype=np.float32)
INV_SCALE = np.maximum(SY-HORIZON, 1)/CAMERA_Y
WZ = FOCAL/INV_SCALE-OFFSET
WX = (SX-W/2)/INV_SCALE
BODY_COLORS = np.array([(22,77,118),(23,111,159),(22,140,181),(32,167,196),
                        (59,193,211),(111,220,227),(176,241,242),(226,251,242)],dtype=np.uint8)
SPRAY_COLORS = [(105,212,227),(151,229,238),(219,250,245),(242,253,236)]


def ease(a,b,v):
    p = np.clip((v-a)/(b-a),0,1)
    return p*p*(3-2*p)


def released(t,decay,ease_in=.027):
    a = -math.expm1(-t/decay)
    b = -math.expm1(-t/ease_in)
    return (a-(ease_in/decay)*b)/(1-ease_in/decay)


def project(x,z,altitude=0):
    scale = FOCAL/(z+OFFSET)
    return W/2+x*scale,HORIZON+(CAMERA_Y-altitude)*scale


def foam_cells(x,z,rounding=0.):
    grid_x,grid_z = np.floor(x),np.floor(z)
    nearest = np.full_like(x,10.)
    second = nearest.copy()
    third = nearest.copy() if rounding else None
    for dz in (-1,0,1):
        for dx in (-1,0,1):
            node_x,node_z = grid_x+dx,grid_z+dz
            h1 = np.sin(node_x*69.411+node_z*147.93)*45758.5453
            h2 = np.sin(node_x*92.207-node_z*41.693)*27436.8374
            seed_x = node_x+.13+.74*(h1-np.floor(h1))
            seed_z = node_z+.13+.74*(h2-np.floor(h2))
            distance = np.hypot(x-seed_x,z-seed_z)
            outside = np.maximum(distance,nearest)
            if rounding:
                third = np.minimum(third,np.maximum(outside,second))
            second = np.minimum(outside,second)
            nearest = np.minimum(nearest,distance)
    if rounding:
        corner = np.maximum(0.,1-(third-second)/rounding)
        second -= .25*rounding*corner**2
    return second-nearest,nearest


def polygon_artist(size,shapes,details):
    image = Image.new("RGBA",size)
    draw = ImageDraw.Draw(image)
    for color,points in shapes:
        draw.polygon(points,fill=color)
    for color,bounds in details:
        draw.rectangle(bounds,fill=color)
    return image


def near_battler():
    return polygon_artist((58,59),[
        ("#242238",[(1,49),(8,42),(17,43),(21,29),(24,23),(22,8),(29,13),(34,4),(41,0),(43,8),(48,12),(53,12),(53,17),(57,17),(56,25),(48,30),(45,43),(50,47),(50,54),(45,58),(36,58),(33,55),(25,56),(21,58),(10,57),(7,53),(1,53)]),
        ("#4d3e77",[(4,49),(9,44),(19,47),(22,39),(22,30),(30,23),(29,15),(34,17),(40,11),(47,14),(50,18),(54,18),(53,24),(45,28),(42,43),(48,49),(47,53),(44,55),(38,55),(36,50),(27,51),(22,55),(12,54),(10,51),(4,51)]),
        ("#7861a4",[(21,44),(24,31),(30,25),(34,24),(38,17),(48,16),(47,21),(52,21),(49,25),(43,27),(39,36),(39,43),(35,48),(26,51),(17,49)]),
        ("#937abc",[(26,33),(31,28),(35,28),(37,33),(33,36),(28,41),(25,41)]),
        ("#a999c3",[(28,21),(25,11),(30,15),(34,21),(33,24)]),
        ("#d9b9c8",[(35,14),(37,7),(40,4),(40,10),(39,14)]),
        ("#6a5597",[(37,43),(43,45),(48,49),(44,52),(39,50)]),
        ("#644d8c",[(11,49),(17,49),(23,48),(24,52),(20,54),(13,53)]),
        ("#bfa695",[(12,54),(16,53),(17,55),(14,56)]),
        ("#a18591",[(43,54),(47,51),(48,53),(46,55)]),
        ("#b191b6",[(23,33),(26,29),(28,28),(28,32),(25,36)]),
        ("#55407b",[(28,40),(31,38),(37,37),(37,39),(32,41),(29,44)]),
    ],[
        ("#231e35",(45,17,48,19)),("#e4d3a9",(45,17,46,17)),
        ("#9e83b1",(41,25,44,25)),("#a78cbc",(33,31,34,33)),
        ("#957bb3",(29,44,33,44)),("#67568f",(25,47,27,47)),
    ])


def far_battler():
    return polygon_artist((42,44),[
        ("#342637",[(2,21),(7,18),(9,12),(6,4),(8,2),(16,7),(20,4),(26,0),(33,2),(30,10),(34,17),(34,23),(38,18),(41,19),(40,28),(35,30),(35,36),(40,40),(38,43),(27,43),(24,40),(15,41),(13,43),(5,43),(3,41),(7,36),(8,30),(4,28),(1,26)]),
        ("#985238",[(5,21),(11,18),(12,12),(9,6),(15,9),(20,6),(26,3),(30,4),(27,11),(31,17),(31,25),(36,25),(38,21),(39,22),(37,27),(32,29),(32,36),(37,40),(35,41),(28,41),(26,38),(16,39),(12,41),(6,41),(10,36),(12,29),(6,27),(4,24)]),
        ("#d5894a",[(7,22),(11,20),(13,14),(19,10),(25,10),(28,14),(30,21),(28,28),(29,35),(22,37),(13,36),(14,29),(9,27),(5,25)]),
        ("#f0bb6d",[(12,17),(16,12),(21,12),(23,16),(20,21),(16,24),(10,25),(6,24),(10,21)]),
        ("#f6ce87",[(20,10),(24,5),(28,4),(27,8),(25,11)]),
        ("#e8ab61",[(12,13),(10,7),(15,10),(16,12)]),
        ("#f1bb75",[(15,29),(18,28),(23,29),(25,34),(21,36),(16,35)]),
        ("#f7d393",[(8,40),(11,38),(13,39),(11,41)]),
        ("#d79b62",[(30,38),(33,38),(35,40),(31,40)]),
        ("#ad6844",[(26,19),(29,19),(30,24),(27,26),(25,23)]),
    ],[
        ("#3a2a37",(12,18,15,21)),("#ffeeac",(12,18,13,18)),
        ("#f9cf80",(17,15,20,16)),("#ac623b",(24,24,26,26)),
        ("#a84f43",(7,26,8,27)),
    ])


SPRITES = [
    far_battler().resize((31,32),Image.Resampling.NEAREST),
    near_battler().resize((64,65),Image.Resampling.NEAREST),
]


class Surf:
    @staticmethod
    def wave_time(stage_time):
        return IMPACT+(stage_time-IMPACT)*WAVE_RATE if stage_time<IMPACT else wave_tail_time(stage_time)

    @staticmethod
    def wave_clear_time():
        return TAIL_CLEAR

    @staticmethod
    def original_wave_clear_time():
        return IMPACT+CREST_DECAY

    @staticmethod
    def wave_opacity(stage_time):
        return float(1-ease(TAIL_CLEAR-TAIL_FADE_SECONDS,TAIL_CLEAR,stage_time))

    def water_carry(self,stage_time):
        dt=max(0.,stage_time-IMPACT)
        if MAINTAIN_MOMENTUM and dt>0:
            if not hasattr(self,"momentum_start"):
                h=1e-4
                at=self.center_and_height(IMPACT)[0]
                before=self.center_and_height(self.wave_time(IMPACT-h))[0]
                self.momentum_start=(at,(at-before)/h)
            at,speed=self.momentum_start
            gain=MOMENTUM_IN if self.incoming else MOMENTUM_OUT
            advance=speed*(gain*dt+(gain-1)*MOMENTUM_BLEND*math.expm1(-dt/MOMENTUM_BLEND))
            carry=advance
            if not hasattr(self,"carry_anchors"):
                self.carry_anchors={}
            self.carry_anchors[round(carry,7)]=at
            return carry
        span=TAIL_CLEAR-IMPACT
        travel=dt+CARRY_EASE*math.expm1(-dt/CARRY_EASE)
        total=span+CARRY_EASE*math.expm1(-span/CARRY_EASE)
        return self.distance*CARRY_FRACTION*travel/max(1e-8,total)

    def advect_floor_world(self,x,z,distance,inverse=False):
        # A shared expanding ground footprint preserves the connected
        # cone as the water carries deeper into the stage.
        along=(x-self.source[0])*self.direction[0]+(z-self.source[1])*self.direction[1]
        lateral=(x-self.source[0])*self.across[0]+(z-self.source[1])*self.across[1]
        anchor=getattr(self,"carry_anchors",{}).get(round(distance,7),self.distance-1.70)
        anchor_depth=max(.25,self.source[1]+anchor*self.direction[1]+OFFSET)
        stretch_rate=TRAILING_REACH*max(0.,self.direction[1])/anchor_depth
        reach=1+stretch_rate*distance
        rear_limit=anchor-.85/stretch_rate if stretch_rate>0 else -1e30
        if inverse:
            moved=along
            shifted=along-distance
            original=np.where(shifted<anchor,anchor+(shifted-anchor)/reach,shifted)
            original=np.where(moved<rear_limit+.15*distance,moved-.15*distance,original)
        else:
            original=along
            moved=np.where(along<anchor,anchor+(along-anchor)*reach,along)+distance
            moved=np.where(along<rear_limit,along+.15*distance,moved)
        original_depth=np.maximum(self.source[1]+original*self.direction[1]+OFFSET,.25)
        moved_depth=np.maximum(self.source[1]+moved*self.direction[1]+OFFSET,.25)
        gain=1+CARRY_WIDTH_STRENGTH*(moved_depth/original_depth-1) if COMPENSATE_CARRY_WIDTH and self.direction[1]>0 else 1.
        lateral=lateral/gain if inverse else lateral*gain
        along=original if inverse else moved
        return (self.source[0]+along*self.direction[0]+lateral*self.across[0],
                self.source[1]+along*self.direction[1]+lateral*self.across[1])

    def wave_pose(self,stage_time,apply_carry=True):
        center,height=self.center_and_height(self.wave_time(stage_time))
        if stage_time>IMPACT:
            if MAINTAIN_MOMENTUM:
                center=self.center_and_height(IMPACT)[0]
            height*=self.wave_opacity(stage_time)
        if apply_carry:
            center+=self.water_carry(stage_time)
        return center,height
    def __init__(self,incoming):
        self.incoming = incoming
        self.source,self.target = (FAR,NEAR) if incoming else (NEAR,FAR)
        difference = self.target-self.source
        self.distance = np.linalg.norm(difference)
        self.direction = difference/self.distance
        self.across = np.array([-self.direction[1],self.direction[0]])
        self.caster = SPRITES[0 if incoming else 1]
        self.launch_lip = -3.75 if incoming else -.44
        self.end_depth = self.source[1]+(self.distance-1.70)*self.direction[1]+OFFSET
        self.crest_u = np.linspace(-CREST_SPAN,CREST_SPAN,33)
        self.axis = np.array([-2.65,-2.27,-1.92,-1.59,-1.29,-1.03,-.81,-.62,-.44,
                              -.29,-.13,.03,.17,.29,.41,.54,.69,.82,.94,1.07,1.19,1.31,1.42,1.53,1.63])
        self.profile = np.array([0,.021,.048,.082,.135,.207,.304,.42,.55,
                                 .69,.83,.94,1,.984,.94,.876,.78,.669,.554,.435,.318,.208,.126,.052,0])
        self.roll_axis = np.array([-2.65,-2.29,-1.94,-1.60,-1.29,-1.0,
                                   -.77,-.57,-.40,-.23,-.07,.12,.33,.55,.81,1.09,
                                   1.36,1.59,1.76,1.83,1.63,1.13,.69,.47,.65])
        self.roll_profile = np.array([0,.020,.044,.078,.126,.195,.286,.402,.543,
                                      .688,.828,.94,1,.998,.981,.946,.889,.815,.726,.632,
                                      .569,.502,.389,.204,0])
        self.lip_coord = np.linspace(0,1,len(self.axis))
        shape = (len(self.crest_u),len(self.axis))
        self.template = np.broadcast_to(self.crest_u[:,None],shape)
        self.profile_v = np.broadcast_to(self.lip_coord,shape)
        self.triangles = []
        for i in range(shape[0]-1):
            for j in range(shape[1]-1):
                a = i*shape[1]+j
                b = a+shape[1]
                self.triangles.extend(((a,b,b+1),(a,b+1,a+1)))
        dx,dz = WX-self.source[0],WZ-self.source[1]
        self.along = dx*self.direction[0]+dz*self.direction[1]
        self.cross = dx*self.across[0]+dz*self.across[1]
        self.spray = self.generate_spray()
        self.launch_spray = self.generate_launch_spray()

    def travel_progress(self,t):
        return float(np.clip((t-TRAVEL_START)/(IMPACT-TRAVEL_START),0.,1.))

    def approach_position(self,t,original_start,end,launch):
        p = self.travel_progress(t)
        scale = 1+LAUNCH_EASE*math.expm1(-1/LAUNCH_EASE)
        q = (p+LAUNCH_EASE*math.expm1(-p/LAUNCH_EASE))/scale
        caster_depth = self.source[1]+OFFSET
        first_depth = caster_depth+original_start*self.direction[1]
        last_depth = caster_depth+end*self.direction[1]
        launch_depth = caster_depth+launch*self.direction[1]
        # Blend the offset in projected space. Its slope vanishes at contact,
        # keeping the crest's impact velocity continuous with the runoff.
        launch_offset = (launch-original_start)*last_depth/((end-original_start)*launch_depth)
        q += launch_offset*(1-q)**2
        world_progress = q*first_depth/((1-q)*last_depth+q*first_depth)
        return original_start+(end-original_start)*world_progress

    def travel_position(self,t):
        return self.approach_position(t,.95,self.distance-1.70,self.launch_lip-.65)

    def impact_speed(self):
        launch_norm = 1+LAUNCH_EASE*math.expm1(-1/LAUNCH_EASE)
        end_rate = -math.expm1(-1/LAUNCH_EASE)/launch_norm
        first_depth = self.source[1]+1.62*self.direction[1]+OFFSET
        last_depth = self.target[1]+OFFSET
        return (self.distance-1.62)*last_depth/first_depth*end_rate/(IMPACT-TRAVEL_START)

    def center_and_height(self,t):
        center = self.travel_position(t)
        sample_depth = self.source[1]+center*self.direction[1]+OFFSET
        after = max(0,t-IMPACT)
        follow = self.carried_front(after)
        initial_height = .26*self.caster.height
        peak_height_world = 3.43 if self.incoming else 5.92
        peak_height = peak_height_world*FOCAL/self.end_depth
        growth = np.clip((t-TRAVEL_START)/(IMPACT-.052-TRAVEL_START),0.,1.)
        # Most of the rise happens early. The shoulder gains its last bit
        # of height as the overhanging lip arrives at the opponent.
        growth = 1-(1-growth)**2.95
        arc = .76*growth+.24*ease(0.,1.,growth)
        reveal = ease(WAVE_FORMATION,TRAVEL_START,t)
        collapse = 1-ease(FALL_START, IMPACT+CREST_DECAY, t)
        break_weight = ease(FALL_START,IMPACT+LIP_FALL,t)
        apparent_height = initial_height+(peak_height-initial_height)*arc
        height = (apparent_height*sample_depth/FOCAL*reveal*
                  collapse*(1-.07*break_weight))
        return center+follow,height

    def crest_width_factor(self,t):
        growth = ease(.045,.72,self.travel_progress(t))
        maximum = .800 if self.incoming else .758
        return .54+(maximum-.54)*growth

    def runoff_front(self,age):
        depth = self.target[1]+OFFSET
        speed = self.impact_speed()/(depth*RATE*(1+BIAS))
        # Continue the crest path after the last transparent wash frame.
        extra = max(0.,age-RUNOFF_DURATION)*RATE*(1-BIAS)
        age = runoff_age(age)+extra
        drag,tail_speed = (.60,.15) if self.incoming else (.92,.49)
        projected = (speed-tail_speed)*drag*(-math.expm1(-age/drag))+tail_speed*age
        convergence = self.direction[1]*projected
        if convergence > .87:
            convergence = .87-.11*math.expm1(-((convergence-.87)/.11))
            projected = convergence/self.direction[1]
        travel = projected*depth/(1-convergence)
        # Carry both the leading lip and its released sheet past contact.
        # The squared release starts at zero speed at the impact frame.
        carry = 1.9 if self.incoming else 6.3
        return travel+carry*released(age,.40)**2

    def runoff_scale(self,seconds):
        # Ease into the longer footprint after contact so the lip keeps its
        # incoming velocity. Scale in ground coordinates before projection.
        transfer = ease(0., .32, runoff_age(seconds))
        return 1+.25*transfer, 1-.13*transfer

    def carried_front(self,seconds):
        length_scale, _ = self.runoff_scale(seconds)
        return self.runoff_front(seconds)*length_scale

    def crest_front(self,t):
        if t <= IMPACT:
            return self.approach_position(t,1.62,self.distance,self.launch_lip)
        return self.distance+self.carried_front(t-IMPACT)

    def runoff_shape(self,t):
        age = t-IMPACT
        front = self.carried_front(age)
        phase = runoff_age(age)
        rear = -.08-(.32 if self.incoming else .85)*released(phase,.22)
        # Give the released sheet extra reach beyond the traveling lip.
        original_length = (front-rear)*.5
        front *= 1+.32*released(phase,.19)
        length = (front-rear)*.5
        # Keep the near shore wetted. Scaling width with sqrt(length)
        # lets every cross-section grow as the long axis opens.
        width_gain = (2.94 if self.incoming else 4.45)*RUNOFF_SCALE*.87
        width = np.sqrt(original_length)*width_gain*(.15+.85*released(phase,.12))
        width *= 1+.075*phase/1.112
        return (front+rear)*.5, length, width

    def base_span_scale(self,t):
        p = self.travel_progress(t)
        first_width = 1.50*self.caster.width
        last_width = 211. if self.incoming else 153.
        growth = 1-(1-p)**1.32
        width = first_width+(last_width-first_width)*(.37*growth+.63*ease(0.,1.,growth))
        center_x,center_z = self.source+self.direction*self.travel_position(t)
        depth = center_z+OFFSET
        slope = 2*FOCAL*abs(self.across[0]*depth-center_x*self.across[1])
        denom = slope+math.sqrt(slope*slope+4*(width*self.across[1]*depth)**2)
        # Include the width the leading and trailing slopes add at launch.
        first_correction = .94 if self.incoming else .62
        correction = first_correction+(1-first_correction)*ease(0.,.87,growth)
        return self.crest_width_factor(t)*correction*(2*width*depth**2/denom)/(CREST_SPAN*.93)

    def span_scale(self,t):
        base=self.base_span_scale(t)
        if t<=IMPACT:
            return base
        if not hasattr(self,"spreading_span_cache"):
            self.spreading_span_cache={}
        key=round(t,7)
        if key in self.spreading_span_cache:
            return self.spreading_span_cache[key]
        if not hasattr(self,"impact_projected_width"):
            bank=self.wave_ground_footprint(IMPACT,span_override=self.base_span_scale(IMPACT),apply_carry=False)
            self.impact_projected_width=float(np.ptp(np.asarray(bank)[:,0]))
        # Compensate for the receding camera perspective before adding
        # sideways growth. The lowered wave must not narrow on the screen.
        growth=released(max(0.,t-IMPACT),POST_WIDTH_SECONDS)
        desired=self.impact_projected_width*(1+POST_WIDTH_GROWTH*growth)
        def width(scale):
            bank=self.wave_ground_footprint(t,span_override=scale,apply_carry=False)
            return float(np.ptp(np.asarray(bank)[:,0])) if bank else desired
        if width(base)>=desired:
            # A wave coming toward the camera already widens naturally.
            scale=base
        else:
            low,high=base,base*1.25
            while width(high)<desired and high<base*16:
                high*=1.25
            for _ in range(20):
                middle=(low+high)/2
                if width(middle)<desired:low=middle
                else:high=middle
            scale=(low+high)/2
        self.spreading_span_cache[key]=scale
        return scale

    def puddle(self,t):
        water = np.zeros((H,W,4),dtype=np.uint8)
        age = t-IMPACT
        if t <= WAVE_FORMATION or age >= RUNOFF_DURATION:
            return water

        # The moving wave has a shallow toe. The larger sheet is emitted
        # from the point of impact and keeps moving in the attack direction.
        if age < 0:
            center = self.travel_position(t)
            half_width = max(.20,5.65*self.span_scale(t))
            depth = 1.12+.48*self.travel_progress(t)
            u = self.cross/half_width
            v = (self.along-center+.19)/depth
            radius = np.hypot(u,v)
            edge = radius-1.
            active = (edge<.055)&(SY>HORIZON+3.5)
            if active.any():
                rolloff = 1-ease(-.29,.036,edge[active])
                rise = ease(WAVE_FORMATION,TRAVEL_START,t)*(1-.72*ease(IMPACT-.18,IMPACT,t))
                water[:,:,:3][active] = (27,135,171)
                water[:,:,3][active] = (80*rolloff*rise).astype(np.uint8)
            return water

        near = self.incoming
        advance,length,width = self.runoff_shape(t)
        age = runoff_age(age)
        along = self.along-self.distance
        cross = self.cross
        skew = (.46 if near else .14)*self.across[1]/self.direction[1]
        u = (along+skew*cross-advance)/length
        v = cross/width
        # A static, gentle ground-space warp adds variation to the bank.
        # Its phase is fixed so a crest ripple cannot uncover wet ground.
        v *= 1+.035*np.sin(.9*along+.43*cross)*np.sin(.34*cross)
        distance = np.hypot(u,v)
        angle = np.arctan2(v,u)
        edge_field = distance-1.
        floor = SY>HORIZON+3.5
        active = (edge_field<.27)&floor
        if not active.any():
            return water

        u,v,r = u[active],v[active],distance[active]
        advance_at_pixel,cross_at_pixel = along[active],cross[active]
        theta = angle[active]
        edge = edge_field[active]
        # Pixel-space thickness keeps the white rim readable when the
        # distant end foreshortens. Its position still comes from the floor.
        grad_y,grad_x = np.gradient(edge_field)
        edge_pixels = edge/np.maximum(.002,np.hypot(grad_x[active],grad_y[active]))
        wet = (edge <= 0.).astype(float)

        settled = ease(.24,.94,age)
        flow_shift = advance+.39*(advance+length)
        transverse = .64*cross_at_pixel+.27*np.sin(advance_at_pixel*.81-age*7.1)+.14*v
        flow = .85*(advance_at_pixel-flow_shift)+.26*np.sin(cross_at_pixel*.88+age*3.7)+.18*u
        if near:
            # Bend the foam ribs and soften the junctions between cells.
            warped_x = transverse+.25*np.sin(1.72*flow-.63*transverse)
            warped_z = flow+.28*np.sin(1.81*transverse+.54*flow)
            margins,cells = foam_cells(warped_x,warped_z,rounding=.51)
        else:
            margins,cells = foam_cells(transverse+.22*np.sin(flow*1.6),flow+.27*np.sin(transverse*1.4),rounding=.55)
        swells = (.60*np.sin(transverse*2.69+flow*1.52)+
                  .45*np.sin(flow*3.06-transverse*1.24)+.24*np.cos(transverse*5.03+flow*.71))
        pockets = ease(-.57,.58,swells)
        perimeter = ease(.49,.92,r)
        joints = ease(.24,.51,cells)
        # At the contact end leave a fine line of white. Let larger foam
        # lobes build progressively across the sheet in the attack direction.
        past_target = ease(.04,.66,(u+1)*.5)
        strand_scale = .32+.68*past_target
        # Uneven cells with linked white ribs and thicker junctions.
        seam_width = (.122+.088*perimeter+.071*joints)*(1-.34*settled)
        seam_width *= strand_scale
        if near:
            seam_width *= .86
        seams = 1-ease(.39*seam_width,seam_width,margins)
        breakup = ease(-.47,.64,np.sin(theta*13-age*4.5)+.51*swells)
        lace = seams*(.67+.33*pockets)*(.83+.17*perimeter)
        lace *= 1-settled*(.13+.22*(1-breakup))

        # The moving border carries a lagging blue trough and a bright lip.
        bank = (.51+.49*ease(-.54,.67,np.sin(theta*16-11.1*age)
                   +.48*np.sin(theta*31+7.5*age)+.31*swells))
        rim_width = (1.36+.54*bank+.39*ease(-.26,.93,u))*(1-.21*settled)
        rim_width *= strand_scale
        rim = (1-ease(.41,1.,np.abs(edge_pixels+.63*rim_width)/rim_width))
        rim *= .94+.06*bank
        trough = np.exp(-((edge_pixels+2.06*rim_width)/(1.28*rim_width))**2)
        bands = np.zeros_like(r)
        for offset in (.045,.15,.25):
            elapsed = age-offset
            if elapsed <= 0:
                continue
            leading_band = -.50+1.57*(-math.expm1(-elapsed/.28))
            contour = u-(leading_band-.21*v*v+.041*np.sin(v*13+elapsed*6.2))
            wave = 1-ease(.016,.062,np.abs(contour))
            lifetime = ease(0.,.046,elapsed)*(1-ease(.30,.70,elapsed))
            broken = .26+.74*ease(-.47,.67,np.sin(theta*9+offset*29-7*elapsed)+.46*swells)
            bands = np.maximum(bands,wave*lifetime*broken)
        if not near:
            # Distant water has a relatively clear interior. Save dense
            # white foam for the rim and the narrow strip just inside it.
            edge_band = 1-ease(1.18,3.72,-edge_pixels)
            lace *= .20+.80*edge_band
            bands *= .16+.60*edge_band
        energy = np.maximum.reduce((1.13*lace,1.08*rim,.69*bands))
        foam = .18*ease(.17,.49,energy)+.82*ease(.47,.73,energy)
        foam = np.floor(foam*6.999)/6

        # Reuse the crest's stepped petrol blue, cyan and foam palette.
        shade = (.52*np.sin(.44*transverse+.73*flow)+
                 .37*np.cos(.87*transverse-.48*flow)+
                 .16*np.sin(1.41*transverse+1.58*flow))
        shade += .25*swells+.19*perimeter
        shade -= .39*trough+.14*ease(.36,-.82,u)
        light = ease(-.82,.85,shade+.10*cells)
        # Match the traveling face's blue middle tone and use its bright
        # cyan sparingly on lit moving ridges across the settled water.
        middle = 1.52 if near else 1.97
        tone = middle+3.15*(light-.5)+.68*ease(.32,.92,swells)
        index = np.clip(np.rint(tone),0,5).astype(int)
        pigment = BODY_COLORS[index].astype(float)
        white = BODY_COLORS[-1].astype(float)
        fade = np.clip((1.112-age)/.245,0.,1.)
        appear = ease(.005,.105,age)
        water_alpha = (.69+.13*light)*(1-.10*settled)*wet*fade*appear

        # Foam has its own opacity. Its white cores stay solid as the
        # colored sheet thins, then the strands break up and disappear.
        breakup = ease(.72,1.075,age)
        # Rounded lobes live in moving surface coordinates. The rim is
        # continuous early, then breaks into shrinking opaque islands.
        depth_to_edge = -edge_pixels
        bead = 1-ease(.22*strand_scale,.45*strand_scale,cells+.052*np.sin(flow*5+transverse*2))
        inner_band = 1-ease(2.,6.7,depth_to_edge)
        lobes = bead*(.60+.40*pockets)*(.58+.42*perimeter)
        if not near:
            lobes *= .42+.58*inner_band
        relief = np.maximum.reduce((rim, lobes, .72*lace, .48*bands))
        # Thin the entire film together. Advection belongs to the foam
        # pattern and the leading bank, never to a moving rear cutoff.
        erosion = ease(.76,1.112,age)
        threshold = .44+.66*erosion**2+.59*(1-appear)
        strength = relief-threshold
        foam_alpha = ease(-.045,.045,strength)*wet
        foam_light = strength+.105*np.cos(flow*3.1+transverse*1.6)-.05*trough
        shade_tone = np.select([foam_light<.06,foam_light<.20,foam_light<.39],
                               [0,1,2],default=3)
        white = np.array([(112,191,205),(179,226,229),(222,246,242),
                          (247,255,249)],dtype=float)[shade_tone]
        # Composite the foam over the water in premultiplied form, then
        # store straight RGBA for the sprite atlas.
        base = water_alpha*(1-foam_alpha)
        alpha = base+foam_alpha
        rgb = pigment*base[:,None]+white*foam_alpha[:,None]
        rgb = np.divide(rgb,alpha[:,None],out=np.zeros_like(rgb),where=alpha[:,None]>0)
        water[:,:,:3][active] = np.rint(rgb).astype(np.uint8)
        water[:,:,3][active] = np.rint(255*alpha).astype(np.uint8)
        return water

    def crest(self,t,center,height,carry=0.):
        empty = np.zeros((H,W,4),np.uint8)
        depth = np.full((H,W),np.inf,np.float32)
        if height < .065:
            return empty,depth
        u = self.crest_u[:,None]
        span = CREST_SPAN+.17
        ends = np.maximum(0,1-(abs(u)/span)**3)**1.14
        ripple = (.94+.068*np.sin(u*.71-t*4.8)+.044*np.sin(u*1.7+t*3.4)
                  +.022*np.sin(u*3.1-t*5))
        delay = abs(u)*.022+.022*np.sin(u*1.28)
        curl = ease(CURL_START,CURL_FULL,t-delay)
        dive = np.clip((t-delay-FALL_START)/LIP_FALL,0,1)**1.3
        q = self.lip_coord[None,:]
        lip = np.exp(-((q-.760)/.165)**2)
        axis = self.axis[None,:]+(self.roll_axis-self.axis)[None,:]*curl
        profile = self.profile[None,:]+(self.roll_profile-self.profile)[None,:]*curl
        if not self.incoming:
            # Lift the lip farther forward so the roll reads from the rear.
            axis = axis + .42*curl*lip
            back_of_lip = np.exp(-((q-.49)/.153)**2)
            profile = profile + .10*curl*lip*(1-dive)-.16*dive*back_of_lip
        profile = np.maximum(0,profile-.728*dive*lip*(.93+.07*np.sin(u*3.2)))
        length = .48+.52*ease(0.,1.,self.travel_progress(t))
        offset = axis*length+.24*dive*lip-.028*u**2*length
        offset += .18*np.sin(u*.69+t*4.8)+.082*np.sin(u*1.79-t*3.2)
        lip_vertex = int(np.argmin(np.abs(self.lip_coord-.75)))
        center_vertex = len(self.crest_u)//2
        align = 1.
        front_offset = self.crest_front(t)-self.center_and_height(t)[0]
        offset += align*(front_offset-offset[center_vertex,lip_vertex])*lip/lip[0,lip_vertex]
        along = center+offset
        altitude = height*profile*ends*ripple
        spread_after_hit = .08 if self.incoming else .29
        collapse_spread = 1+spread_after_hit*ease(IMPACT,IMPACT+.35,t)
        scaled_u = u*self.span_scale(t)*collapse_spread
        pos_x = self.source[0]+scaled_u*self.across[0]+along*self.direction[0]
        pos_z = self.source[1]+scaled_u*self.across[1]+along*self.direction[1]
        if carry>0:
            pos_x,pos_z=self.advect_floor_world(pos_x-self.direction[0]*carry,pos_z-self.direction[1]*carry,carry)
        sz = np.maximum(pos_z,-1.05)
        px,py = project(pos_x,sz,altitude)
        px,py,sz,source_u,source_v = [np.asarray(a).flatten() for a in
                                    (px,py,sz,self.template,self.profile_v)]
        uv_u = np.zeros((H,W),np.float32)
        uv_v = np.zeros((H,W),np.float32)
        for tri in self.triangles:
            idx = list(tri)
            ax,bx,cx = px[idx]
            ay,by,cy = py[idx]
            left,right = max(0,int(math.floor(min(ax,bx,cx)))),min(W,int(math.ceil(max(ax,bx,cx)))+1)
            top,bottom = max(0,int(math.floor(min(ay,by,cy)))),min(H,int(math.ceil(max(ay,by,cy)))+1)
            if right <= left or bottom <= top:
                continue
            denominator = (by-cy)*(ax-cx)+(cx-bx)*(ay-cy)
            if abs(denominator)<.04:
                continue
            xs,ys = SX[top:bottom,left:right]+.5,SY[top:bottom,left:right]+.5
            aa = ((by-cy)*(xs-cx)+(cx-bx)*(ys-cy))/denominator
            bb = ((cy-ay)*(xs-cx)+(ax-cx)*(ys-cy))/denominator
            cc = 1-aa-bb
            zu,zv,zw = sz[idx]
            zz = aa*zu+bb*zv+cc*zw
            section = np.s_[top:bottom,left:right]
            use = (aa>=-.002)&(bb>=-.002)&(cc>=-.002)&(zz<depth[section])
            if not use.any():
                continue
            depth[section][use] = zz[use]
            a,b,c = source_u[idx]
            uv_u[section][use] = (aa*a+bb*b+cc*c)[use]
            a,b,c = source_v[idx]
            uv_v[section][use] = (aa*a+bb*b+cc*c)[use]
        eligible = np.isfinite(depth)
        if not eligible.any():
            return empty,depth
        u,v = uv_u[eligible],uv_v[eligible]
        crest = np.exp(-((v-.686)/.113)**2)
        foam_tip = np.exp(-((v-.738)/.064)**2)
        defined = ease(CURL_START,CURL_FULL,t)
        curl_shadow = np.exp(-((v-.878)/.088)**2)*(.55+.45*defined)
        striation = np.sin(u*4.2+v*14+np.sin(u*1.3-v*22)+t*3.6)
        flowing_streaks = np.sin(u*10.3+1.4*np.sin(v*10.1-u*.48))
        flowing_streaks *= .39+.61*np.sin(v*21.3-23.4*t+u*1.7)**2
        gloss = ease(.33,.86,flowing_streaks)*ease(.10,.29,v)*(1-ease(.52,.76,v))
        corrugated = np.sin(u*1.45+v*31+t*7)+.46*np.sin(u*5.8-v*35)
        mottled = np.sin(u*13+v*38)*np.sin(u*8.6-v*69+t*11)
        ridge = (.60+.40*np.sin(u*3.2+np.sin(u)*2.0+t*7))*crest
        cap_near_edge = .411+.034*np.sin(u*3.9-t*8.2)+.018*np.sin(u*9.1+t*5)
        cap_far_edge = .548+.027*np.cos(u*4.63+t*6)
        upper_foam = (ease(cap_near_edge,cap_near_edge+.033,v)*
                      (1-ease(cap_far_edge-.018,cap_far_edge,v))*defined)
        if not self.incoming:
            front_foam = .365+.043*np.sin(u*4.2+t*8.2)+.024*np.sin(u*9.7-t*13.0)
            back_foam = .665+.027*np.sin(u*5.9-t*9.)
            roll = ease(front_foam,front_foam+.046,v)*(1-ease(back_foam-.053,back_foam,v))
            upper_foam = np.maximum(upper_foam,roll*defined)
        foam_start = .58+.057*np.sin(u*4.1-t*9)+.013*mottled
        foam_end = .75+.031*defined+.027*np.sin(u*5.4+t*7)+.017*mottled
        white = (v>foam_start)&(v<foam_end)
        tone = 2.02+2.03*crest+1.15*foam_tip*defined-2.09*curl_shadow+.52*striation+.42*corrugated
        tone += .88*ridge*ease(-.25,.9,mottled)+1.05*upper_foam+.94*gloss
        tone = np.where(white,np.maximum(tone,5.12+2.13*ease(-.63,.77,corrugated)),tone)
        cap_tone = 4.85+2.08*ease(-.65,.67,corrugated+.21*mottled)
        tone = np.maximum(tone,cap_tone*upper_foam)
        if not self.incoming:
            clean_cap = 6.1+1.03*ease(-.65,.52,corrugated+.45*np.sin(14.6*v+u*7.6))
            tone = np.maximum(tone,clean_cap*upper_foam)
        index = np.clip(np.rint(tone),0,len(BODY_COLORS)-1).astype(int)
        empty[:,:,:3][eligible] = BODY_COLORS[index]
        opacity = (.77+.13*foam_tip+.05*crest+.09*upper_foam-.17*curl_shadow)
        opacity *= (.34+.66*ease(.02,.22,v))*(1-.84*ease(.90,1.01,v))
        opacity *= 1-.68*ease(IMPACT+.12, IMPACT+CREST_DECAY, t)
        opacity *= ease(.08,.69,height)*(1-ease(CREST_SPAN-.82,CREST_SPAN,abs(u)))
        # Lumps bulge toward the lit face, with a blue-grey turn under the lip.
        cap_center = .5*(foam_start+foam_end)
        cross_section = (v-cap_center)/(.5*(foam_end-foam_start))
        phase = u*2.8+.80*np.sin(u*1.47+t*2.1)-t*3.4+v*4
        crown = .82+.18*np.cos(phase)
        relief = np.maximum(1-(cross_section/crown)**2, upper_foam-.14)
        threshold = (.07+.92*ease(IMPACT+.16,IMPACT+CREST_DECAY,t)
                     +.94*ease(CREST_SPAN-.61,CREST_SPAN,abs(u)))
        shell = relief>threshold
        cap_normal = np.clip((v-.51)/.145,-1,1)
        lit_normal = np.where(v<foam_start,cap_normal,np.clip(cross_section,-1,1))
        lighting = (.48*relief-.27*lit_normal+.31*np.cos(phase-.7)
                    +.08*np.sin(u*5.2+v*20+t*3))
        shade_tone = np.digitize(lighting,[.05,.33,.60])
        palette = np.array([(109,187,202),(172,221,227),(219,244,241),(249,255,250)])
        # The color and alpha of vanishing foam erode together.
        colors = BODY_COLORS[np.minimum(index,5)]
        blend=ease(IMPACT,IMPACT+.18,t)
        shell_weight=shell.astype(float)+(ease(-.10,.10,relief-threshold)-shell)*blend
        colors=np.rint(colors*(1-shell_weight[:,None])+palette[shade_tone]*shell_weight[:,None]).astype(np.uint8)
        empty[:,:,:3][eligible] = colors
        opacity = np.clip(opacity,0,1)*(1-shell_weight)+shell_weight
        empty[:,:,3][eligible] = np.rint(255*opacity).astype(np.uint8)
        return empty,depth

    def generate_spray(self):
        rng = np.random.default_rng(853 if self.incoming else 394)
        particles = []
        for lapse in np.arange(.58,IMPACT+.21,.027):
            center,height = self.center_and_height(lapse)
            for _ in range(3 if lapse < IMPACT-.44 else 7):
                u = rng.uniform(-CREST_SPAN+.7,CREST_SPAN-.7)
                crest_tip = .56+1.10*ease(CURL_START,CURL_FULL,lapse)
                source = (self.source+self.direction*(center+crest_tip-.029*u*u)+
                          self.across*u*self.span_scale(lapse))
                dip = float(np.clip((lapse-abs(u)*.022-FALL_START)/LIP_FALL,0,1)**1.3)
                altitude = height*max(0,1-(abs(u)/(CREST_SPAN+.17))**3)*rng.uniform(.69,.94)*(1-.74*dip)
                velocity = self.direction*rng.uniform(.5,4.7)+self.across*rng.uniform(-1.5,1.5)
                particles.append((lapse,source,altitude,velocity,rng.uniform(.2,3.1),
                                  rng.uniform(.16,.46),rng.uniform(.024,.086),False))
        for _ in range(107):
            lapse = rng.uniform(IMPACT,IMPACT+.22)
            source = self.target+self.direction*rng.uniform(-.33,.75)+self.across*rng.uniform(-1.1,1.1)
            velocity = self.direction*rng.uniform(.6,5.4)+self.across*rng.uniform(-4.1,4.1)
            particles.append((lapse,source,rng.uniform(.35,1.47),velocity,rng.uniform(1.3,5.1),
                              rng.uniform(.23,.62),rng.uniform(.032,.148),True))
        return particles

    @staticmethod
    def layer(z):
        if z > FAR[1]+.06:
            return 0
        if z > NEAR[1]+.06:
            return 1
        return 2

    def droplets(self,t,images,body_depth):
        overlays = [Image.new("RGBA",(W,H)) for _ in images]
        draws = [ImageDraw.Draw(im,"RGBA") for im in overlays]
        for born,origin,h0,velocity,vertical,lifetime,radius,impact in self.spray:
            age = t-born
            if age < 0 or age >= lifetime:
                continue
            x,z = origin+velocity*age
            height = h0+vertical*age-7.1*age**2
            if height < .085 or z < -1:
                continue
            px,py = project(x,z,height)
            x1,y1 = int(px),int(py)
            if not (0<=x1<W and 0<=y1<H) or z > body_depth[y1,x1]+.28:
                continue
            time_left = 1-age/lifetime
            width = max(1,round(radius*FOCAL/(z+OFFSET)*(.50+.5*time_left)))
            alpha = int((235 if impact else 207)*min(1,time_left*2.4))
            color = SPRAY_COLORS[(round(height*11)+round(radius*100))%len(SPRAY_COLORS)]
            length = width+max(0,round(abs(vertical-14.2*age)*.63))
            draw = draws[self.layer(z)]
            if width < 3:
                draw.rectangle((x1,y1,x1+width-1,y1+min(length,3)-1),fill=color+(alpha,))
            else:
                draw.polygon([(x1+width//2,y1-1),(x1+width,y1+length//2),
                              (x1+width//2,y1+length),(x1,y1+length//2)],fill=color+(alpha,))

        for i,(offset,forward,spread,hmax) in enumerate([
            (-.82,.30,-2.2,2.00),(.53,.80,2.22,2.48),(-.13,1.1,-1.2,1.48),(1.0,.9,2.9,1.32)
        ]):
            phase = (t-(IMPACT+.019+i*.019))/.32
            peak = math.sin(math.pi*phase)**.9 if 0 < phase < 1 else 0
            if peak <= .10:
                continue
            origin = self.target+self.direction*forward+self.across*offset
            left,right = [],[]
            for s in np.linspace(0,1,13):
                position = origin+self.across*(spread*s*(.54+.53*phase))+self.direction*(s*.93+.25*phase)
                h = .14+hmax*peak*math.sin(s*1.9)*(1+.046*math.sin(s*29+i))
                x,z = position
                px,py = project(x,z,h)
                thickness = (9.1-8.0*s)*peak*FOCAL/(28*(z+OFFSET))*(1+.18*math.sin(s*39.0+i))
                left.append((px-thickness,py+.28*thickness))
                right.append((px+thickness*.52,py+.82*thickness))
            draw = draws[self.layer(origin[1])]
            draw.polygon(left+right[::-1],fill=(137,219,233,int(190*peak)))
            draw.line(left[2:7],fill=(222,248,241,int(225*peak)),width=1)

        for image,overlay in zip(images,overlays):
            image.alpha_composite(overlay)

    def plunging_foam(self,t,layer):
        if self.incoming:
            return
        age = t-IMPACT
        weight = ease(FALL_START-IMPACT,.035,age)*(1-ease(.17,.51,age))
        if weight <= 0:
            return
        _,height = self.center_and_height(t)
        plunge = ease(FALL_START-IMPACT,.31,age)
        tip = self.source+self.direction*(self.crest_front(t)-.12-.63*plunge)
        spread = (2.9+1.1*plunge)*self.crest_width_factor(t)
        top,bottom,inside = [],[],[]
        for u in np.linspace(-1.,1.,39):
            shape = max(0.,1-u*u)**.59
            edge = (.77+.15*math.sin(u*13+age*22)+.08*math.sin(u*28-age*15))
            upper_height = height*(.74+.16*shape)+.18*math.sin(u*10+age*20)*shape
            tongue = (0.32+3.42*plunge)*shape*edge
            point = tip+self.across*(u*spread)-self.direction*(.37*u*u)
            x,z = point
            top.append(project(x,z,upper_height))
            landing = point+self.direction*(.12+.63*plunge*shape)
            lower = max(.07,upper_height-tongue)
            bottom.append(project(*landing,lower))
            inside.append(project(*landing,min(upper_height,lower+.48*shape)))
        foam = Image.new("RGBA",(W,H))
        draw = ImageDraw.Draw(foam)
        draw.polygon(top+bottom[::-1],fill=(122,216,226,int(227*weight)))
        # Taper the bright face geometrically while keeping the foam solid.
        if weight>.05:
            strip = [(x+(a-x)*weight, y+(b-y)*weight)
                     for (x,y),(a,b) in zip(top,inside)]
            draw.polygon(top+strip[::-1],fill=(226,249,246,255))
        # Broken blue-green openings in the falling surface reveal the
        # wave's shape while preserving a white striking edge.
        for i,ratio in ((8,.44),(15,.32),(23,.54),(31,.40)):
            start = np.array(top[i])
            end = np.array(inside[i])
            middle = start+(end-start)*ratio
            span = 1.2+1.2*plunge
            draw.polygon([tuple(middle+[0,-2]),tuple(middle+[span,1]),
                          tuple(middle+[.6,4]),tuple(middle+[-span,1])],
                         fill=(113,208,222,int(192*weight)))
        layer.alpha_composite(foam)

    def generate_launch_spray(self):
        rng = np.random.default_rng(937 if self.incoming else 364)
        drops = []
        for _ in range(88):
            born = rng.uniform(.044,.18)
            angle = rng.uniform(0,2*math.pi)
            offset = rng.uniform(.10,.43)
            speed = rng.uniform(.65,1.95)
            velocity = np.array([math.cos(angle),math.sin(angle)])*speed
            drops.append((born,velocity*offset,velocity,rng.uniform(2.8,5.8),
                          rng.uniform(.20,.46),rng.uniform(.012,.042)))
        return drops

    def launch_column(self,t,overlays):
        rise = min(1.,max(0.,(t-.021)/(SURGE_PEAK-.021)))
        lift = 1-(1-rise)**2
        descent = min(1.,max(0.,(t-SURGE_PEAK)/(SURGE_LANDING-SURGE_PEAK)))
        collapse = descent**2*(2.55-1.55*descent)
        spread = ease(.021+.47*(SURGE_PEAK-.021),SURGE_PEAK+.32,t)
        opacity = ease(.025,.078,t)*(1-ease(.56+HOLD,.81+HOLD,t))
        if opacity <= .01:
            return
        x,z = self.source
        px,py = project(x,z+.08)
        span = float(self.caster.width)
        height = self.caster.height*1.59*lift*(1-.94*collapse)
        if height < .5:
            return
        radius = span*(.27+.16*lift+.20*spread+.34*collapse)
        half_depth = span*(.075+.043*lift+.052*spread+.05*collapse)
        background = self.layer(z+.09)
        shaft = Image.new("RGBA",(W,H))
        ink = ImageDraw.Draw(shaft)
        left,right = [],[]
        for h in np.linspace(0,1,28):
            width = radius*(.88-.12*h+.053*math.sin(h*7+t*9)+.29*spread*h**2+.34*collapse*(1-h)**2)
            width += span*.032*(math.sin(h*22-21*t)+.55*math.sin(h*51-37*t))
            ripple = span*.024*math.sin(h*9-21*t)
            yy = py-height*h
            left.append((px+ripple-width,yy))
            right.append((px+ripple+width,yy))
        cap = []
        cap_width = .5*(right[-1][0]-left[-1][0])
        cap_height = half_depth*(1+.49*collapse)
        cap_center = .5*(right[-1][0]+left[-1][0])
        for u in np.linspace(-1,1,37):
            crest = max(0.,1-u*u)**.64
            foam = .73+.23*math.sin(18*u-21*t)+.12*math.sin(47*u-10*t)
            cap.append((cap_center+u*cap_width,py-height+cap_height*(1-crest*foam)))
        base = [(px+radius*u,py+half_depth*max(0.,1-u*u)**.6)
                for u in np.linspace(1,-1,21)]
        ink.polygon(left+cap+right[::-1]+base,fill=(226,247,244,int(246*opacity)))

        # Narrow shaded seams follow the rising water around the round face.
        for index,(edge,inner,lower,upper) in enumerate([
            (-.91,-.66,.05,.82),(-.81,-.51,.25,.66),(-.44,-.21,.03,.78),
            (.60,.85,.08,.97),(.27,.44,.18,.80),(.74,.94,.35,.91),
            (-.14,.02,.23,.71)
        ]):
            first,last = [],[]
            for v in np.linspace(0,1,18):
                h = lower+(upper-lower)*v
                wave = .048*math.sin(24*h-22*t+index)+.021*math.sin(58*h+index)
                taper = max(0.,math.sin(math.pi*v))**.56
                low = edge+(inner-edge)*(1-taper)*.50+wave
                high = inner-(inner-edge)*(1-taper)*.50+wave
                yy = py-h*height
                first.append((px+radius*low,yy))
                last.append((px+radius*high,yy-.33*half_depth*taper))
            color = (117,200,219) if index in (0,3,5) else (163,222,231)
            ink.polygon(first+last[::-1],fill=color+(int(209*opacity),))
        rim = [(xx,yy+.46*cap_height) for xx,yy in cap]
        ink.polygon(cap+rim[::-1],fill=(249,255,248,int(253*opacity)))
        # The rim spills outward first. Each lip peels off at its own height
        # and its tip falls faster than the water still feeding it.
        for side,lag in ((-1.,0.),(1.,.045)):
            amount = ease(SURGE_PEAK-.10+lag,SURGE_PEAK+.25+lag,t)
            if amount <= 0:
                continue
            top_edge,lower_edge = [],[]
            for v in np.linspace(0,1,20):
                xx = cap_center+side*(cap_width*.66+span*.49*amount*v)
                drop = height*(.045+.59*amount*v*v)
                yy = py-height+drop+half_depth*.15*math.sin(11*v+side)
                thickness = span*amount*(.027+.058*math.sin(math.pi*v)**.7)
                top_edge.append((xx,yy))
                lower_edge.append((xx-side*thickness,yy+thickness))
            ink.polygon(top_edge+lower_edge[::-1],fill=(155,225,233,int(230*opacity*amount)))
            ink.line(top_edge,fill=(235,252,245,int(248*opacity*amount)),
                     width=max(1,round(span*.043)))
        overlays[background].alpha_composite(shaft)

        # The front toe splashes around the feet as the column falls.
        brush = ImageDraw.Draw(overlays[self.layer(z-.09)])
        skirt = ease(.039,.123,t)*(1-ease(.51+HOLD,.84+HOLD,t))
        foot_span = radius*(.96+.31*collapse)
        top,bottom = [],[]
        for u in np.linspace(-1,1,39):
            r = max(0.,1-u*u)**.52
            foam = .55+.30*math.sin(u*19-34*t)+.16*math.cos(u*44+16*t)
            xx = px+u*foot_span
            top.append((xx,py-height*.10*r-half_depth*r*(.38+foam)))
            bottom.append((xx,py+half_depth*r*(.65+.48*collapse)))
        if skirt > .015:
            brush.polygon(top+bottom[::-1],fill=(116,209,225,int(185*skirt)))
            brush.line(top,fill=(238,255,247,int(237*skirt)),width=2)

    def landing_sheet(self,t):
        # Released from the column base, its low white edge runs along the floor.
        sheet = np.zeros((H,W,4),np.uint8)
        if not .28 < t < 1.11:
            return sheet
        age = t-.28
        scale = (self.source[1]+OFFSET)*self.caster.height/FOCAL
        radius = scale*(.34+1.17*released(age,.31)+.25*age)
        x = (WX-self.source[0])/radius
        z = (WZ-self.source[1])/(.76*radius)
        angle = np.arctan2(z,x)
        contour = np.hypot(x,z)-1-.038*np.sin(7*angle+3*t)-.022*np.cos(13*angle-4*t)
        active = (SY>HORIZON+1)&(contour<.06)
        edge = contour[active]
        phase = ease(.28,.55,t)*(1-ease(.67,1.11,t))
        pockets = .5+.5*np.sin(15*x[active]+2*np.cos(7*z[active])-4*t)*np.cos(10*z[active]+3*t)
        rim = (1-ease(.018,.093,np.abs(edge+.052)))
        trailing = (1-ease(.018,.070,np.abs(edge+.21+.045*np.sin(9*angle[active]))))*pockets
        cells,_ = foam_cells(x[active]*3+.23*np.sin(6*z[active]),z[active]*3.1-age*.9,.24)
        broken_foam = (1-ease(.025,.115,cells))*ease(-.94,-.34,edge)*(.34+.46*pockets)
        foam = np.maximum.reduce((rim,trailing,broken_foam))
        wet = ease(.052,-.036,edge)*(.61+.18*pockets)
        wash = .66+.31*ease(-.96,-.42,edge)
        alpha = np.clip(phase*(.65*wet*wash+.88*foam),0,1)
        color = BODY_COLORS[3]*(1-foam[:,None])+BODY_COLORS[-1]*foam[:,None]
        sheet[active,:3] = color.astype(np.uint8)
        sheet[active,3] = np.rint(alpha*255).astype(np.uint8)
        return sheet

    def launch_burst(self,t,layers):
        if not .023 < t < .86+HOLD:
            return

        scale = (self.source[1]+OFFSET)*self.caster.height/FOCAL
        overlays = [Image.new("RGBA",(W,H)) for _ in layers]
        brushes = [ImageDraw.Draw(layer) for layer in overlays]
        strength = ease(.024,.18,t)*(1-ease(.43,.70,t))
        self.launch_column(t,overlays)

        for born,offset,velocity,speed,life,radius in self.launch_spray:
            age = t-born
            if not 0 <= age < life:
                continue
            height = scale*(.10+speed*age-11.2*age**2)
            if height <= .04:
                continue
            x,z = self.source+scale*(offset+velocity*age)
            if z+OFFSET < .65:
                continue
            px,py = map(round,project(x,z,height))
            width = max(1,round(radius*scale*FOCAL/(z+OFFSET)))
            length = width+int(3.2*max(0.,1-2.5*age))
            alpha = int(239*min(1.,(1-age/life)*2.8)*max(.45,strength))
            color = SPRAY_COLORS[2+(width%2)]
            brushes[self.layer(z)].rectangle((px,py,px+width-1,py+length-1),
                                              fill=color+(alpha,))

        for layer,overlay in zip(layers,overlays):
            layer.alpha_composite(overlay)

    def wave_ground_footprint(self,stage_time,span_override=None,apply_carry=True):
        """Ground-contact contour from the unchanged original wave mesh."""
        t=self.wave_time(stage_time)
        if stage_time<travel_beat_ms(WAVE_FORMATION)/1000. or stage_time>TAIL_CLEAR:
            return []
        center,height=self.wave_pose(stage_time,apply_carry=apply_carry)
        if height<.065:
            return []
        u = self.crest_u[:,None]
        span = CREST_SPAN+.17
        ends = np.maximum(0,1-(abs(u)/span)**3)**1.14
        ripple = (.94+.068*np.sin(u*.71-t*4.8)+.044*np.sin(u*1.7+t*3.4)
                  +.022*np.sin(u*3.1-t*5))
        delay = abs(u)*.022+.022*np.sin(u*1.28)
        curl = ease(CURL_START,CURL_FULL,t-delay)
        dive = np.clip((t-delay-FALL_START)/LIP_FALL,0,1)**1.3
        q = self.lip_coord[None,:]
        lip = np.exp(-((q-.760)/.165)**2)
        axis = self.axis[None,:]+(self.roll_axis-self.axis)[None,:]*curl
        profile = self.profile[None,:]+(self.roll_profile-self.profile)[None,:]*curl
        if not self.incoming:
            # Lift the lip farther forward so the roll reads from the rear.
            axis = axis + .42*curl*lip
            back_of_lip = np.exp(-((q-.49)/.153)**2)
            profile = profile + .10*curl*lip*(1-dive)-.16*dive*back_of_lip
        profile = np.maximum(0,profile-.728*dive*lip*(.93+.07*np.sin(u*3.2)))
        length = .48+.52*ease(0.,1.,self.travel_progress(t))
        offset = axis*length+.24*dive*lip-.028*u**2*length
        offset += .18*np.sin(u*.69+t*4.8)+.082*np.sin(u*1.79-t*3.2)
        lip_vertex = int(np.argmin(np.abs(self.lip_coord-.75)))
        center_vertex = len(self.crest_u)//2
        align = 1.
        front_offset = self.crest_front(t)-self.center_and_height(t)[0]
        offset += align*(front_offset-offset[center_vertex,lip_vertex])*lip/lip[0,lip_vertex]
        along = center+offset
        altitude = height*profile*ends*ripple
        spread_after_hit = .08 if self.incoming else .29
        collapse_spread = 1+spread_after_hit*ease(IMPACT,IMPACT+.35,t)
        scaled_u = u*(self.span_scale(t) if span_override is None else span_override)*collapse_spread
        pos_x = self.source[0]+scaled_u*self.across[0]+along*self.direction[0]
        pos_z = self.source[1]+scaled_u*self.across[1]+along*self.direction[1]
        if apply_carry:
            carry=self.water_carry(stage_time)
            if carry>0:
                pos_x,pos_z=self.advect_floor_world(pos_x-self.direction[0]*carry,pos_z-self.direction[1]*carry,carry)
        sz = np.maximum(pos_z,-1.05)
        px,py=project(pos_x,sz,0.)
        indices=np.arange(len(self.crest_u))
        bank=[]
        for column,steps in ((0,np.linspace(len(indices)-1,0,21)),(-1,np.linspace(0,len(indices)-1,39))):
            bank.extend(zip(np.interp(steps,indices,px[:,column]),np.interp(steps,indices,py[:,column])))
        return [(float(x),float(y)) for x,y in bank]

    def effect(self,t):
        # Compress travel about the contact frame. The launch column
        # and impact runoff each keep their own stage time.
        travel_t = self.wave_time(t)
        impact_fx_t = IMPACT+(t-IMPACT)*WAVE_RATE if t<IMPACT else t
        center,height = self.wave_pose(t)
        crest,depth = self.crest(travel_t,center,height,carry=self.water_carry(t))
        if t>TAIL_START:
            # Finish the last low water gently, with no held or cut frame.
            alpha=self.wave_opacity(t)
            crest[:,:,3]=np.rint(crest[:,:,3].astype(float)*alpha).astype(np.uint8)
        if not hasattr(self,"water_trail"):
            self.water_trail=_trail.TrailWater(self,travel_beat_ms(WAVE_FORMATION)/1000.,IMPACT,TAIL_CLEAR,WAVE_RATE)
        ground=self.water_trail.ground(t,crest)
        bands = [depth>FAR[1]+.06,(depth<=FAR[1]+.06)&(depth>NEAR[1]+.06),depth<=NEAR[1]+.06]
        layers = [ground,Image.new("RGBA",(W,H)),Image.new("RGBA",(W,H))]
        if self.incoming and .28+HOLD < t+.045 < 1.11+HOLD:
            layers[0].alpha_composite(Image.fromarray(self.landing_sheet(t+.045-HOLD),'RGBA'))
        for layer,mask in zip(layers,bands):
            body = np.where(mask[:,:,None],crest,0).astype(np.uint8)
            layer.alpha_composite(Image.fromarray(body,"RGBA"))
        self.plunging_foam(impact_fx_t,layers[0 if t>IMPACT+.16 else 1])
        self.launch_burst(t+.045,layers)
        self.droplets(impact_fx_t,layers,depth)
        return layers

    def preview(self,t,layers,background):
        image = background.copy()
        for i,(position,sprite) in enumerate(zip([FAR,NEAR],SPRITES)):
            image.alpha_composite(layers[i].resize((2*W,2*H),Image.Resampling.NEAREST))
            x,y = project(*position)
            is_target = np.array_equal(position,self.target)
            kick = .114*math.exp(-11*(t-(IMPACT+.04))) if t>IMPACT+.04 and is_target else 0
            dx = int(3*kick*self.direction[0]*10)
            dy = int(-4*kick*10)
            x,y = round(x),round(y)
            shadow = Image.new("RGBA",(W,H))
            ImageDraw.Draw(shadow).ellipse((x-sprite.width*.37,y-3,x+sprite.width*.37,y+4),
                                            fill=(43,32,53,101 if t<.24 or t>2.1 else 63))
            image.alpha_composite(shadow.resize((2*W,2*H),Image.Resampling.NEAREST))
            scaled = sprite.resize((2*sprite.width,2*sprite.height),Image.Resampling.NEAREST)
            image.alpha_composite(scaled,(2*(x-sprite.width//2+dx),2*(y-sprite.height+dy)))
        image.alpha_composite(layers[2].resize((2*W,2*H),Image.Resampling.NEAREST))
        return image.convert("RGB")


def render(incoming,pilot=False):
    name = "incoming" if incoming else "outgoing"
    surf = Surf(incoming)
    folder = ROOT/name
    folder.mkdir(exist_ok=True)
    background = Image.open(ROOT/"arena.png").convert("RGBA")
    frames = [0,1,2,3,4,5,6,7,8,9,10,11,12,14,16,19,24,33,34,35,36,37,38,39,40,42,46,49,52,54,56,58,59] if pilot else range(COUNT)
    atlases = [Image.new("RGBA",(W*COLUMNS,H*ROWS)) for _ in range(3)]
    for index in frames:
        t = index/FPS
        layers = surf.effect(t)
        surf.preview(t,layers,background).save(folder/f"{index:03d}.png")
        if not pilot:
            xy = (index%COLUMNS*W,index//COLUMNS*H)
            for atlas,layer in zip(atlases,layers):
                atlas.paste(layer,xy)
    if not pilot:
        assets = ROOT/"assets"
        assets.mkdir(exist_ok=True)
        for atlas,scope in zip(atlases,["behind","between","front"]):
            atlas.save(assets/f"surf-{name}-{scope}.png",optimize=True)


if __name__ == "__main__":
    pilot = "--pilot" in sys.argv
    with concurrent.futures.ProcessPoolExecutor(max_workers=2) as executor:
        tasks = [executor.submit(render,side,pilot) for side in (False,True)]
        for task in tasks:
            task.result()
    if not pilot:
        timing = json.loads((ROOT/"manifest-template.json").read_text())
        timing.update(frameCount=COUNT, durationMs=round(1000*COUNT/FPS))
        timing["atlas"]["rows"] = ROWS
        timing["beatsMs"].update(surgeBreaksSurface=0,waveRises=travel_beat_ms(WAVE_FORMATION),waveAdvances=travel_beat_ms(TRAVEL_START),
            crestClears=round(1000*TAIL_CLEAR),surgePeaks=round(1000*(SURGE_PEAK-.045)),surgeHangEnds=round(1000*(SURGE_PEAK-.045)),
            surgeSettles=round(1000*(.86+HOLD-.045)),surgeWashClears=round(1000*(1.11+HOLD-.045)),
            lipCurls=travel_beat_ms(CURL_START),crestPlunges=travel_beat_ms(FALL_START),
            targetImpact=round(1000*IMPACT),crestPassesTarget=round(1000*(IMPACT+.21)),
            washSpreads=round(1000*(IMPACT+.05/RATE)),washSlows=round(1000*(IMPACT+.26/RATE)),
            washClears=round(1000*(IMPACT+RUNOFF_DURATION)),waterClears=round(1000*END))
        timing.update(baseVersion="surf-behind-caster",puddleVersion="surf-closer-receding-trail",surgeAndWaveTimingPreserved=True,postImpactWidthGrowth=POST_WIDTH_GROWTH,postImpactPerspectiveWidthCompensated=True,trailPostImpactStartsAtFullWidth=False,trailPostImpactStartsNarrow=True,waveBaseContactFullWidth=True,
            waterTrailEnabled=True,dissipationPuddleEnabled=False,openingSurgeEnabled=True,dampGroundOpacity=_trail.DAMP_OPACITY)
        timing["beatsMs"].update(waterClears=round(1000*_trail.WATER_STAGE_END),dampGroundClears=round(1000*END),
            trailRecedeStarts=round(1000*_trail.TRAIL_BOTTOM_CLEAR),trailFarBankRecedes=round(1000*_trail.TRAIL_TOP_CLEAR))
        for beat in ("washSpreads","washSlows","washClears"):
            timing["beatsMs"].pop(beat,None)
        timing.update(trailStartCutMs=round(1000*_trail.TRAIL_START_CUT),trailAppearanceDelayMs=round(1000*_trail.TRAIL_APPEARANCE_DELAY),puddleFoamEdgeOnly=True,waveContactTealFill=True,trailRowFadeMs=round(1000*_trail.TRAIL_ROW_FADE),trailReleasedStartWidthFraction=_trail.TRAIL_RELEASE_START)
        (ROOT/"assets"/"surf-timing.json").write_text(json.dumps(timing,indent=2)+"\n")
