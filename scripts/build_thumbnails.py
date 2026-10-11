#!/usr/bin/env python3
"""Build local, script-free SVG steering guides from library.json.

No network calls or image model calls are made. These are illustrative diagrams,
not generated photographs. Run from any directory; use --output for a probe in
TMPDIR. Existing IDs and library content are never rewritten by this builder.
"""
from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INK = '#26344a'
SKIN = '#c88d6c'
BLUE = '#6387ad'
PAPER = '#eef2f6'


def esc(text):
    return html.escape(str(text), quote=True)


def tag(name, body='', **attrs):
    attributes = ' '.join(f'{key.replace("_", "-")}="{esc(value)}"' for key, value in attrs.items())
    return f'<{name} {attributes}>{body}</{name}>'


def rect(x, y, w, h, color, **kw):
    return tag('rect', x=x, y=y, width=w, height=h, fill=color, **kw)


def circle(x, y, r, color, **kw):
    return tag('circle', cx=x, cy=y, r=r, fill=color, **kw)


def ellipse(x, y, rx, ry, color, **kw):
    return tag('ellipse', cx=x, cy=y, rx=rx, ry=ry, fill=color, **kw)


def line(x1, y1, x2, y2, color=INK, width=3, **kw):
    return tag('line', x1=x1, y1=y1, x2=x2, y2=y2, stroke=color, stroke_width=width, stroke_linecap='round', **kw)


def path(d, color='none', stroke=INK, width=3, **kw):
    return tag('path', d=d, fill=color, stroke=stroke, stroke_width=width, stroke_linejoin='round', stroke_linecap='round', **kw)


def poly(points, color, **kw):
    return tag('polygon', points=' '.join(f'{x},{y}' for x, y in points), fill=color, **kw)


def words(text, x=140, y=150, size=11, color=INK, **kw):
    return tag('text', esc(text), x=x, y=y, fill=color, font_family='sans-serif', font_size=size, text_anchor='middle', **kw)


def palette(aid, vid, index=0):
    colors = {
        'pale_pinkish':'#edc6bc','porcelain':'#f4dfd0','fair':'#e6baa0',
        'light_beige':'#d5ab87','medium_beige':'#b88a61','warm_tan':'#a87852',
        'golden_brown':'#976139','deep_brown':'#65402e','rich_ebony':'#3f2d26',
        'golden_blonde':'#d0a34c','light_auburn_copper':'#a97152','platinum':'#e5dfcf',
        'ash_blonde':'#b1a38c','jet_black':'#23242b','espresso':'#3d2922','chestnut':'#795139',
        'chocolate':'#664333','silver':'#b9c0c6','salt_and_pepper':'#72777a','copper_red':'#b86536','dark_auburn':'#65312c',
        'pale_pink':'#e8b8c5','emerald':'#247b55','deep_red':'#932e36','ivory':'#f2e8d2',
        'champagne':'#d7bf94','black':'#24252b','sage':'#9da987','navy':'#243758',
        'cobalt':'#365eca','ochre':'#b58e35','terracotta':'#b86649','lavender':'#b4a0d4',
        'plum':'#673b65','teal':'#267a81','charcoal':'#50545d','white':'#faf9f4',
        'icy_blue':'#8fc1dd','pale_green':'#a8c891','aqua':'#64b4b6','gray_blue':'#879faf',
        'dark_brown':'#4e3226','amber':'#bd8b31','hazel':'#8e8442','olive_green':'#697944','warm_gray':'#9a9690',
        'natural_rose':'#b4767a','peach_nude':'#ce9d85','berry':'#8b435c','brick_red':'#a94e42',
        'classic_red':'#c2353b','mauve':'#a47c95','warm_brown':'#805445','clear_balm':'#d4a899',
        'yellow_gold':'#d0a147','rose_gold':'#bd8880','brushed_steel':'#8697a3','oxidized_silver':'#58606b',
        'matte_brass':'#ae8d48','polished_chrome':'#cfdae3','hammered_gold':'#c69f52',
        'cool_rose':'#dba7b3','warm_gold':'#d5ac6d','neutral_beige':'#c6aa90','olive':'#aea379',
        'peach':'#e6b18e','copper':'#bc845f','cool_blue':'#b4b6c6','warm_red':'#c58379',
        'candle_warm':'#eaa247','warm_lamp':'#e8bb72','tungsten_source':'#e9cf9e',
        'neutral_white':'#eee9dc','daylight_source':'#e6eef2','cool_sky':'#aacbe1',
        'blue_hour':'#6b8dbd','mixed_warm_cool':'#bca6b0',
    }
    if vid in colors:
        return colors[vid]
    return ['#56799a','#9b6a63','#679985','#ab945d','#8b78a6','#749fa8','#b77e53','#667c77'][index % 8]


def adult(x=140, y=78, scale=1, color=BLUE):
    body = circle(0, -43, 10, SKIN)
    body += path('M -14 -28 L 14 -28 L 18 17 L -18 17 Z', color, INK, 1.5)
    body += line(-13,-23,-25,10,INK,7)+line(13,-23,25,10,INK,7)
    body += line(-9,17,-12,55,INK,8)+line(9,17,12,55,INK,8)
    return tag('g', body, transform=f'translate({x} {y}) scale({scale})')


# Joint chains (shoulder -> elbow -> wrist, hip -> knee -> ankle) describe
# the actual posture, rather than varying a shared generic person icon.
# Each tuple: head, left arm, right arm, left leg, right leg, optional support.
POSES = {
'hands_on_hips':((140,26),[(126,47),(107,64),(127,82)],[(154,47),(176,65),(153,82)],[(132,90),(128,117),(120,145)],[(148,90),(151,118),(164,145)],''),
'weight_shift':((145,26),[(129,47),(117,75),(123,100)],[(157,47),(172,72),(166,98)],[(138,90),(130,119),(128,145)],[(150,90),(156,117),(177,140)],''),
'over_shoulder':((151,25),[(132,49),(111,37),(143,19)],[(156,49),(169,78),(166,102)],[(137,91),(132,119),(124,145)],[(150,91),(151,119),(159,145)],'turn'),
'adjusting_strap':((140,26),[(126,48),(112,69),(125,48)],[(154,48),(169,77),(165,102)],[(132,90),(130,118),(124,145)],[(148,90),(151,118),(161,145)],''),
'finger_near_lips':((140,26),[(126,48),(105,78),(136,33)],[(154,48),(169,76),(170,102)],[(132,90),(129,117),(126,145)],[(148,90),(151,117),(157,145)],''),
'seated':((140,23),[(125,44),(119,67),(137,81)],[(155,44),(162,65),(150,81)],[(132,85),(166,100),(134,145)],[(148,85),(132,113),(170,145)],'chair'),
'arms_relaxed':((140,26),[(126,47),(119,73),(118,100)],[(154,47),(161,73),(162,100)],[(132,90),(132,119),(130,145)],[(148,90),(148,119),(150,145)],''),
'hand_in_hair':((140,26),[(126,48),(100,33),(137,16)],[(154,48),(168,75),(165,103)],[(132,90),(128,118),(120,145)],[(148,90),(153,118),(160,145)],''),
'looking_back':((151,27),[(128,48),(118,72),(119,96)],[(154,48),(165,71),(166,96)],[(134,90),(136,119),(130,145)],[(149,90),(158,117),(176,145)],'turn'),
'slight_arch':((145,24),[(128,46),(119,72),(126,100)],[(157,46),(170,71),(166,99)],[(135,91),(126,119),(120,145)],[(150,91),(157,119),(165,145)],'curve'),
'leaning':((157,28),[(143,49),(160,74),(177,74)],[(168,49),(182,73),(196,76)],[(144,92),(135,118),(122,145)],[(157,92),(172,118),(187,145)],'wall'),
 'three_quarter':((147,25),[(127,47),(114,75),(120,99)],[(153,47),(162,74),(154,99)],[(133,91),(127,119),(124,145)],[(145,91),(152,119),(168,145)],'turn'),
}

# Curated additional posture chains use the same anatomical joint convention.
POSE_ROWS = [
('walking_forward', (140,26), [(126,48),(111,73),(104,95)],[(154,48),(167,69),(158,85)],[(132,90),(113,116),(100,145)],[(148,90),(163,116),(165,141)],''),
('walking_left',(136,25),[(124,47),(108,62),(91,69)],[(150,47),(165,69),(175,87)],[(132,89),(111,112),(92,144)],[(144,89),(157,116),(162,135)],'left'),
('walking_right',(145,25),[(130,47),(115,69),(105,87)],[(156,47),(173,62),(190,69)],[(137,89),(124,116),(119,135)],[(149,89),(170,112),(189,144)],'right'),
('long_stride',(140,25),[(126,47),(107,62),(91,78)],[(154,47),(176,65),(189,85)],[(132,89),(103,113),(76,144)],[(148,89),(177,113),(205,143)],''),
('short_step',(140,26),[(126,48),(117,73),(116,96)],[(154,48),(163,70),(169,92)],[(132,90),(128,116),(122,144)],[(148,90),(153,115),(164,143)],''),
('paused_step',(141,25),[(126,48),(116,73),(115,98)],[(155,48),(165,69),(158,87)],[(132,90),(133,118),(130,145)],[(148,90),(165,117),(158,134)],''),
('crossed_ankles',(140,25),[(126,48),(118,73),(118,99)],[(154,48),(162,73),(161,99)],[(132,90),(143,116),(152,145)],[(148,90),(137,119),(129,145)],''),
('feet_together',(140,24),[(126,47),(119,74),(119,101)],[(154,47),(161,74),(161,101)],[(132,90),(137,118),(137,146)],[(148,90),(143,118),(143,146)],''),
('wide_stance',(140,25),[(126,48),(113,74),(103,98)],[(154,48),(167,74),(177,98)],[(132,90),(117,118),(96,145)],[(148,90),(163,118),(184,145)],''),
('one_knee_bent',(144,25),[(128,48),(116,73),(116,99)],[(156,48),(168,73),(164,99)],[(135,90),(132,118),(131,145)],[(150,90),(165,113),(152,138)],''),
('one_foot_forward',(140,25),[(126,48),(119,73),(117,98)],[(154,48),(163,73),(161,98)],[(132,90),(126,118),(113,145)],[(148,90),(154,119),(165,151)],''),
('hands_clasped_front',(140,25),[(126,48),(112,71),(139,86)],[(154,48),(168,71),(141,86)],[(132,90),(130,118),(126,145)],[(148,90),(152,118),(158,145)],''),
('hands_behind_back',(140,25),[(126,48),(114,71),(139,87)],[(154,48),(166,71),(141,87)],[(132,90),(128,118),(125,145)],[(148,90),(152,118),(155,145)],'behind'),
('one_hand_on_hip',(142,25),[(126,48),(106,65),(129,83)],[(156,48),(166,74),(165,100)],[(134,90),(130,118),(126,145)],[(149,90),(155,118),(169,145)],''),
('arms_folded',(140,25),[(126,48),(110,71),(151,67)],[(154,48),(170,65),(129,69)],[(132,90),(129,118),(126,145)],[(148,90),(152,118),(158,145)],''),
('hand_on_forearm',(140,25),[(126,48),(115,75),(157,87)],[(154,48),(160,74),(163,104)],[(132,90),(129,118),(126,145)],[(148,90),(152,118),(157,145)],''),
('hand_on_elbow',(140,25),[(126,48),(110,75),(161,72)],[(154,48),(162,74),(148,45)],[(132,90),(130,118),(126,145)],[(148,90),(151,118),(157,145)],''),
('touching_collar',(140,25),[(126,48),(107,68),(138,47)],[(154,48),(164,74),(165,101)],[(132,90),(130,118),(126,145)],[(148,90),(151,118),(157,145)],''),
('touching_cuff',(140,25),[(126,48),(112,77),(165,83)],[(154,48),(175,67),(164,86)],[(132,90),(129,118),(126,145)],[(148,90),(153,118),(160,145)],''),
('holding_lapel',(140,25),[(126,48),(112,71),(139,61)],[(154,48),(166,75),(162,101)],[(132,90),(127,118),(120,145)],[(148,90),(153,118),(163,145)],''),
('holding_hem',(140,25),[(126,48),(115,77),(126,97)],[(154,48),(171,76),(183,97)],[(132,90),(126,118),(119,145)],[(148,90),(157,118),(169,145)],'hem'),
('checking_watch',(140,27),[(126,48),(107,68),(145,72)],[(154,48),(169,69),(138,75)],[(132,90),(129,118),(126,145)],[(148,90),(152,118),(157,145)],'watch'),
('reading_book',(140,28),[(126,48),(110,76),(130,72)],[(154,48),(170,76),(152,72)],[(132,90),(129,118),(126,145)],[(148,90),(152,118),(157,145)],'book'),
('holding_cup',(140,25),[(126,48),(109,74),(138,67)],[(154,48),(172,74),(147,67)],[(132,90),(129,118),(126,145)],[(148,90),(152,118),(157,145)],'cup'),
('carrying_bag',(140,25),[(126,48),(115,75),(109,101)],[(154,48),(165,74),(165,100)],[(132,90),(128,118),(123,145)],[(148,90),(154,118),(166,145)],'bag'),
('holding_umbrella',(140,25),[(126,48),(113,75),(137,74)],[(154,48),(166,74),(165,101)],[(132,90),(128,118),(123,145)],[(148,90),(154,118),(162,145)],'umbrella'),
('waving',(140,25),[(126,48),(116,74),(117,100)],[(154,48),(179,45),(179,15)],[(132,90),(127,118),(122,145)],[(148,90),(153,118),(161,145)],''),
('pointing_side',(140,25),[(126,48),(95,50),(68,46)],[(154,48),(168,74),(165,101)],[(132,90),(129,118),(126,145)],[(148,90),(151,118),(159,145)],''),
('open_hand_gesture',(140,25),[(126,48),(107,71),(77,66)],[(154,48),(165,74),(162,101)],[(132,90),(129,118),(126,145)],[(148,90),(151,118),(157,145)],''),
('reaching_shelf',(140,25),[(126,48),(113,74),(112,101)],[(154,48),(176,41),(204,39)],[(132,90),(129,118),(126,145)],[(148,90),(153,118),(160,145)],'shelf'),
('reaching_up',(140,25),[(126,48),(115,74),(114,100)],[(154,48),(166,23),(165,4)],[(132,90),(131,118),(130,145)],[(148,90),(158,118),(166,145)],''),
('stretching_shoulders',(140,34),[(126,55),(114,24),(139,5)],[(154,55),(166,24),(141,5)],[(132,96),(128,121),(123,148)],[(148,96),(152,121),(157,148)],''),
('turning_in_place',(147,25),[(127,48),(115,72),(124,98)],[(155,48),(174,70),(177,94)],[(133,90),(138,118),(136,145)],[(146,90),(160,116),(181,136)],'turn'),
('pivot_left',(134,25),[(123,48),(103,66),(94,90)],[(148,48),(165,74),(152,97)],[(132,90),(113,115),(101,140)],[(144,90),(144,119),(151,145)],'left'),
('pivot_right',(146,25),[(132,48),(115,74),(128,97)],[(157,48),(177,66),(186,90)],[(136,90),(136,119),(129,145)],[(148,90),(167,115),(179,140)],'right'),
('seated_upright',(140,22),[(126,43),(116,66),(133,88)],[(154,43),(164,66),(149,88)],[(132,83),(127,111),(126,145)],[(148,83),(157,111),(158,145)],'chair'),
('seated_sideways',(132,22),[(122,43),(109,66),(131,85)],[(143,43),(157,65),(155,86)],[(128,83),(165,99),(182,145)],[(141,83),(173,103),(191,145)],'chair'),
('seated_ankles_crossed',(140,22),[(126,43),(114,66),(134,84)],[(154,43),(166,66),(147,84)],[(132,83),(130,110),(151,145)],[(148,83),(155,110),(131,145)],'chair'),
('seated_lean_forward',(151,28),[(134,48),(117,83),(129,99)],[(162,48),(177,82),(154,99)],[(131,85),(124,111),(118,145)],[(148,85),(156,111),(163,145)],'chair'),
('seated_lean_back',(124,19),[(111,41),(107,69),(130,89)],[(139,41),(160,66),(154,91)],[(129,84),(163,108),(165,145)],[(145,84),(180,107),(185,145)],'chair'),
('seated_hands_clasped',(140,22),[(126,43),(113,69),(139,87)],[(154,43),(169,69),(141,87)],[(132,83),(127,111),(126,145)],[(148,83),(157,111),(158,145)],'chair'),
('seated_one_arm_on_back',(140,22),[(126,43),(101,47),(80,51)],[(154,43),(170,68),(151,88)],[(132,83),(126,112),(126,145)],[(148,83),(157,112),(159,145)],'chair'),
('seated_reading',(140,26),[(126,46),(113,74),(130,79)],[(154,46),(168,74),(151,79)],[(132,83),(127,111),(126,145)],[(148,83),(157,111),(158,145)],'chair book'),
('seated_looking_up',(142,17),[(126,42),(113,66),(133,86)],[(154,42),(166,66),(150,86)],[(132,83),(127,111),(126,145)],[(148,83),(157,111),(158,145)],'chair'),
('bench_side_sit',(130,22),[(118,43),(105,69),(129,88)],[(145,43),(160,67),(172,88)],[(127,83),(149,110),(166,145)],[(141,83),(163,110),(182,145)],'bench'),
('stool_perch',(140,18),[(126,39),(113,62),(133,82)],[(154,39),(165,62),(149,82)],[(132,79),(124,103),(139,120)],[(148,79),(166,111),(172,145)],'stool'),
('step_sit',(140,22),[(126,43),(112,70),(132,89)],[(154,43),(166,70),(149,89)],[(132,83),(111,109),(103,145)],[(148,83),(166,109),(176,145)],'step'),
('ledge_sit',(140,23),[(126,44),(112,68),(102,89)],[(154,44),(168,68),(181,89)],[(132,83),(129,110),(126,142)],[(148,83),(153,110),(159,142)],'ledge'),
('wall_lean_shoulder',(174,28),[(160,49),(147,75),(159,100)],[(188,49),(192,75),(188,100)],[(159,92),(142,118),(126,145)],[(174,92),(174,119),(177,145)],'wall'),
('wall_lean_back',(162,26),[(146,47),(135,74),(145,100)],[(174,47),(184,74),(178,100)],[(144,91),(132,118),(115,145)],[(159,91),(170,112),(163,140)],'wall'),
('rail_lean',(145,32),[(128,52),(113,82),(141,82)],[(157,52),(174,82),(150,82)],[(132,94),(127,120),(120,146)],[(148,94),(154,120),(162,146)],'rail'),
('table_lean',(145,27),[(127,48),(110,73),(99,83)],[(155,48),(168,76),(168,101)],[(133,92),(126,118),(119,145)],[(149,92),(157,118),(167,145)],'table'),
('doorway_rest',(140,25),[(126,48),(116,75),(116,100)],[(154,48),(179,47),(197,34)],[(132,90),(129,118),(124,145)],[(148,90),(154,117),(170,143)],'door'),
('ascending_step',(147,25),[(131,48),(110,67),(101,90)],[(159,48),(177,64),(170,78)],[(137,90),(137,120),(128,145)],[(152,90),(174,105),(170,127)],'stairs'),
('descending_step',(142,22),[(128,45),(113,64),(98,65)],[(156,45),(170,65),(185,66)],[(134,87),(122,116),(109,144)],[(150,87),(165,105),(178,122)],'stairs'),
('looking_into_window',(141,25),[(126,48),(115,74),(139,86)],[(154,48),(167,74),(143,86)],[(132,90),(127,118),(124,145)],[(148,90),(151,118),(156,145)],'window'),
('tying_scarf',(140,25),[(126,48),(109,70),(137,48)],[(154,48),(171,70),(145,48)],[(132,90),(128,118),(124,145)],[(148,90),(152,118),(158,145)],'scarf'),
('buttoning_jacket',(140,25),[(126,48),(109,73),(137,76)],[(154,48),(171,73),(145,76)],[(132,90),(128,118),(124,145)],[(148,90),(152,118),(158,145)],'button'),
]
POSES.update({row[0]: row[1:] for row in POSE_ROWS})


