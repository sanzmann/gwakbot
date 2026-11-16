// 곽봇 홈 3D 무대.
//
// 가운데에 곽봇이 둥실 떠 있고, 그 둘레를 밥공기·확성기·달력 같은 물건들이 떠다닌다.
// 곽봇을 누르면 대화로, 물건을 누르면 그 정보 창으로 간다.
// 모델 파일 없이 전부 여기서 도형을 조립해 만든다 (내려받을 게 없어 가볍다).
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';

const TAU = Math.PI * 2;
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const lerp = (a, b, t) => a + (b - a) * t;
const easeOutBack = t => 1 + 2.4 * Math.pow(t - 1, 3) + 1.4 * Math.pow(t - 1, 2);

// 장난감 플라스틱 같은 매끈한 재질
const plastic = (color, opts = {}) => new THREE.MeshPhysicalMaterial({
  color, roughness: 0.36, metalness: 0, clearcoat: 0.75, clearcoatRoughness: 0.22, ...opts });
const glow = color => new THREE.MeshBasicMaterial({ color, toneMapped: false });

function canvasTex(w, h, draw) {
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  draw(c.getContext('2d'), w, h);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  return t;
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

const mesh = (geo, mat, x = 0, y = 0, z = 0) => {
  const m = new THREE.Mesh(geo, mat);
  m.position.set(x, y, z);
  return m;
};

// ───────────────────────── 곽봇 ─────────────────────────

// 얼굴 화면: 웃는 눈·입·볼. glowOnly 면 빛나는 부분만 (발광 지도용)
function drawFace(ctx, w, h, glowOnly) {
  ctx.clearRect(0, 0, w, h);
  if (glowOnly) {
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, w, h);
  } else {
    roundRect(ctx, 6, 6, w - 12, h - 12, 150);        // 화면 테두리
    ctx.fillStyle = '#b3bac6';
    ctx.fill();
    roundRect(ctx, 30, 30, w - 60, h - 60, 128);      // 어두운 화면
    ctx.fillStyle = '#121829';
    ctx.fill();
  }
  ctx.lineCap = 'round';
  ctx.shadowColor = '#38b6ff';
  ctx.shadowBlur = glowOnly ? 34 : 18;
  ctx.strokeStyle = '#8adcff';
  ctx.lineWidth = 30;
  for (const cx of [w * 0.335, w * 0.665]) {            // 웃는 눈 ∩ ∩
    ctx.beginPath();
    ctx.arc(cx, h * 0.52, 62, Math.PI * 1.12, Math.PI * 1.88);
    ctx.stroke();
  }
  ctx.lineWidth = 24;                                    // 입
  ctx.beginPath();
  ctx.arc(w * 0.5, h * 0.5, 78, Math.PI * 0.22, Math.PI * 0.78);
  ctx.stroke();
  ctx.shadowColor = '#ff6a4d';                           // 볼
  ctx.strokeStyle = '#ff8f73';
  ctx.lineWidth = 17;
  for (const [cx, dir] of [[w * 0.2, 1], [w * 0.8, 1]]) {
    for (const dx of [-17, 17]) {
      ctx.beginPath();
      ctx.moveTo(cx + dx - 9 * dir, h * 0.75);
      ctx.lineTo(cx + dx + 9 * dir, h * 0.64);
      ctx.stroke();
    }
  }
}

// 가슴의 T 엠블럼
function drawEmblem(ctx, w, h) {
  ctx.clearRect(0, 0, w, h);
  ctx.shadowColor = '#2f9bff';
  ctx.shadowBlur = 16;
  ctx.strokeStyle = '#4db4ff';
  ctx.lineCap = 'round';
  ctx.lineWidth = 17;
  ctx.beginPath();
  ctx.arc(w / 2, h / 2, w * 0.33, 0, TAU);
  ctx.stroke();
  ctx.lineWidth = 21;
  ctx.beginPath();
  ctx.moveTo(w * 0.34, h * 0.4); ctx.lineTo(w * 0.66, h * 0.4);
  ctx.moveTo(w * 0.5, h * 0.4); ctx.lineTo(w * 0.5, h * 0.68);
  ctx.stroke();
}

