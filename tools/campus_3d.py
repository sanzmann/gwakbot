"""Blender 에서 실행해 캠퍼스 3D 조감도를 만드는 스크립트.

static/campus_vector.json (OSM 에서 받아둔 건물 윤곽·층수·길·녹지) 을 읽어
건물을 층수만큼 세우고, 조명을 달아 이미지로 렌더링한다.

Blender 의 Scripting 탭에서 이 파일을 열고 실행하거나, MCP 로 연결해 실행한다.
결과: static/img/campus_3d.png
"""
import json
import math
import pathlib

import bmesh
import bpy

ROOT = pathlib.Path(r"C:\Users\USER\Desktop\곽봇")
DATA = ROOT / "static" / "campus_vector.json"
OUT = ROOT / "static" / "img" / "campus_3d.png"

# campus_vector.json 의 좌표 단위는 '지도 px'. 가로 1000px ≈ 837m 이므로 1px ≈ 0.84m
M_PER_PX = 0.84
LEVEL_H = 3.3 / M_PER_PX          # 한 층 높이(px 단위)
DEFAULT_LEVELS = {"academic": 5, "dorm": 8, "library": 4, "student": 3,
                  "sports": 2, "admin": 5, "service": 2, "other": 4}

# (지붕색, 벽색) — 학교 일러스트처럼 알록달록하게
PALETTE = {
    "academic": ((0.94, 0.78, 0.55), (0.88, 0.70, 0.46)),
    "dorm":     ((0.93, 0.68, 0.68), (0.85, 0.58, 0.58)),
    "library":  ((0.68, 0.79, 0.94), (0.58, 0.70, 0.88)),
    "student":  ((0.78, 0.89, 0.65), (0.68, 0.80, 0.55)),
    "sports":   ((0.96, 0.84, 0.58), (0.88, 0.74, 0.48)),
    "admin":    ((0.80, 0.72, 0.92), (0.70, 0.62, 0.85)),
    "service":  ((0.95, 0.86, 0.52), (0.87, 0.77, 0.43)),
    "other":    ((0.80, 0.82, 0.85), (0.72, 0.74, 0.78)),
}
AREA_COLORS = {
    "green":   (0.72, 0.86, 0.60),
    "pitch":   (0.88, 0.60, 0.40),
    "water":   (0.55, 0.78, 0.92),
    "parking": (0.82, 0.81, 0.77),
}
GROUND_COLOR = (0.84, 0.91, 0.78)
ROAD_COLOR = (0.97, 0.96, 0.92)
FOOT_COLOR = (0.92, 0.88, 0.79)


def category(name: str, has_num: bool) -> str:
    """건물 이름으로 쓰임새를 짐작 (화면 지도와 같은 기준)."""
    if not has_num and not any(k in name for k in ("학사", "관", "센터", "도서관")):
        return "other"
    for keys, cat in (("학사 생활관 기숙", "dorm"), ("도서관 전산", "library"),
                      ("학생회관 식당 생협", "student"), ("체육 운동 수영", "sports"),
                      ("본부 행정 테크노파크 창업 연구", "admin"),
                      ("카페 어린이집 우체국 파워플랜트 동력 주차", "service")):
        if any(k in name for k in keys.split()):
            return cat
    return "academic" if has_num else "other"


def material(name: str, color, roughness=0.75):
    mat = bpy.data.materials.get(name)
    if mat is None:
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        bsdf = next(n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        bsdf.inputs["Roughness"].default_value = roughness
    return mat


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.curves):
        for item in list(block):
            if item.users == 0:
                block.remove(item)


def flat_polygon(name, pts, z, color, mat_name):
    """바닥에 깔리는 평면 도형 (녹지·운동장·물·주차장)."""
    mesh = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bm = bmesh.new()
    verts = [bm.verts.new((x, -y, z)) for x, y in pts]   # y 뒤집기: 화면 좌표 → 3D
    try:
        bm.faces.new(verts)
    except ValueError:
        pass                                             # 자기 교차 등은 건너뜀
    bm.to_mesh(mesh)
    bm.free()
    obj.data.materials.append(material(mat_name, color))
    return obj


def ribbon(name, pts, width, z, color, mat_name):
    """길: 선분마다 폭을 가진 납작한 사각형을 깔아 만든다."""
    mesh = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bm = bmesh.new()
    half = width / 2
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        dx, dy = x2 - x1, -(y2 - y1)
        length = math.hypot(dx, dy)
        if length < 0.01:
            continue
        ox, oy = -dy / length * half, dx / length * half
        quad = [(x1 + ox, -y1 + oy, z), (x2 + ox, -y2 + oy, z),
                (x2 - ox, -y2 - oy, z), (x1 - ox, -y1 - oy, z)]
        bm.faces.new([bm.verts.new(p) for p in quad])
    bm.to_mesh(mesh)
    bm.free()
    obj.data.materials.append(material(mat_name, color))
    return obj