def draw_pose(vid):
    head, la, ra, ll, rl, support = POSES[vid]
    art = line(50,151,230,151,'#bac5d0',1)
    if 'wall' in support: art += rect(198,6,9,146,'#c0c8ce')
    if 'chair' in support: art += path('M 100 42 L 100 92 L 181 92 M 109 92 L 106 148 M 169 92 L 177 148','none','#9b8063',6)
    if 'bench' in support or 'ledge' in support: art += rect(66,90,148,8,'#a6a095')+line(80,98,80,149)+line(200,98,200,149)
    if 'stool' in support: art += rect(111,84,61,8,'#a6a095')+line(119,92,110,149)+line(165,92,176,149)+line(117,125,170,125)
    if 'step' in support or 'stairs' in support: art += path('M 190 153 L 190 127 L 162 127 L 162 153','none','#9eacb8',4)
    if 'rail' in support: art += line(58,85,229,85,'#9eacb8',6)+line(80,85,80,150)+line(210,85,210,150)
    if 'table' in support: art += rect(51,83,62,7,'#a68b6b')+line(60,90,60,150)+line(105,90,105,150)
    if 'door' in support: art += path('M 85 150 L 85 5 L 203 5 L 203 150','none','#9eacb8',5)
    if 'window' in support: art += rect(195,12,52,100,'#d8e8f0',stroke='#99b1c1')+line(221,12,221,112)+line(195,61,247,61)
    if 'shelf' in support: art += rect(200,40,51,7,'#a68b6b')+rect(209,15,14,24,'#8b78a6')
    hips = (ll[0],rl[0]); shoulders=(la[0],ra[0])
    art += poly([shoulders[0],shoulders[1],hips[1],hips[0]],BLUE,stroke=INK,stroke_width=1.5)
    if 'behind' in support:
        art += path('M 117 70 Q 140 110 165 70','none',SKIN,3,stroke_dasharray='4 4')
    else:
        for chain in (la,ra):
            for p,q in zip(chain,chain[1:]):art+=line(*p,*q,SKIN,7)
            art+=circle(*chain[-1],3,SKIN)
    for chain in (ll,rl):
        for p,q in zip(chain,chain[1:]):art+=line(*p,*q,INK,8)
        art+=line(chain[-1][0]-3,chain[-1][1]+1,chain[-1][0]+6,chain[-1][1]+1,INK,4)
    art += line(head[0],head[1]+9,(la[0][0]+ra[0][0])/2,(la[0][1]+ra[0][1])/2,SKIN,6)+circle(*head,11,SKIN)
    eye_x=head[0]-4 if 'left' in support else head[0]+5
    art += circle(eye_x,head[1]-2,1.5,INK)
    if 'turn' in support:art+=path(f'M {head[0]-13} {head[1]-11} Q {head[0]} {head[1]-20} {head[0]+13} {head[1]-11}','none','#b58a43',2)
    if 'book' in support:art+=path('M 126 70 L 140 74 L 156 70 L 156 84 L 140 88 L 126 84 Z','#d4b883',INK,1)+line(140,74,140,88,INK,1)
    if 'cup' in support:art+=rect(137,61,12,16,'#e8ddd0',rx=2)+path('M 149 64 Q 159 67 149 73','none',INK,2)
    if 'bag' in support:art+=rect(92,111,33,28,'#a68b6b',rx=4)+path('M 98 111 Q 106 94 119 111','none',INK,2)
    if 'umbrella' in support:art+=line(139,14,139,110)+path('M 110 27 Q 139 -7 168 27 Z','#a88eae',INK,2)
    if 'watch' in support:art+=circle(139,73,4,'#d0a147',stroke=INK)
    if 'scarf' in support:art+=path('M 133 45 L 147 45 L 143 58 L 149 75 L 142 77 L 137 58 Z','#b77e53',INK,1)
    if 'button' in support:art+=circle(141,76,3,'#d0a147')
    if 'hem' in support:art+=path('M 129 82 L 183 98 L 164 119 L 125 119 Z',BLUE,INK,1)
    return art


# A scene recipe combines recognizable architectural/landscape elements.
# Location identity changes geometry (not just an arbitrary caption or hue).
SCENES = {
'window_left':'room window curtains','garden_path':'garden path flowers','balcony':'city rail clouds','meadow':'field flowers tree',
'apartment':'room window sofa','terrace':'city rail chairs','library':'room shelves table','rainy_window':'room window rain',
'loft':'room beams window','courtyard':'walls paving plants','hallway':'hall doors','bedroom_window':'room window curtains bed',
'coastal_boardwalk':'sea boardwalk rail','rocky_shore':'sea rocks','sandy_beach':'sea sand surf','harbor_quay':'sea boats bollards paving',
'marina':'sea boats masts dock','lighthouse_path':'sea lighthouse path','dune_trail':'sand dunes grass path','cliff_overlook':'sea cliffs rail',
'pine_forest':'forest pines needles','birch_grove':'forest birch','woodland_trail':'forest tree roots path','bamboo_walk':'forest bamboo path',
'orchard':'garden orchard','olive_grove':'garden olives','lavender_field':'field rows lavender','sunflower_field':'field rows sunflowers',
'vineyard':'field rows vines','tea_garden':'hills rows tea','botanical_glasshouse':'glasshouse broadleaf','palm_garden':'garden palms',
'rose_garden':'garden flowers hedge','formal_hedge_garden':'garden hedge gridpath','stone_bridge':'river bridge stone',
'riverside_walk':'river path rail','lakeside_pier':'lake dock','mountain_lake':'lake mountains','waterfall_path':'rocks waterfall path',
'wetland_boardwalk':'lake reeds boardwalk','desert_courtyard':'walls adobe cactus','cactus_garden':'sand cactus rocks',
'red_rock_trail':'rocks redcliffs path','salt_flat':'salt horizon','prairie':'field grass horizon','rolling_hills':'hills grass',
'snowy_park':'snow baretrees bench','alpine_village':'snow mountains chalets','cabin_porch':'cabin porch chair',
'urban_crosswalk':'city road zebra','cobblestone_lane':'lane paving stone','brick_alley':'lane brick lamps','shopping_arcade':'hall arches shops',
'cafe_exterior':'shop awning chairs','cafe_interior':'room counter chairs','bakery':'room counter bread','bookshop':'room shelves counter',
'museum_gallery':'room art','sculpture_hall':'hall sculpture','train_platform':'station tracks shelter','tram_stop':'city tracks shelter',
'station_concourse':'hall beams columns clock','airport_lounge':'room window seats aircraft','rooftop':'city parapet skyline',
'city_park':'garden tree bench path','plaza':'city paving civic','fountain_square':'city fountain paving','colonnade':'hall columns',
'arched_passage':'hall arches','spiral_stair':'room spiral','grand_staircase':'hall stairs','industrial_studio':'room beams table',
'white_cyclorama':'studio whitecurve','gray_studio':'studio gray','black_studio':'studio black','paper_backdrop':'studio paperroll',
'daylight_studio':'studio window','art_workshop':'room easel canvas','ceramics_studio':'room shelves pottery table',
'music_room':'room piano panels','conservatory':'glasshouse sofa plants','dining_room':'room table chairs pendant',
'kitchen':'room cabinets counter','entryway':'room console rack','sunroom':'room window sofa plants',
'hotel_lobby':'hall reception seats','dressing_room':'room garments mirror','tailor_workshop':'room mannequin sewing',
'covered_veranda':'porch posts horizon','pergola':'garden beams vines','greenhouse_path':'glasshouse path planting',
'courtyard_pool':'walls pool paving','canal_bridge':'city canal bridge','market_hall':'hall beams stalls',
'concert_foyer':'hall window stairs',
}


def tree(x,y,kind='tree',size=1):
    art=line(x,y+28*size,x,y+67*size,'#8b735a',5*size)
    if kind=='pines':
        for dy,w in [(0,14),(13,20),(27,25)]: art+=poly([(x,y+dy),(x-w*size,y+(dy+32)*size),(x+w*size,y+(dy+32)*size)],'#507761')
    elif kind=='palms':
        for dx in [-35,-22,22,35]:art+=path(f'M {x} {y+20} Q {x+dx/2} {y-12} {x+dx} {y+15}','none','#557a5f',6)
    elif kind=='baretrees':
        for dx,dy in [(-22,8),(20,0),(-12,-8),(28,22)]:art+=line(x,y+35,x+dx*size,y+dy*size,'#82796c',3)
    else:
        art+=ellipse(x,y+14*size,24*size,30*size,'#879e72' if kind!='olives' else '#96a58a')
        if kind=='orchard':
            for dx,dy in [(-9,8),(10,19),(6,-1)]:art+=circle(x+dx,y+dy,3,'#c88a5b')
    return art