function buildBot() {
  const root = new THREE.Group();
  const bot = new THREE.Group();
  bot.position.y = -0.35;                 // 눈으로 보는 중심이 원점에 오도록
  root.add(bot);

  const white = plastic(0xf2f4f8);
  const gray = plastic(0x7c8493, { roughness: 0.42 });
  const dark = plastic(0x2a2f3e, { roughness: 0.5, clearcoat: 0.35 });
  const blue = glow(0x58c6ff);

  // 몸통
  const body = mesh(new THREE.SphereGeometry(0.62, 48, 32), white, 0, -0.5, 0);
  body.scale.set(1, 1.1, 0.92);
  bot.add(body);
  const emblem = mesh(
    new THREE.SphereGeometry(0.628, 32, 16, Math.PI / 2 - 0.42, 0.84, Math.PI / 2 - 0.55, 0.84),
    new THREE.MeshBasicMaterial({ map: canvasTex(256, 256, drawEmblem), transparent: true,
                                  toneMapped: false, depthWrite: false }),
    0, -0.5, 0);
  emblem.scale.copy(body.scale);
  bot.add(emblem);

  const hip = mesh(new THREE.SphereGeometry(0.44, 32, 20), dark, 0, -1.0, 0);
  hip.scale.set(1, 0.5, 0.86);
  bot.add(hip);
  bot.add(mesh(new THREE.CylinderGeometry(0.3, 0.34, 0.22, 32), dark, 0, 0.1, 0));   // 목

  // 머리 (마우스를 따라 살짝 돈다)
  const head = new THREE.Group();
  head.position.y = 0.92;
  bot.add(head);
  const helmet = mesh(new THREE.SphereGeometry(0.95, 64, 48), gray);
  helmet.scale.set(1.1, 0.93, 1.0);
  head.add(helmet);

  const faceMat = new THREE.MeshPhysicalMaterial({
    map: canvasTex(1024, 448, (c, w, h) => drawFace(c, w, h, false)),
    emissiveMap: canvasTex(1024, 448, (c, w, h) => drawFace(c, w, h, true)),
    emissive: 0xffffff, emissiveIntensity: 1.5, alphaTest: 0.5,
    roughness: 0.18, clearcoat: 1, clearcoatRoughness: 0.08 });
  const face = mesh(new THREE.SphereGeometry(0.96, 64, 32, Math.PI / 2 - 0.98, 1.96,
                                             Math.PI / 2 - 0.5, 1.0), faceMat);
  face.scale.copy(helmet.scale);
  head.add(face);

  for (const sx of [-1, 1]) {
    // 옆으로 뻗은 귀
    const fin = mesh(new THREE.ConeGeometry(0.2, 0.58, 28), gray, sx * 0.99, 0.42, -0.06);
    fin.rotation.z = -sx * 1.05;
    head.add(fin);
    // 헤드폰
    const can = mesh(new THREE.CylinderGeometry(0.27, 0.27, 0.18, 36), dark, sx * 1.02, -0.1, 0.04);
    can.rotation.z = Math.PI / 2;
    head.add(can);
    const ring = mesh(new THREE.TorusGeometry(0.17, 0.034, 12, 36), blue, sx * 1.115, -0.1, 0.04);
    ring.rotation.y = Math.PI / 2;
    head.add(ring);
    const cap = mesh(new THREE.CylinderGeometry(0.1, 0.1, 0.04, 24), gray, sx * 1.12, -0.1, 0.04);
    cap.rotation.z = Math.PI / 2;
    head.add(cap);
  }

  // 뿔 (테크뇽의 빨강·파랑 뿔)
  const horn = (sx, color) => {
    const g = new THREE.Group();
    const mat = plastic(color, { roughness: 0.22, clearcoat: 1 });
    g.add(mesh(new THREE.CylinderGeometry(0.15, 0.18, 0.18, 24), dark, 0, 0.06, 0));
    g.add(mesh(new THREE.CapsuleGeometry(0.15, 0.36, 8, 24), mat, 0, 0.44, 0));
    const nub = mesh(new THREE.SphereGeometry(0.14, 24, 16), mat, sx * 0.17, 0.5, 0);
    nub.scale.set(1.2, 0.95, 1);
    g.add(nub);
    g.position.set(sx * 0.42, 0.76, 0);
    g.rotation.z = -sx * 0.3;
    return g;
  };
  head.add(horn(-1, 0xe9505c), horn(1, 0x2f6fe8));

  // 팔: 어깨를 축으로 돈다. 오른팔(화면 오른쪽)은 들어서 흔든다
  const arm = (sx, raised) => {
    const g = new THREE.Group();
    g.position.set(sx * 0.58, -0.2, 0);
    g.add(mesh(new THREE.SphereGeometry(0.16, 24, 16), dark));
    g.add(mesh(new THREE.CapsuleGeometry(0.13, 0.3, 8, 20), white, 0, -0.3, 0));
    const hand = mesh(new THREE.SphereGeometry(raised ? 0.2 : 0.17, 28, 20), white, 0, -0.6, 0);
    g.add(hand);
    const mark = mesh(new THREE.TorusGeometry(0.085, 0.024, 10, 28), blue, 0, -0.6, raised ? 0.185 : 0.155);
    g.add(mark);
    if (raised) g.add(mesh(new THREE.SphereGeometry(0.035, 12, 8), blue, 0, -0.6, 0.195));
    return g;
  };
  const armL = arm(-1, false);
  armL.rotation.z = -0.42;
  const armR = arm(1, true);
  bot.add(armL, armR);

  // 다리와 발
  for (const sx of [-1, 1]) {
    bot.add(mesh(new THREE.CapsuleGeometry(0.17, 0.2, 8, 20), white, sx * 0.26, -1.2, 0));
    const foot = mesh(new THREE.SphereGeometry(0.23, 28, 20), white, sx * 0.26, -1.47, 0.07);
    foot.scale.set(1, 0.62, 1.3);
    bot.add(foot);
    const strip = mesh(new THREE.CapsuleGeometry(0.022, 0.15, 4, 10), blue, sx * 0.26, -1.5, 0.352);
    strip.rotation.z = Math.PI / 2;
    bot.add(strip);
  }

  // 꼬리
  const tailCurve = new THREE.CatmullRomCurve3([
    new THREE.Vector3(0.2, -0.95, -0.38), new THREE.Vector3(0.72, -1.18, -0.5),
    new THREE.Vector3(1.14, -0.98, -0.4), new THREE.Vector3(1.2, -0.58, -0.28)]);
  const tail = new THREE.Group();
  tail.add(mesh(new THREE.TubeGeometry(tailCurve, 32, 0.065, 12), gray));
  tail.add(mesh(new THREE.SphereGeometry(0.2, 28, 20), white, 1.19, -0.42, -0.24));
  bot.add(tail);

  return { root, head, armR, armL, tail, faceMat };
}

