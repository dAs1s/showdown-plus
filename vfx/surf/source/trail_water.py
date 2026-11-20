"""Render both Surf directions and pack 320 by 205 alpha-layered frames."""
import concurrent.futures
import math
import json
from pathlib import Path
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent
W, H = 320, 205
CONTROLS = json.loads((ROOT/"trail-controls.json").read_text())
HOLD = float(CONTROLS["columnHoldSeconds"])
RATE = float(CONTROLS["runoffPlaybackRate"])
BIAS = float(CONTROLS["earlySpreadBias"])
FPS, COLUMNS = 20, 8
WAVE_FORMATION, TRAVEL_START, IMPACT = -.055, .025, float(CONTROLS["impactSeconds"])
WAVE_RATE = float(CONTROLS.get("waveTravelRate", 1.0))
if not math.isfinite(WAVE_RATE) or WAVE_RATE < 1.:
    raise ValueError("waveTravelRate must be finite and at least 1")

WATER_RATE = float(CONTROLS.get("waterPlaybackRate", 1.))
if not math.isfinite(WATER_RATE) or WATER_RATE <= 0:
    raise ValueError("waterPlaybackRate must be finite and positive")
WATER_START = max(0.,IMPACT+(WAVE_FORMATION-IMPACT)/WAVE_RATE)

def water_time(stage_time):
    return WATER_START+max(0.,stage_time-WATER_START)*WATER_RATE if stage_time>WATER_START else stage_time


def water_beat_ms(source_time):
    stage_time = WATER_START+(source_time-WATER_START)/WATER_RATE
    return max(0,round(1000*stage_time))


def travel_beat_ms(source_time):
    """Map a pre-contact animation beat to the stage timeline."""
    return water_beat_ms(IMPACT+(source_time-IMPACT)/WAVE_RATE)

if not (0 <= HOLD <= 2 and .8 <= IMPACT <= 4 and .50 <= RATE <= 3 and 0 <= BIAS <= .65):
    raise ValueError("Use the timing ranges in EDITING.md")
SURGE_PEAK = .168+.60*HOLD
SURGE_LANDING = .76+HOLD
CREST_DECAY = float(CONTROLS.get("crestDecaySeconds", .70))
if not .35 <= CREST_DECAY <= 1.1:
    raise ValueError("crestDecaySeconds must be between 0.35 and 1.1")
BASE_CREST_DECAY = .80
LIP_FALL = .50
RUNOFF_EXTRA = float(CONTROLS.get("runoffExtraSeconds", 0.))
if not math.isfinite(RUNOFF_EXTRA) or RUNOFF_EXTRA < 0:
    raise ValueError("runoffExtraSeconds must be finite and nonnegative")
BASE_RUNOFF_DURATION = 1.112/RATE+RUNOFF_EXTRA
BOTTOM_CLEAR_LEAD = float(CONTROLS.get("bottomWaterClearLeadSeconds", .60))
FADE_MULTIPLIER = float(CONTROLS.get("fadeDurationMultiplier", 2.))
if not all(math.isfinite(value) and value>0 for value in (BOTTOM_CLEAR_LEAD,FADE_MULTIPLIER)):
    raise ValueError("Fade duration and bottom lead must be finite and positive")
fade_progress = (2*(.82/1.112) /
                 (1+BIAS+math.sqrt((1+BIAS)**2-4*BIAS*(.82/1.112))))
FADE_START = BASE_RUNOFF_DURATION*fade_progress
FADE_DURATION = (BASE_RUNOFF_DURATION-FADE_START)*FADE_MULTIPLIER
RUNOFF_DURATION = FADE_START+FADE_DURATION
NEAR_CLEAR_LEAD = float(CONTROLS.get("nearWaterClearLeadSeconds", .30))
if not math.isfinite(NEAR_CLEAR_LEAD) or NEAR_CLEAR_LEAD < 0:
    raise ValueError("nearWaterClearLeadSeconds must be finite and nonnegative")
WATER_END = max(IMPACT+RUNOFF_DURATION, IMPACT+CREST_DECAY, IMPACT+.86)
END = max(WATER_START+(WATER_END-WATER_START)/WATER_RATE,1.11+HOLD)
DAMP_FADE=float(CONTROLS.get("dampGroundFadeSeconds",.9))
DAMP_OPACITY=float(CONTROLS.get("dampGroundOpacity",.23))
FAR_BANK_CARRY=float(CONTROLS.get("farBankCarryMultiplier",1.))
if not (math.isfinite(DAMP_FADE) and DAMP_FADE>0 and 0<=DAMP_OPACITY<=1 and FAR_BANK_CARRY>=0):
    raise ValueError("Invalid damp-ground or far-bank settings")
COPY_THICKNESS=float(CONTROLS.get("surgeCopyThicknessScale",1.5))
COPY_RATE=float(CONTROLS.get("surgeCopyPlaybackRate",.75))
COPY_RISE_SCALE=float(CONTROLS.get("surgeCopyRiseTimeScale",1.20))
if not math.isfinite(COPY_RISE_SCALE) or not 1<=COPY_RISE_SCALE<=2:
    raise ValueError("Rise time scale must be between 1 and 2")
COPY_START=float(CONTROLS.get("surgeCopyStartSeconds",.55))
COPY_TRAVEL_RATE=float(CONTROLS.get("surgeCopyTravelRate",.70))
COPY_HEIGHT=float(CONTROLS.get("surgeCopyHeightScale",.70))
if not all(math.isfinite(v) and v>0 for v in (COPY_THICKNESS,COPY_RATE,COPY_TRAVEL_RATE,COPY_HEIGHT)):
    raise ValueError("Copy thickness and playback rate must be positive and finite")
COPY_END=COPY_START+(.86+HOLD-.045)/COPY_RATE
END=max(END,COPY_END)
BASE_CONTACT=WATER_START+(IMPACT-WATER_START)/WATER_RATE
COPY_BACKTRACK=float(CONTROLS.get("surgeCopyBacktrackFraction",.24))
if not math.isfinite(COPY_BACKTRACK) or COPY_BACKTRACK<0:
    raise ValueError("Copy backtrack fraction must be finite and nonnegative")
REFERENCE_TRAVEL_DURATION=(BASE_CONTACT-.55)/COPY_TRAVEL_RATE
COPY_CONTACT=COPY_START+REFERENCE_TRAVEL_DURATION*(1+COPY_BACKTRACK)
CONTACT_DELAY=COPY_CONTACT-BASE_CONTACT
END+=CONTACT_DELAY
COPY_POST_RATE=float(CONTROLS.get("wavePostImpactRate",.30))
COPY_POST_BLEND=float(CONTROLS.get("wavePostImpactBlendSeconds",.10))
CRASH_FOAM_LIFE=float(CONTROLS.get("crashFoamLifetimeSeconds",.64))
CRASH_FOAM_STRENGTH=float(CONTROLS.get("crashFoamStrength",1.))
WAVE_FADE_START=float(CONTROLS.get("waveFadeStartSourceSeconds",.92))
WAVE_FADE_END=float(CONTROLS.get("waveFadeEndSourceSeconds",1.08))
if not (0<COPY_POST_RATE<=1 and COPY_POST_BLEND>0 and CRASH_FOAM_LIFE>0 and 0<=CRASH_FOAM_STRENGTH<=2):
    raise ValueError("Invalid post-impact timing or crash foam controls")
if not (0<WAVE_FADE_START<WAVE_FADE_END<=.86+HOLD):
    raise ValueError("Wave source fade must finish within the complete wave animation")

def wave_source_time(stage_time):
    """Keep approach/contact intact, then ease into a slower crash clock."""
    dt=max(0.,stage_time-COPY_CONTACT)
    return stage_time if dt==0 else COPY_CONTACT+COPY_POST_RATE*dt+(1-COPY_POST_RATE)*COPY_POST_BLEND*(-math.expm1(-dt/COPY_POST_BLEND))

base_copy_end=COPY_END
lo,hi=base_copy_end,COPY_CONTACT+(base_copy_end-COPY_CONTACT)/COPY_POST_RATE
for _ in range(48):
    middle=(lo+hi)/2
    if wave_source_time(middle)<base_copy_end:lo=middle
    else:hi=middle
COPY_END=(lo+hi)/2
TRAIL_HOLD_EXTRA=float(CONTROLS.get("trailHoldExtraSeconds",1.))
if not math.isfinite(TRAIL_HOLD_EXTRA) or TRAIL_HOLD_EXTRA<0:
    raise ValueError("Trail extra hold must be finite and nonnegative")
TRAIL_LIFETIME=.64+TRAIL_HOLD_EXTRA
TRAIL_RECEDE_RATE=float(CONTROLS.get("trailRecedePlaybackRate",1.25))
TRAIL_RECEDE_ADVANCE=float(CONTROLS.get("trailRecedeAdvanceSeconds",0.))
TRAIL_EXPANSION=float(CONTROLS.get("trailExpansionMultiplier",1.))
if not (math.isfinite(TRAIL_RECEDE_ADVANCE) and 0<=TRAIL_RECEDE_ADVANCE<TRAIL_LIFETIME/TRAIL_RECEDE_RATE
        and math.isfinite(TRAIL_EXPANSION) and TRAIL_EXPANSION>=1.):
    raise ValueError("Invalid trail recession advance or expansion")
TRAIL_VISIBLE_LIFETIME=TRAIL_LIFETIME/TRAIL_RECEDE_RATE-TRAIL_RECEDE_ADVANCE
TRAIL_LATE_SPREAD=float(CONTROLS.get("trailLateSpreadPerSecond",.11))
TRAIL_IRREGULARITY=float(CONTROLS.get("trailEdgeIrregularityPixels",3.2))/2
FOAM_PATCH_STRENGTH=float(CONTROLS.get("trailFoamPatchStrength",.9))
if not (TRAIL_RECEDE_RATE>0 and TRAIL_LATE_SPREAD>=0 and TRAIL_IRREGULARITY>=0 and FOAM_PATCH_STRENGTH>=0):
    raise ValueError("Invalid trail recession, spread, or foam settings")
TAIL_RECEDE_START=float(CONTROLS.get("trailRearRecedeStartSeconds",.35))
TAIL_LAG=float(CONTROLS.get("trailRearLagPixels",90.))/2
TAIL_FADE_WIDTH=float(CONTROLS.get("trailRearFadeWidthPixels",32.))/2
TAIL_BOUNDARY_SLOPE=float(CONTROLS.get("trailRearBoundarySlope",.11))
TAIL_VISIBLE_MARGIN=float(CONTROLS.get("trailRearVisibleMarginPixels",16.))/2
TRAIL_INITIAL_WIDTH=float(CONTROLS.get("trailStartWidthFraction",.35))
TRAIL_CASTER_WIDTH=float(CONTROLS.get("trailCasterWidthFraction",.50))
TRAIL_TAPER_DISTANCE=float(CONTROLS.get("trailTaperDistanceFraction",.90))
if not (0<TRAIL_CASTER_WIDTH<=1 and TRAIL_TAPER_DISTANCE>0):
    raise ValueError("Invalid caster-end taper")
TRAIL_SPREAD_SECONDS=float(CONTROLS.get("trailSpreadSeconds",.50))
TRAIL_SPREAD_UNIFORMITY=float(CONTROLS.get("trailSpreadUniformity",0.))
TRAIL_SPREAD_REFERENCE=float(CONTROLS.get("trailSpreadReferenceSeconds",1.25))
if not (0<=TRAIL_SPREAD_UNIFORMITY<=1 and math.isfinite(TRAIL_SPREAD_REFERENCE) and TRAIL_SPREAD_REFERENCE>0):
    raise ValueError("Invalid uniform puddle spread controls")