def building(name, pts, height, cat):
    roof_color, wall_color = PALETTE[cat]
    mesh = bpy.data.meshes.new(name)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)

    bm = bmesh.new()
    verts = [bm.verts.new((x, -y, 0.0)) for x, y in pts]
    try:
        face = bm.faces.new(verts)
    except ValueError:
        bm.free()
        bpy.data.objects.remove(obj)
        return None
    # 바닥면을 위로 밀어 올려 벽을 만든다
    result = bmesh.ops.extrude_face_region(bm, geom=[face])
    moved = [v for v in result["geom"] if isinstance(v, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, 0, height), verts=moved)
    bm.to_mesh(mesh)
    bm.free()

    obj.data.materials.append(material(f"wall_{cat}", wall_color, 0.8))
    obj.data.materials.append(material(f"roof_{cat}", roof_color, 0.65))
    # 가장 윗면만 지붕 재질로
    mesh.polygons.foreach_set("material_index", [0] * len(mesh.polygons))
    top = max(mesh.polygons, key=lambda p: p.center.z)
    top.material_index = 1
    mesh.update()
    return obj


def setup_camera_and_light(focus, sun_angle=35):
    x, y, w, h = focus
    cx, cy = x + w / 2, -(y + h / 2)

    cam_data = bpy.data.cameras.new("Camera")
    cam_data.type = "ORTHO"
    cam_data.ortho_scale = max(w, h) * 1.05
    cam = bpy.data.objects.new("Camera", cam_data)
    bpy.context.collection.objects.link(cam)
    # 위-옆에서 내려다보는 각도 (0° 면 정수직, 커질수록 옆에서 봄)
    tilt = math.radians(90 - 52)
    dist = max(w, h) * 1.5
    cam.location = (cx, cy - dist * math.sin(tilt), dist * math.cos(tilt))
    cam.rotation_euler = (tilt, 0, 0)
    bpy.context.scene.camera = cam

    sun_data = bpy.data.lights.new("Sun", type="SUN")
    sun_data.energy = 4.0
    sun_data.angle = math.radians(2)
    sun = bpy.data.objects.new("Sun", sun_data)
    bpy.context.collection.objects.link(sun)
    sun.location = (cx - w * 0.4, cy - h * 0.4, max(w, h))
    sun.rotation_euler = (math.radians(sun_angle), math.radians(12), math.radians(35))

    world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.78, 0.88, 0.96, 1.0)
    bg.inputs[1].default_value = 0.6


def main():
    data = json.loads(DATA.read_text(encoding="utf-8"))
    focus = data.get("focus") or [0, 0, data["width"], data["height"]]
    clear_scene()

    # 바닥
    x, y, w, h = focus
    pad = 60
    flat_polygon("Ground", [(x - pad, y - pad), (x + w + pad, y - pad),
                            (x + w + pad, y + h + pad), (x - pad, y + h + pad)],
                 -0.4, GROUND_COLOR, "ground")

    for i, area in enumerate(data["areas"]):
        color = AREA_COLORS.get(area["kind"])
        if color and len(area["pts"]) >= 3:
            flat_polygon(f"area_{i}", area["pts"], -0.2 + 0.02 * (area["kind"] == "water"),
                         color, f"area_{area['kind']}")

    for i, path in enumerate(data["paths"]):
        if len(path["pts"]) < 2:
            continue
        is_road = path["kind"] == "road"
        ribbon(f"path_{i}", path["pts"], 7 if is_road else 2.6, 0.0,
               ROAD_COLOR if is_road else FOOT_COLOR, "road" if is_road else "foot")

    made = 0
    for b in data["buildings"]:
        if len(b["pts"]) < 4:
            continue
        cat = category(b.get("name", ""), bool(b.get("num")))
        levels = b.get("levels") or DEFAULT_LEVELS[cat]
        if building(b.get("name") or f"bld_{made}", b["pts"][:-1], levels * LEVEL_H, cat):
            made += 1

    setup_camera_and_light(focus)

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in [
        i.identifier for i in type(scene.render).bl_rna.properties["engine"].enum_items
    ] else "BLENDER_EEVEE"
    scene.render.resolution_x = 2400
    scene.render.resolution_y = 1700
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(OUT)
    print(f"건물 {made}개 생성 완료. 렌더링 시작 → {OUT}")
    bpy.ops.render.render(write_still=True)
    print("렌더링 완료")


main()