// ───────────────────────── 떠다니는 물건들 ─────────────────────────

const BOWL_PROFILE = [[0, -0.4], [0.22, -0.4], [0.24, -0.34], [0.2, -0.3], [0.34, -0.2], [0.47, -0.02],
  [0.52, 0.14], [0.48, 0.15], [0.43, 0], [0.3, -0.16], [0, -0.2]].map(([x, y]) => new THREE.Vector2(x, y));

// 🍚 밥공기
function riceBowl() {
  const g = new THREE.Group();
  g.add(mesh(new THREE.LatheGeometry(BOWL_PROFILE, 56),
             plastic(0xe9505c, { side: THREE.DoubleSide, roughness: 0.28 })));
  const rim = mesh(new THREE.TorusGeometry(0.5, 0.022, 10, 56), plastic(0xffffff), 0, 0.145, 0);
  rim.rotation.x = Math.PI / 2;
  g.add(rim);

  const riceMat = new THREE.MeshStandardMaterial({ color: 0xfffdf6, roughness: 0.9 });
  const dome = mesh(new THREE.SphereGeometry(0.46, 40, 20, 0, TAU, 0, Math.PI / 2), riceMat, 0, 0.1, 0);
  dome.scale.y = 0.8;
  g.add(dome);
  // 밥알을 표면에 흩뿌려 고슬고슬한 느낌을 낸다
  const grains = new THREE.InstancedMesh(new THREE.CapsuleGeometry(0.03, 0.055, 4, 8), riceMat, 150);
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), e = new THREE.Euler();
  for (let i = 0; i < 150; i++) {
    const th = Math.acos(1 - Math.random() * 0.82), ph = Math.random() * TAU;
    e.set(Math.random() * 3, Math.random() * 3, Math.random() * 3);
    m.compose(new THREE.Vector3(Math.sin(th) * Math.cos(ph) * 0.46,
                                0.1 + Math.cos(th) * 0.46 * 0.8,
                                Math.sin(th) * Math.sin(ph) * 0.46),
              q.setFromEuler(e), new THREE.Vector3(1, 1, 1));
    grains.setMatrixAt(i, m);
  }
  g.add(grains);
  g.rotation.x = 0.38;
  return g;
}

// 📢 확성기
function megaphone() {
  const g = new THREE.Group();
  const red = plastic(0xff5568, { side: THREE.DoubleSide, roughness: 0.3 });
  const whiteM = plastic(0xffffff);
  const horn = mesh(new THREE.CylinderGeometry(0.44, 0.13, 0.72, 56, 1, true), red);
  horn.rotation.z = -Math.PI / 2;
  g.add(horn);
  const rim = mesh(new THREE.TorusGeometry(0.44, 0.04, 12, 56), whiteM, 0.36, 0, 0);
  rim.rotation.y = Math.PI / 2;
  g.add(rim);
  const back = mesh(new THREE.CylinderGeometry(0.145, 0.145, 0.26, 36), whiteM, -0.48, 0, 0);
  back.rotation.z = Math.PI / 2;
  g.add(back);
  const cap = mesh(new THREE.SphereGeometry(0.145, 28, 18), plastic(0xc9cfdb), -0.61, 0, 0);
  cap.scale.x = 0.5;
  g.add(cap);
  const handle = mesh(new THREE.CapsuleGeometry(0.055, 0.26, 6, 16), plastic(0x2c3350), -0.44, -0.3, 0);
  handle.rotation.z = 0.18;
  g.add(handle);
  // 소리 물결
  const wave = glow(0xffcf4a);
  for (const r of [0.5, 0.66]) {
    const arc = mesh(new THREE.TorusGeometry(r, 0.024, 8, 28, 1.1), wave, 0.3, 0, 0);
    arc.rotation.z = -0.55;
    g.add(arc);
  }
  g.rotation.set(0.1, -0.5, 0.32);
  return g;
}