def trail_spread_release(wet_age,reference=False):
    age=max(0.,wet_age)
    initial=-math.expm1(-age/(TRAIL_SPREAD_SECONDS*.48))
    if reference:
        return initial
    # Redistribute the early burst into continued later expansion.
    # Both curves meet at the reference age; neither has a stop or clamp.
    reference_release=-math.expm1(-TRAIL_SPREAD_REFERENCE/(TRAIL_SPREAD_SECONDS*.48))
    steady=age*reference_release/TRAIL_SPREAD_REFERENCE
    return (1-TRAIL_SPREAD_UNIFORMITY)*initial+TRAIL_SPREAD_UNIFORMITY*steady

TRAIL_ATTACHMENT_SECONDS=float(CONTROLS.get("trailAttachmentSeconds",.28))
if not math.isfinite(TRAIL_ATTACHMENT_SECONDS) or TRAIL_ATTACHMENT_SECONDS<=0:
    raise ValueError("Trail attachment time must be finite and positive")
if not (0<TRAIL_INITIAL_WIDTH<=1 and math.isfinite(TRAIL_SPREAD_SECONDS) and TRAIL_SPREAD_SECONDS>0):
    raise ValueError("Trail initial width must be in (0,1] and spread time positive")
if not all(math.isfinite(v) and v>0 for v in (TAIL_LAG,TAIL_FADE_WIDTH)):
    raise ValueError("Tail lag and fade width must be positive")
TRAIL_BOTTOM_CLEAR=float(CONTROLS.get("trailBottomRecedeSeconds",.30))
TRAIL_TOP_CLEAR=float(CONTROLS.get("trailTopRecedeSeconds",2.05))
TRAIL_ROW_FADE=float(CONTROLS.get("trailRowFadeSeconds",.55))
TRAIL_SIDE_STRAIGHTNESS=float(CONTROLS.get("trailSideStraightness",.65))
TRAIL_START_CUT=float(CONTROLS.get("trailStartCutSeconds",0.))
if not math.isfinite(TRAIL_START_CUT) or TRAIL_START_CUT<0:
    raise ValueError("Puddle start cut must be finite and nonnegative")
TRAIL_APPEARANCE_DELAY=float(CONTROLS.get("trailAppearanceDelaySeconds",0.))
if not math.isfinite(TRAIL_APPEARANCE_DELAY) or TRAIL_APPEARANCE_DELAY<0:
    raise ValueError("Puddle appearance delay must be finite and nonnegative")
TRAIL_RELEASE_START=float(CONTROLS.get("trailReleasedStartWidthFraction",.55))
TRAIL_RELEASE_FULL=float(CONTROLS.get("trailReleasedMatureWidthFraction",1.05))
TRAIL_EDGE_BAND=float(CONTROLS.get("trailFoamEdgeBandPixels",7.))/2
TRAIL_CONTACT_WIDTH=float(CONTROLS.get("trailContactFillPixels",12.))/2
FOAM_VOLUME=float(CONTROLS.get("trailFoamVolumePixels",0.))/2
if not math.isfinite(FOAM_VOLUME) or not 0<=FOAM_VOLUME<=4:
    raise ValueError("Foam volume must be between zero and eight stage pixels")
if not (0<TRAIL_RELEASE_START<=TRAIL_RELEASE_FULL and TRAIL_EDGE_BAND>0 and TRAIL_CONTACT_WIDTH>0):
    raise ValueError("Invalid released-water width, foam band, or contact fill")
if not (0<=TRAIL_BOTTOM_CLEAR<TRAIL_TOP_CLEAR and TRAIL_ROW_FADE>0 and 0<=TRAIL_SIDE_STRAIGHTNESS<=1):
    raise ValueError("Invalid bottom-up recession or side-bank settings")
WATER_STAGE_END=max(COPY_END,TRAIL_TOP_CLEAR+TRAIL_ROW_FADE)
END=max(WATER_STAGE_END+DAMP_FADE,COPY_END+CRASH_FOAM_LIFE)
COUNT = math.ceil(END*FPS)+1
ROWS = math.ceil(COUNT/COLUMNS)
LAUNCH_EASE = .008

def fall_time(t):
    # Keep the original motion through impact and stretch the descent.
    return min(t,IMPACT)+max(0.,t-IMPACT)*BASE_CREST_DECAY/CREST_DECAY


def runoff_age(seconds):
    # Continue the shoreline's momentum during the longer fade.
    phase = max(seconds/BASE_RUNOFF_DURATION,0.)
    return 1.112*phase*(1+BIAS*(1-phase))

CREST_SPAN = 6.3
RUNOFF_AREA = float(CONTROLS.get("runoffAreaMultiplier", 1.0))
if not math.isfinite(RUNOFF_AREA) or RUNOFF_AREA <= 0:
    raise ValueError("runoffAreaMultiplier must be positive and finite")
REFERENCE_RUNOFF_AREA = 1.30
RUNOFF_CARRY=float(CONTROLS.get("runoffCarryMultiplier",1.))
if not math.isfinite(RUNOFF_CARRY) or RUNOFF_CARRY<0:
    raise ValueError("runoffCarryMultiplier must be finite and nonnegative")
OUTGOING_RUNOFF_AREA = float(CONTROLS.get("outgoingRunoffAreaMultiplier", 1.0))
INCOMING_RUNOFF_AREA = float(CONTROLS.get("incomingRunoffAreaMultiplier", 1.0))
if not all(math.isfinite(area) and area > 0 for area in (OUTGOING_RUNOFF_AREA, INCOMING_RUNOFF_AREA)):
    raise ValueError("Directional runoff area multipliers must be positive and finite")
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
FOAM_COLORS = np.array([(109,187,202),(172,221,227),(219,244,241),(249,255,250)])
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


# The drawing is a tapered wash, with the long back bank running diagonally
# away from the contact tip. Round each corner with a quadratic join.
RUNOFF_CORNERS = np.array([(-8,5),(-34,-15),(21,-23),(60,-20),(110,-10)],dtype=float)
RUNOFF_BANK = []
for i,corner in enumerate(RUNOFF_CORNERS):
    before = .76*corner+.24*RUNOFF_CORNERS[i-1]
    after = .76*corner+.24*RUNOFF_CORNERS[(i+1)%len(RUNOFF_CORNERS)]
    for fraction in np.linspace(0.,1.,9):
        RUNOFF_BANK.append((1-fraction)**2*before+2*fraction*(1-fraction)*corner+fraction**2*after)


def rounded_bank_distance(x,y,bank=RUNOFF_BANK):
    distance = np.full_like(x,np.inf)
    inside = np.zeros_like(x,dtype=bool)
    for (ax,ay),(bx,by) in zip(bank,bank[1:]+bank[:1]):
        dx,dy = bx-ax,by-ay
        segment = np.clip(((x-ax)*dx+(y-ay)*dy)/(dx*dx+dy*dy),0.,1.)
        distance = np.minimum(distance,np.hypot(x-ax-segment*dx,y-ay-segment*dy))
        if dy != 0.:
            inside ^= ((y>ay)!=(y>by)) & (x<ax+(y-ay)*dx/dy)
    return np.where(inside,-distance,distance)