def draw_scene(vid):
    tokens=SCENES[vid].split()
    has=lambda s:s in tokens
    sky='#dae8ed';ground='#c3d1bd'
    if has('snow'):ground='#f0f4f7'
    if has('sand'):ground='#e0cdab'
    if has('salt'):ground='#ece7dd'
    if has('room') or has('hall') or has('studio'):ground='#c8c6c4';sky='#e4ded5'
    if has('black'):sky='#354052';ground='#4b5563'
    if has('gray'):sky='#abb4bf';ground='#929ca9'
    art=rect(0,0,280,104,sky)+rect(0,104,280,56,ground)
    if has('hills') or has('dunes'):
        art+=path('M 0 105 Q 45 40 120 98 Q 210 33 280 85 L 280 135 L 0 135 Z','#a8bc92' if has('hills') else '#cbb890','none',0)
    if has('mountains'):art+=poly([(0,105),(60,22),(114,82),(181,9),(280,105)],'#96a9b5')+poly([(151,40),(181,9),(207,43),(187,35),(173,41)],'#f3f5f6')
    if any(has(t) for t in ['sea','lake','river','canal','pool']):
        art+=rect(0 if not has('pool') else 74,91,280 if not has('pool') else 139,50,'#88b2c2')
        for y in [100,112,125]:art+=line(12,y,264,y,'#c0d8dd',1)
        if has('river') or has('canal'):art+=poly([(98,92),(178,92),(243,160),(47,160)],'#78aabb')
    if has('surf'):art+=path('M 0 121 Q 80 113 155 129 Q 210 142 280 129','none','#f2f7f4',4)
    if any(has(t) for t in ['path','boardwalk','dock','gridpath']):
        art+=poly([(128,95),(154,95),(236,160),(48,160)],'#ac947a' if has('boardwalk') or has('dock') else '#d6c9ae')
        if has('boardwalk') or has('dock'):
            for y in range(109,161,9):art+=line(90-(y-109)*.7,y,191+(y-109)*.7,y,'#897761',1)
    if has('rail') or has('parapet'):
        art+=line(10,99,270,99,'#7b8794',5)+line(10,121,270,121,'#7b8794',2)
        for x in range(20,280,38):art+=line(x,99,x,143,'#7b8794',3)
    if has('field') or has('grass') or has('reeds'):
        for x in range(5,280,13):
            y=123+(x%4)*5
            art+=path(f'M {x} {y+18} L {x-4} {y-5} M {x} {y+18} L {x+5} {y}','none','#81925f',1.5)
    if has('rows'):
        for x in [10,55,100,185,230,275]:
            art+=line(140+(x-140)*.25,95,x,155,'#748556',14)
            if has('lavender') or has('sunflowers'):
                for f in range(3):
                    px=140+(x-140)*(.45+f*.2);py=108+f*19
                    art+=circle(px,py,4,'#9a82ba' if has('lavender') else '#d5b64d')
                    if has('sunflowers'):art+=circle(px,py,2,'#69513b')
            if has('vines'):art+=line(x,125,x,156,'#937856',2)+line(x-12,128,x+12,128,'#547357',4)
            if has('tea'):art+=ellipse(x,135,23,14,'#72985c')
    for kind in ['tree','pines','palms','baretrees','orchard','olives']:
        if has(kind):
            for x,y,s in [(32,26,.9),(235,12,1.1),(76,42,.65)]:art+=tree(x,y,kind,s)
    if has('birch'):
        for x in [35,73,208,246]:
            art+=rect(x,7,8,126,'#f4f0e5')
            for y in range(19,122,17):art+=line(x,y,x+5,y+1,'#5b6367',2)
            art+=ellipse(x,17,25,20,'#91a476')
    if has('bamboo'):
        for x in [22,42,64,215,236,258]:
            art+=rect(x,0,5,146,'#72885b')
            for y in range(13,148,25):art+=line(x-2,y,x+7,y,'#4e6d4e',2)+line(x+3,y,x+14,y-13,'#65845a',2)
    if has('hedge'):art+=rect(10,80,95,40,'#6c8b5b',rx=8)+rect(180,80,90,40,'#6c8b5b',rx=8)
    if has('flowers'):
        for x,y in [(20,119),(42,129),(66,115),(215,127),(242,114),(265,132)]:
            art+=line(x,y,x,y+19,'#608262',2)+circle(x,y,5,'#cba2b0')+circle(x,y,2,'#dfc66f')
    if has('cactus'):
        for x,y in [(40,63),(230,42),(80,95)]:art+=path(f'M {x} 142 L {x} {y} M {x} {y+37} L {x-12} {y+37} L {x-12} {y+15} M {x} {y+56} L {x+14} {y+56} L {x+14} {y+28}','none','#708964',9)
    if has('rocks') or has('cliffs') or has('redcliffs'):
        for x,y in [(18,80),(66,103),(225,69)]:
            art+=poly([(x,y+45),(x+10,y),(x+33,y-10),(x+49,y+39)],'#b48268' if has('redcliffs') else '#929896')
            if has('redcliffs'):art+=line(x+9,y+12,x+40,y+10,'#e1b291',2)+line(x+4,y+29,x+43,y+26,'#765c54',2)
    if has('waterfall'):art+=path('M 226 55 Q 233 104 204 144','none','#cce7ef',12)
    if has('boats'):
        for x,y in [(30,115),(162,101),(222,121)]:
            art+=poly([(x,y),(x+39,y),(x+30,y+12),(x+9,y+12)],'#e7e2d9')
            art+=line(x+19,y,x+19,y-44,'#697d8a',2)
            if not has('masts'):art+=poly([(x+19,y-40),(x+19,y-4),(x+2,y-4)],'#f3ece0')
    if has('bollards'):
        for x in [35,99,229]:art+=rect(x,121,10,23,'#596775',rx=3)
    if has('lighthouse'):art+=path('M 205 92 L 211 20 L 228 20 L 235 92 Z','#ece9df',INK,1)+rect(210,12,20,13,'#9c6c5c')+rect(215,43,8,14,BLUE)
    if has('walls') or has('lane') or has('city') or has('shop') or has('cabin'):
        fill='#c8ab91' if has('adobe') else '#bcc6cd'
        if has('cabin'):fill='#a78b6a'
        if has('brick'):fill='#bd8e7b'
        if has('lane'):art+=poly([(0,0),(105,43),(105,114),(0,160)],fill)+poly([(280,0),(175,43),(175,114),(280,160)],fill)
        else:
            for x,h in [(0,82),(42,68),(199,89),(245,62)]:
                art+=rect(x,104-h,35,h,fill)
                for wy in range(110-h,95,18):art+=rect(x+7,wy,7,10,'#6f8b9c')+rect(x+21,wy,7,10,'#6f8b9c')
        if has('shop'):art+=rect(40,32,195,73,'#c9b197')+rect(56,52,162,48,'#94b2bd')
        if has('awning'):art+=path('M 43 43 L 231 43 L 241 64 L 33 64 Z','#a87572',INK,1)
        if has('cabin'):art+=poly([(3,52),(76,9),(145,52)],'#7a6759')+rect(31,72,26,40,'#786450')
        if has('paving') or has('brick'):
            for y in [128,145]:
                art+=line(0,y,280,y,'#a0a6aa',1)
                for x in range((y%3)*8,280,30):art+=line(x,y-15,x,y,'#a0a6aa',1)
    if has('zebra'):
        art+=rect(0,116,280,44,'#7d8790')
        for x in range(10,260,40):art+=poly([(x,125),(x+20,125),(x+33,156),(x+6,156)],'#eceeed')
    if has('clouds'):art+=ellipse(71,25,34,10,'#f5f7f8')+ellipse(170,40,31,9,'#f5f7f8')
    if has('bridge'):art+=path('M 52 105 Q 140 37 230 105 L 230 119 Q 140 67 52 119 Z','#aaa497',INK,1)
    if has('fountain'):art+=ellipse(140,132,63,15,'#a7b7b8')+ellipse(140,129,51,9,'#78aabb')+line(140,124,140,78,'#7caec4',5)+path('M 140 78 Q 115 87 112 113 M 140 78 Q 164 87 168 113','none','#9dcbdc',3)
    if has('room') or has('hall'):
        art+=path('M 0 0 L 49 33 L 49 106 L 0 160 M 280 0 L 231 33 L 231 106 L 280 160 M 49 33 L 231 33','none','#b2aca4',1)
    if has('window'):
        art+=rect(65,9,146,86,'#bbd6e2',stroke='#809aaa',stroke_width=4)
        art+=line(138,10,138,95,'#f0eee8',4)+line(66,52,211,52,'#f0eee8',4)
    if has('curtains'):art+=path('M 51 6 L 73 6 L 68 111 L 45 111 Z','#d1c0ad',INK,1)+path('M 206 6 L 225 6 L 233 111 L 212 111 Z','#d1c0ad',INK,1)
    if has('rain'):
        for x,y in [(80,20),(104,60),(128,32),(156,76),(190,35)]:art+=path(f'M {x} {y} l -3 9','none','#6a9eb3',2)
    if has('glasshouse'):
        art+=path('M 18 136 L 18 49 L 140 6 L 262 49 L 262 136 M 18 49 L 262 49 M 80 27 L 80 136 M 140 6 L 140 136 M 200 27 L 200 136 M 18 91 L 262 91','none','#788f98',3)
    if has('beams') or has('posts'):
        for x in [30,94,186,250]:art+=line(x,10,x,135,'#7c7b77',5)
        art+=line(13,13,267,13,'#7c7b77',6)+line(13,41,267,41,'#7c7b77',3)
    if has('shelves'):
        for x in [15,200]:
            art+=rect(x,20,64,113,'#a68b70')
            for y in [48,78,110]:
                art+=line(x,y,x+64,y,'#756656',3)
                for j in range(6):art+=rect(x+3+j*10,y-22,7,21,['#627f90','#967270','#bdab87'][j%3])
    if has('pottery'):
        for x,y in [(25,29),(48,84),(210,66),(234,110)]:art+=ellipse(x,y,8,10,'#d5b491')
    if has('counter') or has('reception') or has('stalls'):art+=rect(25,95,113,44,'#ad9580')+rect(22,91,119,6,'#6e7881')
    if has('bread'):
        for x in [40,64,88,112]:art+=ellipse(x,78,10,7,'#d6a66b')+line(x-4,73,x,79,'#b68b55',1)
    if has('cabinets'):
        for x in [29,68,107,146,185,224]:art+=rect(x,30,34,44,'#c8bbab',stroke='#958d83')+circle(x+27,53,2,INK)
    if has('table') or has('console') or has('sewing') or has('planting'):
        art+=poly([(84,96),(182,96),(210,115),(63,115)],'#b5a086')+line(78,115,70,152)+line(197,115,205,152)
    if has('chairs') or has('chair') or has('seats') or has('bench'):
        xs=[36,227] if not has('seats') else [26,79,186,237]
        for x in xs:art+=path(f'M {x} 92 L {x} 120 L {x+23} 120 M {x+3} 120 L {x} 148 M {x+20} 120 L {x+24} 148','none','#7c8792',4)
    if has('sofa') or has('bed'):art+=rect(56,102,158,39,'#9caeae' if has('sofa') else '#c2bab3',rx=7)+rect(64,89,64,24,'#b8c6c5',rx=4)+rect(139,89,64,24,'#b8c6c5',rx=4)
    if has('plants') or has('broadleaf') or has('planting'):
        for x in [30,250]:
            art+=path(f'M {x-10} 143 L {x+10} 143 L {x+14} 117 L {x-14} 117 Z','#b78f75',INK,1)
            for dx,dy in [(-18,-33),(17,-24),(-11,-52),(12,-63)]:art+=line(x,120,x+dx,120+dy,'#50785b',2)+ellipse(x+dx,120+dy,8,14,'#7b9b76',transform=f'rotate({-dx} {x+dx} {120+dy})')
    if has('columns'):
        for x in [30,80,199,249]:art+=rect(x,22,13,120,'#b7b2a7')+rect(x-4,17,21,7,'#cfc9bc')
    if has('arches'):
        for x,s in [(15,1),(66,.68),(108,.38)]:art+=path(f'M {x} 146 L {x} {66*s} Q 140 {-28*s} {280-x} {66*s} L {280-x} 146','none','#a5a9a6',7*s)
    if has('shops'):
        for x in [19,204]:art+=rect(x,72,54,49,'#91acb8',stroke='#8c9da4',stroke_width=2)+rect(x,63,54,8,'#aa8981')+line(x+27,74,x+27,121,'#e7e6df',2)
    if has('doors'):
        for x,y,w,h in [(18,25,34,94),(74,50,20,62),(211,41,24,75),(132,57,16,52)]:art+=rect(x,y,w,h,'#a68d7c',stroke='#82776c')+circle(x+w-4,y+h*.6,2,INK)
    if has('art') or has('canvas'):
        for x,y in [(75,30),(176,41)]:art+=rect(x,y,44,42,'#e7ddca',stroke='#786d62',stroke_width=3)+poly([(x+5,y+35),(x+19,y+10),(x+39,y+35)],'#809aaa')
    if has('sculpture'):art+=rect(119,113,43,18,'#b9b5ac')+ellipse(140,76,17,35,'#a7a09a')+ellipse(145,64,8,15,sky)
    if has('easel'):art+=path('M 88 151 L 140 23 L 190 151 M 103 113 L 178 113','none','#a08769',5)+rect(112,51,55,55,'#ece7db',stroke=INK)
    if has('piano'):art+=rect(72,72,132,58,'#424952')+rect(81,89,116,13,'#e9e7df')+line(86,130,86,154,INK,5)+line(192,130,192,154,INK,5)
    if has('panels'):
        for x in [32,210]:art+=rect(x,27,28,52,'#b0a799')
    if has('garments'):art+=path('M 33 145 L 33 27 L 121 27 L 121 145','none',INK,3)+path('M 56 35 L 45 43 L 43 114 L 74 114 L 70 43 Z',BLUE,INK,1)+path('M 93 35 L 80 43 L 80 114 L 112 114 L 106 43 Z','#a98b83',INK,1)
    if has('mirror'):art+=rect(183,22,61,117,'#b7d4dc',stroke='#847568',stroke_width=4)+line(190,106,234,46,'#e0edf0',2)
    if has('mannequin'):art+=path('M 74 34 L 65 42 L 61 79 L 87 79 L 83 42 Z','#cbbb9f',INK,2)+line(74,79,74,139)+line(58,139,90,139)
    if has('sewing'):art+=path('M 133 92 L 133 70 L 164 70 L 169 91 Z','#667985',INK,1)+rect(128,91,49,6,INK)
    if has('rack'):art+=line(224,35,224,145)+line(205,61,243,61)+line(224,61,208,45)+line(211,145,237,145)
    if has('pendant') or has('lamps'):art+=line(140,0,140,30)+path('M 123 44 L 132 29 L 149 29 L 158 44 Z','#b5a387',INK,1)
    if has('tracks'):
        for x in [85,185]:art+=line(140+(x-140)*.3,93,x,160,INK,3)
        for y in [112,130,150]:art+=line(105-(y-112)*.3,y,170+(y-112)*.3,y,'#8e8c88',3)
    if has('shelter'):art+=rect(22,34,84,9,'#81939d')+line(31,43,31,111)+line(97,43,97,111)+rect(39,48,50,40,'#adcbd5')
    if has('clock'):art+=circle(140,32,13,'#f1eee4',stroke=INK)+line(140,32,140,23)+line(140,32,148,36)
    if has('aircraft'):art+=path('M 83 51 L 142 51 L 152 38 L 163 38 L 157 51 L 181 55 L 181 59 L 82 59 Z','#7c95a4','none',0)
    if has('spiral'):art+=ellipse(142,60,40,18,'none',stroke='#82919d',stroke_width=4)+ellipse(142,94,40,18,'none',stroke='#82919d',stroke_width=4)+ellipse(142,128,40,18,'none',stroke='#82919d',stroke_width=4)+line(142,15,142,153,INK,4)
    if has('stairs'):
        for y in range(77,151,12):art+=rect(120-(y-77)*.8,y,40+(y-77)*1.6,8,'#b0aaa0',stroke='#8d9191',stroke_width=1)
    if has('whitecurve'):art+=path('M 0 79 Q 140 86 280 79 M 0 83 Q 140 104 280 83','none','#d2dce1',2)
    if has('paperroll'):art+=rect(55,12,170,117,'#cabcae')+ellipse(140,13,85,6,'#a99989')+poly([(55,129),(225,129),(259,153),(22,153)],'#cabcae')
    if has('porch'):art+=line(0,30,280,30,'#8b806f',7)+line(28,30,28,153,'#8b806f',6)+line(252,30,252,153,'#8b806f',6)
    return art