// 📅 달력
function calendar() {
  const g = new THREE.Group();
  g.add(mesh(new RoundedBoxGeometry(0.92, 0.92, 0.16, 5, 0.07), plastic(0xfafbff)));
  g.add(mesh(new RoundedBoxGeometry(0.925, 0.27, 0.175, 5, 0.07), plastic(0x3d8bff, { roughness: 0.28 }), 0, 0.325, 0));
  const steel = new THREE.MeshPhysicalMaterial({ color: 0xdfe3ea, metalness: 0.9, roughness: 0.22 });
  for (const x of [-0.24, 0.24]) {
    const ring = mesh(new THREE.TorusGeometry(0.075, 0.022, 10, 28), steel, x, 0.47, 0);
    ring.rotation.y = Math.PI / 2;
    g.add(ring);
  }
  const cell = new RoundedBoxGeometry(0.135, 0.125, 0.03, 3, 0.03);
  const pale = plastic(0xd9d6f3), today = plastic(0xff5568, { roughness: 0.25 });
  for (let r = 0; r < 3; r++) {
    for (let c = 0; c < 4; c++) {
      g.add(mesh(cell, r === 1 && c === 2 ? today : pale, -0.3 + c * 0.2, 0.06 - r * 0.18, 0.085));
    }
  }
  g.rotation.set(-0.08, -0.42, 0.04);
  return g;
}

// 🔗 사슬 고리
function chainLink() {
  const g = new THREE.Group();
  const L = 0.2, R = 0.17, pts = [];
  for (let i = 0; i <= 10; i++) {
    const a = -Math.PI / 2 + (i / 10) * Math.PI;
    pts.push(new THREE.Vector3(L + R * Math.cos(a), R * Math.sin(a), 0));
  }
  for (let i = 0; i <= 10; i++) {
    const a = Math.PI / 2 + (i / 10) * Math.PI;
    pts.push(new THREE.Vector3(-L + R * Math.cos(a), R * Math.sin(a), 0));
  }
  const geo = new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts, true), 96, 0.072, 16, true);
  const metal = new THREE.MeshPhysicalMaterial({ color: 0xcfc8ee, metalness: 0.92, roughness: 0.2,
                                                 clearcoat: 0.6 });
  const d = 0.16;
  const a = new THREE.Group();
  a.add(mesh(geo, metal));
  a.rotation.z = Math.PI / 4;
  a.position.set(-d, -d, 0);
  const b = new THREE.Group();
  const inner = mesh(geo, metal);
  inner.rotation.x = Math.PI / 2;          // 옆 고리와 엇갈려 끼워지도록 긴 축으로 90° 돌린다
  b.add(inner);
  b.rotation.z = Math.PI / 4;
  b.position.set(d, d, 0);
  g.add(a, b);
  g.rotation.set(0.25, 0.4, 0);
  return g;
}

// 🗺️ 접힌 지도 + 핀
function foldedMap() {
  const g = new THREE.Group();
  const tex = canvasTex(384, 320, (c, w, h) => {
    c.fillStyle = '#9bdc98'; c.fillRect(0, 0, w, h);
    c.fillStyle = '#b9e8a8';
    for (const [x, y, r] of [[70, 60, 60], [300, 250, 70], [210, 90, 46]]) {
      c.beginPath(); c.arc(x, y, r, 0, TAU); c.fill();
    }
    c.fillStyle = '#6cbcf2';                               // 물
    c.beginPath(); c.moveTo(0, 215); c.bezierCurveTo(90, 180, 120, 290, 210, 320);
    c.lineTo(0, 320); c.closePath(); c.fill();
    c.strokeStyle = '#fffdf2'; c.lineWidth = 15; c.lineCap = 'round';   // 길
    c.beginPath(); c.moveTo(-10, 120); c.bezierCurveTo(120, 90, 230, 200, 400, 150); c.stroke();
    c.beginPath(); c.moveTo(250, -10); c.bezierCurveTo(220, 110, 300, 200, 270, 330); c.stroke();
    c.strokeStyle = '#ff6b5e'; c.lineWidth = 6; c.setLineDash([13, 11]);  // 가는 길 점선
    c.beginPath(); c.moveTo(50, 270); c.bezierCurveTo(120, 170, 190, 190, 262, 108); c.stroke();
  });
  const w = 0.31, a = 0.46, paper = plastic(0xf6f1e2, { roughness: 0.7, clearcoat: 0.1 });
  for (let i = 0; i < 3; i++) {
    const t = tex.clone();
    t.repeat.set(1 / 3, 1);
    t.offset.set(i / 3, 0);
    t.needsUpdate = true;
    const front = new THREE.MeshPhysicalMaterial({ map: t, roughness: 0.55, clearcoat: 0.25 });
    const panel = mesh(new THREE.BoxGeometry(w, 0.82, 0.03), [paper, paper, paper, paper, front, paper],
                       (i - 1) * w * Math.cos(a), 0, 0);
    panel.rotation.y = (i % 2 ? 1 : -1) * a;
    g.add(panel);
  }
  // 위치 핀
  const pin = new THREE.Group();
  const red = plastic(0xff4d5e, { roughness: 0.2, clearcoat: 1 });
  pin.add(mesh(new THREE.SphereGeometry(0.13, 28, 20), red, 0, 0.3, 0));
  const tip = mesh(new THREE.ConeGeometry(0.1, 0.26, 24), red, 0, 0.13, 0);
  tip.rotation.x = Math.PI;
  pin.add(tip);
  pin.add(mesh(new THREE.SphereGeometry(0.05, 16, 12), plastic(0xffffff), 0, 0.3, 0.1));
  pin.position.set(0.13, 0.12, 0.16);
  g.add(pin);
  g.rotation.set(-0.3, 0.3, -0.06);
  return g;
}