def runoff_foam_coordinates(x,y):
    """Map the floor to foam coordinates with smaller cells at greater depth."""
    far_y = HORIZON+3.5
    near_y = project(*NEAR)[1]
    depth_span = near_y-far_y
    clamped_y = np.clip(y,far_y,near_y)
    near_scale = .65*1.50
    far_scale = .5*near_scale
    slope = (near_scale-far_scale)/depth_span
    cell_scale = far_scale+slope*(clamped_y-far_y)

    # Integrate reciprocal cell size in the depth direction. This gives
    # the correct spacing on both sides of each depth transition.
    depth = np.log(cell_scale/near_scale)/slope
    depth += near_y+(y-clamped_y)/cell_scale
    lateral = (x-W/2)/cell_scale+W/2
    return lateral,depth


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
        self.wake_stamps = self.make_wake_stamps()
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
        collapse = 1-ease(FALL_START, IMPACT+BASE_CREST_DECAY, fall_time(t))
        break_weight = ease(FALL_START,IMPACT+LIP_FALL,fall_time(t))
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
        # Keep the fall moving across the bank as it decelerates. The
        # near target has less stage floor left in the direction of travel.
        coast = .080 if self.incoming else .31
        forward_time = coast*math.log1p(seconds/coast)
        length_scale, _ = self.runoff_scale(forward_time)
        return self.runoff_front(forward_time)*length_scale

    def crest_front(self,t):
        if t <= IMPACT:
            return self.approach_position(t,1.62,self.distance,self.launch_lip)
        return self.distance+self.carried_front(t-IMPACT)

    def runoff_coordinates(self,age):
        # Trace the red footprint in stage projection. The closest tip is
        # anchored at the hit point and the long bank opens into the distance.
        x,y = project(*self.target)
        opening = released(age,.25)
        progress = .86*opening+.14*age/1.112
        direction_area = INCOMING_RUNOFF_AREA if self.incoming else OUTGOING_RUNOFF_AREA
        scale = math.sqrt(RUNOFF_AREA * direction_area / REFERENCE_RUNOFF_AREA)
        reach = scale*(.05+.95*progress)
        breadth = scale*(.19+.81*progress)
        if self.incoming:
            # Reverse the path for the near target. Keep the foreshortened
            # tip inside the bottom edge so its white bank is still readable.
            span_x = (x-SX)/(.86*reach)
            span_y = (y-SY)/(.80*breadth)
        else:
            span_x = (SX-x)/reach
            span_y = (SY-y)/breadth
        return span_x,span_y

    def runoff_drift(self,seconds):
        """Keep the entire settling sheet moving along the attack axis."""
        seconds=max(0.,seconds)
        # Integrate a short release into a coast that slows without stopping.
        elapsed=seconds-.18*(-math.expm1(-seconds/.18))
        speed=.46 if self.incoming else 7.1
        return RUNOFF_CARRY*speed*elapsed/(1+.35*seconds)

    def advect_runoff(self,x,y,seconds,inverse=False):
        """Translate the ground plane before projecting, including its texture."""
        scale=(np.asarray(y)-HORIZON)/CAMERA_Y
        scale=np.maximum(scale,1e-4)
        world_x=(np.asarray(x)-W/2)/scale
        world_z=FOCAL/scale-OFFSET
        drift=self.runoff_drift(seconds)*(-1. if inverse else 1.)
        return project(world_x+self.direction[0]*drift,
                       world_z+self.direction[1]*drift)

    def fanned_bank(self,seconds):
        """Retract the heel along the attack line while the far shore opens."""
        phase = runoff_age(seconds)
        heading = np.array(project(*self.target))-np.array(project(*self.source))
        heading /= np.linalg.norm(heading)
        target = np.array(project(*self.target))
        contact_bank=np.asarray(self.copied_footprint(COPY_CONTACT))
        rear=contact_bank[np.argmin(contact_bank@heading)]
        front=contact_bank[np.argmax(contact_bank@heading)]
        left=contact_bank[np.argmin(contact_bank[:,0])]
        right=contact_bank[np.argmax(contact_bank[:,0])]
        if self.incoming:
            left,right=right,left
        initial=np.array([rear,left,.45*left+.55*front,.35*front+.65*right,right])

        opening = released(phase,.25)
        progress = .86*opening+.14*phase/1.112
        area = INCOMING_RUNOFF_AREA if self.incoming else OUTGOING_RUNOFF_AREA
        scale = math.sqrt(RUNOFF_AREA*area/REFERENCE_RUNOFF_AREA)
        # Carry the newly released water farther during the additional
        # settling time, strongest along the direction of the fan.
        reach = scale*(.65+.50*progress)*(1+.26*released(seconds,.62))
        breadth = scale*(.65+.50*progress)*(1+.10*released(seconds,.67))
        flip = -1. if self.incoming else 1.
        dimensions = np.array([.86,.80]) if self.incoming else np.ones(2)
        final = target+flip*RUNOFF_CORNERS*np.array([reach,breadth])*dimensions
        final[2,1] -= flip*7.*breadth
        final[3,1] -= flip*5.*breadth
        final[0] = target-heading*(25.+5.*(1-progress))
        # Foreshorten the receding bank before it reaches the horizon.
        # Preserve its contour instead of clipping it to a horizontal row.
        depth_to_horizon = max(4.,target[1]-HORIZON-2.)
        receding = np.minimum(final[:,1]-target[1],0.)
        projected_depth = receding/(1-receding/depth_to_horizon)
        receding_bank = (final[:,1]<target[1]) & (np.arange(len(final))>0)
        final[:,1] = np.where(receding_bank,target[1]+projected_depth,final[:,1])
        # Span the two shoulders with one shallow perspective arc.
        # The broad curve carries through the middle of the far bank.
        left_bank,right_bank = final[1].copy(),final[4].copy()
        lift=(8.+4.*released(seconds,.62))*scale*dimensions[1]
        if self.incoming:
            apex_y=max(left_bank[1],right_bank[1])+lift
        else:
            apex_y=max(HORIZON+8.,min(left_bank[1],right_bank[1])-lift)
        control=.5*(left_bank+right_bank)
        control[1]=2*apex_y-.5*(left_bank[1]+right_bank[1])
        for index,fraction in ((2,.34),(3,.68)):
            final[index]=(1-fraction)**2*left_bank+2*fraction*(1-fraction)*control+fraction**2*right_bank
        transfer = .91*released(seconds,.24)+.09*min(seconds/RUNOFF_DURATION,1.)
        transfer = np.clip(transfer,0.,1.)
        corners = initial*(1-transfer)+final*transfer

        # Round each turn and use a short curve at the heel. Pull its
        # control point out so the curve still passes through the
        # perspective-aligned apex halfway around the turn.
        bank=[]
        for index,corner in enumerate(corners):
            rounding = .11 if index==0 else .34
            before = corner*(1-rounding)+rounding*corners[index-1]
            after = corner*(1-rounding)+rounding*corners[(index+1)%len(corners)]
            control = 2*corner-.5*(before+after) if index==0 else corner
            for fraction in np.linspace(0.,1.,11):
                bank.append((1-fraction)**2*before+2*fraction*(1-fraction)*control+fraction**2*after)
        # Bow the spans between rounded turns into flowing arcs, with
        # smaller lobes moving around them as the outer bank advances.
        center=np.mean(bank,axis=0)
        rippled=[]
        tip=bank[5]
        for first,last in zip(bank,bank[1:]+bank[:1]):
            delta=last-first
            length=np.linalg.norm(delta)
            if length<1e-6:
                continue
            normal=np.array([delta[1],-delta[0]])/length
            if np.dot(.5*(first+last)-center,normal)<0:
                normal=-normal
            for fraction in np.linspace(0.,1.,max(2,math.ceil(length/2.5)),endpoint=False):
                point=first+fraction*delta
                envelope=math.sin(math.pi*fraction)**2
                lobes=1.2*math.sin(point[0]*.23+point[1]*.17-seconds*3.1)
                bow=min(4.2,length*.13)+lobes
                guard=ease(3.,13.,np.linalg.norm(point-tip))
                rippled.append(point+normal*bow*envelope*guard)
        # Carry every bank, including the near heel, with the flow. The
        # ground projection preserves foreshortening in both directions.
        points=np.asarray(rippled)
        x,y=self.advect_runoff(points[:,0],points[:,1],seconds)
        moved=np.column_stack((x,y))
        # Extend only the leading bank. Keep the heel and side contact
        # intact, while the receding arc settles into a cleaner contour.
        top,bottom=np.min(moved[:,1]),np.max(moved[:,1])
        fraction=(moved[:,1]-top)/max(1.,bottom-top)
        leading=fraction if self.incoming else 1-fraction
        weight=ease(.32,.88,leading)
        settle=ease(.20,1.42,seconds)
        smooth=sum(np.roll(moved,shift,axis=0)*coefficient
                   for shift,coefficient in [(-3,1),(-2,2),(-1,3),(0,4),(1,3),(2,2),(3,1)])/16.
        moved+=(smooth-moved)*(.85*settle*weight[:,None])
        plane_scale=np.maximum((moved[:,1]-HORIZON)/CAMERA_Y,1e-4)
        wx=(moved[:,0]-W/2)/plane_scale
        wz=FOCAL/plane_scale-OFFSET
        extra=FAR_BANK_CARRY*(.38 if self.incoming else 11.)*released(seconds,.55)*weight
        x,y=project(wx+self.direction[0]*extra,wz+self.direction[1]*extra)
        return list(zip(x,y))

    def span_scale(self,t):
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

    def make_wake_stamps(self):
        """Lay footprints along the same path as the traveling wave."""
        first = TRAVEL_START+.26*(IMPACT-TRAVEL_START)
        stamps = []
        for contact_time in np.linspace(first,IMPACT+.16,35):
            impact_progress = np.clip((contact_time-first)/(IMPACT-first),0.,1.)
            position = self.source+self.direction*self.crest_front(contact_time)
            x,y = project(*position)
            if self.incoming:
                x -= 11.+11.*impact_progress
                y -= 5.+3.*impact_progress
                width = 31.+22.*impact_progress
                depth = 8.+10.*impact_progress
            else:
                x += 28.-19.*impact_progress
                y += 7.+4.*impact_progress
                width = 47.+8.*impact_progress
                depth = 9.+5.*impact_progress
            # The last footprints stay as the front half of the impact
            # pool. Earlier foam thins while the wave is still traveling.
            hold = ease(IMPACT-.36,IMPACT-.14,contact_time)
            fade_start = contact_time+.34+hold*.55
            fade_end = contact_time+.64+hold*.70
            stamps.append((contact_time,x,y,width,depth,fade_start,fade_end))
        return stamps

    def wake_field(self,t):
        edge = np.full((H,W),1e3)
        coverage = np.zeros((H,W))
        for born,x,y,width,depth,fade_start,fade_end in self.wake_stamps:
            if t < born or t >= fade_end:
                continue
            elapsed = t-born
            fill = ease(0.,.16,elapsed)
            linger = 1-ease(fade_start,fade_end,t)
            # Water keeps spreading after the initial fill. Carry some
            # momentum down the stage, with the edge slowing over time.
            spread = released(elapsed,.32)
            travel = released(elapsed,.24)
            direction = -1. if self.incoming else 1.
            x += direction*width*.17*travel
            y -= direction*depth*.34*travel
            wet_width = width*(.21+.79*fill+.32*spread)
            wet_depth = depth*(.38+.62*fill+.82*spread)
            footprint_x = (SX-x+.21*(SY-y))/wet_width
            footprint_y = (SY-y)/wet_depth
            radius = np.hypot(footprint_x,footprint_y)
            shore = (radius-1.)*wet_depth
            shore += 1.45*np.sin(.19*SX+.17*SY)+.72*np.cos(.30*SY-.09*SX)
            shore += .48*np.sin(.43*SX-.31*SY+2.6*t)
            # Thin the advancing edge as the deposit fades.
            shore += 1.7*(1-linger)**2
            edge = np.minimum(edge,shore)
            strength = (1-ease(-2.,.35,shore))*fill*linger
            coverage = np.maximum(coverage,strength)
        return edge,coverage

    def wake_attachment(self,t,geometry):
        """Project the ground contact from one wing of the wave to the other."""
        lateral,along,_ = geometry
        # Share the actual bottom row of the mesh with the flat wake.
        # Every point of this contact row is on the ground plane.
        points = (self.source[:,None]+self.across[:,None]*lateral[:,0]
                  +self.direction[:,None]*along[:,0])
        px,py = project(points[0],np.maximum(points[1],-1.05))
        order = np.argsort(px)
        left,right = px[order[0]],px[order[-1]]
        join_y = np.interp(SX,px[order],py[order])
        breadth = max(1.,right-left)
        across = np.clip((SX-left)/breadth,0.,1.)
        # Draw the marked trailing bank as a broad arc. The left shoulder
        # bows out more and the right returns to the wing in a shallow line.
        back = -1. if self.incoming else 1.
        distance = back*(SY-join_y)
        reveal = ease(TRAVEL_START+.25*(IMPACT-TRAVEL_START),
                      TRAVEL_START+.54*(IMPACT-TRAVEL_START),t)
        release = 1-ease(IMPACT+.30,IMPACT+.81,t)
        # Aim the visible rear bank along the same projected attack
        # line as the mesh tip, rather than dropping it vertically.
        middle = len(self.crest_u)//2
        attack_x,attack_y = project(*self.target)
        caster_x,caster_y = project(*self.source)
        heading = np.array([attack_x-caster_x,attack_y-caster_y])
        heading /= np.linalg.norm(heading)
        extension = (8.+9.*released(max(0.,t-TRAVEL_START),.38))*reveal
        rear_tip = np.array([px[middle],py[middle]])-heading*extension
        # Both banks meet this point with a sharper turn at the apex.
        left_fraction = np.clip((SX-left)/max(1.,rear_tip[0]-left),0.,1.)
        right_fraction = np.clip((right-SX)/max(1.,right-rear_tip[0]),0.,1.)
        left_y = py[order[0]]+(rear_tip[1]-py[order[0]])*left_fraction**.83
        right_y = py[order[-1]]+(rear_tip[1]-py[order[-1]])*right_fraction**.83
        rear_y = np.where(SX<=rear_tip[0],left_y,right_y)
        irregular = (1.28*np.sin(.23*SX-3.1*t)+.67*np.sin(.51*SX+4.2*t))
        tip_guard = ease(2.,9.,abs(SX-rear_tip[0]))
        end_guard = np.sin(np.pi*across)**.6
        rear_y += irregular*tip_guard*end_guard
        rear = np.maximum(0.,back*(rear_y-join_y))
        side = np.maximum(left-SX,SX-right)
        edge = np.maximum.reduce((side,-distance-.5,distance-rear-.5))
        fill = reveal*release*(edge<=0.)
        return edge,distance,fill

    def puddle_appearance(self,stage_time):
        # Keep the short smooth reveal even when there is no start delay.
        start=COPY_START+TRAIL_APPEARANCE_DELAY
        return float(ease(start,start+2/FPS,stage_time))

    def puddle(self,t,geometry,crest,stage_time):
        water = np.zeros((H,W,4),dtype=np.uint8)
        age = t-IMPACT
        if stage_time<COPY_START or stage_time>=WATER_STAGE_END:
            return water
        appearance=self.puddle_appearance(stage_time)
        if appearance<=0:
            return water

        phase = runoff_age(age)
        wake_edge,wake_coverage,distance=self.matched_wake(stage_time)
        x,y = self.runoff_coordinates(phase)
        # Keep only the swept water deposited by the traveling wave.
        # No new impact fan or separate pool is spawned behind the target.
        edge = wake_edge
        contact=self.wave_contact_fill(stage_time,crest)
        retreat=self.tail_visibility(stage_time)
        active = ((edge <= 0.) | (contact>.01)) & (SY > HORIZON+3.5)
        if not active.any():
            return water

        # Use one silhouette for the raised wave and its wake. Erode this
        # union to measure the outer shore, so the contact line cannot
        # become a separate white border across the middle of the water.
        wave_surface = crest[:,:,3]>12
        visible_ground=active & (np.maximum(wake_coverage*retreat,contact)>.05)
        united = visible_ground | wave_surface
        silhouette = Image.fromarray((united*255).astype(np.uint8),"L")
        outer_inset = np.zeros((H,W),dtype=float)
        previous = 0
        for radius in (1,3,5,8,12,18,24):
            eroded = np.asarray(silhouette.filter(ImageFilter.MinFilter(2*radius+1)))>0
            outer_inset += (radius-previous)*eroded
            previous = radius
        inset = outer_inset[active]
        # The colored film may overlap the translucent low face, while
        # the foam is restricted to the combined outer shoreline.
        uncovered = ~wave_surface[active]
        x,y = x[active],y[active]
        far=np.full(len(x),.61)
        floor_x,floor_y = SX[active],SY[active]
        pattern_x,pattern_y=self.advect_runoff(floor_x,floor_y,max(age,0.),inverse=True)
        # Keep the web drifting over the floor as the separate patches
        # meet. Use a single texture across the seam.
        transverse = .0435*pattern_x+.013*pattern_y+.19*np.sin(pattern_y*.19+t*5)
        flow = .12*pattern_y-.012*pattern_x-.47*t+.21*np.sin(pattern_x*.09-t*6)
        cell_x,cell_y = runoff_foam_coordinates(pattern_x,pattern_y)
        foam_across = .0435*cell_x+.013*cell_y+.19*np.sin(cell_y*.19+t*5)
        foam_along = .12*cell_y-.012*cell_x-.47*t+.21*np.sin(cell_x*.09-t*6)
        margins,_ = foam_cells(foam_across,foam_along,rounding=.55)
        swell = .52*np.sin(transverse*2.5+flow*1.5)+.31*np.cos(flow*4.1-transverse*1.2)
        light = ease(-.74,.81,swell+.17*np.cos(transverse*4.6-flow*2.7)+.16*far)
        middle = 1.52 if self.incoming else 1.97
        tone = middle+2.7*(light-.5)+.55*ease(.32,.95,swell)
        pigment = BODY_COLORS[np.clip(np.rint(tone),0,5).astype(int)].astype(float)
        contact_weight=contact[active]
        join_teal=BODY_COLORS[np.clip(np.rint(2.+.65*light),2,3).astype(int)].astype(float)
        pigment=pigment*(1-contact_weight[:,None])+join_teal*contact_weight[:,None]

        appear = wake_coverage[active]
        # The single bottom-up retreat mask below controls disappearance.
        # Do not apply a second whole-puddle fade on top of it.
        clear=0.
        water_alpha = .64+.16*light
        # Patchy thicker foam follows the scalloped sides and rear.
        patches=ease(.25,.80,.5+.32*np.sin(.074*floor_x+.051*floor_y-.7*stage_time)
                     +.18*np.sin(.043*floor_x-.092*floor_y+.45*stage_time))
        self.tail_visibility(stage_time)
        rear_depth=self.rear_depth[active]
        rear_center=.42*TAIL_FADE_WIDTH
        rear_band=(1-ease(3.,9.,abs(rear_depth-rear_center)))*ease(TAIL_RECEDE_START,TAIL_RECEDE_START+.2,stage_time)
        line_width = (.086+.114*far+.027*np.sin(flow*2.5+transverse))*(.55+.45*far)
        line_width*=1+.35*FOAM_PATCH_STRENGTH*patches
        rib = 1-ease(.37*line_width,line_width,np.maximum(0.,margins))
        intact = ease(-.49,.45,swell+.18*np.sin(flow*3.1+transverse*2.4)+.89*far+.13)
        cell_depth_scale = np.clip((floor_y-(HORIZON+3.5))/(project(*NEAR)[1]-HORIZON-3.5),0.,1.)
        band_width = TRAIL_EDGE_BAND+3.*cell_depth_scale
        band_width*=1+.12*patches
        perimeter_foam = 1-ease(.25*band_width,band_width,inset)
        ribs = rib*intact
        rim_width = (.71+1.16*far+.24*np.sin(transverse*2.4+phase*7))*(.54+.46*far)
        rim_width*=1+FOAM_PATCH_STRENGTH*patches
        rim = 1-ease(.34*rim_width,rim_width,inset)
        # Keep the white outline on the bank, away from the mesh join.
        rim *= np.maximum(ease(.7,3.5,distance[active]),ease(.20,.44,age))
        rim *= .76+.24*far
        # Broken parallel ripples wrap around the softened banks and
        # connect into the foam cells near the outside of the pool.
        ripple_phase = .95*np.sin(.18*floor_x-.13*floor_y-3.4*t)
        ripple_phase += .47*np.sin(.32*floor_y+.09*floor_x+2.1*t)
        first_arc = 1-ease(.30,.85,abs(inset-3.1-ripple_phase))
        second_arc = 1-ease(.25,.77,abs(inset-6.6-1.3*ripple_phase))
        breakup = ease(-.26,.57,np.sin(.26*floor_x+.33*floor_y-4.1*t))
        arcs = np.maximum(first_arc,.73*second_arc)*breakup*(.55+.45*far)
        arcs *= np.maximum(ease(.7,3.5,distance[active]),ease(.20,.44,age))
        rear_width=.70+FOAM_PATCH_STRENGTH*patches
        rear_foam=(1-ease(.35*rear_width,rear_width,abs(rear_depth-rear_center)))*rear_band
        rear_foam*=.30+.70*patches
        relief = np.maximum.reduce((.90*rim,ribs,.81*arcs,rear_foam))
        # Fade the foam with the cyan film; do not erode it into white pixels.
        threshold = .41+.12*(1-far)
        foam_alpha = ease(-.07,.07,relief-threshold)*perimeter_foam
        foam_alpha *= uncovered*(1-contact_weight)
        # Keep a thin continuous film under the contact row so partial
        # transparency cannot open a strip of dry ground at the seam.
        foam_light = relief-.15*np.cos(flow*2.7+transverse*1.5)+.12*patches
        foam = FOAM_COLORS[np.digitize(foam_light,[.32,.48,.70])]

        base = water_alpha*(1-foam_alpha)
        alpha = base+foam_alpha
        rgb = pigment*base[:,None]+foam*foam_alpha[:,None]
        rgb = np.divide(rgb,alpha[:,None],out=np.zeros_like(rgb),where=alpha[:,None]>0)
        water[:,:,:3][active] = np.rint(rgb).astype(np.uint8)
        visibility=appear*(1-clear)*retreat[active]
        # Fully teal contact water seals the base; the ordinary sheet
        # keeps its transparency and bottom-up fade away from the wave.
        water[:,:,3][active] = np.rint(255*np.maximum(alpha*visibility,contact_weight)*appearance).astype(np.uint8)
        if FOAM_VOLUME>0:
            # Lift existing outer foam cells into low irregular crests.
            # The cool sidewall gives the white cap visible thickness.
            support=np.zeros((H,W),np.float32)
            support[active]=ease(.40,.82,foam_alpha)*visibility*appearance
            support[active]*=(1-ease(.60*band_width,band_width,inset))*(.55+.45*patches)
            support[active]*=uncovered*(1-contact_weight)
            heights=np.zeros((H,W),np.int16)
            heights[active]=np.maximum(1,np.rint(FOAM_VOLUME*(.55+.65*cell_depth_scale)*(.82+.18*patches))).astype(np.int16)
            wall=np.zeros_like(support);cap=np.zeros_like(support)
            for lift in range(1,int(heights.max())+1):
                lower=support*(heights>=lift)
                wall[:-lift]=np.maximum(wall[:-lift],lower[lift:])
                top=support*(heights==lift)
                cap[:-lift]=np.maximum(cap[:-lift],top[lift:])
            wall*=~wave_surface;cap*=~wave_surface
            image=Image.fromarray(water,"RGBA")
            for field,color in ((wall,(142,207,217)),(cap,(249,255,250))):
                overlay=np.empty_like(water);overlay[:,:,:3]=color
                overlay[:,:,3]=np.rint(255*np.clip(field,0,1)).astype(np.uint8)
                image.alpha_composite(Image.fromarray(overlay,"RGBA"))
            water=np.asarray(image).copy()
        return water

    def crest_geometry(self,t,center,height):
        u = self.crest_u[:,None]
        span = CREST_SPAN+.17
        ends = np.maximum(0,1-(abs(u)/span)**3)**1.14
        ripple = (.94+.068*np.sin(u*.71-t*4.8)+.044*np.sin(u*1.7+t*3.4)
                  +.022*np.sin(u*3.1-t*5))
        delay = abs(u)*.022+.022*np.sin(u*1.28)
        curl = ease(CURL_START,CURL_FULL,t-delay)
        dive = np.clip((fall_time(t)-delay-FALL_START)/LIP_FALL,0,1)**1.3
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
        front_offset = self.crest_front(t)-center
        offset += align*(front_offset-offset[center_vertex,lip_vertex])*lip/lip[0,lip_vertex]
        along = center+offset
        altitude = height*profile*ends*ripple
        spread_after_hit = .08 if self.incoming else .29
        collapse_spread = 1+spread_after_hit*ease(IMPACT,IMPACT+.35,t)
        # Define the visible ground-contact row in stage perspective.
        # Its tip follows the attack axis while both wings sweep forward.
        heel = 1-ease(0.,.23,q)
        heel *= ease(.22,.48,self.travel_progress(t))*(1-ease(IMPACT+.18,IMPACT+.78,t))
        scaled_u = u*self.span_scale(t)*collapse_spread
        side_positions = self.source[:,None]+self.across[:,None]*scaled_u[:,0]+self.direction[:,None]*along[:,0]
        side_x,side_y = project(side_positions[0],np.maximum(side_positions[1],-1.05))
        retract = .70*released(max(0.,t-IMPACT),.31)
        tip_ground = self.source+self.direction*(center-2.65*length-1.37+retract)
        tip_x,tip_y = project(*tip_ground)
        back = -1. if self.incoming else 1.
        right_y = tip_y-back*max(6.,back*(tip_y-side_y[0]))
        left_y = tip_y-back*max(6.,back*(tip_y-side_y[-1]))
        fraction = abs(u/CREST_SPAN)
        endpoint_x = np.where(u<0,side_x[0],side_x[-1])
        endpoint_y = np.where(u<0,right_y,left_y)
        row_x = tip_x+(endpoint_x-tip_x)*fraction
        rounded_fraction = (np.sqrt(fraction*fraction+.01)-.10)/(np.sqrt(1.01)-.10)
        row_y = tip_y+(endpoint_y-tip_y)*rounded_fraction**.85
        # Flowing tongues roughen the two sides but retain the shared tip.
        tongues = np.sin(np.pi*fraction)**.62
        row_y += tongues*(1.06*np.sin(18*fraction-3.8*t)+.58*np.sin(39*fraction+5.1*t))
        row_x += tongues*.47*np.sin(27*fraction+3.4*t)
        # Unproject the corrected contact row to the floor before joining
        # it to the wall, so the edge and wake use identical 3D positions.
        floor_z = FOCAL*CAMERA_Y/np.maximum(row_y-HORIZON,1.)-OFFSET
        floor_x = (row_x-W/2)*(floor_z+OFFSET)/FOCAL
        dx,dz = floor_x-self.source[0],floor_z-self.source[1]
        ground_across = dx*self.across[0]+dz*self.across[1]
        ground_along = dx*self.direction[0]+dz*self.direction[1]
        scaled_u = scaled_u+heel*(ground_across-scaled_u)
        along += heel*(ground_along-along)
        return scaled_u, along, altitude

    def crest(self,t,height,geometry):
        empty = np.zeros((H,W,4),np.uint8)
        depth = np.full((H,W),np.inf,np.float32)
        if height < .065:
            return empty,depth
        scaled_u, along, altitude = geometry
        pos_x = self.source[0]+scaled_u*self.across[0]+along*self.direction[0]
        pos_z = self.source[1]+scaled_u*self.across[1]+along*self.direction[1]
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
        tail_flow = (1-ease(.06,.30,v))*(.36*np.sin(u*3.1+v*21-t*4.1)
                                         +.29*np.sin(u*6.7-v*37+t*5.3))
        tone += tail_flow
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
        opacity *= (.80+.20*ease(.015,.19,v))*(1-.84*ease(.90,1.01,v))
        tail_clock = t+NEAR_CLEAR_LEAD*(1-ease(.15,.62,v))*ease(IMPACT,IMPACT+.16,t)
        opacity *= 1-.68*ease(IMPACT+.12, IMPACT+CREST_DECAY, tail_clock)
        opacity *= ease(.08,.69,height)*(1-ease(CREST_SPAN-.82,CREST_SPAN,abs(u)))
        # Lumps bulge toward the lit face, with a blue-grey turn under the lip.
        cap_center = .5*(foam_start+foam_end)
        cross_section = (v-cap_center)/(.5*(foam_end-foam_start))
        phase = u*2.8+.80*np.sin(u*1.47+t*2.1)-t*3.4+v*4
        crown = .82+.18*np.cos(phase)
        relief = np.maximum(1-(cross_section/crown)**2, upper_foam-.14)
        threshold = (.07+.92*ease(IMPACT+.16,IMPACT+CREST_DECAY,tail_clock)
                     +.94*ease(CREST_SPAN-.61,CREST_SPAN,abs(u)))
        shell = relief>threshold
        cap_normal = np.clip((v-.51)/.145,-1,1)
        lit_normal = np.where(v<foam_start,cap_normal,np.clip(cross_section,-1,1))
        lighting = (.48*relief-.27*lit_normal+.31*np.cos(phase-.7)
                    +.08*np.sin(u*5.2+v*20+t*3))
        shade_tone = np.digitize(lighting,[.05,.33,.60])
        palette = FOAM_COLORS
        # The color and alpha of vanishing foam erode together.
        colors = BODY_COLORS[np.minimum(index,5)]
        colors[shell] = palette[shade_tone[shell]]
        empty[:,:,:3][eligible] = colors
        opacity = np.where(shell,1.,np.clip(opacity,0,1))
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
                dip = float(np.clip((fall_time(lapse)-abs(u)*.022-FALL_START)/LIP_FALL,0,1)**1.3)
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
            if not self.incoming:
                # Frame the far battler with a wide, tall impact splash
                # drawn on its camera-facing side.
                origin[1] = min(origin[1], self.target[1]-.48)
                spread *= 1.52
                hmax *= 1.39
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
        hit_scale = 1+.36*ease(-.045,.050,age)*(1-ease(.21,.45,age))
        spread = (2.9+1.1*plunge)*self.crest_width_factor(t)*hit_scale
        top,bottom,inside = [],[],[]
        for u in np.linspace(-1.,1.,39):
            shape = max(0.,1-u*u)**.59
            edge = (.77+.15*math.sin(u*13+age*22)+.08*math.sin(u*28-age*15))
            upper_height = height*(.74+.16*shape)+.18*math.sin(u*10+age*20)*shape
            tongue = (0.32+3.42*plunge)*shape*edge*hit_scale
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
            fan = math.cos(angle)*(-self.across)+1.35*math.sin(angle)*self.direction
            velocity = (fan+.32*self.direction)*speed
            drops.append((born,fan*speed*offset,velocity,rng.uniform(2.8,5.8),
                          rng.uniform(.20,.46),rng.uniform(.012,.042)))
        return drops

    def launch_column(self,t,overlays,footprint=None):
        rise = min(1.,max(0.,(t-.021)/(SURGE_PEAK-.021)))
        lift = 1-(1-rise)**2
        descent = min(1.,max(0.,(t-SURGE_PEAK)/(SURGE_LANDING-SURGE_PEAK)))
        collapse = descent**2*(2.55-1.55*descent)
        spread = ease(.021+.47*(SURGE_PEAK-.021),SURGE_PEAK+.32,t)
        opacity = ease(.025,.078,t)*(1-ease(WAVE_FADE_START,WAVE_FADE_END,t))
        if opacity <= .01:
            return
        span = float(self.caster.width)
        # Grow altitude at a constant rate until the existing peak beat.
        # Keep the original breadth/spill clock independent of the height.
        height = self.caster.height*1.59*rise*(1-.94*collapse)
        if height < .5:
            return

        # Work in the battle's ground plane. Width runs across the line of
        # attack, reach follows it, and altitude is vertical in world space.
        world_per_pixel = (self.source[1]+OFFSET)/FOCAL
        facing = self.direction
        right_axis = -self.across
        radius = span*(.27+.16*lift+.20*spread+.34*collapse)
        half_depth = span*(.075+.043*lift+.052*spread+.05*collapse)
        reach = half_depth*1.78
        push = span*(.055+.10*spread+.12*collapse)

        def point(lateral,forward,altitude):
            x,z = self.source+world_per_pixel*(right_axis*lateral+facing*forward)
            return project(x,z,altitude*world_per_pixel)

        shaft = Image.new("RGBA",overlays[0].size)
        ink = ImageDraw.Draw(shaft)
        left,right = [],[]
        for h in np.linspace(0,1,28):
            width = radius*(.88-.12*h+.053*math.sin(h*7+t*9)+.29*spread*h**2+.34*collapse*(1-h)**2)
            width += span*.032*(math.sin(h*22-21*t)+.55*math.sin(h*51-37*t))
            ripple = span*.024*math.sin(h*9-21*t)
            forward = -.30*reach + push*h
            left.append(point(ripple-width,forward,height*h))
            right.append(point(ripple+width,forward,height*h))
        cap = []
        cap_width = width
        cap_forward = push-.30*reach
        cap_ripple = ripple
        cap_depth = half_depth*(1+.49*collapse)
        # The crest wraps around the far lip of an ellipse. Project its
        # near lip separately to expose the depth of the foam.
        for u in np.linspace(-1,1,37):
            bulge = max(0.,1-u*u)**.64
            foam = .73+.23*math.sin(18*u-21*t)+.12*math.sin(47*u-10*t)
            cap.append(point(cap_ripple+u*cap_width,cap_forward+reach*.80*bulge,
                             height+cap_depth*.40*bulge*foam))
        base = [point(radius*u,-.82*reach*max(0.,1-u*u)**.6-.30*reach,0.)
                for u in np.linspace(1,-1,21)]
        ink.polygon(left+cap+right[::-1]+base,fill=(226,247,244,int(246*opacity)))
        if footprint is not None:
            footprint.extend(base)

        # Place the shaded seams around the visible, camera-facing wall.
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
                forward = push*h-.30*reach
                first.append(point(radius*low,forward,height*h))
                last.append(point(radius*high,forward,height*h+.33*half_depth*taper))
            color = (117,200,219) if index in (0,3,5) else (163,222,231)
            ink.polygon(first+last[::-1],fill=color+(int(209*opacity),))

        rim = [point(cap_ripple+u*cap_width,cap_forward-.56*reach*max(0.,1-u*u)**.64,
                     height-.36*cap_depth*max(0.,1-u*u)**.64)
               for u in np.linspace(-1,1,37)]
        ink.polygon(cap+rim[::-1],fill=(249,255,248,int(253*opacity)))
        # As the cap spills, arcs fan out and advance toward the target.
        for side,lag in ((-1.,0.),(1.,.045)):
            amount = ease(SURGE_PEAK-.10+lag,SURGE_PEAK+.25+lag,t)
            if amount <= 0:
                continue
            top_edge,lower_edge = [],[]
            for v in np.linspace(0,1,20):
                lateral = cap_ripple+side*(cap_width*.66+span*.35*amount*v)
                forward = cap_forward+reach*.33+span*.45*amount*v
                drop = height*(.045+.59*amount*v*v)
                altitude = height-drop+half_depth*.15*math.sin(11*v+side)
                thickness = span*amount*(.027+.058*math.sin(math.pi*v)**.7)
                top_edge.append(point(lateral,forward,altitude))
                lower_edge.append(point(lateral-side*thickness,forward,altitude-thickness))
            ink.polygon(top_edge+lower_edge[::-1],fill=(155,225,233,int(230*opacity*amount)))
            ink.line(top_edge,fill=(235,252,245,int(248*opacity*amount)),
                     width=max(1,round(span*.043)))
        z = self.source[1]
        overlays[self.layer(z+.09)].alpha_composite(shaft)

        # The target-facing lip sits ahead of the caster while the rear
        # wash remains at their feet. Depth-order the lip by its world Z.
        skirt = ease(.039,.123,t)*(1-ease(.51+HOLD,.84+HOLD,t))
        if skirt <= .015:
            return
        foot_span = radius*(.96+.31*collapse)
        foot_forward = push+reach*.28
        top,bottom = [],[]
        for u in np.linspace(-1,1,39):
            r = max(0.,1-u*u)**.52
            foam = .55+.30*math.sin(u*19-34*t)+.16*math.cos(u*44+16*t)
            lateral = u*foot_span
            top.append(point(lateral,foot_forward-reach*.46*r,height*.10*r+half_depth*r*(.38+foam)))
            bottom.append(point(lateral,foot_forward+reach*r*(.68+.46*collapse),0.))
        if footprint is not None:
            footprint.extend(bottom)
        front_z = z+world_per_pixel*foot_forward*facing[1]
        brush = ImageDraw.Draw(overlays[self.layer(front_z)])
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
        x = -self.cross/(.84*radius)
        z = (self.along-.27*radius)/radius
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
        overlays = [Image.new("RGBA",layer.size) for layer in layers]
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

    def prepare_damp_ground(self):
        """Reveal wet footprints as the retreating water clears them."""
        samples=[]
        release=np.full((H,W),np.inf,np.float32)
        for stage in np.arange(COPY_START,WATER_STAGE_END+.05,.04):
            cleared=self.tail_visibility(float(stage))<=.5
            release=np.where(cleared & ~np.isfinite(release),float(stage),release)
        for stage in np.arange(COPY_START,COPY_END,.075):
            bank=self.copied_footprint(float(stage))
            if len(bank)<3:continue
            wet_age=min(.95,WATER_STAGE_END-float(stage))
            bank=self.growing_footprint(bank,wet_age)
            bank=self.irregular_footprint(bank,wet_age,float(stage))
            source_age=self.copied_animation_age(float(stage))+.045
            strength=ease(.010,.065,source_age)*(1-ease(WAVE_FADE_START,WAVE_FADE_END,source_age))
            mask=Image.new("L",(W,H));ImageDraw.Draw(mask).polygon(bank,fill=round(255*strength))
            mask=mask.filter(ImageFilter.GaussianBlur(1.1))
            wet=np.asarray(mask,dtype=np.float32)/255.*(SY>HORIZON+3.5)
            born=np.maximum(release,float(stage))
            samples.append((born,wet))
        return samples

    def damp_ground(self,t):
        if not hasattr(self,"damp_samples"):
            self.damp_samples=self.prepare_damp_ground()
        wet=np.zeros((H,W),dtype=np.float32)
        for born,footprint in self.damp_samples:
            elapsed=t-born
            strength=ease(-.04,.08,elapsed)*(1-ease(.15,DAMP_FADE+.15,elapsed))
            wet=np.maximum(wet,footprint*strength)
        result=np.zeros((H,W,4),dtype=np.uint8);result[:,:,:3]=(21,29,39)
        result[:,:,3]=np.rint(wet*255*DAMP_OPACITY).astype(np.uint8)
        return Image.fromarray(result,"RGBA")

    def exact_surge_frame(self,age,canvas_height=H):
        """Render the original surge, using its original clock and dimensions."""
        layers=[Image.new("RGBA",(W,canvas_height)) for _ in range(3)]
        self.launch_burst(round(age,10)+.045,layers)
        result=Image.new("RGBA",(W,canvas_height))
        for layer in layers:
            result.alpha_composite(layer)
        return result

    @staticmethod
    def ground_time(stage_time):
        # Map the longer approach to the established impact wash clock.
        if stage_time<=COPY_START:
            return WATER_START
        if stage_time<COPY_CONTACT:
            progress=(stage_time-COPY_START)/(COPY_CONTACT-COPY_START)
            return WATER_START+(BASE_CONTACT-WATER_START)*progress
        return stage_time-CONTACT_DELAY

    @staticmethod
    def copied_animation_age(stage_time):
        """Give the rise more time, then smoothly rejoin the original ending."""
        stage_time=wave_source_time(stage_time)
        nominal=round((stage_time-COPY_START)*COPY_RATE,10)
        peak=SURGE_PEAK-.045
        slow_peak=peak*COPY_RISE_SCALE
        end=.86+HOLD-.045
        if nominal<=slow_peak:
            return round(nominal/COPY_RISE_SCALE,10)
        if nominal>=end:
            return nominal
        # Cubic Hermite clock: continuous speed at both joins, with the
        # existing fade-out time retained after the slightly delayed apex.
        span=end-slow_peak
        u=(nominal-slow_peak)/span
        age=(2*u**3-3*u**2+1)*peak+(u**3-2*u**2+u)*span/COPY_RISE_SCALE
        age+=(-2*u**3+3*u**2)*end+(u**3-u**2)*span
        return round(age,10)

    def copied_surge(self,stage_time):
        """Widen and slow the original surge frames, then translate the copy."""
        start=COPY_START
        elapsed=round(wave_source_time(stage_time)-start,10)
        age=self.copied_animation_age(stage_time)
        layers=[Image.new("RGBA",(W,H)) for _ in range(3)]
        depth=np.full((H,W),np.inf,np.float32)
        if age<0. or age>.86+HOLD:
            return layers,np.zeros((H,W,4),np.uint8),depth
        contact=COPY_CONTACT
        fraction=elapsed/max(.05,contact-start)
        if fraction>1.:
            fraction=1.+.32*math.log1p((fraction-1.)/.32)
        source=np.array(project(*self.source))
        target=np.array(project(*self.target))
        fraction=-COPY_BACKTRACK+(1+COPY_BACKTRACK)*fraction
        displacement=np.rint((target-source)*fraction).astype(int)
        # Give the original drawing more canvas below the stage, preserving
        # the source pixels while keeping its translated base from clipping.
        frame=self.exact_surge_frame(age,canvas_height=2*H)
        # Scale the copied frame around its feet. The opening surge
        # continues to use its original dimensions and animation.
        scaled_width=round(frame.width*COPY_THICKNESS)
        frame=frame.resize((scaled_width,round(frame.height*COPY_HEIGHT)),Image.Resampling.NEAREST)
        anchor_offset=round(source[0]*(1-COPY_THICKNESS))
        shifted=Image.new("RGBA",(W,H))
        anchor_offset_y=round(source[1]*(1-COPY_HEIGHT))
        shifted.alpha_composite(frame,dest=(int(displacement[0])+anchor_offset,int(displacement[1])+anchor_offset_y))
        position=source+displacement
        z=FOCAL*CAMERA_Y/max(1.,position[1]-HORIZON)-OFFSET
        layer=self.layer(z+.09)
        # Contact briefly covers the target before the copy passes it.
        if abs(stage_time-contact)<.09:
            layer=2 if self.incoming else 1
        layers[layer]=shifted
        array=np.asarray(shifted)
        depth[array[:,:,3]>8]=z
        return layers,array,depth

    def copied_footprint(self,stage_time):
        if not hasattr(self,"footprint_cache"):
            self.footprint_cache={}
        key=round(stage_time,7)
        if key in self.footprint_cache:
            return self.footprint_cache[key]
        elapsed=round(wave_source_time(stage_time)-COPY_START,10)
        age=self.copied_animation_age(stage_time)
        if age<0. or age>.86+HOLD:
            return []
        local=age+.045
        layers=[Image.new("RGBA",(W,2*H)) for _ in range(3)]
        bank=[]
        self.launch_column(local,layers,footprint=bank)
        if len(bank)<3:
            return []
        source=np.array(project(*self.source));target=np.array(project(*self.target))
        fraction=elapsed/max(.05,COPY_CONTACT-COPY_START)
        if fraction>1.:
            fraction=1.+.32*math.log1p((fraction-1.)/.32)
        fraction=-COPY_BACKTRACK+(1+COPY_BACKTRACK)*fraction
        displacement=np.rint((target-source)*fraction)
        # Use the same scaling and integer anchors as the visible copy.
        scale=np.array([round(W*COPY_THICKNESS)/W,round(2*H*COPY_HEIGHT)/(2*H)])
        anchor=np.array([round(source[0]*(1-COPY_THICKNESS)),round(source[1]*(1-COPY_HEIGHT))])
        bank=np.asarray(bank)*scale+anchor+displacement
        result=[tuple(p) for p in bank]
        self.footprint_cache[key]=result
        return result

    def recession_start_field(self):
        """Stable row times: the near edge clears before the distant edge."""
        if hasattr(self,"recession_starts"):
            return self.recession_starts
        reference=Image.new("L",(W,H))
        ink=ImageDraw.Draw(reference)
        for born in np.arange(COPY_START,COPY_END,.065):
            bank=self.copied_footprint(float(born))
            if len(bank)<3:
                continue
            bank=self.deposit_footprint(bank,.65,float(born),reference=True)
            ink.polygon(bank,fill=255)
        mask=(np.asarray(reference)>0)&(SY>HORIZON+3.5)
        # Retain the shallow perspective angle and a gently curved front.
        row=SY-TAIL_BOUNDARY_SLOPE*(SX-W/2)
        row+=.50*np.sin(.055*SX)+.22*np.sin(.103*SX+.7)
        top,bottom=np.quantile(row[mask],[.02,.98]) if mask.any() else (100.,200.)
        progress=np.clip((bottom-row)/max(1.,bottom-top),0.,1.)
        self.recession_starts=TRAIL_BOTTOM_CLEAR+(TRAIL_TOP_CLEAR-TRAIL_BOTTOM_CLEAR)*progress
        return self.recession_starts

    def tail_visibility(self,stage_time):
        starts=self.recession_start_field()
        # Only a narrow horizontal band dissolves at a time. The top of
        # the sheet keeps spreading while the already-cleared bottom dries.
        self.rear_depth=(starts+TRAIL_ROW_FADE-stage_time)*TAIL_FADE_WIDTH/TRAIL_ROW_FADE-.5*TAIL_FADE_WIDTH
        return 1-ease(starts,starts+TRAIL_ROW_FADE,stage_time)

    def clean_side_edges(self,coverage,clearance,release):
        """Straighten the long banks, retaining rounded ends and mild lobes."""
        rows=np.flatnonzero(np.any(coverage>1e-4,axis=1))
        if len(rows)<12:
            return coverage
        left=np.array([np.flatnonzero(coverage[y]>1e-4)[0] for y in rows],dtype=float)
        right=np.array([np.flatnonzero(coverage[y]>1e-4)[-1] for y in rows],dtype=float)
        progress=(rows-rows[0])/max(1.,rows[-1]-rows[0])
        middle=(progress>.20)&(progress<.80)
        if middle.sum()<4:
            return coverage
        end_guard=ease(.04,.22,progress)*(1-ease(.78,.96,progress))
        cleaned=np.zeros_like(coverage)
        def bank(profile,sign):
            kernel=np.array([1,2,3,4,5,4,3,2,1],dtype=float)/25
            smooth=np.convolve(np.pad(profile,4,mode="edge"),kernel,mode="valid")
            straight=np.polyval(np.polyfit(rows[middle],smooth[middle],1),rows)
            shape=smooth+(straight-smooth)*TRAIL_SIDE_STRAIGHTNESS
            ripple=.50*np.sin(rows*.115+sign*.8)+.25*np.sin(rows*.237+sign*1.7)
            weight=end_guard.copy()
            samples=np.clip(np.rint(profile).astype(int),0,W-1)
            # Preserve the exact wave-to-puddle join during the approach.
            weight*=release+(1-release)*ease(2.,12.,clearance[rows,samples])
            return profile+(shape+ripple-profile)*weight
        new_left,new_right=bank(left,-1),bank(right,1)
        for i,y in enumerate(rows):
            lo=max(0,int(round(new_left[i])));hi=min(W-1,int(round(new_right[i])))
            if hi<lo:
                continue
            x=np.arange(lo,hi+1)
            original=left[i]+(x-new_left[i])*(right[i]-left[i])/max(1.,new_right[i]-new_left[i])
            cleaned[y,lo:hi+1]=np.interp(original,np.arange(W),coverage[y])
        return cleaned

    def wave_contact_fill(self,stage_time,crest=None):
        return np.zeros((H,W),np.float32)

    def deposit_footprint(self,bank,wet_age,born,reference=False):
        return self.growing_footprint(bank,wet_age,reference=reference)

    def growing_footprint(self,bank,wet_age,reference=False):
        """Spread the deposited sheet sideways on the perspective floor."""
        wet_age=max(0.,wet_age)
        release=trail_spread_release(wet_age,reference=reference)
        width=TRAIL_INITIAL_WIDTH+(1-TRAIL_INITIAL_WIDTH)*.82*release+TRAIL_LATE_SPREAD*wet_age
        points=np.asarray(bank,dtype=float)
        center=np.mean(points,axis=0)
        center_scale=max((center[1]-HORIZON)/CAMERA_Y,1e-3)
        origin=np.array([(center[0]-W/2)/center_scale,FOCAL/center_scale-OFFSET])
        floor_scale=np.maximum((points[:,1]-HORIZON)/CAMERA_Y,1e-3)
        world=np.column_stack(((points[:,0]-W/2)/floor_scale,FOCAL/floor_scale-OFFSET))
        lateral=(world-origin)@self.across
        world+=(width-1)*lateral[:,None]*self.across
        # Pinch the caster end into the narrow mouth in the reference,
        # widening smoothly toward the target while preserving perspective.
        along=(world-self.source)@self.direction
        across=(world-self.source)@self.across
        taper=TRAIL_CASTER_WIDTH+(1-TRAIL_CASTER_WIDTH)*ease(0.,self.distance*TRAIL_TAPER_DISTANCE,along)
        world+=(taper-1)[:,None]*across[:,None]*self.across
        # Keep the initial narrow deposit and full wave attachment intact.
        # Spread the released water a little farther on the ground plane.
        extra=1+(TRAIL_EXPANSION-1)*release
        world=origin+(world-origin)*extra
        x,y=project(world[:,0],np.maximum(world[:,1],-1.05))
        return list(zip(x,y))

    def irregular_footprint(self,bank,wet_age,born):
        points=np.asarray(bank,dtype=float)
        center=np.mean(points,axis=0)
        tangent=np.roll(points,-1,axis=0)-np.roll(points,1,axis=0)
        normals=np.column_stack((tangent[:,1],-tangent[:,0]))
        normals/=np.maximum(np.linalg.norm(normals,axis=1,keepdims=True),1e-5)
        flip=np.sum(normals*(points-center),axis=1)<0
        normals[flip]*=-1
        angle=np.arctan2(points[:,1]-center[1],points[:,0]-center[0])
        lobes=.65*np.sin(5*angle+.2*born-.3*wet_age)+.35*np.sin(9*angle+.6*born+.45*wet_age)
        depth=.55+.45*np.clip((points[:,1]-HORIZON)/(project(*NEAR)[1]-HORIZON),0.,1.)
        offset=TRAIL_IRREGULARITY*ease(.025,.25,wet_age)*depth*lobes
        return [tuple(p) for p in points+normals*offset[:,None]]

    def matched_wake(self,stage_time):
        """Sweep the wave's own ground edges into one connected trail."""
        coverage=np.zeros((H,W),np.float32)
        if stage_time<COPY_START:
            return np.full((H,W),1e3),coverage,np.ones((H,W))
        times=list(np.arange(COPY_START,min(stage_time,COPY_END),.04))+[stage_time]
        current=self.copied_footprint(stage_time)
        for born in times:
            bank=self.copied_footprint(float(born))
            if len(bank)<3:
                continue
            elapsed=stage_time-born
            bank=np.asarray(self.deposit_footprint(bank,elapsed,float(born)))
            # Deposited water grows directly from its narrow footprint.
            # The separate teal contact film joins it to the moving wave;
            # starting every stamp full-width made it contract, then spread.
            bank=self.irregular_footprint(bank,elapsed,float(born))
            # Lifetime is controlled by the bottom-up ground mask, not by
            # simultaneous fading of large footprint stamps.
            strength=1.
            age=self.copied_animation_age(born)
            strength*=ease(.010,.065,age+.045)*(1-ease(WAVE_FADE_START,WAVE_FADE_END,age+.045))
            mask=Image.new("L",(W,H))
            ImageDraw.Draw(mask).polygon(bank,fill=255)
            coverage=np.maximum(coverage,np.asarray(mask,dtype=np.float32)/255.*strength)
        source=np.array(project(*self.source));target=np.array(project(*self.target))
        heading=(target-source)/np.linalg.norm(target-source)
        # Follow the rear contact arc, not the most forward corner of the
        # whole footprint. A single forward limit let the ground sheet lead
        # the oblique wave on one side, especially as its white lip fell.
        contact=current or self.copied_footprint(min(stage_time,COPY_END-.09))
        if contact:
            rear=np.asarray(contact[:21])
            side=np.array([-heading[1],heading[0]])
            across=rear@side
            order=np.argsort(across)
            front=np.interp(SX*side[0]+SY*side[1],across[order],(rear@heading)[order])
            clearance=front-(SX*heading[0]+SY*heading[1])
        else:
            clearance=np.full((H,W),1e6)
        # Once the wave has passed, let the deposited front bank keep
        # spreading with its contour instead of hitting a straight clip.
        free_spread=ease(COPY_END-.10,COPY_END+.30,stage_time)
        # Release the ground contour as the last raised water dissolves,
        # rather than holding a cut-out arc after the wave has vanished.
        source_age=self.copied_animation_age(stage_time)+.045
        free_spread=max(free_spread,ease(.90,1.035,source_age))
        # A one-pixel overlap hides the join under the wave; all exposed
        # water stays behind this perspective-projected contact arc.
        coverage*=(1-free_spread)*(1-ease(.25,1.25,-clearance))+free_spread
        coverage=self.clean_side_edges(coverage,clearance,free_spread)
        if hasattr(self,"connect_wave_edges"):
            coverage=self.connect_wave_edges(stage_time,coverage)
        coverage*=(1-free_spread)*(1-ease(.25,1.25,-clearance))+free_spread
        active=coverage>1e-4
        silhouette=Image.fromarray((active*255).astype(np.uint8),"L")
        inset=np.zeros((H,W),np.float32)
        previous=0
        for radius in (1,3,6,10,16):
            eroded=np.asarray(silhouette.filter(ImageFilter.MinFilter(2*radius+1)))>0
            inset+=(radius-previous)*eroded;previous=radius
        edge=np.where(active,-.5-inset,1e3)
        return edge,coverage,clearance

    def crash_foam(self,stage_time):
        """Rounded opaque boils at the crash line, breaking into a low web."""
        result=Image.new("RGBA",(W,H))
        first=COPY_CONTACT-.16
        if stage_time<first or stage_time>COPY_END+CRASH_FOAM_LIFE or CRASH_FOAM_STRENGTH<=0:
            return result
        floor_visibility=self.tail_visibility(stage_time)
        for born in np.arange(first,min(stage_time,COPY_END)+1e-6,.085):
            elapsed=stage_time-float(born)
            if not 0<elapsed<CRASH_FOAM_LIFE:
                continue
            bank=self.copied_footprint(float(born))
            if len(bank)<21:
                continue
            source_age=self.copied_animation_age(float(born))+.045
            emission=ease(.40,.61,source_age)*(1-ease(.91,WAVE_FADE_END,source_age))
            life=elapsed/CRASH_FOAM_LIFE
            strength=ease(0.,.065,elapsed)*(1-ease(.22,CRASH_FOAM_LIFE,elapsed))*emission*CRASH_FOAM_STRENGTH
            if strength<.01:
                continue
            for index in range(1,20,2):
                point=np.asarray(bank[index])
                if point[1]<=HORIZON+3.5:
                    continue
                depth_scale=max(3.,(point[1]-HORIZON)/CAMERA_Y)
                wx=(point[0]-W/2)/depth_scale
                wz=FOCAL/depth_scale-OFFSET
                variation=.5+.5*math.sin(index*2.71+born*19.)
                radius=(1.7+1.0*variation)*(depth_scale/25.)**.62
                world_radius=radius/depth_scale
                center=np.array([wx,wz])+self.direction*world_radius*(.35+1.2*life)
                center+=self.across*world_radius*.32*math.sin(index*3.1+born*11.)
                r=world_radius*(1+1.65*life)
                local=Image.new("RGBA",(W,H));ink=ImageDraw.Draw(local)
                angles=np.linspace(0,2*math.pi,25)
                ring=r*(1+.11*np.sin(5*angles+index)+.05*np.sin(9*angles-born*13.))
                px,py=project(center[0]+ring*np.cos(angles),center[1]+ring*np.sin(angles))
                clump=.48+.52*ease(-.55,.75,math.sin(index*1.83+born*11.))
                alpha=round(255*min(1.,strength*clump))
                # A blue underside and raised white lobes give the fresh
                # collision foam a little volume above the water film.
                ink.polygon(list(zip(px,py+.8)),fill=(157,222,231,round(.66*alpha)))
                ink.polygon(list(zip(px,py)),fill=(248,255,248,alpha))
                cx,cy=project(*center)
                lift=radius*1.8*math.exp(-elapsed/.22)
                for offset in (-.55,.18,.68):
                    rr=radius*(.45+.20*math.cos(index+offset))*(1-.40*life)
                    x=cx+radius*offset;y=cy-lift*(1-offset*offset)
                    ink.ellipse((x-rr,y-rr*.75,x+rr,y+rr*.45),fill=(251,255,249,alpha))
                # Holes grow as the raised foam settles into rounded cells.
                hole=ease(.11,.43,elapsed)
                for offset,scale in ((-.36,.42),(.40,.31)):
                    hr=radius*hole*scale*(1+.75*life)
                    if hr>.25:
                        hx,hy=project(*(center+self.across*world_radius*offset))
                        ink.ellipse((hx-hr,hy-.48*hr,hx+hr,hy+.48*hr),fill=(0,0,0,0))
                # Fresh crash foam survives briefly at the landing point;
                # settled patches then share the ground's bottom-up fade.
                a=np.asarray(local).copy()
                settle=ease(.12,.44,elapsed)
                a[:,:,3]=np.rint(a[:,:,3]*(1-settle+settle*floor_visibility)).astype(np.uint8)
                # Overlapping emissions form one foam mass; do not stack
                # faint old patches back into an opaque rectangular strip.
                previous=np.asarray(result)
                take=a[:,:,3]>previous[:,:,3]
                combined=previous.copy();combined[take]=a[take]
                result=Image.fromarray(combined,"RGBA")
        return result

    def effect(self,t):
        # Retime the wave and runoff together; the launch column
        # keeps its own stage clock.
        water_t = water_time(self.ground_time(t))
        travel_t = IMPACT+(water_t-IMPACT)*WAVE_RATE if water_t<IMPACT else water_t
        center,height = self.center_and_height(travel_t)
        geometry = self.crest_geometry(travel_t,center,height)
        moving,crest,depth = self.copied_surge(t)
        puddle = self.puddle(travel_t,geometry,crest,t)
        ground=self.damp_ground(t)
        ground.alpha_composite(Image.fromarray(puddle,"RGBA"))
        ground.alpha_composite(self.crash_foam(t))
        layers = [ground,Image.new("RGBA",(W,H)),Image.new("RGBA",(W,H))]
        for layer,copy in zip(layers,moving):
            layer.alpha_composite(copy)
        return layers

    def preview(self,t,layers,background):
        image = background.copy()
        water_t = water_time(self.ground_time(t))
        for i,(position,sprite) in enumerate(zip([FAR,NEAR],SPRITES)):
            image.alpha_composite(layers[i].resize((2*W,2*H),Image.Resampling.NEAREST))
            x,y = project(*position)
            is_target = np.array_equal(position,self.target)
            kick = .114*math.exp(-11*(water_t-(IMPACT+.04))) if water_t>IMPACT+.04 and is_target else 0
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