def draw_face(aid, vid, index):
    skin=palette(aid,vid,index) if aid=='skin_tone' else SKIN
    undertones=['#dba7b3','#d5ac6d','#c6aa90','#aea379','#e6b18e','#bc845f','#b4b6c6','#c58379']
    if aid=='skin_undertone':skin=undertones[index]
    if aid=='complexion_detail':skin=['#d6b1b8','#d9aba6','#c8ad95'][index]
    shapes={
      'oval':'M 88 38 Q 140 -9 192 38 L 187 101 Q 170 143 140 149 Q 110 143 93 101 Z',
      'round':'M 82 45 Q 140 -4 198 45 Q 217 116 140 145 Q 63 116 82 45 Z',
      'square':'M 89 29 Q 140 9 191 29 L 195 117 L 169 145 L 111 145 L 85 117 Z',
      'heart':'M 82 38 Q 140 -5 198 38 L 187 99 L 140 150 L 93 99 Z',
      'long':'M 98 20 Q 140 0 182 20 L 185 100 Q 174 147 140 158 Q 106 147 95 100 Z',
      'diamond':'M 110 15 L 170 15 L 200 77 L 174 116 L 140 149 L 106 116 L 80 77 Z',
      'soft_rectangle':'M 95 22 Q 140 2 185 22 Q 198 81 187 121 Q 175 146 140 146 Q 105 146 93 121 Q 82 81 95 22 Z',
      'tapered_oval':'M 87 34 Q 140 -3 193 34 Q 191 109 140 149 Q 89 109 87 34 Z',
    }
    outline=shapes.get(vid,shapes['oval']) if aid=='face_shape' else shapes['oval']
    art=path(outline,skin,INK,1.5)
    art+=ellipse(83,78,7,14,skin)+ellipse(197,78,7,14,skin)
    # Natural eyes; iris pigment and gaze each change independently.
    iris=palette(aid,vid,index) if aid=='eye_color' else '#5b777b'
    gaze={'at_camera':(0,0),'camera_left':(-5,0),'camera_right':(5,0),'upward_gaze':(0,-3),'downward_gaze':(0,3),'distant_horizon':(3,-2),'at_hands':(-2,4)}.get(vid,(0,0))
    eye_rx,eye_ry=15,6
    if aid=='eye_shape':
        eye_rx,eye_ry={'almond':(16,6),'round_eyes':(12,10),'hooded':(16,4),'monolid':(16,5),'deep_set':(14,5),'upturned':(16,6),'downturned':(16,6),'wide_aperture':(16,10)}[vid]
    for x in [112,168]:
        if vid=='eyes_closed':art+=path(f'M {x-15} 73 Q {x} 82 {x+15} 73','none',INK,2)
        else:
            tilt=-12 if vid=='upturned' else 12 if vid=='downturned' else 0
            eyes=ellipse(x,73,eye_rx,eye_ry,'#f4eee8',stroke='#725746',stroke_width=1)
            eyes+=circle(x+gaze[0],73+gaze[1],5,iris)+circle(x+gaze[0],73+gaze[1],2,INK)+circle(x+gaze[0]+1,71+gaze[1],1,'white')
            art+=tag('g',eyes,transform=f'rotate({tilt} {x} 73)')
        brow_arc={'straight':0,'soft_arch':6,'high_arch':13,'angled':11,'rounded':10,'flat_outer':2,'upward':-5,'low_arch':3}.get(vid,5)
        d=f'M {x-17} 60 Q {x} {60-brow_arc} {x+17} 60'
        if vid=='angled':d=f'M {x-17} 60 L {x+1} 49 L {x+17} 60'
        if vid=='upward':d=f'M {x-17} 63 L {x+17} 52'
        art+=path(d,'none','#654c3a',3)
        if aid=='eyelashes':
            n={'dark_long':7,'soft_dark':5,'short_natural':4,'fine_sparse':3,'curled':6,'straight_lashes':6,'brown_lashes':5,'full_natural':9}[vid]
            for j in range(n):
                px=x-13+26*j/max(1,n-1);length=8 if vid in ('dark_long','curled') else 4
                art+=path(f'M {px} 69 q {-2 if vid=="curled" else 0} {-length} -2 {-length}','none','#775744' if vid=='brown_lashes' else INK,1.3)
    nose={'straight_bridge':(137,100,143),'soft_rounded_tip':(134,104,146),'defined_bridge':(137,108,145),'low_bridge':(134,97,145),'broad_bridge':(128,103,152),'narrow_bridge':(139,104,144),'gentle_convex':(134,109,146),'upturned_tip':(133,96,147)}.get(vid,(136,102,146))
    art+=path(f'M 140 80 L {nose[0]} {nose[1]} Q 140 {nose[1]+4} {nose[2]} {nose[1]}','none','#97694f',2)
    lips=palette(aid,vid,index) if aid=='lip_color' else '#a95e61'
    width=28 if vid=='wide_lips' else 14 if vid=='petite_lips' else 21
    upper=3 if vid=='thin_balanced' else 9 if vid in ('full_balanced','defined_cupid_bow') else 5
    lower=9 if vid in ('full_lower','full_balanced') else 3 if vid=='thin_balanced' else 6
    if vid in ('gentle_smile','open_smile','amused','luminous','classic_beauty'):
        art+=path(f'M {140-width} 118 Q 140 {137 if vid=="open_smile" else 131} {140+width} 118','none',lips,4)
        if vid=='open_smile':art+=path('M 124 120 Q 140 128 156 120','#f5eee3',lips,1)
    elif vid=='surprised':art+=ellipse(140,122,8,11,lips)+ellipse(140,122,5,7,'#6b4440')
    else:art+=path(f'M {140-width} 120 Q 130 {120-upper} 140 117 Q 150 {120-upper} {140+width} 120 Q 140 {120+lower} {140-width} 120 Z',lips,'#92504f',1)
    if aid=='cheekbones':
        y={'prominent_soft':85,'defined_natural':91,'rounded':103,'broad':92,'subtle':99,'angular':86,'low_set':106,'high_narrow':83}[vid]
        art+=path(f'M 92 {y+10} Q 107 {y-4} 121 {y+5} M 159 {y+5} Q 173 {y-4} 188 {y+10}','none','#a87155',2 if vid=='subtle' else 4,opacity='.7')
    if aid=='freckles' and vid!='off':
        for side in [0,55]:
            for j in range(14 if vid=='prominent' else 6):art+=circle(96+side+(j*7)%29,87+(j*11)%19,1.1,'#8c5b43')
    if aid=='micro_texture' and vid=='on':
        for j in range(90):art+=circle(98+(j*13)%85,83+(j*17)%45,.6,'#946953',opacity='.55')
    if aid=='skin_finish' or aid=='makeup_finish':
        glows={'matte':0,'satin':.13,'dewy':.48,'dry_natural':0,'hydrated':.32,'t_zone_glow':.4,'cheek_glow':.38,'bare_natural':.08,'bare_face':0,'sheer_tint':.1,'soft_matte':.03,'luminous':.45,'satin_base':.2,'minimal_concealer':.1,'editorial_polish':.3,'sunlit_bronze':.2}
        glow=glows.get(vid,.1)
        if vid!='t_zone_glow':art+=ellipse(103,88,8,16,'#fff8e6',opacity=glow)+ellipse(178,88,8,16,'#fff8e6',opacity=glow)
        if vid!='cheek_glow':art+=ellipse(141,95,3,13,'#fff8e6',opacity=glow)
        if vid in ('dry_natural','bare_face'):
            for j in range(12):art+=circle(102+(j*17)%78,92+(j*7)%26,.8,'#946953')
        if vid=='sunlit_bronze':art+=path('M 92 44 Q 84 107 106 125 M 188 44 Q 195 107 174 125','none','#9c6848',7,opacity='.4')
    if aid=='blush_placement' and vid!='no_blush':
        x,y,rx,ry={'cheek_apples':(110,96,13,9),'high_cheeks':(109,84,18,6),'outer_cheeks':(98,93,8,16),'soft_diagonal':(108,89,18,10),'diffuse_cheeks':(111,96,21,16),'nose_bridge':(140,92,13,5),'low_cheeks':(108,108,16,7)}[vid]
        art+=ellipse(x,y,rx,ry,'#c87079',opacity='.45')
        if x!=140:art+=ellipse(280-x,y,rx,ry,'#c87079',opacity='.45')
    if aid=='eye_makeup' and vid!='no_eye_makeup':
        for x in [112,168]:
            if vid in ('fine_liner','short_wing'):art+=path(f'M {x-15} 71 Q {x} 61 {x+15+(5 if vid=="short_wing" else 0)} 69','none',INK,2)
            else:art+=path(f'M {x-16} 68 Q {x} 48 {x+16} 68','none',{'soft_brown_shadow':'#795a45','taupe_wash':'#998b7b','bronze_lid':'#b19356','charcoal_smudge':'#5b6068','rose_lid':'#b58490'}[vid],7,opacity='.65')
    if aid=='age':
        age=24 if vid=='24' else int(vid.split('_')[-1])
        for j in range(max(0,(age-30)//10)):
            art+=path(f'M 113 {36+j*5} Q 140 {32+j*5} 167 {36+j*5}','none','#aa7860',1)
            art+=line(187,77+j*4,198,78+j*5,'#aa7860',1)+line(82,77+j*4,93,78+j*5,'#aa7860',1)
        if age>=42:art+=path('M 109 107 Q 103 120 111 131 M 171 107 Q 177 120 169 131','none','#aa7860',1.5)
        art+=line(223,18,223,143,'#8194a1',2)
        for tick in range(21,81,10):art+=line(218,18+(tick-21)*125/59,228,18+(tick-21)*125/59,'#8194a1',1)
        art+=circle(223,18+(age-21)*125/59,5,'#b58c4e')
    if aid=='head_tilt':
        angle={'level':0,'tilt_left':-18,'tilt_right':18,'chin_up':-6,'chin_down':6,'turn_left':-12,'turn_right':12,'forward_incline':8}[vid]
        art=tag('g',art,transform=f'rotate({angle} 140 83)')
        if vid in ('chin_up','chin_down','forward_incline'):art+=line(222,66 if vid=='chin_up' else 100,222,103 if vid=='chin_up' else 64,'#b5894f',3)
    if aid=='facial_balance':
        # Subtle asymmetry is the actual steering difference.
        art+=line(139 if index==0 else 145,13,139 if index==0 else 145,149,'#6387ad',1,stroke_dasharray='4 5')
    if aid=='lip_shape' and vid=='soft_bow':
        art+=path('M 119 120 Q 140 110 161 120','none',lips,3)
    if aid=='expression':
        if vid=='thoughtful':art+=path('M 96 60 L 124 57 M 154 55 L 183 60','none',INK,3)
        if vid=='serious':art+=line(119,121,161,121,'#995c5a',2)+line(99,58,126,58,INK,2)
        if vid=='serene':art+=path('M 98 70 Q 112 75 126 70 M 154 70 Q 168 75 182 70','none',INK,2)
        if vid=='amused':art+=path('M 154 60 Q 168 48 182 55','none',INK,3)+path('M 117 122 Q 139 140 160 117','none',lips,2)
    if aid=='makeup_finish' and vid=='minimal_concealer':
        art+=ellipse(113,84,10,3,'#dfb797',opacity='.3')+ellipse(167,84,10,3,'#dfb797',opacity='.3')
    return art


def draw_hair(aid,vid,index):
    pigment=palette(aid,vid,index) if aid=='hair_color' else '#73503a'
    art=ellipse(140,91,42,50,SKIN)+rect(123,130,34,24,SKIN)
    top='M 94 86 Q 87 20 140 14 Q 193 20 186 86 L 176 48 Q 140 31 104 49 Z'
    art+=path(top,pigment,INK,1)
    left,right=91,189
    end=143
    if aid=='hair_length':end={'shaved':46,'buzz_cut':53,'ear_length':87,'chin_length':123,'shoulder_length':144,'collarbone_length':152,'mid_back':158,'waist_length':160}[vid]
    if aid=='hair_length' and vid in ('shaved','buzz_cut'):
        art=ellipse(140,91,42,50,SKIN)+path('M 100 61 Q 104 16 140 15 Q 176 16 180 61 Q 140 32 100 61 Z',pigment,INK,1)
        if vid=='buzz_cut':
            for j in range(45):art+=line(111+(j*7)%59,33+(j*11)%24,111+(j*7)%59,30+(j*11)%24,INK,1)
    elif aid=='hair_style' and vid in ('low_bun','high_bun','low_ponytail','high_ponytail','braided_crown','twin_braids'):
        if vid=='low_bun':art+=circle(181,123,22,pigment,stroke=INK)+path('M 167 123 Q 183 101 192 124 Q 180 141 173 127','none','#ae8866',2)
        if vid=='high_bun':art+=circle(140,16,25,pigment,stroke=INK)+ellipse(140,14,16,9,'none',stroke='#ae8866',stroke_width=2)
        if vid=='low_ponytail':art+=path('M 178 102 Q 226 113 213 158 Q 189 138 172 113 Z',pigment,INK,1)
        if vid=='high_ponytail':art+=path('M 171 32 Q 227 21 214 152 Q 188 113 174 47 Z',pigment,INK,1)
        if vid=='braided_crown':
            for j in range(13):art+=ellipse(99+j*7,46-23*math.sin(j*math.pi/12),6,5,'#a88765',stroke=pigment,stroke_width=2)
        if vid=='twin_braids':
            for x in [96,184]:
                for y in range(79,157,10):art+=ellipse(x+(2 if y%20 else -2),y,9,7,pigment,stroke='#ae8866',stroke_width=1)
    else:
        art+=path(f'M 100 47 Q 80 70 {left} {end} L 115 {end} Q 99 96 110 57 Z',pigment,INK,1)
        art+=path(f'M 180 47 Q 200 70 {right} {end} L 165 {end} Q 181 96 170 57 Z',pigment,INK,1)
        texture='straight' if aid!='hair_style' else vid
        if texture in ('messy_waves','soft_waves','loose_curls','tight_coils'):
            step=10 if texture=='tight_coils' else 24 if texture=='loose_curls' else 35
            for x in [97,107,174,184]:
                for y in range(62,end-4,step):art+=path(f'M {x} {y} q {-7 if texture=="messy_waves" else 6} {step/3} 0 {step/2} q 6 {step/3} 0 {step/2}','none','#b49a76',1.5)
        else:
            for x in [98,104,109,172,178,184]:art+=path(f'M {x} 61 Q {x-4} 96 {x+2} {end-4}','none','#ac8c65',1)
        if vid=='side_part':art+=path('M 119 24 Q 145 38 178 62','none','#bd9a76',4)
        if vid=='sleek_center_part':art+=line(140,17,140,42,SKIN,3)
    art+=line(112,91,123,91,INK,2)+line(157,91,168,91,INK,2)+path('M 128 119 Q 140 125 152 119','none','#a45f60',2)
    if aid=='hair_fringe':
        forms={
          'open_forehead':'M 99 54 Q 140 11 181 54 L 181 64 Q 140 32 99 64 Z',
          'blunt_bangs':'M 101 45 L 179 45 L 179 76 L 101 76 Z',
          'curtain_bangs':'M 101 44 L 140 39 L 126 83 L 99 66 Z M 140 39 L 179 44 L 181 66 L 154 83 Z',
          'side_swept_fringe':'M 102 42 L 180 42 Q 171 85 106 86 Q 124 70 102 42 Z',
          'micro_bangs':'M 102 42 L 178 42 L 178 58 L 102 58 Z',
          'curved_fringe':'M 102 42 L 178 42 L 178 68 Q 140 88 102 68 Z',
        }
        if vid in forms:art+=path(forms[vid],pigment,INK,1)
        if vid=='wispy_fringe':
            for x in [107,119,131,147,160,173]:art+=path(f'M {x} 43 Q {x+5} 66 {x-3} 76','none',pigment,3)
        if vid=='face_framing_strands':art+=path('M 108 50 Q 125 83 108 117 M 172 50 Q 155 83 172 117','none',pigment,4)
    if aid=='hair_accessory' and vid!='none':
        if vid=='silk_ribbon':art+=path('M 181 94 L 165 83 L 166 104 Z M 181 94 L 197 83 L 196 104 Z','#b8888c',INK,1)+line(181,94,183,125,'#b8888c',4)
        if vid=='metal_barrette':art+=rect(167,61,31,7,'#c0bdab',rx=3,transform='rotate(-24 167 61)')
        if vid=='wide_headband':art+=path('M 97 76 Q 103 18 140 20 Q 181 18 185 76','none','#8c789f',10)
        if vid=='small_clips':art+=line(175,59,190,51,'#c1ae7e',5)+line(175,70,191,63,'#c1ae7e',5)
        if vid=='scrunchie':art+=ellipse(184,108,15,9,'#b78991',stroke='#865c68',stroke_width=3)
        if vid=='decorative_comb':art+=path('M 171 41 L 191 49 M 174 43 L 171 57 M 181 46 L 178 60 M 188 49 L 185 63','none','#c3ab77',3)
        if vid=='flower_pin':
            for dx,dy in [(0,-7),(7,0),(0,7),(-7,0)]:art+=circle(183+dx,63+dy,6,'#cbaaaf')
            art+=circle(183,63,4,'#d1b455')
    if aid=='hair_color' and vid=='salt_and_pepper':
        for x in [97,106,173,184]:art+=path(f'M {x} 61 Q {x-3} 105 {x+2} 140','none','#ccd0d0',2)
    return art


def swatch(aid,vid,index):
    color=palette(aid,vid,index)
    art=rect(30,15,220,127,color,rx=12,stroke=INK,stroke_width=1)
    if aid=='fabric_color':art+=path('M 64 24 Q 107 76 66 133 M 129 24 Q 91 76 136 133 M 205 24 Q 159 76 214 133','none','#ffffff',5,opacity='.22')
    if aid=='metal_finish':
        art=ellipse(140,82,72,47,color,stroke=INK,stroke_width=1)+ellipse(140,82,49,28,PAPER,stroke=INK,stroke_width=1)
        if vid in ('brushed_steel','matte_brass'):
            for y in range(42,124,5):art+=line(110,y,170,y,'#5d6770',.7,opacity='.3')
        if vid=='hammered_gold':
            for j in range(36):art+=circle(140+63*math.cos(j),82+37*math.sin(j),3,'#e6c475',stroke='#a58342',stroke_width=.5)
        if vid in ('silver','polished_chrome','yellow_gold','rose_gold'):art+=path('M 73 64 Q 141 17 209 64','none','#fff9e9',6,opacity='.7')
    return art


def draw_textile(aid,vid,index):
    art=rect(30,14,220,130,'#9aaabe',rx=5,stroke=INK,stroke_width=1)
    if aid=='garment_pattern':
        if vid=='solid':return art
        if vid in ('pinstripe','wide_stripe'):
            for x in range(42,245,12 if vid=='pinstripe' else 35):art+=line(x,18,x,140,'#e6e8e6',1 if vid=='pinstripe' else 14)
        if vid=='gingham':
            for x in range(30,250,16):
                for y in range(14,144,16):
                    if ((x-30)//16+(y-14)//16)%2:art+=rect(x,y,16,16,'#d4dce0')
        if vid=='herringbone':
            for y in range(21,140,13):
                for x in range(38,240,19):art+=path(f'M {x} {y} l 8 6 l 8 -6','none','#e0e4e6',2)
        if vid=='polka_dot':
            for x in range(43,240,23):
                for y in range(27,139,23):art+=circle(x,y,4,'#eef0e8')
        if vid=='botanical_print':
            for x,y in [(65,65),(111,107),(173,52),(218,104)]:art+=path(f'M {x} {y+21} L {x} {y-25}','none','#e6e8d8',2)+ellipse(x-7,y-7,7,13,'#e6e8d8',transform=f'rotate(-35 {x-7} {y-7})')+ellipse(x+8,y+3,7,13,'#e6e8d8',transform=f'rotate(35 {x+8} {y+3})')
        if vid=='color_block':art+=rect(30,14,95,73,'#b3877c')+rect(125,87,125,57,'#c9bf98')
    if aid in ('fabric_material','shoe_material','wall_surface','ground_surface'):
        if vid in ('cotton_poplin','canvas','woven_fabric','linen','tweed'):
            spacing=4 if vid in ('cotton_poplin','canvas') else 8
            for x in range(34,249,spacing):art+=line(x,15,x,143,'#e1e3dc',1)
            for y in range(18,143,spacing):art+=line(31,y,249,y,'#647585',1)
            if vid in ('linen','tweed'):
                for j in range(55):art+=line(38+(j*37)%204,21+(j*17)%113,42+(j*37)%204,23+(j*17)%113,'#bfb3a1',2)
            if vid=='tweed':
                for j in range(90):art+=line(35+(j*19)%211,20+(j*23)%119,40+(j*19)%211,22+(j*23)%119,'#736d62' if j%2 else '#d4c4a4',2)
        if vid in ('wool','velvet','suede','nubuck'):
            for j in range(240):
                x=35+(j*29)%207;y=18+(j*43)%122
                art+=line(x,y,x+2,y+(4 if vid=='wool' else 2),'#b8c1c4',.8,opacity='.6')
            if vid in ('velvet','suede'):art+=path('M 43 124 Q 143 -6 239 80','none','#c2ccd0',20,opacity='.35')
        if vid in ('denim','herringbone'):
            for x in range(-72,250,8):art+=line(max(31,x),max(15,15+31-x),min(249,x+129),min(143,15+249-x),'#697f92',2)
            art+=line(44,19,44,139,'#d6b88c',2)+line(50,19,50,139,'#d6b88c',2)
        if vid=='corduroy':
            for x in range(38,250,10):art+=line(x,19,x,139,'#bbc7cb',5)+line(x+4,19,x+4,139,'#687b8a',1)
        if vid in ('satin','smooth_leather','patent_leather','rubber','grained_leather'):
            art+=path('M 53 24 Q 120 80 65 134 M 170 24 Q 114 80 210 135','none','#d5dee0',15 if vid in ('satin','patent_leather') else 5,opacity='.8' if vid=='patent_leather' else '.4')
            if vid=='grained_leather':
                for j in range(140):art+=ellipse(38+(j*17)%201,22+(j*29)%110,2,1,'#657889')
            if vid=='rubber':art+=path('M 48 125 Q 105 138 234 127','none','#586c7e',7)+rect(34,18,212,121,'#a9bac4',opacity='.25')
        if vid in ('exposed_brick','brick_paving','limestone','ceramic_tile','tile_floor','stone_paving'):
            material={'exposed_brick':'#bb8e79','brick_paving':'#ad826b','limestone':'#d3cbb7','ceramic_tile':'#c1ced0','tile_floor':'#c1ced0','stone_paving':'#aaa9a0'}[vid]
            art=rect(30,14,220,130,material,stroke=INK)
            for row,y in enumerate(range(14,144,26)):
                art+=line(30,y,250,y,'#787b7b',2)
                for x in range(30-(20 if row%2 else 0),250,44):art+=line(max(30,x),y,max(30,x),min(144,y+26),'#787b7b',2)
            if vid=='stone_paving':art+=path('M 39 39 L 59 45 L 55 65 M 134 92 L 150 80 L 162 98','none','#747970',3)
        if vid in ('wood_panel','wood_boards'):
            art=rect(30,14,220,130,'#b19a7c',stroke=INK)
            for x in range(34,245,29):art+=line(x,15,x,144,'#76634b',2)+path(f'M {x+7} 22 Q {x+16} 63 {x+7} 135','none','#937b5b',1)
        if vid in ('white_plaster','painted_stucco','concrete_wall','concrete'):
            art=rect(30,14,220,130,'#e3ded3' if vid=='white_plaster' else '#b8bab6',stroke=INK)
            for j in range(60 if vid=='painted_stucco' else 25):art+=circle(39+(j*23)%201,23+(j*31)%110,1.5 if vid=='painted_stucco' else .8,'#929792')
            if vid=='concrete_wall':art+=line(30,76,250,76,'#909691',1)+circle(77,45,3,'#949994')+circle(201,116,3,'#949994')
        if vid=='glass_wall':art=rect(30,14,220,130,'#bcd3de',stroke=INK)+line(104,15,104,143,'#6c8295',4)+line(176,15,176,143,'#6c8295',4)+path('M 41 124 L 122 27 M 158 131 L 235 31','none','#e9f4f7',7,opacity='.7')
        if vid=='grass':
            art=rect(30,14,220,130,'#9ba983',stroke=INK)
            for j in range(90):
                x=37+(j*37)%203;y=22+(j*13)%109
                art+=path(f'M {x} {y+10} l -3 -9 M {x} {y+10} l 4 -7','none','#5d7b53',1.4)
        if vid in ('gravel','packed_earth'):
            art=rect(30,14,220,130,'#bba88e',stroke=INK)
            for j in range(120 if vid=='gravel' else 25):art+=ellipse(39+(j*23)%198,24+(j*31)%107,3 if vid=='gravel' else 1.7,2,'#8c8c7e',stroke='#d0c4b0',stroke_width=.5)
    return art


def draw_clothing(aid,vid,index):
    color=BLUE
    art=circle(140,15,9,SKIN)+line(140,23,140,33,SKIN,7)
    art+=line(120,47,102,82,SKIN,7)+line(160,47,178,82,SKIN,7)
    art+=line(128,94,122,153,INK,8)+line(152,94,158,153,INK,8)
    bodice='M 120 35 L 160 35 L 170 92 L 110 92 Z'
    if aid=='body_build' or aid=='silhouette':
        widths={'lean':16,'athletic':26,'soft_average':24,'broad_frame':32,'petite_frame':18,'full_figure':35,'tall_frame':21,'compact_athletic':27,'elegant_hourglass':25,'couture_hourglass':28,'slender_hourglass':20,'slender_toned_legs':18,'graceful_curves':31,'statuesque':23}
        w=widths[vid];waist=w-8 if 'hourglass' in vid else w-3
        art=draw_pose('arms_relaxed')
        art+=path(f'M {140-w} 47 L {140+w} 47 L {140+waist} 73 L {140+w} 100 L {140-w} 100 L {140-waist} 73 Z',BLUE,INK,1.5)
        if vid in ('petite_frame','compact_athletic'):art=tag('g',art,transform='translate(26 25) scale(.82)')
        if vid in ('tall_frame','statuesque','slender_toned_legs'):art=tag('g',art,transform='translate(10 -2) scale(.94 1.07)')
        if vid in ('athletic','compact_athletic'):art+=path('M 115 56 Q 119 62 116 68 M 165 56 Q 161 62 164 68','none',INK,2)
        return art
    if aid=='shoulder_shape':
        w={'narrow_shoulders':17,'balanced_shoulders':23,'broad_shoulders':34,'soft_slope':24,'square_shoulders':29,'rounded_shoulders':27,'defined_shoulders':28,'relaxed_shoulders':22}[vid]
        slope=12 if vid=='soft_slope' else 1 if vid=='square_shoulders' else 7
        d=f'M 130 31 Q 140 37 150 31 L {140+w} {31+slope} L 168 91 L 112 91 L {140-w} {31+slope} Z'
        if vid=='rounded_shoulders':d='M 130 31 Q 110 32 109 58 L 113 91 L 167 91 L 171 58 Q 170 32 150 31 Z'
        art+=path(d,BLUE,INK,2)
        if vid=='defined_shoulders':art+=line(115,44,125,40,'#c4d4e1',2)+line(155,40,165,44,'#c4d4e1',2)
        if vid=='relaxed_shoulders':art+=path('M 90 28 l 0 16 l -4 -5 M 190 28 l 0 16 l 4 -5','none','#b18b4f',2)
        return art
    art+=path(bodice,color,INK,1.5)
    if aid in ('dress_style','hem_length','high_slit','drape_effect','skirt_cut'):
        hem={'above_knee':105,'at_knee':113,'below_knee':122,'mid_calf':135,'ankle':149,'floor':157,'asymmetric':145,'high_low':142}.get(vid,145)
        w=46 if vid in ('a_line','fit_and_flare','circle','a_line_skirt') else 27 if vid in ('bodycon','column_dress','pencil','straight_skirt','shift_dress') else 38
        art+=path(f'M 119 80 L 161 80 L {140+w} {hem} L {140-w} {hem} Z',color,INK,1.5)
        if vid in ('slip','bodycon'):art+=line(124,27,121,49,color,5)+line(156,27,159,49,color,5)+rect(128,30,24,14,SKIN)
        if vid=='off_shoulder':art+=path('M 110 48 Q 140 67 170 48','none','#a8bfd0',10)
        if vid=='shirt_dress':art+=poly([(126,34),(139,42),(131,54)],'#b1c5d5')+poly([(154,34),(141,42),(149,54)],'#b1c5d5')+line(140,45,140,140,INK,1)
        if vid in ('wrap_dress','wrap_skirt'):art+=path(f'M 160 50 L 123 90 L {160} {hem}','none','#c9d9e3',3)+line(117,82,168,82,INK,2)
        if vid=='high_neck_dress':art+=rect(132,27,16,18,color,stroke=INK,stroke_width=1)
        if vid in ('pleated_dress','pleated'):
            for x in range(109,180,9):art+=line(140+(x-140)*.4,86,x,hem,INK,1)
        if vid=='fit_and_flare':art+=line(118,80,162,80,INK,3)+path('M 125 89 L 114 140 M 155 89 L 166 140','none','#c9d9e3',2)
        if vid=='shift_dress':art+=path('M 117 39 L 108 143 L 172 143 L 163 39 Z',color,INK,1.5)
        if vid=='circle':art+=path('M 119 82 Q 93 106 87 145 L 193 145 Q 187 106 161 82 Z',color,INK,1)+path('M 122 91 L 106 140 M 140 91 L 140 140 M 158 91 L 174 140','none','#c9d9e3',2)
        if vid=='pencil':art+=line(115,92,116,140,'#c9d9e3',1)+line(165,92,164,140,'#c9d9e3',1)
        if vid=='tiered':
            for y in [104,125]:art+=line(105,y,177,y,'#c9d9e3',3)
        if vid=='bias_cut':art+=path(f'M 119 92 Q 148 104 163 {hem-4}','none','#c9d9e3',3)
        if vid=='asymmetric':art+=poly([(102,141),(178,118),(178,145)],PAPER)
        if vid=='high_low':art+=path('M 107 130 Q 140 111 173 130','none',PAPER,9)
        if aid=='high_slit':
            if vid=='on':art+=poly([(155,105),(152,145),(169,145)],SKIN)+line(155,105,152,145,INK,1)
            else:art+=line(104,145,176,145,'#ccdae2',3)
        if aid=='drape_effect':
            if vid=='on':art+=path('M 121 76 Q 132 115 109 139 M 156 74 Q 148 109 169 139 M 138 86 Q 126 105 138 136','none','#b9cddd',3)
            else:art+=line(121,82,116,139,'#c3d5df',1)+line(159,82,164,139,'#c3d5df',1)
    if aid=='top_style':
        if vid=='crew_tee':art+=path('M 120 35 L 106 41 L 101 59 L 115 63 M 160 35 L 174 41 L 179 59 L 165 63',color,INK,1)
        if vid=='button_shirt':art+=line(140,36,140,92,INK,1)+poly([(123,35),(140,44),(131,52)],'#cbd9e2')+poly([(157,35),(140,44),(149,52)],'#cbd9e2')
        if vid=='blouse':art+=path('M 119 37 Q 100 53 112 94 L 168 94 Q 180 53 161 37 Z',color,INK,1)+path('M 124 41 Q 130 62 119 87 M 155 41 Q 148 62 162 87','none','#c3d5df',2)
        if vid=='turtleneck':art+=rect(132,23,16,22,color,stroke=INK)
        if vid=='polo':art+=poly([(127,35),(140,40),(134,51)],'#c3d5df')+poly([(153,35),(140,40),(146,51)],'#c3d5df')+line(140,42,140,62,INK,1)
        if vid=='boat_neck_top':art+=path('M 120 35 Q 140 51 160 35',SKIN,'none',0)
        if vid=='tunic':art+=path('M 116 76 L 109 117 L 172 117 L 164 76 Z',color,INK,1)
        if vid=='knit_pullover':
            for y in range(49,91,5):art+=line(121,y,160,y,'#aec0cc',1)
    if aid=='neckline':
        forms={'crew_neck':'M 126 35 Q 140 50 154 35 Z','boat_neck':'M 120 35 Q 140 48 160 35 Z','square_neck':'M 126 35 L 126 51 L 154 51 L 154 35 Z','modest_v_neck':'M 124 35 L 140 58 L 156 35 Z','cowl_neck':'M 124 35 Q 140 60 156 35 Q 140 49 124 35 Z'}
        if vid in forms:art+=path(forms[vid],SKIN,INK,1)
        if vid in ('high_neck','stand_collar'):art+=rect(131,24 if vid=='high_neck' else 29,18,20 if vid=='high_neck' else 10,color,stroke=INK,stroke_width=1)
        if vid=='collared':art+=poly([(123,35),(140,40),(131,54)],'#cedde6')+poly([(157,35),(140,40),(149,54)],'#cedde6')
    if aid in ('sleeve_length','sleeve_shape'):
        length={'sleeveless':0,'cap_sleeve':10,'short_sleeve':19,'elbow_sleeve':30,'three_quarter_sleeve':38,'wrist_sleeve':47,'extended_cuff':54,'rolled_sleeve':37}.get(vid,46)
        if length:
            wide=14 if vid in ('bell_sleeve','bishop_sleeve','dolman_sleeve') else 9 if vid in ('puff_sleeve','structured_sleeve') else 5 if vid=='fitted_sleeve' else 7
            for x,dx in [(120,-1),(160,1)]:
                end=x+dx*length*.48
                art+=path(f'M {x-6} 37 L {x+6} 37 L {end+wide} {37+length} L {end-wide} {37+length} Z',color,INK,1)
                if vid in ('bishop_sleeve','rolled_sleeve','extended_cuff'):art+=line(end-wide,37+length-5,end+wide,37+length-5,'#c3d5df',4)
                if vid=='puff_sleeve':art+=ellipse(x+dx*5,49,13,15,color,stroke=INK)
                if vid=='raglan_sleeve':art+=line(140+dx*8,34,x+dx*4,57,'#c3d5df',2)
                if vid=='structured_sleeve':art+=line(x+dx*8,41,end+dx*3,75,INK,1)
                if vid=='dolman_sleeve':art+=path(f'M {x} 42 L {x+dx*24} 78 L {140+dx*17} 84 Z',color,INK,1)
                if vid=='bell_sleeve':art+=line(end-wide,37+length,end+wide,37+length,'#c3d5df',3)
        if vid=='straight_sleeve':art+=line(108,54,99,82,'#c3d5df',2)+line(172,54,181,82,'#c3d5df',2)
    if aid=='trouser_cut':
        w={'straight_leg':12,'wide_leg':23,'tapered':7,'bootcut':17,'culottes':23,'pleated_trousers':15,'relaxed_cargo':19,'slim_tailored':9}[vid]
        end=128 if vid=='culottes' else 151
        art+=path(f'M 114 80 L 166 80 L {155+w} {end} L {155-w} {end} L 140 96 L {125+w} {end} L {125-w} {end} Z',BLUE,INK,1)
        if vid=='bootcut':art+=path('M 107 151 L 115 120 L 133 120 L 140 151 M 140 151 L 148 120 L 165 120 L 172 151',BLUE,INK,1)
        if vid=='pleated_trousers':art+=line(126,85,121,143,'#c3d5df',2)+line(154,85,159,143,'#c3d5df',2)
        if vid=='relaxed_cargo':art+=rect(108,111,16,17,BLUE,stroke=INK)+rect(156,111,16,17,BLUE,stroke=INK)
    if aid=='waist_position':
        y={'natural_waist':80,'high_waist':69,'mid_rise':89,'hip_rise':96,'paperbag_waist':70,'contoured_waist':79,'wide_waistband':76,'elastic_waist':82}[vid]
        art+=rect(112,y,56,9 if vid=='wide_waistband' else 5,'#c2aa78',stroke=INK,stroke_width=1)
        if vid=='paperbag_waist':art+=path('M 112 70 l 5 -8 l 6 8 l 7 -8 l 6 8 l 7 -8 l 7 8 l 6 -8 l 6 8','none',BLUE,4)+circle(140,75,4,'#b89966')
        if vid=='contoured_waist':art+=path('M 112 79 Q 140 92 168 79','none','#c2aa78',6)
        if vid=='elastic_waist':
            for x in range(116,168,6):art+=line(x,y,x,y+5,INK,1)
    if aid in ('outerwear_style','outerwear_length') and vid!='no_outerwear':
        end={'cropped_jacket':70,'waist_jacket':81,'hip_jacket':96,'longline_jacket':111,'mid_thigh_coat':121,'knee_coat':132,'calf_coat':146,'ankle_coat':155,'blazer':99,'trench_coat':143,'wool_coat':149,'denim_jacket':85,'cardigan':103,'bomber':79,'cape':113}.get(vid,100)
        d=f'M 122 32 L 98 43 L 93 87 L 110 88 L 105 {end} L 175 {end} L 170 88 L 187 87 L 182 43 L 158 32 L 151 51 L 140 44 L 129 51 Z'
        if vid=='cape':d='M 120 32 L 87 113 L 193 113 L 160 32 Z'
        art+=path(d,'#9c8b79',INK,1.5)+line(140,46,140,end,INK,1)
        if vid=='trench_coat':art+=rect(108,77,65,6,'#6f6559')+rect(133,76,14,8,'#c3aa73',stroke=INK)
        if vid=='denim_jacket':art+=rect(115,53,16,14,'#9c8b79',stroke=INK)+rect(149,53,16,14,'#9c8b79',stroke=INK)
        if vid=='bomber':art+=line(105,end,175,end,'#6f6559',7)
        if vid=='wool_coat':art+=path('M 123 33 L 136 58 L 121 66 M 157 33 L 144 58 L 159 66','none','#b7a58e',6)
        if vid=='cardigan':
            for y in range(55,97,10):art+=circle(141,y,2,'#cbbf9d')
        if vid=='blazer':art+=path('M 121 34 L 133 58 L 124 63 L 140 75 M 159 34 L 147 58 L 156 63 L 140 75','none','#d0bda2',2)
    if aid=='seam_detail':
        if vid=='clean_seams':art+=line(120,41,113,88,'#a8bfd0',.8)+line(160,41,167,88,'#a8bfd0',.8)
        if vid=='topstitch':art+=line(119,43,114,88,'#dec49b',2,stroke_dasharray='2 3')+line(161,43,166,88,'#dec49b',2,stroke_dasharray='2 3')
        if vid=='piped_seams':art+=path('M 120 40 L 116 86 L 164 86 L 160 40','none','#d6b087',3)
        if vid=='panel_seams':art+=path('M 130 37 L 127 89 M 150 37 L 153 89 M 115 64 L 165 64','none',INK,2)
        if vid=='princess_seams':art+=path('M 129 37 Q 135 61 124 89 M 151 37 Q 145 61 156 89','none',INK,2)
        if vid=='flat_fell':art+=line(135,36,135,89,'#d4c293',1)+line(141,36,141,89,'#d4c293',1)+line(138,36,138,89,INK,1)
        if vid=='bound_edges':art+=path(bodice,'none','#d5b07e',5)
        if vid=='raised_welts':art+=line(129,39,126,87,'#c3d5df',4)+line(151,39,154,87,'#c3d5df',4)
    return art


def draw_shoe(vid,index):
    art=line(32,135,249,135,'#adb8c2',2)
    uppers={
      'loafers':'M 56 112 L 76 75 L 112 81 L 138 111 L 221 116 L 232 127 L 48 127 Z',
      'ballet_flats':'M 48 119 Q 54 91 82 96 Q 108 128 144 101 Q 195 111 226 119 L 230 128 L 48 128 Z',
      'ankle_boots':'M 65 112 L 72 41 L 130 41 L 140 108 Q 184 112 218 119 L 223 129 L 54 129 Z',
      'knee_boots':'M 65 112 L 72 5 L 127 5 L 137 108 Q 185 112 218 119 L 223 129 L 54 129 Z',
      'low_pumps':'M 53 112 L 76 72 Q 105 76 134 107 L 217 117 L 227 127 L 58 127 Z',
      'sneakers':'M 49 110 L 79 68 L 125 75 L 161 106 L 214 112 Q 231 116 230 130 L 48 130 Z',
      'oxfords':'M 54 110 L 82 71 L 125 79 L 152 105 L 218 114 L 230 127 L 52 127 Z',
      'sandals':'M 46 119 L 229 119 L 233 130 L 47 130 Z',
    }
    art+=path(uppers[vid],'#977a61',INK,2)
    if vid=='loafers':art+=path('M 93 91 L 125 93 M 85 107 Q 142 122 193 112','none','#d5ba98',4)
    if vid in ('oxfords','sneakers'):
        for i in range(5):art+=line(101+i*8,80+i*5,113+i*8,78+i*5,'#e1d7bf',2)
        if vid=='oxfords':art+=path('M 171 110 Q 166 118 173 125','none','#d5ba98',1.5)
        else:art+=line(53,122,225,122,'#ece7df',7)
    if vid in ('ankle_boots','knee_boots'):art+=line(102,15 if vid=='knee_boots' else 47,102,110,'#d5ba98',2)+rect(64,128,17,8,INK)
    if vid=='low_pumps':art+=poly([(63,126),(77,126),(74,136),(67,136)],INK)
    if vid=='sandals':art+=path('M 78 117 L 88 77 L 99 79 L 90 117 M 146 117 L 155 88 L 167 93 L 157 117','#977a61',INK,2)
    return art


def draw_accessory(aid,vid,index):
    if aid=='metal_finish':return swatch(aid,vid,index)
    if aid in ('jewelry_style','scarf_style','eyewear'):
        art=draw_face('expression','neutral',0)
        if vid in ('no_jewelry','no_scarf','no_eyewear'):return art+path('M 218 22 L 238 42 M 238 22 L 218 42','none','#9b7070',3)
        if aid=='eyewear':
            roundness=18 if 'round' in vid else 11 if 'oval' in vid else 3
            fill='#354457' if 'sunglasses' in vid else '#dcebf0'
            art+=rect(89,58,47,29,fill,rx=roundness,stroke=INK,stroke_width=2,fill_opacity=1 if 'sunglasses' in vid else .35)
            art+=rect(144,58,47,29,fill,rx=roundness,stroke=INK,stroke_width=2,fill_opacity=1 if 'sunglasses' in vid else .35)+line(136,66,144,66)
            if vid=='browline_glasses':art+=line(91,58,134,58,INK,5)+line(146,58,189,58,INK,5)
            if vid=='cat_eye_glasses':art+=poly([(88,58),(89,49),(106,58)],INK)+poly([(174,58),(192,49),(191,58)],INK)
        if aid=='jewelry_style':
            if vid=='stud_earrings':art+=circle(80,89,4,'#d1ae65')+circle(200,89,4,'#d1ae65')
            if vid=='hoop_earrings':art+=ellipse(79,99,10,15,'none',stroke='#d1ae65',stroke_width=3)+ellipse(201,99,10,15,'none',stroke='#d1ae65',stroke_width=3)
            if vid=='pendant':art+=path('M 101 130 Q 140 171 179 130','none','#d1ae65',2)+circle(140,154,5,'#d1ae65')
            if vid=='pearl_strand':
                for j in range(15):art+=circle(104+j*5.2,135+15*math.sin(j*math.pi/14),3,'#f2e8ce',stroke='#ac9f86',stroke_width=.5)
            if vid=='cuff_bracelet':art+=rect(33,74,24,49,SKIN,rx=7)+rect(29,92,32,13,'#d1ae65',stroke=INK,stroke_width=1)
            if vid=='fine_rings':
                for j in range(3):art+=rect(25+j*10,82,7,48,SKIN,rx=3)+rect(24+j*10,103,9,4,'#d1ae65')
            if vid=='sculptural_earrings':art+=poly([(79,87),(87,102),(78,115),(70,102)],'#d1ae65')+poly([(201,87),(209,102),(200,115),(192,102)],'#d1ae65')
        if aid=='scarf_style':
            if vid=='loose_loop':art+=path('M 104 132 Q 140 163 176 132','none','#b28888',12)
            if vid=='single_knot':art+=path('M 111 137 L 162 137 L 145 150 L 154 160 L 137 157 L 127 160 L 132 150 Z','#b28888',INK,1)
            if vid=='shoulder_drape':art+=poly([(92,122),(116,143),(119,160),(74,160)],'#b28888')
            if vid=='neck_wrap':art+=path('M 106 137 L 175 137 L 167 154 L 112 154 Z','#b28888',INK,1)+line(111,143,169,143,'#d1b0ac',2)
            if vid=='long_ends':art+=rect(106,133,12,27,'#b28888')+rect(163,133,12,27,'#b28888')+line(110,139,170,139,'#b28888',9)
            if vid=='triangle_fold':art+=poly([(102,132),(177,132),(140,160)],'#b28888')
            if vid=='small_bow':art+=poly([(138,146),(117,136),(119,155)],'#b28888')+poly([(142,146),(163,136),(161,155)],'#b28888')+circle(140,146,4,'#966c70')
        return art
    if aid=='bag_style':
        if vid=='no_bag':return adult()+path('M 200 72 l 22 22 M 222 72 l -22 22','none','#9b7070',3)
        d={'structured_tote':'M 75 51 L 205 51 L 217 140 L 63 140 Z','crossbody':'M 84 76 L 196 76 L 196 138 L 84 138 Z','satchel':'M 67 61 L 213 61 L 213 139 L 67 139 Z','clutch':'M 54 77 L 226 77 L 226 129 L 54 129 Z','bucket_bag':'M 90 49 Q 140 35 190 49 L 181 138 Q 140 153 99 138 Z','shoulder_bag':'M 64 79 Q 140 122 216 79 L 203 135 Q 140 157 77 135 Z','backpack':'M 89 62 Q 140 23 191 62 L 198 137 L 82 137 Z'}[vid]
        art=path(d,'#aa8c6b',INK,2)
        if vid=='structured_tote':art+=path('M 95 53 Q 95 12 120 53 M 159 53 Q 184 12 184 53','none',INK,4)
        if vid=='crossbody':art+=path('M 83 78 Q 16 -31 196 78','none',INK,4)
        if vid=='satchel':art+=path('M 117 61 Q 140 19 164 61','none',INK,4)+path('M 69 62 L 86 95 L 194 95 L 212 62','none','#d5b58a',3)+rect(133,90,14,13,'#cdb577')
        if vid=='clutch':art+=path('M 55 78 L 140 106 L 225 78','none','#d5b58a',3)
        if vid=='bucket_bag':art+=line(92,56,188,56,'#e0c7a1',4)+path('M 91 56 Q 54 5 183 54','none',INK,3)
        if vid=='shoulder_bag':art+=path('M 76 82 Q 140 -26 205 82','none',INK,6)
        if vid=='backpack':art+=rect(100,96,80,33,'#947759',rx=6,stroke=INK)+path('M 114 40 Q 140 10 165 40','none',INK,5)
        return art
    if aid=='belt_style':
        art=rect(26,60,228,34,'#798da6',rx=6)
        if vid=='no_belt':return art+line(30,79,249,79,'#bccbd6',1,stroke_dasharray='4 4')
        w=22 if vid=='wide_leather' else 8 if vid=='narrow_leather' else 13
        art+=rect(27,77-w/2,226,w,'#8c7157')
        if vid=='round_buckle':art+=circle(140,77,12,'none',stroke='#d4b573',stroke_width=4)
        elif vid=='fabric_tie':art+=poly([(139,77),(115,62),(115,88)],'#b48c79')+poly([(141,77),(165,62),(165,88)],'#b48c79')+line(140,78,147,115,'#b48c79',6)
        else:art+=rect(129,68,23,18,'none',rx=1,stroke='#d4b573',stroke_width=3 if vid=='minimal_buckle' else 4)
        if vid=='braided_belt':
            for x in range(30,250,12):art+=path(f'M {x} 71 l 9 11 l 9 -11','none','#d2b696',2)
        if vid=='double_wrap':art+=rect(27,89,226,6,'#8c7157')
        return art
    raise ValueError(f'Unsupported accessory: {aid}')


def draw_optics(aid,vid,index):
    art=rect(24,9,232,139,'#d9e3e9',rx=5,stroke=INK,stroke_width=2)
    if aid=='focal_length':
        focal=int(vid[:-2]);scale=.5+(focal-24)/160
        art+=poly([(31,136),(84,29),(118,136)],'#a0b5bd')+poly([(183,136),(217,42),(248,136)],'#a0b5bd')
        art+=adult(140,92,scale)
        art+=path(f'M 39 20 L {39+90*24/focal} 65 M 241 20 L {241-90*24/focal} 65','none','#ab874d',2)
        return art
    if aid=='aperture':
        f=float(vid[2:].replace('_','.'));r=26/math.sqrt(f)
        for x,y in [(55,50),(85,109),(207,40),(224,105)]:art+=circle(x,y,r,'#a6b4ca',opacity='.8')
        art+=adult(140,89,.95)+rect(129-f*2,32,22+f*4,109,'none',stroke='#b19353',stroke_width=2)
        art+=circle(52,131,13,'#485468')+circle(52,131,max(2,14-f*.65),'#dce7ee')
        return art
    if aid=='shutter_motion':
        strength={'frozen':0,'crisp_still':0,'slight_fabric_blur':2,'walking_blur':3,'panned':5,'long_background':7,'handheld_trace':1,'wind_trace':4}[vid]
        art+=adult(140,88,.95)
        if vid=='frozen':art+=path('M 128 58 L 176 69 L 163 92 L 135 85 Z',BLUE,INK,1)
        for j in range(strength):
            y=50+j*12 if vid in ('panned','long_background') else 118+j*6 if vid=='walking_blur' else 70+j*8
            art+=line(45,y,95+strength*7,y,'#8ca4b7',2,opacity='.5')+line(187,y,244,y,'#8ca4b7',2,opacity='.5')
        if vid=='handheld_trace':art+=tag('g',adult(142,90,.95),opacity='.15')
        if vid in ('slight_fabric_blur','wind_trace'):art+=path('M 153 72 Q 190 54 207 83 L 176 94 Z',BLUE,'#9db5c6',3,opacity='.45')
        return art
    if aid=='grain':
        art+=rect(25,10,116,137,'#63758b')+rect(141,10,114,137,'#c1c9cc')+adult(140,86,.9)
        count={'clean_digital':0,'fine_grain':190,'medium_grain':110,'coarse_grain':70,'shadow_grain':150,'soft_film_grain':220,'high_iso':300,'low_iso':40}[vid]
        radius=1.7 if vid=='coarse_grain' else 1.1 if vid in ('medium_grain','high_iso') else .6
        for j in range(count):
            x=28+(j*37)%222;y=13+(j*29)%130
            if vid!='shadow_grain' or x<141:art+=circle(x,y,radius,'#182c41' if j%2 else '#e9edea',opacity='.4' if vid=='soft_film_grain' else '.65')
        return art
    if aid=='focus_target':
        art+=adult(140,83,1.05)+rect(187,61,46,58,'#b3b5a5')
        box={'near_eye':(135,29,14,14),'both_eyes':(126,29,28,14),'face_plane':(124,21,33,28),'garment_detail':(124,67,24,26),'hands':(105,88,69,22),'full_subject':(107,19,66,126),'accessory':(159,91,26,29),'environmental':(29,14,221,127)}[vid]
        if vid=='accessory':art+=rect(159,94,21,23,'#b69570')
        art+=rect(*box,'none',stroke='#b68c4f',stroke_width=3)
        return art
    if aid in ('white_balance','highlight_rolloff'):
        colors=['#cedce4','#e3d3bb','#ead0ae','#abc7dc','#b2c7db','#dac9b3','#d3d3c8','#cdd4d9'] if aid=='white_balance' else ['#e8e3d4','#e1e4e5','#e9d9bd','#ffffff','#efede4','#ece1c6','#d1cfbf','#f0ece1']
        art+=rect(25,10,230,137,colors[index])+adult(140,87,.95)
        if aid=='white_balance':
            for j,c in enumerate(['#af6d63','#779568','#657fa6','#bca972','#8d758e','#ccccbc']):art+=rect(41+j*33,126,28,14,c)
        else:
            for j in range(8):
                level=min(255,145+j*14+(index-3)*3)
                art+=rect(32+j*27,122,26,18,f'#{level:02x}{level:02x}{level:02x}')
            if vid=='glowing_edge':art+=ellipse(140,57,22,28,'#fff5d3',opacity='.18')
        return art
    if aid=='camera':
        art=rect(37,55,94,62,'#64768d',rx=8,stroke=INK)+rect(55,42,43,15,'#64768d',rx=3,stroke=INK)+circle(84,85,25,'#334055')+circle(84,85,18,'#98b4c4')
        art+=adult(213,88,.9)
        if vid=='on':art+=rect(168,16,86,125,'none',stroke='#b09055',stroke_width=2)+path('M 157 55 L 166 55 M 157 93 L 166 93','none','#b09055',2)
        else:art+=rect(151,21,120,123,'none',stroke='#84969f',stroke_width=1,stroke_dasharray='5 4')
        return art
    raise ValueError(aid)


def draw_light(aid,vid,index):
    art=circle(140,81,33,SKIN)+rect(131,111,18,16,SKIN)+path('M 118 125 L 162 125 L 183 157 L 98 157 Z',BLUE,INK,1)
    if aid=='light_direction':
        x,y={'front_light':(140,18),'left_light':(42,74),'right_light':(238,74),'top_light':(140,0),'back_light':(140,135),'front_left':(62,20),'front_right':(218,20),'low_side_light':(40,131)}[vid]
        art+=circle(x,y,13,'#ddc67b',stroke='#a98b4e')+line(x,y,140,80,'#d0b65a',2,stroke_dasharray='4 4')
        if x<140:art+=path('M 140 48 A 33 33 0 0 1 140 114 Z','#755649','none',0,opacity='.35')
        if x>140:art+=path('M 140 48 A 33 33 0 0 0 140 114 Z','#755649','none',0,opacity='.35')
        if vid in ('top_light','front_light'):art+=ellipse(140,91,13,5,'#785748',opacity='.25' if vid=='front_light' else '.55')
        if vid=='back_light':art+=circle(140,81,33,'none',stroke='#e3ce8e',stroke_width=5)+circle(140,81,28,'#806055',opacity='.3')
        if vid=='low_side_light':art+=ellipse(137,63,24,9,'#79584a',opacity='.4')
    if aid=='light_quality':
        sizes={'hard':7,'soft':30,'diffuse':46,'filtered':24,'dappled':14,'strip_softbox':8,'bounce':38,'fresnel':12}
        w=sizes[vid];art+=rect(34,31,2*w,54,'#e0cb8a',rx=5,stroke='#ab9158')
        art+=poly([(34+2*w,31),(126,61),(126,99),(34+2*w,85)],'#e1cf91',opacity='.2')
        art+=ellipse(192,130,36,8,'#698090',opacity='.5' if vid in ('hard','fresnel') else '.18')
        if vid=='filtered':art+=line(96,22,96,114,'#b6c4c8',7,stroke_dasharray='2 4')
        if vid=='dappled':
            for x,y in [(122,60),(151,77),(127,92),(160,104)]:art+=ellipse(x,y,6,9,'#eddaae',opacity='.7')
        if vid=='bounce':art+=path('M 222 18 L 248 72 L 201 127','none','#eee2bf',8)+line(140,49,222,30,'#c8ad65',2)
        if vid=='fresnel':
            for r in [5,9,13]:art+=circle(54,58,r,'none',stroke='#b49659',stroke_width=1)
    if aid=='lighting_pattern':
        if vid in ('split','rembrandt','loop','short','broad'):art+=path('M 140 48 A 33 33 0 0 1 140 114 Z','#705349','none',0,opacity='.55')
        if vid=='rembrandt':art+=poly([(146,80),(164,80),(153,95)],'#dfb793')
        if vid=='loop':art+=ellipse(151,85,6,4,'#7d5b48')+ellipse(162,86,8,12,'#cf9e7b')
        if vid=='butterfly':art+=poly([(130,91),(150,91),(140,101)],'#865e48')
        if vid=='broad':art+=path('M 140 48 A 33 33 0 0 0 140 114 Z','#ead0ae','none',0,opacity='.6')
        if vid=='short':art+=ellipse(162,72,8,18,'#ead0ae',opacity='.65')
        if vid=='clamshell':art+=ellipse(140,81,26,27,'#ead0ae',opacity='.4')+rect(100,12,80,12,'#d6bf7b')+rect(112,127,56,9,'#d6bf7b')
        if vid=='rim':art+=circle(140,81,33,'none',stroke='#e3cf93',stroke_width=5)+circle(140,81,28,'#765549',opacity='.5')
    if aid=='fill_ratio':
        ratios=[1,2,3,4,6,8,16,24];ratio=ratios[index]
        art+=circle(44,52,18,'#dcc982')+circle(233,53,18,'#dcc982',opacity=max(.08,1/ratio))
        art+=path('M 140 48 A 33 33 0 0 1 140 114 Z','#51463f','none',0,opacity=.05+.75*(1-1/ratio))
        art+=rect(28,110,31,29,'#d0b774')+rect(216,110,31,29,'#d0b774',opacity=max(.04,1/ratio))
        if vid=='no_fill':art+=path('M 220 40 l 26 26 M 246 40 l -26 26','none','#9c7071',3)
        if vid=='negative_fill':art+=rect(203,30,26,72,'#26344a')
    if aid=='light_temperature':
        hue=palette(aid,vid,index)
        art=rect(15,10,250,140,hue,rx=8)+circle(140,81,33,SKIN)+adult(140,113,.5)
        art+=circle(56,42,14,hue,stroke='#9d925e',stroke_width=2)+line(66,48,108,71,'#f3ead2',3)
        if vid=='mixed_warm_cool':art+=rect(15,10,125,140,'#e7bb7f',rx=8,opacity='.5')+rect(140,10,125,140,'#8db1d5',rx=8,opacity='.5')
    if aid=='practical_light':
        art=rect(13,7,254,143,'#d4d8d8',rx=5)+adult(150,94,.78)
        if vid=='no_practical':return art+path('M 29 28 l 19 19 M 48 28 l -19 19','none','#9b7070',3)
        if vid in ('table_lamp','floor_lamp'):
            x,y=(53,81) if vid=='table_lamp' else (53,45)
            art+=path(f'M {x-20} {y} L {x-12} {y-30} L {x+12} {y-30} L {x+20} {y} Z','#d7be7c',INK,1)+line(x,y,x,137 if vid=='floor_lamp' else 108)
            if vid=='table_lamp':art+=rect(24,111,59,6,'#a28f76')+line(29,117,29,149)+line(79,117,79,149)
        if vid=='pendant_lamp':art+=line(62,8,62,43)+path('M 38 62 L 50 41 L 74 41 L 86 62 Z','#d7be7c',INK,1)
        if vid=='wall_sconce':art+=rect(39,44,10,51,'#9b8c76')+ellipse(56,67,17,23,'#d7be7c')
        if vid=='string_lights':
            art+=path('M 15 28 Q 140 83 267 28','none',INK,1)
            for x in range(30,270,29):art+=circle(x,30+22*math.sin((x-15)/252*math.pi),4,'#e5cf8e')
        if vid=='shop_sign':art+=rect(27,30,79,26,'#758b98',rx=4,stroke='#e5cf8e',stroke_width=4)
        if vid=='lantern':art+=rect(43,83,32,41,'#dac688',rx=3,stroke=INK,stroke_width=3)+path('M 44 82 Q 59 53 74 82','none',INK,2)+line(59,87,59,120)
    art+=circle(130,78,2,INK)+circle(150,78,2,INK)
    return art


def draw_composition(aid,vid,index):
    art=rect(18,6,244,149,'#dbe6ea',stroke=INK,stroke_width=2)
    if aid=='shot_size':
        scale,x,y={'face_closeup':(3.2,140,193),'head_and_shoulders':(2.1,140,133),'chest_up':(1.7,140,111),'waist_up':(1.36,140,96),'three_quarter_body':(1.1,140,85),'full_body':(.94,140,88),'environmental_wide':(.52,140,112),'detail_crop':(2.7,140,38)}[vid]
        art+=rect(29,91,47,55,'#b2c3bd')+adult(x,y,scale)
        # Nested viewport clips only the illustration, never relies on CSS.
        return tag('svg',art,x=0,y=0,width=280,height=160,viewBox='0 0 280 160',overflow='hidden')
    if aid=='subject_placement':
        x,y={'centered':(140,88),'left_third':(99,88),'right_third':(181,88),'lower_center':(140,120),'upper_center':(140,65),'far_left':(62,88),'far_right':(220,88),'balanced_offset':(120,88)}[vid]
        art+=adult(x,y,.76)
        if vid=='balanced_offset':art+=tree(220,54,'tree',.65)
        art+=line(99,8,99,153,'#a9b9c1',1,stroke_dasharray='4 4')+line(181,8,181,153,'#a9b9c1',1,stroke_dasharray='4 4')
        return art
    if aid=='camera_height':
        art=adult(183,84,1.05)+line(28,148,251,148,'#9aaeb8',1)
        y={'eye_level':38,'chest_level':64,'waist_level':88,'knee_level':120,'above_eye':22,'high_angle':8,'ground_level':145,'overhead':0}[vid]
        x=181 if vid=='overhead' else 44
        art+=rect(x-13,y-8,24,16,'#62778d',rx=2,stroke=INK)+circle(x,y,5,'#b6d1dc')+line(x+12,y,180,78,'#b58d4f',2,stroke_dasharray='5 3')
        return art
    if aid=='leading_lines':
        art+=adult(140,101,.7)
        if vid=='path_convergence':art+=line(25,148,124,108,'#b6976c',3)+line(255,148,156,108,'#b6976c',3)
        if vid=='vertical_columns':
            for x in [48,79,204,235]:art+=rect(x,14,11,134,'#a8b3b5')
        if vid=='diagonal_rail':art+=line(20,147,221,45,'#a28f76',6)
        if vid=='curved_walkway':art+=path('M 27 149 Q 239 154 140 118','none','#bda17e',16)
        if vid=='stair_rhythm':
            for y in range(114,155,9):art+=line(140-(y-90)*1.3,y,140+(y-90)*1.3,y,'#a28f76',3)
        if vid=='window_grid':
            for x in range(46,240,39):art+=line(x,13,x,148,'#9caeb8',3)
            for y in [43,79,115]:art+=line(20,y,260,y,'#9caeb8',3)
        if vid=='arch_frame':art+=path('M 55 150 L 55 58 Q 140 -15 225 58 L 225 150','none','#abb5b5',13)
        if vid=='no_strong_lines':art+=ellipse(67,106,25,15,'#b9cdc5',opacity='.4')
        return art
    if aid=='foreground':
        art+=adult(140,88,.83)
        if vid=='soft_leaves':art+=ellipse(47,65,35,16,'#83a187',opacity='.55',transform='rotate(-30 47 65)')+ellipse(25,121,23,33,'#83a187',opacity='.55')
        if vid=='window_edge':art+=rect(30,8,13,147,'#8497a4')+rect(31,90,105,10,'#8497a4')
        if vid=='door_frame':art+=rect(22,7,22,148,'#a28a70')+rect(22,7,215,14,'#a28a70')
        if vid=='flower_blur':
            for x in [30,59,218,244]:art+=circle(x,146,16,'#c89ba5',opacity='.6')
        if vid=='rail_edge':art+=line(19,127,261,140,'#8497a4',13)
        if vid=='reflective_pane':art+=poly([(28,7),(84,7),(246,155),(190,155)],'#ecf5f5',opacity='.55')+line(21,8,21,155,'#8497a4',4)
        if vid=='fabric_edge':art+=path('M 18 8 Q 89 56 49 156 L 18 156 Z','#b79291','none',0,opacity='.7')
        if vid=='clear_foreground':art+=line(33,146,59,146,'#9ab1bb',1)
        return art
    if aid=='horizon_height':
        y={'low_horizon':119,'middle_horizon':82,'high_horizon':45,'near_bottom':145,'near_top':16,'no_horizon':160,'descending_left':90,'descending_right':70}[vid]
        tilt=-24 if vid=='descending_left' else 24 if vid=='descending_right' else 0
        art+=poly([(19,y-tilt),(261,y+tilt),(261,154),(19,154)],'#aec1ac')
        art+=adult(140,100,.7)
        return art
    raise ValueError(aid)


def draw_weather(aid,vid,index):
    art=rect(0,0,280,109,'#d7e6ed')+rect(0,109,280,51,'#a9bb91')+tree(45,49,'tree',.9)+tree(237,40,'tree',1.0)
    if aid=='weather':
        if vid in ('clear','broken_cloud'):art+=circle(189,31,17,'#e8ce7e')
        if vid in ('overcast','light_rain','after_rain','snowfall','broken_cloud'):art+=ellipse(142,26,64,19,'#adbcc5')+ellipse(201,36,48,16,'#c3cdd2')
        if vid=='light_rain':
            for j in range(35):
                x=18+(j*23)%248;y=44+(j*17)%105
                art+=line(x,y,x-3,y+9,'#7b9eb3',1.3)
        if vid=='after_rain':art+=ellipse(112,137,42,9,'#89aebe')+ellipse(192,123,22,5,'#89aebe')
        if vid=='snowfall':
            art+=rect(0,110,280,50,'#eaf0f2')
            for j in range(32):art+=circle(12+(j*29)%257,6+(j*19)%140,2,'#f9fbfd')
        if vid in ('misty','hazy'):
            for y in [70,88,110,126]:art+=rect(0,y,280,12,'#e5edf0',opacity='.5' if vid=='misty' else '.22')
        return art
    if aid=='time_of_day':
        sky=['#b4bccd','#cddfeb','#d9e9f1','#c9e3ed','#e3c498','#cd9c91','#8e9bb6','#34435d'][index]
        sun_y=[96,68,17,56,94,108,130,175][index]
        art=rect(0,0,280,110,sky)+rect(0,110,280,50,'#91a881' if index<5 else '#657463')+tree(43,45,'tree',1)+tree(237,39,'tree',1.1)
        if index<6:art+=circle(170,sun_y,17,'#e9c576')
        else:
            art+=circle(193,23,12,'#dce4e6')
            if vid=='night':
                for x,y in [(17,22),(62,11),(127,42),(164,18),(241,40)]:art+=circle(x,y,1.4,'#eceee4')
        return art
    if aid=='wind':
        amp={'still_air':0,'light_breeze':7,'side_breeze':17,'headwind':11,'back_breeze':-11,'gust':30,'swirling_breeze':22,'sheltered':4}[vid]
        art+=adult(140,91,.9)
        if vid=='headwind':art+=path('M 150 48 Q 132 36 119 50','none','#76553b',6)
        else:art+=path(f'M 146 48 Q {165+amp} 38 {156+amp} 73','none','#76553b',6)
        if amp:
            for y in [42,72,98]:art+=path(f'M 64 {y} Q {90+abs(amp)} {y-8} 111 {y}','none','#7d9caf',2)
            art+=path(f'M 148 91 L {162+amp} 103 L 147 111 Z',BLUE,INK,1)
        if vid=='swirling_breeze':art+=path('M 192 101 Q 226 80 209 58 Q 197 51 188 64','none','#7d9caf',2)
        if vid=='sheltered':art+=rect(96,18,8,132,'#a8b3b3')+path('M 20 56 Q 75 26 89 70','none','#7d9caf',3)
        return art
    if aid=='season':
        foliage=['#a6bf8e','#7f9f73','#668765','#8b9561','#be9357','#9e8062','#cdd4d7','#b8c6bd'][index]
        art=rect(0,0,280,108,'#d7e2e8')+rect(0,108,280,52,foliage)
        art+=tree(51,34,'baretrees' if index>=5 else 'tree',1)+tree(223,39,'baretrees' if index>=5 else 'tree',1)
        if index<5:art+=ellipse(51,48,30,31,foliage)+ellipse(223,53,30,31,foliage)
        if vid=='spring':
            for x,y in [(30,36),(66,52),(224,33),(211,67)]:art+=circle(x,y,4,'#e0bdc5')
        if vid=='early_summer':art+=circle(180,25,14,'#e9d396')
        if vid=='high_summer':art+=circle(180,18,20,'#e7cb73')+rect(92,127,112,8,'#c9b287')
        if vid=='late_summer':
            for x in range(80,200,15):art+=line(x,141,x+5,110,'#beaa77',2)
        if vid in ('autumn','late_autumn'):
            for x,y in [(18,135),(64,146),(174,121),(215,144)]:art+=ellipse(x,y,6,3,'#bb8752')
        if vid=='winter':art+=rect(0,128,280,32,'#edf1f3')
        if vid=='early_winter':art+=line(15,143,261,143,'#e6edef',2,stroke_dasharray='4 3')
        return art
    raise ValueError(aid)


def draw_prop(aid,vid,index):
    if aid=='eyewear':return draw_accessory(aid,vid,index)
    if aid=='hand_prop':
        if vid=='no_hand_prop':return path('M 100 135 L 100 74 Q 102 61 107 75 L 110 100 L 109 49 Q 115 39 120 49 L 121 96 L 124 39 Q 130 30 135 40 L 135 95 L 140 49 Q 147 39 151 51 L 151 104 L 173 83 Q 188 82 180 101 L 163 135 Z',SKIN,INK,2)
        if vid in ('book','notebook'):return rect(89,26,101,116,'#9b7b69' if vid=='book' else '#7a8eab',rx=3,stroke=INK,stroke_width=2)+rect(94,31,8,105,'#d4c2a6')+line(111,47,169,47,'#e0d5bb',2)+(line(179,31,179,137,'#473f46',3) if vid=='notebook' else rect(111,61,58,39,'none',stroke='#d4c2a6'))
        if vid=='coffee_cup':return path('M 97 49 L 184 49 L 173 141 L 110 141 Z','#d9cbb5',INK,2)+rect(92,37,98,13,'#eee4d1',rx=3,stroke=INK)+rect(104,80,75,34,'#aa8b6e')
        if vid=='ceramic_mug':return rect(82,54,106,87,'#8ca5b5',rx=8,stroke=INK,stroke_width=2)+path('M 188 68 Q 241 88 188 121','none','#8ca5b5',13)+path('M 107 31 Q 95 13 108 3 M 139 30 Q 125 14 140 4','none','#a8bcc6',2)
        if vid=='folded_scarf':return path('M 61 57 L 208 35 L 221 115 L 74 138 Z','#b08787',INK,2)+path('M 78 129 L 73 69 L 211 47 M 84 92 L 218 71','none','#d6b5ac',3)
        if vid=='flower_stem':
            art=line(144,138,137,47,'#65845b',4)+ellipse(127,98,13,6,'#91a373',transform='rotate(30 127 98)')
            for dx,dy in [(-12,0),(12,0),(0,-12),(0,12)]:art+=circle(136+dx,41+dy,11,'#b795a6')
            return art+circle(136,41,7,'#dbc17c')
        if vid=='umbrella':return path('M 140 13 L 158 120 L 147 126 Z','#8498b4',INK,2)+line(151,123,157,143,INK,4)+path('M 157 143 Q 169 156 173 140','none',INK,4)
    if aid=='seating_prop':
        if vid=='no_seat':return line(35,139,244,139,'#acb9c2',2)+path('M 124 73 l 31 31 M 155 73 l -31 31','none','#9c7070',3)
        if vid in ('wood_chair','upholstered_chair','cafe_chair'):
            art=path('M 79 42 L 79 97 L 183 97 M 86 97 L 72 147 M 174 97 L 192 147','none','#a18867',7)
            if vid=='wood_chair':art+=rect(80,38,95,11,'#a18867')+line(108,48,108,93,'#a18867',4)+line(145,48,145,93,'#a18867',4)
            if vid=='upholstered_chair':art+=rect(82,28,94,54,'#9b98a8',rx=13,stroke=INK)+rect(75,87,114,21,'#9b98a8',rx=6,stroke=INK)
            if vid=='cafe_chair':art+=path('M 82 94 Q 51 17 132 20 Q 194 23 175 94','none','#a18867',6)
            return art
        if vid=='bench':return rect(34,85,212,15,'#b49b7b',stroke=INK)+rect(48,39,184,24,'#b49b7b',stroke=INK)+line(60,100,51,146,INK,5)+line(219,100,228,146,INK,5)
        if vid=='stool':return ellipse(140,72,66,16,'#b5a188',stroke=INK)+line(86,80,67,147,INK,5)+line(194,80,213,147,INK,5)+line(76,123,204,123,INK,3)
        if vid=='stone_ledge':return rect(37,78,206,26,'#aaa89c',stroke=INK)+rect(50,104,180,41,'#c2beb0',stroke=INK)+path('M 89 81 L 97 104 M 175 81 L 170 104','none','#838c89',1)
        if vid=='low_ottoman':return rect(45,78,190,49,'#9faeb4',rx=14,stroke=INK)+ellipse(140,78,93,19,'#b5c2c5',stroke=INK)+line(66,123,66,145,INK,5)+line(213,123,213,145,INK,5)
    if aid=='background_prop':
        if vid=='no_background_prop':return rect(39,18,202,116,'#e0e8eb',stroke='#b5c3ca')+line(39,134,241,134,'#b5c3ca',2)
        if vid=='vase':return path('M 122 35 L 158 35 L 154 66 Q 195 121 173 143 L 107 143 Q 85 121 126 66 Z','#b69a86',INK,2)+ellipse(140,35,18,4,'#806b60')
        if vid=='stacked_books':return rect(58,112,155,20,'#a38277',stroke=INK)+rect(71,85,148,22,'#8298b0',stroke=INK)+rect(49,58,145,23,'#c4b68f',stroke=INK)+line(61,121,197,121,'#e5dac2',4)
        if vid=='framed_art':return rect(62,19,156,124,'#c4b39a',stroke=INK,stroke_width=4)+rect(70,27,140,108,'#eadfc9')+circle(110,62,21,'#a88077')+poly([(101,118),(158,45),(193,118)],'#7994a4')
        if vid=='bicycle':return circle(72,113,32,'none',stroke=INK,stroke_width=4)+circle(212,113,32,'none',stroke=INK,stroke_width=4)+path('M 72 113 L 118 65 L 147 113 L 72 113 M 118 65 L 189 65 L 147 113 M 189 65 L 212 113 M 189 65 L 183 41 L 208 41 M 118 65 L 115 48','none','#8b7363',5)+line(101,47,129,47,INK,5)
        if vid=='coat_rack':return path('M 140 15 L 140 139 M 111 141 L 166 141 M 140 55 L 102 34 M 140 43 L 178 25 M 140 76 L 177 57','none','#9c8063',6)
        if vid=='plant_pot':
            art=path('M 105 101 L 175 101 L 165 145 L 115 145 Z','#b79680',INK,2)
            for dx,dy in [(-27,-22),(25,-38),(-12,-61),(12,-77)]:art+=line(140,105,140+dx,105+dy,'#66875b',3)+ellipse(140+dx,105+dy,12,21,'#809a72',transform=f'rotate({-dx} {140+dx} {105+dy})')
            return art
        if vid=='side_table':return ellipse(140,62,86,19,'#bca789',stroke=INK)+line(72,73,59,147,INK,5)+line(207,73,220,147,INK,5)+line(140,78,140,147,INK,5)
    raise ValueError(f'Unsupported prop {aid}:{vid}')


def draw_vegetation(vid):
    art=rect(0,125,280,35,'#c5cfb6')
    if vid=='no_vegetation':return art+rect(25,10,230,116,'#e0e6e8')
    if vid in ('conifer_trees','deciduous_trees'):return art+tree(86,15,'pines' if vid=='conifer_trees' else 'tree',1.5)+tree(205,51,'pines' if vid=='conifer_trees' else 'tree',.9)
    if vid=='tall_grasses':
        for x in range(62,224,13):art+=path(f'M {x} 143 Q {x-13} 66 {x+8} 20 M {x} 143 Q {x+22} 84 {x+21} 49','none','#6d8b5d',3)
    if vid=='fine_ferns':
        for x in [89,140,191]:
            art+=line(140,144,x,30,'#547a5a',3)
            for j in range(1,8):
                xx=140+(x-140)*j/8;yy=144-114*j/8
                art+=line(xx,yy,xx-18,yy-14,'#729568',3)+line(xx,yy,xx+18,yy-14,'#729568',3)
    if vid in ('broad_leaves','flowering_shrubs'):
        for j in range(9):
            x=73+(j*31)%141;y=41+(j*17)%80
            art+=line(140,143,x,y,'#547a5a',2)+ellipse(x,y,15,23,'#829e70',transform=f'rotate({j*21} {x} {y})')
            if vid=='flowering_shrubs':art+=circle(x+8,y,6,'#d4a9b6')+circle(x+8,y,2,'#d7bd6e')
    if vid=='climbing_vines':
        art+=rect(75,0,7,149,'#a79980')+rect(193,0,7,149,'#a79980')
        for x in [80,196]:
            art+=path(f'M {x} 148 Q {x-24} 92 {x+5} 65 Q {x+19} 36 {x-7} 0','none','#5d8358',3)
            for j in range(7):art+=ellipse(x+(-12 if j%2 else 8),j*21+6,8,13,'#80996e',transform=f'rotate({-30 if j%2 else 30} {x} {j*21+6})')
    return art


def draw_style(aid,vid,index):
    # Palette examples show pigment relationships directly.
    if aid=='palette':
        colors={
          'analogous':['#647ba2','#708fa6','#7baca7','#91b4a1'],
          'complementary':['#607b9d','#c6996a','#607b9d','#dfbb89'],
          'triadic':['#647c9f','#b78286','#acb274','#647c9f'],
          'monochromatic':['#344d6d','#647e9d','#91a9bd','#c1cfd8'],
          'neutral_accent':['#d2c7b6','#a9a7a0','#cb755b','#7c7f80'],
          'warm_dominant':['#b8775d','#c9946c','#d9b68b','#aa835f'],
          'cool_dominant':['#5c789a','#699ba5','#8799bc','#a9c5d0'],
          'balanced_warm_cool':['#b8876c','#668da4','#cba983','#8caab9'],
        }[vid]
        return ''.join(rect(23+i*59,23,56,116,c,rx=4) for i,c in enumerate(colors))
    if aid=='ethnic_inspiration':
        if vid=='slavic_inspired':
            art=rect(39,15,202,127,'#e2d5bd',rx=5)
            for x in range(58,241,25):
                for y in range(32,140,25):art+=poly([(x,y-8),(x+8,y),(x,y+8),(x-8,y)],'#ad7775')
            return art+rect(104,48,72,74,'#647b8b',rx=3)
        if vid=='scandinavian_inspired':return rect(39,15,202,127,'#e6e2d7',rx=5)+rect(57,30,72,98,'#bac4c4')+rect(144,30,79,37,'#7c9292')+rect(144,79,79,49,'#bda787')
        return rect(39,15,202,127,'#ddd7c8',rx=5)+rect(54,35,91,83,'#a8b8bd')+path('M 164 44 L 222 44 L 193 112 Z','#9b7c6b',INK,1)+line(61,24,214,135,'#eee6d4',6)
    if aid=='color_grade':
        colors=[('#dce6e9','#8fa4a5'),('#e3d2b5','#b2987a'),('#c1d7e5','#7f9ba9'),('#d2d9d4','#a0a69b'),('#aacfd0','#638f79'),('#e1d6df','#b4b7c9'),('#d7ccb7','#a19270'),('#d3d5d7','#81878e')]
        sky,ground=colors[index]
        art=rect(0,0,280,112,sky)+rect(0,112,280,48,ground)+adult(140,86,.9)
        if vid=='monochrome':art=rect(0,0,280,112,sky)+rect(0,112,280,48,ground)+tag('g',adult(140,86,.9),opacity='.6')+circle(140,47,9,'#b2b2b2')+path('M 127 61 L 153 61 L 157 101 L 123 101 Z','#838b94',INK,1)
        return art
    if aid=='contrast':
        stops={
          'low_contrast':[94,115,135,151,167,181,195,210],
          'soft_contrast':[70,96,123,148,173,198,219,237],
          'balanced_contrast':[35,67,100,132,164,196,224,248],
          'crisp_contrast':[15,43,75,119,163,204,237,254],
          'deep_shadows':[8,25,63,106,150,192,226,249],
          'lifted_shadows':[78,96,119,146,173,202,227,248],
          'soft_highlights':[29,58,92,129,163,187,207,225],
          'strong_midtones':[31,55,80,122,170,212,235,251],
        }[vid]
        art=''.join(rect(24+j*29,29,29,102,f'#{v:02x}{v:02x}{v:02x}') for j,v in enumerate(stops))
        points=[(30+j*31,148-v*.5) for j,v in enumerate(stops)]
        return art+path('M '+' L '.join(f'{x} {y}' for x,y in points),'none','#b48d55',3)
    if aid=='photo_genre':
        if vid=='fashion_editorial':return draw_scene('gray_studio')+adult(143,85,.95)+rect(100,47,86,63,'none',stroke='#b89562',stroke_width=2)
        if vid=='street_style':return draw_scene('urban_crosswalk')+adult(139,87,.9)
        if vid=='lifestyle':return draw_scene('cafe_interior')+adult(155,96,.75)
        if vid=='studio_portrait':return draw_scene('gray_studio')+tag('g',draw_face('expression','neutral',0),transform='translate(70 5) scale(.5)')
        if vid=='environmental_portrait':return draw_scene('city_park')+adult(159,109,.55)
        if vid=='lookbook':return draw_scene('white_cyclorama')+adult(140,87,.9)+line(105,143,174,143,'#b89562',2)
        if vid=='documentary':return draw_scene('bookshop')+adult(147,106,.6)+adult(110,106,.48)
        if vid=='campaign':return draw_scene('colonnade')+adult(140,85,1)
    if aid=='narrative':
        art=adult(140,89,.88)
        if vid=='arrival':art+=rect(206,26,42,119,'#b5c1c7')+path('M 178 108 L 219 108 l -9 -6 M 219 108 l -9 6','none','#b48d55',3)
        if vid=='pause':art+=rect(44,47,10,67,'#b48d55')+rect(65,47,10,67,'#b48d55')
        if vid=='conversation':art+=path('M 177 25 L 243 25 L 243 66 L 209 66 L 188 81 L 188 66 L 177 66 Z','#dae5eb',INK,2)
        if vid=='reflection':art+=rect(36,18,56,112,'#b9d6df',stroke='#99866e',stroke_width=4)+tag('g',adult(67,80,.43),opacity='.4')
        if vid=='exploration':art+=path('M 183 109 Q 219 90 229 48','none','#b48d55',3)+tree(229,19,'tree',.6)
        if vid=='departure':art+=rect(28,26,42,119,'#b5c1c7')+path('M 100 108 L 58 108 l 9 -6 M 58 108 l 9 6','none','#b48d55',3)
        if vid=='preparation':art+=rect(197,33,44,54,'#b9d6df',stroke='#99866e',stroke_width=3)+rect(202,104,44,7,'#a49177')
        if vid=='observation':art+=circle(215,61,21,'#c5b797')+line(160,54,191,60,'#b48d55',2,stroke_dasharray='3 3')
        return art
    if aid=='editorial_mood':
        mapping={'quiet_luxury':'apartment','sensual_luxe':'hotel_lobby','cinematic_romance':'rose_garden','modern_glamour':'museum_gallery'}
        return draw_scene(mapping[vid])+adult(140,93,.8)
    if aid=='face_direction':return draw_face(aid,vid,index)+({'luminous':ellipse(105,89,7,14,'#f0dbb1',opacity='.3')+ellipse(176,89,7,14,'#f0dbb1',opacity='.3'),'classic_beauty':path('M 92 96 Q 112 80 122 91 M 158 91 Q 171 80 188 96','none','#a57458',2),'confident':line(119,57,129,55,INK,2),'soft_sultry':line(103,72,121,74,INK,2)+line(159,74,177,72,INK,2)}.get(vid,''))
    raise ValueError(f'Unsupported style {aid}:{vid}')


FACE_ATTRS={'skin_tone','skin_undertone','skin_finish','freckles','micro_texture','complexion_detail','cheekbones','eye_color','eyelashes','facial_balance','face_shape','brow_shape','eye_shape','nose_shape','lip_shape','expression','gaze_direction','makeup_finish','lip_color','eye_makeup','blush_placement','age','head_tilt'}
CLOTHING_ATTRS={'dress_style','hem_length','high_slit','drape_effect','top_style','neckline','sleeve_length','sleeve_shape','trouser_cut','skirt_cut','waist_position','outerwear_style','outerwear_length','seam_detail','body_build','shoulder_shape','silhouette'}
OPTIC_ATTRS={'camera','focal_length','aperture','shutter_motion','grain','focus_target','white_balance','highlight_rolloff'}
COMPOSITION_ATTRS={'shot_size','camera_height','subject_placement','leading_lines','foreground','horizon_height'}
STYLE_ATTRS={'ethnic_inspiration','photo_genre','color_grade','contrast','palette','narrative','editorial_mood','face_direction'}
ACCESSORY_ATTRS={'jewelry_style','metal_finish','bag_style','belt_style','scarf_style'}
LIGHT_ATTRS={'light_direction','light_quality','lighting_pattern','fill_ratio','practical_light','light_temperature'}


def _artwork(attribute, value, index):
    aid,vid=attribute['id'],value['id']
    if aid=='pose':return draw_pose(vid)
    if aid=='scenery':return draw_scene(vid)
    if aid in FACE_ATTRS:return draw_face(aid,vid,index)
    if aid.startswith('hair_'):return draw_hair(aid,vid,index)
    if aid=='fabric_color':return swatch(aid,vid,index)
    if aid in ('fabric_material','garment_pattern','shoe_material','ground_surface','wall_surface'):return draw_textile(aid,vid,index)
    if aid in CLOTHING_ATTRS:return draw_clothing(aid,vid,index)
    if aid=='shoe_style':return draw_shoe(vid,index)
    if aid in ACCESSORY_ATTRS:return draw_accessory(aid,vid,index)
    if aid in OPTIC_ATTRS:return draw_optics(aid,vid,index)
    if aid in LIGHT_ATTRS:return draw_light(aid,vid,index)
    if aid in COMPOSITION_ATTRS:return draw_composition(aid,vid,index)
    if aid in ('weather','time_of_day','wind','season'):return draw_weather(aid,vid,index)
    if aid in ('hand_prop','seating_prop','background_prop','eyewear'):return draw_prop(aid,vid,index)
    if aid=='vegetation':return draw_vegetation(vid)
    if aid in STYLE_ATTRS:return draw_style(aid,vid,index)
    if aid=='body_orientation':
        angle={'front':0,'quarter_left':-18,'quarter_right':18,'profile_left':-45,'profile_right':45,'back':180,'back_three_quarter_left':-135,'back_three_quarter_right':135}[vid]
        rad=math.radians(angle)
        art=ellipse(140,87,48 if abs(angle) not in (45,) else 25,32,BLUE,stroke=INK,stroke_width=2)
        art+=circle(140,87,20,SKIN)+line(140,87,140+60*math.sin(rad),87-60*math.cos(rad),'#b58c4e',4)
        art+=circle(140+60*math.sin(rad),87-60*math.cos(rad),5,'#b58c4e')
        art+=words('Overhead torso direction',140,150,10)
        return art
    raise ValueError(f'No visual renderer for {aid}:{vid}')


def artwork(attribute, value, index):
    if attribute['type'] != 'boolean':
        return _artwork(attribute, value, index)
    # Both states are visible as a before/after pair. The selected state is
    # outlined, so enabled and disabled assets convey a real visual choice.
    art = ''
    for j, state in enumerate(attribute['values']):
        selected = state['id'] == value['id']
        x = 6 + j * 139
        art += rect(x, 10, 129, 132, '#eef2f6', rx=5,
                    stroke='#b48d55' if selected else '#b9c6cd',
                    stroke_width=3 if selected else 1)
        art += tag('svg', _artwork(attribute, state, j), x=x+3, y=18,
                   width=123, height=110, viewBox='0 0 280 160',
                   preserveAspectRatio='xMidYMid meet')
        art += words('ON' if state['id']=='on' else 'OFF', x+64, 155, 11)
    return art


def svg_document(name, description, art):
    # All text is escaped. No HTML, fonts, CSS imports, images or references.
    display=name if len(name)<=35 else name[:32]+'…'
    body=tag('title',esc(name+' — illustrative steering guide'))
    body+=tag('desc',esc(description+' Illustrative steering guide, not an actual AI example.'))
    body+=rect(0,0,320,242,'#f7f9fb',rx=12)
    body+=words(display,160,25,13,font_weight='600')
    body+=tag('svg',art,x=20,y=40,width=280,height=160,viewBox='0 0 280 160',overflow='hidden',data_art='steering')
    body+=words('Illustrative steering guide',160,219,10,'#596b7c')
    body+=words('Not an actual AI example',160,234,9,'#738393')
    return '<?xml version="1.0" encoding="UTF-8"?>\n'+tag('svg',body,xmlns='http://www.w3.org/2000/svg',width=320,height=242,viewBox='0 0 320 242',role='img')+'\n'


def build(library, output):
    """Render deterministic thumbnails; return the number of written SVGs."""
    written=0
    for category in library['categories']:
        for attribute in category['attributes']:
            dest=output/attribute['id'];dest.mkdir(parents=True,exist_ok=True)
            guides=[]
            for index,value in enumerate(attribute['values']):
                art=artwork(attribute,value,index)
                (dest/(value['id']+'.svg')).write_text(svg_document(value['name'],value['description'],art),encoding='utf-8')
                guides.append(art)
                written+=1
            picks=sorted({0,len(guides)//2,len(guides)-1})
            montage=''
            for j,k in enumerate(picks):
                montage+=tag('svg',guides[k],x=5+j*91,y=22,width=86,height=105,viewBox='0 0 280 160',preserveAspectRatio='xMidYMid meet')
                montage+=words(attribute['values'][k]['name'][:15],47+j*91,143,8)
            (dest/'_attribute.svg').write_text(svg_document(attribute['name'],attribute['description'],montage),encoding='utf-8')
            written+=1
    return written


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library',type=Path,default=ROOT/'library.json')
    parser.add_argument('--output',type=Path,default=ROOT/'thumbnails')
    args=parser.parse_args()
    library=json.loads(args.library.read_text(encoding='utf-8'))
    count=build(library,args.output)
    print(f'Built {count} safe SVG steering guides in {args.output}')


if __name__=='__main__':
    main()