// 🍜 국수 그릇
function noodleBowl() {
  const g = new THREE.Group();
  g.add(mesh(new THREE.LatheGeometry(BOWL_PROFILE, 56),
             plastic(0x27376a, { side: THREE.DoubleSide, roughness: 0.3 })));
  const rim = mesh(new THREE.TorusGeometry(0.5, 0.024, 10, 56), plastic(0xf2c14e, { metalness: 0.3 }), 0, 0.145, 0);
  rim.rotation.x = Math.PI / 2;
  g.add(rim);
  const broth = mesh(new THREE.CircleGeometry(0.47, 48),
                     new THREE.MeshPhysicalMaterial({ color: 0xd98636, roughness: 0.12, clearcoat: 1 }), 0, 0.07, 0);
  broth.rotation.x = -Math.PI / 2;
  g.add(broth);

  const noodle = new THREE.MeshPhysicalMaterial({ color: 0xffe9a8, roughness: 0.45, clearcoat: 0.4 });
  for (let i = 0; i < 7; i++) {                           // 국물 위에 사린 면
    const ang = (i / 7) * TAU;
    const loop = mesh(new THREE.TorusGeometry(0.13 + (i % 3) * 0.045, 0.028, 8, 28, Math.PI * 1.5), noodle,
                      Math.cos(ang) * 0.13, 0.09 + (i % 2) * 0.02, Math.sin(ang) * 0.13);
    loop.rotation.set(Math.PI / 2 + (i % 2 ? 0.25 : -0.2), 0, ang);
    g.add(loop);
  }
  const tipPos = new THREE.Vector3(0.12, 0.66, 0.02);     // 젓가락이 면을 집어 올린 자리
  for (let i = 0; i < 4; i++) {
    const dx = (i - 1.5) * 0.05;
    const strand = new THREE.CatmullRomCurve3([
      new THREE.Vector3(dx * 1.6, 0.06, (i % 2 ? 0.05 : -0.05)),
      new THREE.Vector3(dx + 0.05 * (i % 2 ? 1 : -1), 0.28, 0.03),
      new THREE.Vector3(tipPos.x + dx * 0.5 - 0.04, 0.48, -0.02),
      new THREE.Vector3(tipPos.x + dx * 0.3, tipPos.y, tipPos.z)]);
    g.add(mesh(new THREE.TubeGeometry(strand, 24, 0.024, 8), noodle));
  }
  const wood = plastic(0xb9834f, { roughness: 0.6, clearcoat: 0.2 });
  const up = new THREE.Vector3(0, 1, 0);
  for (const off of [-0.035, 0.035]) {
    const from = tipPos.clone().add(new THREE.Vector3(-0.06, -0.05, off));
    const to = new THREE.Vector3(0.82, 1.08, off * 3);
    const stick = mesh(new THREE.CylinderGeometry(0.022, 0.016, from.distanceTo(to), 10), wood);
    stick.position.copy(from).add(to).multiplyScalar(0.5);
    stick.quaternion.setFromUnitVectors(up, to.clone().sub(from).normalize());
    g.add(stick);
  }
  // 고명: 달걀 반쪽, 파
  const egg = mesh(new THREE.SphereGeometry(0.12, 24, 16), plastic(0xffffff), -0.25, 0.1, 0.12);
  egg.scale.y = 0.45;
  g.add(egg);
  const yolk = mesh(new THREE.SphereGeometry(0.062, 20, 14), plastic(0xffa41c, { roughness: 0.25 }), -0.25, 0.135, 0.12);
  yolk.scale.y = 0.5;
  g.add(yolk);
  const onion = plastic(0x57b85a);
  for (let i = 0; i < 8; i++) {
    const ang = 2.2 + i * 0.55, r = 0.2 + (i % 3) * 0.07;
    const bit = mesh(new THREE.TorusGeometry(0.022, 0.011, 6, 12), onion, Math.cos(ang) * r, 0.095, Math.sin(ang) * r);
    bit.rotation.x = Math.PI / 2;
    g.add(bit);
  }
  g.rotation.x = 0.34;
  return g;
}