class TrailWater(Surf):
    """Recent ground-water renderer driven by the classic wave's own mesh."""
    def __init__(self,classic,wave_start,impact,wave_end,wave_rate=1.13):
        global COPY_START,COPY_CONTACT,COPY_END,IMPACT,WATER_STAGE_END
        COPY_START=wave_start
        COPY_CONTACT=impact
        COPY_END=wave_end
        IMPACT=impact
        WATER_STAGE_END=max(wave_end,TRAIL_TOP_CLEAR+TRAIL_ROW_FADE)
        self.classic=classic
        self.classic_wave_rate=wave_rate
        super().__init__(classic.incoming)

    def copied_footprint(self,stage_time):
        if not hasattr(self,"classic_footprint_cache"):
            self.classic_footprint_cache={}
        key=round(stage_time,7)
        if key not in self.classic_footprint_cache:
            self.classic_footprint_cache[key]=self.classic.wave_ground_footprint(stage_time)
        return self.classic_footprint_cache[key]

    def connect_wave_edges(self,stage_time,coverage):
        """Curved floor-plane shoulders from both wave tips into the wake."""
        bank=self.copied_footprint(stage_time)
        if len(bank)<21 or stage_time>=COPY_END:
            return coverage
        visible=(coverage*self.tail_visibility(stage_time)>.12)&(SY>HORIZON+3.5)
        if visible.sum()<12:
            return coverage
        def floor(points):
            points=np.asarray(points,dtype=float)
            scale=np.maximum((points[:,1]-HORIZON)/CAMERA_Y,1e-3)
            return np.column_stack(((points[:,0]-W/2)/scale,FOCAL/scale-OFFSET))
        rear=floor(np.asarray(bank[:21]))
        trail=floor(np.column_stack((SX[visible],SY[visible])))
        along=(trail-self.source)@self.direction
        across=(trail-self.source)@self.across
        # Join the exposed existing sheet rather than spawning a new pool.
        back=float(np.quantile(along,.14))
        front=float(np.mean((rear-self.source)@self.direction))
        length=front-back
        if length<=.04:
            return coverage
        section=abs(along-back)<max(.025,.10*length)
        if section.sum()<4:
            return coverage
        low,high=np.quantile(across[section],[.02,.98])
        tips=[rear[0],rear[-1]]
        anchors=[self.source+self.direction*back+self.across*(low if (tip-self.source)@self.across<np.mean([low,high]) else high) for tip in tips]
        def curve(tip,anchor):
            delta=float((tip-anchor)@self.direction)
            control1=tip-self.direction*max(.02,delta)*.36
            control2=anchor+self.direction*max(.02,delta)*.32
            t=np.linspace(0.,1.,25)[:,None]
            return (1-t)**3*tip+3*(1-t)**2*t*control1+3*(1-t)*t*t*control2+t**3*anchor
        first=curve(tips[0],anchors[0]);last=curve(tips[1],anchors[1])
        contour=np.vstack((rear,last[1:],first[::-1]))
        px,py=project(contour[:,0],np.maximum(contour[:,1],-1.05))
        mask=Image.new("L",(W,H));ImageDraw.Draw(mask).polygon(list(zip(px,py)),fill=255)
        # Use the puddle's existing pigment, edge foam and retreat mask.
        # A short formation blend avoids introducing an early full fan.
        strength=ease(COPY_START+.08,COPY_START+.28,stage_time)*(1-ease(COPY_END-.18,COPY_END,stage_time))
        return np.maximum(coverage,np.asarray(mask,dtype=np.float32)/255.*strength)

    def deposit_footprint(self,bank,wet_age,born,reference=False):
        # Spread in the approved local shape, then carry the complete
        # deposited sheet by the same current offset as the raised wave.
        if not hasattr(self,"uncarried_cache"):
            self.uncarried_cache={}
        key=round(born,7)
        if key not in self.uncarried_cache:
            self.uncarried_cache[key]=self.classic.wave_ground_footprint(born,apply_carry=False)
        bank=self.uncarried_cache[key]
        narrow=np.asarray(self.growing_footprint(bank,wet_age,reference=reference))
        spread=ease(IMPACT-.16,IMPACT,born)
        if spread<=0:
            return self.carry_floor(narrow,0. if reference else self.classic.water_carry(born+wet_age))
        # Released water begins narrower and spreads toward its mature
        # fan. A separate teal contact film seals it to the full wave base.
        points=np.asarray(bank,dtype=float)
        scale=np.maximum((points[:,1]-HORIZON)/CAMERA_Y,1e-3)
        world=np.column_stack(((points[:,0]-W/2)/scale,FOCAL/scale-OFFSET))
        center=np.mean(world,axis=0)
        lateral=(world-center)@self.across
        forward=(world-center)@self.direction
        release=trail_spread_release(wet_age,reference=reference)
        # Keep a nonzero late spread after the initial release settles.
        # This clock is never capped, including while opacity fades out.
        width=TRAIL_RELEASE_START+(TRAIL_RELEASE_FULL-TRAIL_RELEASE_START)*release+TRAIL_LATE_SPREAD*max(0.,wet_age)
        extra=(TRAIL_EXPANSION-1)*release+TRAIL_LATE_SPREAD*max(0.,wet_age)
        world+=(width-1)*lateral[:,None]*self.across
        world+=.35*extra*forward[:,None]*self.direction
        x,y=project(world[:,0],np.maximum(world[:,1],-1.05))
        full=np.column_stack((x,y))
        return self.carry_floor(narrow+(full-narrow)*spread,0. if reference else self.classic.water_carry(born+wet_age))

    def carry_floor(self,points,distance):
        points=np.asarray(points,dtype=float)
        if distance==0:
            return [tuple(p) for p in points]
        scale=np.maximum((points[:,1]-HORIZON)/CAMERA_Y,1e-3)
        world=np.column_stack(((points[:,0]-W/2)/scale,FOCAL/scale-OFFSET))
        world[:,0],world[:,1]=self.classic.advect_floor_world(world[:,0],world[:,1],distance)
        x,y=project(world[:,0],np.maximum(world[:,1],-1.05))
        return list(zip(x,y))

    def tail_visibility(self,stage_time):
        starts=self.recession_start_field()
        distance=self.classic.water_carry(stage_time)
        if distance>0:
            # Transport the existing near-to-far fade with the water,
            # rather than letting a stationary mask stop the moving edge.
            x,z=self.classic.advect_floor_world(WX,WZ,distance,inverse=True)
            px,py=project(x,np.maximum(z,-1.05))
            px=np.clip(px,0,W-1);py=np.clip(py,0,H-1)
            ix=np.floor(px).astype(int);iy=np.floor(py).astype(int)
            jx=np.minimum(ix+1,W-1);jy=np.minimum(iy+1,H-1)
            fx=px-ix;fy=py-iy
            starts=(starts[iy,ix]*(1-fx)+starts[iy,jx]*fx)*(1-fy)+(starts[jy,ix]*(1-fx)+starts[jy,jx]*fx)*fy
        self.rear_depth=(starts+TRAIL_ROW_FADE-stage_time)*TAIL_FADE_WIDTH/TRAIL_ROW_FADE-.5*TAIL_FADE_WIDTH
        return 1-ease(starts,starts+TRAIL_ROW_FADE,stage_time)

    def copied_animation_age(self,stage_time):
        # Map deposit strength only; the classic wave animation is never
        # rendered or retimed by this module.
        sample=stage_time if stage_time<=IMPACT else self.classic.wave_time(stage_time)
        return (sample-COPY_START)/max(.01,self.classic.original_wave_clear_time()-COPY_START)*1.035

    def ground(self,stage_time,crest):
        water=self.puddle(stage_time,None,crest,stage_time)
        # Trim only the opening water frames; preserve all later clocks.
        if stage_time<COPY_START+TRAIL_APPEARANCE_DELAY+TRAIL_START_CUT:
            water[:]=0
        ground=self.damp_ground(stage_time)
        ground.alpha_composite(Image.fromarray(water,"RGBA"))
        return ground

    def wave_contact_fill(self,stage_time,crest=None):
        result=np.zeros((H,W),np.float32)
        bank=self.copied_footprint(stage_time)
        if not bank or stage_time>=COPY_END:
            return result
        points=np.asarray(bank)
        source=np.array(project(*self.source));target=np.array(project(*self.target))
        heading=(target-source)/np.linalg.norm(target-source)
        rear=points[1:20]
        depth=TRAIL_CONTACT_WIDTH
        strip=Image.new("L",(W,H));ink=ImageDraw.Draw(strip)
        ink.polygon([tuple(p) for p in rear]+[tuple(p) for p in (rear-heading*depth)[::-1]],fill=255)
        ink.line([tuple(p) for p in rear],fill=255,width=max(2,round(depth*.66)),joint="curve")
        support=np.asarray(strip,dtype=np.float32)/255.
        if crest is not None:
            floor=Image.new("L",(W,H));ImageDraw.Draw(floor).polygon(bank,fill=255)
            support=np.maximum(support,(np.asarray(floor)>0)*(crest[:,:,3]>8))
        support*=SY>HORIZON+3.5
        support=Image.fromarray(np.rint(support*255).astype(np.uint8),"L").filter(ImageFilter.GaussianBlur(.40))
        strength=1-ease(COPY_END-.22,COPY_END,stage_time)
        # Match the classic approach clock without changing its motion.
        center,height=self.classic.wave_pose(stage_time)
        depth=max(-1.05,float((self.classic.source+self.classic.direction*center)[1]))+OFFSET
        pixel_height=height*FOCAL/depth
        strength*=ease(.75,10.,pixel_height)*self.classic.wave_opacity(stage_time)
        return np.asarray(support,dtype=np.float32)/255.*strength

    def prepare_actual_wet_ground(self):
        # Record the deposited trail itself, including its leading-edge
        # clip and retreat, instead of wetting the whole wave bounding area.
        last=np.full((H,W),np.inf,np.float32)
        wet=np.zeros((H,W),np.float32)
        for stage in np.arange(COPY_START+TRAIL_APPEARANCE_DELAY,WATER_STAGE_END,.06):
            _,coverage,_=self.matched_wake(float(stage))
            contact=self.wave_contact_fill(float(stage))
            visible=np.maximum(coverage*self.tail_visibility(float(stage)),contact)*self.puddle_appearance(float(stage))
            present=(visible>.20)&(SY>HORIZON+3.5)
            last[present]=float(stage)
            wet=np.maximum(wet,np.where(present,np.maximum(coverage,contact),0.))
        wet=np.asarray(Image.fromarray(np.rint(wet*255).astype(np.uint8),"L").filter(ImageFilter.GaussianBlur(.9)),dtype=np.float32)/255.
        return last,wet

    def damp_ground(self,t):
        if not hasattr(self,"actual_wet_ground"):
            self.actual_wet_ground=self.prepare_actual_wet_ground()
        last,wet=self.actual_wet_ground
        elapsed=t-last
        fade=ease(-.025,.09,elapsed)*(1-ease(.12,DAMP_FADE+.12,elapsed))
        result=np.zeros((H,W,4),np.uint8)
        result[:,:,:3]=(21,29,39)
        alpha=np.rint(255*DAMP_OPACITY*wet*fade).astype(np.uint8)
        result[:,:,3]=np.asarray(Image.fromarray(alpha,"L").filter(ImageFilter.GaussianBlur(1.1)))
        return Image.fromarray(result,"RGBA")


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
        timing["openingSurgeEnabled"]=False
        timing["dissipationPuddleEnabled"]=False
        timing["waterTrailEnabled"]=True
        timing["restoredWaveVersion"]="surf-narrower-slower-rise-comparison.mp4"
        timing["trailHoldExtraMs"]=round(1000*TRAIL_HOLD_EXTRA)
        timing["trailRearRecedeStartMs"]=round(1000*TRAIL_BOTTOM_CLEAR)
        timing["trailFadesToTransparency"]=True
        timing["trailRearBoundarySlope"]=TAIL_BOUNDARY_SLOPE
        timing["trailStartWidthFraction"]=TRAIL_INITIAL_WIDTH
        timing["trailSpreadMs"]=round(1000*TRAIL_SPREAD_SECONDS)
        timing["trailRecedePlaybackRate"]=TRAIL_RECEDE_RATE
        timing["trailContinuesExpandingDuringFade"]=True
        timing["trailCasterWidthFraction"]=TRAIL_CASTER_WIDTH
        timing["waveHeightRiseCurve"]="linear"
        timing["trailAttachmentMs"]=round(1000*TRAIL_ATTACHMENT_SECONDS)
        timing["trailFollowsRearContactArc"]=True
        timing["trailRecedeAdvanceMs"]=round(1000*TRAIL_RECEDE_ADVANCE)
        timing["trailExpansionMultiplier"]=TRAIL_EXPANSION
        timing["trailRecessionDirection"]="screen-bottom-to-top"
        timing["trailTopRecedeStartMs"]=round(1000*TRAIL_TOP_CLEAR)
        timing["trailRowFadeMs"]=round(1000*TRAIL_ROW_FADE)
        timing["trailSideStraightness"]=TRAIL_SIDE_STRAIGHTNESS
        timing["wavePostImpactRate"]=COPY_POST_RATE
        timing["wavePostImpactBlendMs"]=round(1000*COPY_POST_BLEND)
        timing["crashFoamEnabled"]=True
        timing["crashFoamLifetimeMs"]=round(1000*CRASH_FOAM_LIFE)
        timing["waveFadeSourceSeconds"]={"start":WAVE_FADE_START,"end":WAVE_FADE_END}
        for legacy in ("trailHoldExtraMs","trailRecedePlaybackRate","trailRecedeAdvanceMs"):
            timing.pop(legacy,None)
        timing["beatsMs"].update(surgeBreaksSurface=0,waveRises=round(1000*CONTROLS.get("surgeCopyStartSeconds",.55)),waveAdvances=round(1000*CONTROLS.get("surgeCopyStartSeconds",.55)),
            crestClears=round(1000*COPY_END),surgePeaks=round(1000*(SURGE_PEAK-.045)),surgeHangEnds=round(1000*(SURGE_PEAK-.045)),
            surgeSettles=round(1000*(.86+HOLD-.045)),surgeWashClears=round(1000*(1.11+HOLD-.045)),
            lipCurls=round(1000*(COPY_START+(SURGE_PEAK-.10-.045)*COPY_RISE_SCALE/COPY_RATE)),crestPlunges=round(1000*(COPY_START+(SURGE_PEAK-.045)*COPY_RISE_SCALE/COPY_RATE)),
            targetImpact=round(1000*COPY_CONTACT),crestPassesTarget=water_beat_ms(IMPACT+.21)+round(1000*CONTACT_DELAY),
            washSpreads=water_beat_ms(IMPACT+.05/RATE)+round(1000*CONTACT_DELAY),washSlows=water_beat_ms(IMPACT+.26/RATE)+round(1000*CONTACT_DELAY),
            washClears=water_beat_ms(IMPACT+RUNOFF_DURATION)+round(1000*CONTACT_DELAY),waterClears=round(1000*WATER_STAGE_END),dampGroundClears=round(1000*END))
        for beat in ("surgeBreaksSurface","surgePeaks","surgeHangEnds","surgeSettles","surgeWashClears"):
            timing["beatsMs"].pop(beat,None)
        for beat in ("washSpreads","washSlows","washClears"):
            timing["beatsMs"].pop(beat,None)
        timing["beatsMs"]["trailClears"]=round(1000*WATER_STAGE_END)
        (ROOT/"assets"/"surf-timing.json").write_text(json.dumps(timing,indent=2)+"\n")