// 크기와 중심을 맞춘다 — 어떤 물건이든 지름 1 안에 들어오게
function normalize(obj) {
  const box = new THREE.Box3().setFromObject(obj);
  const size = box.getSize(new THREE.Vector3()), center = box.getCenter(new THREE.Vector3());
  const holder = new THREE.Group();
  const inner = new THREE.Group();
  inner.add(obj);
  obj.position.sub(center);
  inner.scale.setScalar(1 / Math.max(size.x, size.y, size.z));
  holder.add(inner);
  return holder;
}

const softDot = () => canvasTex(64, 64, (c, w) => {
  const g = c.createRadialGradient(w / 2, w / 2, 0, w / 2, w / 2, w / 2);
  g.addColorStop(0, 'rgba(255,255,255,1)');
  g.addColorStop(1, 'rgba(255,255,255,0)');
  c.fillStyle = g;
  c.fillRect(0, 0, w, w);
});

// ───────────────────────── 무대 ─────────────────────────

const ITEMS = [
  { key: 'menu',     label: '오늘 식단',        make: riceBowl },
  { key: 'notice',   label: '공지사항',         make: megaphone },
  { key: 'schedule', label: '학사일정',         make: calendar },
  { key: 'hall',     label: '학생회관 식당 · 별점', make: noodleBowl },
  { key: 'link',     label: '자주 가는 곳',      make: chainLink },
  { key: 'map',      label: '캠퍼스 지도',       make: foldedMap },
];

/**
 * @param stage   캔버스를 넣을 요소 (크기는 CSS 가 정한다)
 * @param tip     마우스를 올렸을 때 이름을 띄울 요소
 * @param onPick  (key) => void. key 는 'bot' 또는 ITEMS 의 key
 * @param isActive () => boolean. 홈이 안 보일 때는 그리지 않는다
 * @param topInset () => px. 위쪽에 겹쳐 놓은 로고 높이 (그만큼 비워 둔다)
 */
export function initHome3D({ stage, tip, onPick, isActive, topInset }) {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.toneMapping = THREE.NeutralToneMapping;   // 색이 물 빠지지 않는 톤매핑
  renderer.toneMappingExposure = 1.0;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  stage.prepend(renderer.domElement);

  const scene = new THREE.Scene();
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  const key = new THREE.DirectionalLight(0xffffff, 1.6);
  key.position.set(4, 7, 8);
  scene.add(key, new THREE.HemisphereLight(0xdfeaff, 0x2a3350, 0.5));

  const FOV = 32, CAM_Z = 13;
  const camera = new THREE.PerspectiveCamera(FOV, 1, 0.1, 60);
  camera.position.set(0, 0.4, CAM_Z);

  const world = new THREE.Group();        // 로고 자리를 피해 통째로 살짝 내린다
  scene.add(world);

  const dark = window.matchMedia?.('(prefers-color-scheme: dark)').matches;
  const accent = dark ? 0x5aa9ff : 0x1f6feb;

  // 곽봇
  const bot = buildBot();
  world.add(bot.root);
  const ring = mesh(new THREE.TorusGeometry(2.25, 0.012, 8, 120),
                    new THREE.MeshBasicMaterial({ color: accent, transparent: true, opacity: 0.35, toneMapped: false }));
  const ring2 = mesh(new THREE.TorusGeometry(2.6, 0.008, 8, 120),
                     new THREE.MeshBasicMaterial({ color: accent, transparent: true, opacity: 0.2, toneMapped: false }));
  bot.root.add(ring, ring2);
  // 발밑 그림자 (떠오르면 작아진다)
  const dot = softDot();
  const shadow = new THREE.Sprite(new THREE.SpriteMaterial({
    map: dot, color: dark ? 0x5aa9ff : 0x1b2a4a, transparent: true, opacity: dark ? 0.28 : 0.22, depthWrite: false }));
  world.add(shadow);

  // 물건들
  const items = ITEMS.map((def, i) => {
    const obj = normalize(def.make());
    world.add(obj);
    return { ...def, obj, base: new THREE.Vector3(), size: 1, hover: 0, spin: 0, spinTo: 0,
             phase: i * 1.7 + 0.6, appear: 0 };
  });

  // 반짝이는 먼지
  const N = 70, dust = new Float32Array(N * 3), speed = new Float32Array(N);
  for (let i = 0; i < N; i++) {
    dust[i * 3] = (Math.random() - 0.5) * 16;
    dust[i * 3 + 1] = (Math.random() - 0.5) * 9;
    dust[i * 3 + 2] = (Math.random() - 0.5) * 6 - 1;
    speed[i] = 0.12 + Math.random() * 0.25;
  }
  const dustGeo = new THREE.BufferGeometry();
  dustGeo.setAttribute('position', new THREE.BufferAttribute(dust, 3));
  const dustPts = new THREE.Points(dustGeo, new THREE.PointsMaterial({
    map: dot, color: accent, size: 0.13, transparent: true, opacity: dark ? 0.7 : 0.4, depthWrite: false,
    blending: dark ? THREE.AdditiveBlending : THREE.NormalBlending, toneMapped: false }));
  scene.add(dustPts);

  // ── 배치: 화면 비율에 맞춰 곽봇 둘레에 놓는다 ──
  let W = 1, H = 1, viewW = 1, viewH = 1, botScale = 1, centerY = 0;
  function layout() {
    W = stage.clientWidth || 1;
    H = stage.clientHeight || 1;
    renderer.setSize(W, H, false);
    camera.aspect = W / H;
    camera.updateProjectionMatrix();
    viewH = 2 * CAM_Z * Math.tan(THREE.MathUtils.degToRad(FOV / 2));
    viewW = viewH * camera.aspect;

    const top = clamp((topInset?.() || 0) / H, 0, 0.3) * viewH, bottom = 0.045 * viewH;
    const useH = viewH - top - bottom;
    centerY = (bottom - top) / 2;
    world.position.y = centerY;

    const portrait = viewW < useH * 0.95;
    botScale = Math.min(useH * (portrait ? 0.4 : 0.62) / 3.9, viewW * (portrait ? 0.44 : 0.3) / 2.7);
    bot.root.scale.setScalar(botScale);

    const size = Math.min(useH * (portrait ? 0.17 : 0.25), viewW * (portrait ? 0.25 : 0.13));
    // 곽봇 둘레의 자리 (가로·세로 반지름에 대한 비율). ITEMS 순서대로:
    // 식단, 공지, 학사일정, 학생회관 식당, 자주 가는 곳, 지도
    const spots = portrait
      ? [[0, 1], [0.87, 0.5], [-0.87, 0.5], [0, -1], [-0.87, -0.5], [0.87, -0.5]]   // 위·아래로 셋씩
      : [[-0.55, 0.74], [0.55, 0.74], [-1, 0], [-0.55, -0.74], [0.55, -0.74], [1, 0]]; // 양옆으로 셋씩
    const rx = portrait ? viewW * 0.33 : Math.min(viewW * 0.4, useH * 1.25);
    const ry = portrait ? useH * 0.39 : useH * 0.36;
    items.forEach((it, i) => {
      it.base.set(spots[i][0] * rx, spots[i][1] * ry, (i % 2 ? -0.4 : 0.4));
      it.size = size;
    });
  }

  // ── 마우스: 어디 위에 있는지 화면 좌표로 직접 잰다 ──
  const pointer = { x: 0, y: 0, px: -1e4, py: -1e4, inside: false };
  const v = new THREE.Vector3();
  const toScreen = (obj) => {
    obj.getWorldPosition(v).project(camera);
    return [(v.x * 0.5 + 0.5) * W, (-v.y * 0.5 + 0.5) * H];
  };
  const pxPerUnit = () => H / viewH;
  let hovered = null;

  function pick() {
    if (!pointer.inside) return null;
    let best = null, bestD = Infinity;
    for (const it of items) {
      const [sx, sy] = toScreen(it.obj);
      const d = Math.hypot(pointer.px - sx, pointer.py - sy);
      if (d < it.size * 0.62 * pxPerUnit() && d < bestD) { best = it.key; bestD = d; }
    }
    if (best) return best;
    const [bx, by] = toScreen(bot.root);
    const u = pxPerUnit() * botScale;
    const nx = (pointer.px - bx) / (1.3 * u), ny = (pointer.py - by) / (2.0 * u);
    return nx * nx + ny * ny < 1 ? 'bot' : null;
  }

  function setHover(key) {
    if (key === hovered) return;
    hovered = key;
    stage.style.cursor = key ? 'pointer' : '';
    const it = items.find(x => x.key === key);
    if (it) it.spinTo += TAU;                   // 올리면 한 바퀴 돈다
    tip.textContent = key === 'bot' ? '곽봇과 대화하기 💬' : (it ? it.label : '');
    tip.classList.toggle('show', !!key);
  }

  const onMove = e => {
    const r = stage.getBoundingClientRect();
    pointer.px = e.clientX - r.left;
    pointer.py = e.clientY - r.top;
    pointer.x = (pointer.px / r.width) * 2 - 1;
    pointer.y = -((pointer.py / r.height) * 2 - 1);
    pointer.inside = true;
    if (e.pointerType !== 'touch') setHover(pick());
  };
  stage.addEventListener('pointermove', onMove);
  stage.addEventListener('pointerdown', onMove);
  stage.addEventListener('pointerleave', () => { pointer.inside = false; setHover(null); });
  stage.addEventListener('click', e => {
    onMove(e);
    const key = pick();
    if (e.pointerType === 'touch') { pointer.inside = false; setHover(null); }
    if (key) onPick(key);
  });

  new ResizeObserver(layout).observe(stage);
  layout();

  // ── 움직임 ──
  const clock = new THREE.Clock();
  const still = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  let t = 0, life = 0, camX = 0, camY = 0, headY = 0, headX = 0, botHover = 0;

  function frame() {
    requestAnimationFrame(frame);
    if (!isActive()) { clock.getDelta(); return; }
    const raw = clock.getDelta();
    const dt = Math.min(raw, 0.05);
    t += dt * (still ? 0.25 : 1);
    life += Math.min(raw, 0.3);     // 등장 연출은 실제 흐른 시간으로 (느린 기기에서도 제때 끝나게)

    // 시선: 마우스 쪽으로 카메라와 머리가 살짝 따라간다
    const tx = pointer.inside ? pointer.x : 0, ty = pointer.inside ? pointer.y : 0;
    camX = lerp(camX, tx * 0.9, 0.04);
    camY = lerp(camY, ty * 0.5, 0.04);
    camera.position.set(camX, 0.4 + camY, CAM_Z);
    camera.lookAt(0, centerY * 0.5, 0);
    headY = lerp(headY, tx * 0.42, 0.07);
    headX = lerp(headX, -ty * 0.22, 0.07);

    // 곽봇: 둥실둥실 + 손 흔들기
    const intro = clamp(life / 0.9, 0, 1);
    botHover = lerp(botHover, hovered === 'bot' ? 1 : 0, 0.12);
    const bob = Math.sin(t * 1.5) * 0.13;
    bot.root.position.y = bob * botScale + 0.05;
    bot.root.scale.setScalar(botScale * easeOutBack(intro) * (1 + botHover * 0.06));
    bot.root.rotation.set(0, Math.sin(t * 0.55) * 0.16 + headY * 0.35, Math.sin(t * 0.9) * 0.03);
    bot.head.rotation.set(headX, headY, Math.sin(t * 1.1) * 0.035);
    bot.armR.rotation.z = 2.25 + Math.sin(t * (5 + botHover * 5)) * (0.22 + botHover * 0.12);
    bot.armL.rotation.z = -0.42 + Math.sin(t * 1.5 + 1) * 0.07;
    bot.tail.rotation.y = Math.sin(t * 2.1) * 0.14;
    bot.faceMat.emissiveIntensity = 1.45 + Math.sin(t * 2.6) * 0.18;
    ring.rotation.set(1.28, t * 0.35, 0);
    ring2.rotation.set(1.42, -t * 0.22, 0.4);

    shadow.position.set(0, -2.2 * botScale, 0);
    const sh = (1 - bob * 1.4) * intro;
    shadow.scale.set(2.5 * botScale * sh, 0.34 * botScale * sh, 1);

    // 물건들: 제자리 근처를 떠다니며 고개를 까딱인다
    for (let i = 0; i < items.length; i++) {
      const it = items[i], p = it.phase;
      it.appear = clamp((life - 0.25 - i * 0.09) / 0.6, 0, 1);
      it.hover = lerp(it.hover, hovered === it.key ? 1 : 0, 0.14);
      it.spin = lerp(it.spin, it.spinTo, 0.07);
      const k = it.size * 0.06;
      it.obj.position.set(
        it.base.x * lerp(0.2, 1, easeOutBack(it.appear)) + Math.sin(t * 0.7 + p) * k * 2.2,
        it.base.y * lerp(0.2, 1, easeOutBack(it.appear)) + Math.sin(t * 1.1 + p * 1.3) * k * 3,
        it.base.z + Math.cos(t * 0.6 + p) * 0.3 + it.hover * 0.6);
      it.obj.scale.setScalar(it.size * easeOutBack(it.appear) * (1 + it.hover * 0.22) || 1e-4);
      it.obj.rotation.set(Math.sin(t * 0.5 + p * 2) * 0.13,
                          Math.sin(t * 0.7 + p) * 0.42 + it.spin,
                          Math.sin(t * 0.6 + p * 3) * 0.07);
    }

    // 먼지는 천천히 위로
    const pos = dustGeo.attributes.position;
    for (let i = 0; i < N; i++) {
      let y = pos.getY(i) + speed[i] * dt;
      if (y > 4.8) y = -4.8;
      pos.setY(i, y);
    }
    pos.needsUpdate = true;

    // 이름표를 가리키는 물건 위에 붙인다
    if (hovered) {
      const target = hovered === 'bot' ? bot.head : items.find(x => x.key === hovered).obj;
      const [sx, sy] = toScreen(target);
      const lift = hovered === 'bot' ? 1.55 * botScale * pxPerUnit()
                                     : items.find(x => x.key === hovered).size * 0.72 * pxPerUnit();
      tip.style.transform = `translate(-50%, -100%) translate(${sx.toFixed(1)}px, ${(sy - lift).toFixed(1)}px)`;
    }

    renderer.render(scene, camera);
  }
  frame();
}
