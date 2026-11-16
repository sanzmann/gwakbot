// 곽봇 홈 3D 무대.
//
// 별이 반짝이는 우주 한가운데에 곽봇이 떠 있고, 그 둘레에 밥공기·확성기·달력 같은 메뉴가 떠다닌다.
// 곽봇을 누르면 대화로, 메뉴를 누르면 그 정보 창으로 간다. 메뉴는 끌어서 어디든 옮길 수 있고,
// 서로 부딪히면 튕겨 나간다. 모델 파일 없이 전부 여기서 도형을 조립해 만든다.
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';

const TAU = Math.PI * 2;
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const lerp = (a, b, t) => a + (b - a) * t;
const easeOutBack = t => 1 + 2.4 * Math.pow(t - 1, 3) + 1.4 * Math.pow(t - 1, 2);

// 장난감 플라스틱 같은 매끈한 재질
const plastic = (color, opts = {}) => new THREE.MeshPhysicalMaterial({
  color, roughness: 0.36, metalness: 0, clearcoat: 0.75, clearcoatRoughness: 0.22, ...opts });
// 스스로 빛나는 재질. 밝기를 1 넘게 주면 블룸이 번져 네온처럼 보인다
const glow = (color, power = 2.2) => {
  const m = new THREE.MeshBasicMaterial();
  m.color.set(color).multiplyScalar(power);
  return m;
};

function canvasTex(w, h, draw, srgb = true) {
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  draw(c.getContext('2d'), w, h);
  const t = new THREE.CanvasTexture(c);
  if (srgb) t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  return t;
}

const mesh = (geo, mat, x = 0, y = 0, z = 0) => {
  const m = new THREE.Mesh(geo, mat);
  m.position.set(x, y, z);
  return m;
};

// 곡선을 따라가며 굵기가 변하는 관 (뿔·귀·꼬리처럼 끝이 가늘어지는 모양에 쓴다)
function sweep(points, radiusAt, { tubular = 40, radial = 18 } = {}) {
  const curve = new THREE.CatmullRomCurve3(points.map(p => new THREE.Vector3(...p)));
  const frames = curve.computeFrenetFrames(tubular, false);
  const len = curve.getLength();
  const pos = [], nor = [], idx = [];
  const P = new THREE.Vector3(), n = new THREE.Vector3();
  for (let i = 0; i <= tubular; i++) {
    const t = i / tubular;
    curve.getPointAt(t, P);
    const r = radiusAt(t);
    const slope = (radiusAt(Math.min(1, t + 1e-3)) - radiusAt(Math.max(0, t - 1e-3))) / (2e-3 * len);
    const N = frames.normals[i], B = frames.binormals[i], T = frames.tangents[i];
    for (let j = 0; j <= radial; j++) {
      const a = (j / radial) * TAU, c = Math.cos(a), s = Math.sin(a);
      n.set(c * N.x + s * B.x, c * N.y + s * B.y, c * N.z + s * B.z);
      pos.push(P.x + n.x * r, P.y + n.y * r, P.z + n.z * r);
      n.addScaledVector(T, -slope).normalize();      // 굵기가 변하는 만큼 법선을 기울인다
      nor.push(n.x, n.y, n.z);
    }
  }
  for (let i = 0; i < tubular; i++) {
    for (let j = 0; j < radial; j++) {
      const a = i * (radial + 1) + j, b = a + radial + 1;
      idx.push(a, a + 1, b, a + 1, b + 1, b);
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('normal', new THREE.Float32BufferAttribute(nor, 3));
  g.setIndex(idx);
  return { geo: g, curve };
}

// 굵기 r0→r1, 양 끝을 둥글게 (c0·c1 은 둥글릴 구간의 비율)
const taper = (r0, r1, c0 = 0.14, c1 = 0.14) => t => {
  let r = lerp(r0, r1, t);
  if (c0 && t < c0) r *= Math.sqrt(Math.max(0, 1 - ((c0 - t) / c0) ** 2));
  if (c1 && t > 1 - c1) r *= Math.sqrt(Math.max(0, 1 - ((t - (1 - c1)) / c1) ** 2));
  return r;
};

// 옆모습(반지름, 높이)을 부드럽게 이어 돌린 회전체
function latheProfile(pts, smooth = 44) {
  return new THREE.SplineCurve(pts.map(([r, y]) => new THREE.Vector2(r, y))).getPoints(smooth)
    .map(p => new THREE.Vector2(Math.max(0, p.x), p.y));
}
const lathe = (pts, seg = 56) => new THREE.LatheGeometry(latheProfile(pts), seg);

// ───────────────────────── 곽봇 ─────────────────────────

// 헬멧은 살짝 납작한 타원체. 그 표면 위의 점을 구한다 (얼굴 화면 테두리를 따라 그리려고)
const HELM = { a: 1.12, b: 0.95, c: 1.02 };
const onHelmet = (phi, theta, k = 1) => new THREE.Vector3(
  -HELM.a * k * Math.cos(phi) * Math.sin(theta),
  HELM.b * k * Math.cos(theta),
  HELM.c * k * Math.sin(phi) * Math.sin(theta));

// 얼굴 화면: 헬멧 앞면의 둥근 사각형 (각도 단위)
const VISOR = { hw: 1.02, hh: 0.5, theta0: 1.53, rc: 0.3 };
function visorOutline() {
  const { hw, hh, rc } = VISOR, out = [];
  const corners = [[hw - rc, -hh + rc, -Math.PI / 2], [hw - rc, hh - rc, 0],
                   [-hw + rc, hh - rc, Math.PI / 2], [-hw + rc, -hh + rc, Math.PI]];
  const arcs = corners.map(([cx, cy, a0]) => {
    const pts = [];
    for (let i = 0; i <= 10; i++) {
      const a = a0 + (i / 10) * (Math.PI / 2);
      pts.push([cx + Math.cos(a) * rc, cy + Math.sin(a) * rc]);
    }
    return pts;
  });
  arcs.forEach((arc, k) => {
    out.push(...arc);
    const from = arc[arc.length - 1], to = arcs[(k + 1) % 4][0];     // 모서리 사이의 곧은 변
    for (let i = 1; i < 8; i++) out.push([lerp(from[0], to[0], i / 8), lerp(from[1], to[1], i / 8)]);
  });
  return out;
}

// 얼굴 화면에 띄울 표정. 빛나는 부분만 그린다 (검은 바탕 = 꺼진 화면)
function drawFace(ctx, w, h, mood) {
  ctx.globalAlpha = 1;
  ctx.shadowBlur = 0;
  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, w, h);
  const bg = ctx.createRadialGradient(w / 2, h / 2, 10, w / 2, h / 2, w * 0.56);   // 켜진 화면의 은은한 빛
  bg.addColorStop(0, 'rgba(34, 84, 170, 0.42)');
  bg.addColorStop(1, 'rgba(6, 14, 40, 0)');
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, w, h);

  const cyan = '#93e3ff';
  ctx.lineCap = ctx.lineJoin = 'round';
  ctx.shadowColor = '#2fb0ff';
  ctx.shadowBlur = 30;
  ctx.strokeStyle = ctx.fillStyle = cyan;
  const ex = [w * 0.345, w * 0.655], ey = h * 0.46;

  if (mood === 'ouch') {                       // > <  (부딪혔을 때)
    ctx.lineWidth = 27;
    for (const [cx, dir] of [[ex[0], 1], [ex[1], -1]]) {
      ctx.beginPath();
      ctx.moveTo(cx - 42 * dir, ey - 44); ctx.lineTo(cx + 34 * dir, ey); ctx.lineTo(cx - 42 * dir, ey + 44);
      ctx.stroke();
    }
    ctx.lineWidth = 18;
    ctx.beginPath(); ctx.ellipse(w / 2, h * 0.7, 22, 27, 0, 0, TAU); ctx.stroke();
  } else if (mood === 'excited') {             // 눈을 반짝 뜨고 활짝 (마우스를 올렸을 때)
    for (const cx of ex) { ctx.beginPath(); ctx.ellipse(cx, ey, 54, 66, 0, 0, TAU); ctx.fill(); }
    ctx.shadowBlur = 0;
    ctx.fillStyle = '#04122a';
    for (const cx of ex) {
      ctx.beginPath(); ctx.arc(cx + 17, ey - 22, 17, 0, TAU); ctx.fill();
      ctx.beginPath(); ctx.arc(cx - 19, ey + 24, 8, 0, TAU); ctx.fill();
    }
    ctx.shadowBlur = 26;
    ctx.fillStyle = cyan;
    ctx.beginPath(); ctx.arc(w / 2, h * 0.64, 60, 0, Math.PI); ctx.closePath(); ctx.fill();
  } else {                                     // ∩ ∩ 웃는 눈 (평소)
    ctx.lineWidth = 33;
    for (const cx of ex) {
      ctx.beginPath(); ctx.arc(cx, ey + 28, 64, Math.PI * 1.13, Math.PI * 1.87); ctx.stroke();
    }
    ctx.lineWidth = 25;
    ctx.beginPath(); ctx.arc(w / 2, h * 0.5, 72, Math.PI * 0.25, Math.PI * 0.75); ctx.stroke();
  }

  ctx.shadowColor = '#ff5a3c';                 // 볼
  ctx.shadowBlur = 22;
  ctx.strokeStyle = '#ff9a7a';
  ctx.lineWidth = 16;
  for (const cx of [w * 0.19, w * 0.81]) {
    for (const dx of [-16, 16]) {
      ctx.beginPath(); ctx.moveTo(cx + dx - 9, h * 0.77); ctx.lineTo(cx + dx + 9, h * 0.65); ctx.stroke();
    }
  }
  // LED 전광판처럼 잘게 나뉜 격자
  ctx.shadowBlur = 0;
  ctx.globalAlpha = 0.3;
  ctx.fillStyle = '#000';
  for (let x = 0; x < w; x += 10) ctx.fillRect(x, 0, 2, h);
  for (let y = 0; y < h; y += 10) ctx.fillRect(0, y, w, 2);
  ctx.globalAlpha = 1;
}

function buildBot() {
  const root = new THREE.Group();
  const bot = new THREE.Group();
  root.add(bot);

  const white = plastic(0xf4f6fb, { roughness: 0.28, clearcoat: 1, clearcoatRoughness: 0.1 });
  const shell = plastic(0x8792a6, { roughness: 0.34, metalness: 0.3, clearcoat: 0.85, clearcoatRoughness: 0.15 });
  const shellLight = plastic(0xa4aec0, { roughness: 0.3, metalness: 0.3, clearcoat: 0.85 });
  const joint = plastic(0x687184, { roughness: 0.45, metalness: 0.35, clearcoat: 0.4 });
  const dark = plastic(0x1c2130, { roughness: 0.45, clearcoat: 0.5 });
  const chrome = new THREE.MeshPhysicalMaterial({ color: 0xd3dae6, metalness: 0.85, roughness: 0.2, clearcoat: 0.6 });
  const blue = glow(0x4fc0ff, 2.3);
  const blueSoft = glow(0x4fc0ff, 1.5);

  // ── 몸통 ──
  const torsoPts = [[0, -0.86], [0.3, -0.83], [0.5, -0.68], [0.6, -0.45], [0.63, -0.2],
                    [0.6, 0.02], [0.5, 0.2], [0.36, 0.29], [0, 0.31]];
  const torsoProfile = latheProfile(torsoPts);
  const TZ = 0.9;                                   // 앞뒤로 살짝 납작하게
  const bodyR = y => {                              // 그 높이에서의 몸통 반지름
    for (let i = 1; i < torsoProfile.length; i++) {
      const a = torsoProfile[i - 1], b = torsoProfile[i];
      if (y >= a.y && y <= b.y) return lerp(a.x, b.x, (y - a.y) / ((b.y - a.y) || 1));
    }
    return 0;
  };
  const onBody = (x, y, lift = 0.012) => [x, y, TZ * Math.sqrt(Math.max(0, bodyR(y) ** 2 - x * x)) + lift];

  const torso = mesh(new THREE.LatheGeometry(torsoProfile, 64), white);
  torso.scale.z = TZ;
  bot.add(torso);

  // 가슴의 T 엠블럼 — 몸통 곡면을 따라 붙인다
  const ringPts = [];
  for (let i = 0; i < 40; i++) {
    const a = (i / 40) * TAU;
    ringPts.push(new THREE.Vector3(...onBody(Math.cos(a) * 0.2, -0.1 + Math.sin(a) * 0.2)));
  }
  bot.add(mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(ringPts, true), 80, 0.027, 10, true), blue));
  const bar = (x0, y0, x1, y1) => {
    const pts = [];
    for (let i = 0; i <= 6; i++) pts.push(onBody(lerp(x0, x1, i / 6), lerp(y0, y1, i / 6), 0.014));
    return mesh(sweep(pts, taper(0.03, 0.03, 0.2, 0.2), { tubular: 16, radial: 10 }).geo, blue);
  };
  bot.add(bar(-0.1, -0.04, 0.1, -0.04), bar(0, -0.04, 0, -0.2));

  // 이음매와 허리
  const seam = mesh(new THREE.TorusGeometry(bodyR(-0.52) + 0.003, 0.009, 6, 80), joint, 0, -0.52, 0);
  seam.rotation.x = Math.PI / 2;
  seam.scale.y = TZ;
  bot.add(seam);
  const hip = mesh(new THREE.SphereGeometry(0.47, 40, 24), dark, 0, -0.85, 0);
  hip.scale.set(1, 0.42, 0.85);
  bot.add(hip);
  const collar = mesh(new THREE.TorusGeometry(0.33, 0.07, 14, 48), dark, 0, 0.3, 0);
  collar.rotation.x = Math.PI / 2;
  bot.add(collar);
  const collarGlow = mesh(new THREE.TorusGeometry(0.385, 0.011, 8, 64), blueSoft, 0, 0.27, 0);
  collarGlow.rotation.x = Math.PI / 2;
  bot.add(collarGlow);
  bot.add(mesh(new THREE.CylinderGeometry(0.25, 0.28, 0.3, 32), dark, 0, 0.42, 0));

  // ── 머리 (목을 축으로 돈다) ──
  const head = new THREE.Group();
  head.position.y = 0.3;
  bot.add(head);
  const skull = new THREE.Group();           // 헬멧 중심
  skull.position.y = 0.84;
  head.add(skull);

  const helmet = mesh(new THREE.SphereGeometry(1, 72, 56), shell);
  helmet.scale.set(HELM.a, HELM.b, HELM.c);
  skull.add(helmet);
  const crown = mesh(new THREE.SphereGeometry(1.004, 72, 20, 0, TAU, 0, 0.62), shellLight);   // 정수리 덮개
  crown.scale.copy(helmet.scale);
  skull.add(crown);
  const crownSeam = mesh(new THREE.TorusGeometry(1, 0.016, 8, 96), dark, 0, HELM.b * Math.cos(0.62), 0);
  crownSeam.rotation.x = Math.PI / 2;
  crownSeam.scale.set(HELM.a * Math.sin(0.62) * 1.004, HELM.c * Math.sin(0.62) * 1.004, 1);
  skull.add(crownSeam);

  // 얼굴 화면: 표정은 캔버스에 그려 빛나게 하고, 둥근 모서리는 알파 지도로 오려낸다
  const outline = visorOutline();
  const FW = 1024, FH = 432;
  const faceCanvas = document.createElement('canvas');
  faceCanvas.width = FW; faceCanvas.height = FH;
  const faceCtx = faceCanvas.getContext('2d');
  const faceTex = new THREE.CanvasTexture(faceCanvas);
  faceTex.colorSpace = THREE.SRGBColorSpace;
  faceTex.anisotropy = 8;
  const maskTex = canvasTex(512, 216, (c, w, h) => {
    c.fillStyle = '#000'; c.fillRect(0, 0, w, h);
    c.fillStyle = '#fff';
    c.beginPath();
    outline.forEach(([du, dv], i) => {
      const x = (du + VISOR.hw) / (2 * VISOR.hw) * w, y = (dv + VISOR.hh) / (2 * VISOR.hh) * h;
      i ? c.lineTo(x, y) : c.moveTo(x, y);
    });
    c.closePath(); c.fill();
  }, false);
  const faceMat = new THREE.MeshPhysicalMaterial({
    color: 0x070b18, emissive: 0xffffff, emissiveMap: faceTex, emissiveIntensity: 1.7,
    alphaMap: maskTex, alphaTest: 0.5, roughness: 0.1, clearcoat: 1, clearcoatRoughness: 0.05 });
  const screen = mesh(new THREE.SphereGeometry(1.012, 72, 36, Math.PI / 2 - VISOR.hw, 2 * VISOR.hw,
                                               VISOR.theta0 - VISOR.hh, 2 * VISOR.hh), faceMat);
  screen.scale.copy(helmet.scale);
  skull.add(screen);
  // 화면을 두른 도톰한 테
  const bezelPts = outline.map(([du, dv]) => onHelmet(Math.PI / 2 + du, VISOR.theta0 + dv, 1.02));
  skull.add(mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(bezelPts, true), 220, 0.045, 12, true), chrome));

  let mood = '';
  const setMood = m => {
    if (m === mood) return;
    mood = m;
    drawFace(faceCtx, FW, FH, m);
    faceTex.needsUpdate = true;
  };
  setMood('happy');

  for (const sx of [-1, 1]) {
    // 옆으로 뻗은 귀 (끝으로 갈수록 가늘고 살짝 위로 휜다)
    const ear = mesh(sweep([[sx * 0.72, 0.36, -0.06], [sx * 0.98, 0.52, -0.09], [sx * 1.2, 0.72, -0.11], [sx * 1.3, 0.9, -0.11]],
                           t => lerp(0.3, 0.04, Math.pow(t, 0.8)) * (t > 0.88 ? Math.sqrt(1 - ((t - 0.88) / 0.12) ** 2) : 1),
                           { tubular: 32, radial: 20 }).geo, shell);
    ear.scale.z = 0.6;
    skull.add(ear);
    // 헤드폰
    const cup = new THREE.Group();
    cup.position.set(sx * 1.1, -0.12, 0.03);
    cup.rotation.z = Math.PI / 2;
    cup.add(mesh(new THREE.CylinderGeometry(0.31, 0.33, 0.16, 40), dark));
    cup.add(mesh(new THREE.CylinderGeometry(0.25, 0.27, 0.06, 40), joint, 0, -sx * 0.1, 0));
    const ring = mesh(new THREE.TorusGeometry(0.19, 0.03, 12, 44), blue, 0, -sx * 0.135, 0);
    ring.rotation.x = Math.PI / 2;
    cup.add(ring);
    cup.add(mesh(new THREE.CylinderGeometry(0.12, 0.12, 0.05, 28), dark, 0, -sx * 0.14, 0));
    cup.add(mesh(new THREE.SphereGeometry(0.04, 14, 10), blueSoft, 0, -sx * 0.17, 0));
    skull.add(cup);
  }

  // 뿔 (테크뇽의 빨강·파랑 뿔). 받침 위에 사탕처럼 반들반들한 뿔이 꽂혀 있다
  const horns = [];
  const horn = (sx, color, lobes) => {
    const g = new THREE.Group();
    const candy = plastic(color, { roughness: 0.16, clearcoat: 1, clearcoatRoughness: 0.05 });
    g.add(mesh(new THREE.CylinderGeometry(0.18, 0.21, 0.17, 28), dark, 0, 0.04, 0));
    const lip = mesh(new THREE.TorusGeometry(0.185, 0.022, 10, 32), chrome, 0, 0.125, 0);
    lip.rotation.x = Math.PI / 2;
    g.add(lip);
    for (const [pts, r0, r1] of lobes) {
      g.add(mesh(sweep(pts, taper(r0, r1, 0.16, 0.3), { tubular: 28, radial: 20 }).geo, candy));
    }
    const x = sx * 0.47;
    g.position.set(x, HELM.b * Math.sqrt(1 - (x / HELM.a) ** 2) - 0.03, 0);
    g.rotation.z = -sx * 0.3;
    horns.push(g);
    return g;
  };
  skull.add(
    horn(-1, 0xf04a5a, [                       // 빨강: 옆으로 혹이 난 벙어리장갑 모양
      [[[0, 0.08, 0], [0, 0.36, 0], [-0.03, 0.62, 0], [-0.09, 0.82, 0]], 0.16, 0.175],
      [[[-0.02, 0.36, 0], [-0.17, 0.44, 0], [-0.27, 0.56, 0]], 0.12, 0.14]]),
    horn(1, 0x2f6cf0, [                        // 파랑: 끝이 하트처럼 둘로 갈라진다
      [[[0, 0.08, 0], [0, 0.34, 0], [0.01, 0.52, 0]], 0.16, 0.165],
      [[[0.01, 0.46, 0], [-0.07, 0.66, 0], [-0.14, 0.83, 0]], 0.15, 0.15],
      [[[0.01, 0.46, 0], [0.13, 0.62, 0], [0.24, 0.76, 0]], 0.15, 0.15]]));

  // ── 팔: 어깨를 축으로 돈다. 장갑처럼 끝이 도톰하다 ──
  const forearmGeo = lathe([[0, -0.85], [0.15, -0.84], [0.205, -0.77], [0.2, -0.66], [0.15, -0.5], [0.115, -0.4], [0, -0.39]]);
  const arm = sx => {
    const g = new THREE.Group();
    g.position.set(sx * 0.6, 0.06, 0);
    g.add(mesh(new THREE.SphereGeometry(0.175, 28, 20), dark));
    g.add(mesh(new THREE.CapsuleGeometry(0.105, 0.2, 8, 20), joint, 0, -0.2, 0));
    g.add(mesh(new THREE.SphereGeometry(0.125, 24, 16), dark, 0, -0.36, 0));
    g.add(mesh(forearmGeo, white));
    const cuff = mesh(new THREE.TorusGeometry(0.203, 0.014, 8, 44), blueSoft, 0, -0.73, 0);
    cuff.rotation.x = Math.PI / 2;
    g.add(cuff);
    const hand = mesh(new THREE.SphereGeometry(0.2, 32, 24), white, 0, -0.9, 0);
    hand.scale.set(1, 0.95, 0.86);
    g.add(hand);
    g.add(mesh(new THREE.SphereGeometry(0.088, 20, 14), white, -sx * 0.165, -0.85, 0.07));   // 엄지
    g.add(mesh(new THREE.TorusGeometry(0.082, 0.021, 10, 30), blue, 0, -0.9, 0.172));
    g.add(mesh(new THREE.SphereGeometry(0.03, 12, 8), blue, 0, -0.9, 0.18));
    g.scale.setScalar(0.84);
    return g;
  };
  const armL = arm(-1), armR = arm(1);
  bot.add(armL, armR);

  // ── 다리와 장화, 발바닥의 분사구 ──
  const legGeo = lathe([[0, -0.39], [0.19, -0.385], [0.225, -0.33], [0.2, -0.26], [0.155, -0.1], [0.135, 0], [0, 0.01]]);
  const flames = [];
  const flameTex = canvasTex(8, 128, (c, w, h) => {
    const g = c.createLinearGradient(0, 0, 0, h);          // 위(뾰족한 끝)는 투명, 아래(분사구)는 밝게
    g.addColorStop(0, 'rgba(60,150,255,0)');
    g.addColorStop(0.55, 'rgba(70,170,255,0.55)');
    g.addColorStop(1, 'rgba(220,245,255,1)');
    c.fillStyle = g; c.fillRect(0, 0, w, h);
  });
  for (const sx of [-1, 1]) {
    const x = sx * 0.27;
    bot.add(mesh(new THREE.SphereGeometry(0.15, 24, 16), dark, x, -0.96, 0));
    bot.add(mesh(legGeo, white, x, -0.98, 0));
    const boot = mesh(new THREE.SphereGeometry(0.25, 36, 24), white, x, -1.43, 0.1);
    boot.scale.set(1, 0.58, 1.38);
    bot.add(boot);
    const sole = mesh(new THREE.SphereGeometry(0.256, 36, 14, 0, TAU, Math.PI * 0.6, Math.PI * 0.4), dark, x, -1.43, 0.1);
    sole.scale.copy(boot.scale);
    bot.add(sole);
    const toe = [];
    for (let i = 0; i <= 10; i++) {
      const a = lerp(-0.85, 0.85, i / 10);
      toe.push([x + Math.sin(a) * 0.253, -1.405, 0.1 + Math.cos(a) * 0.349]);
    }
    bot.add(mesh(sweep(toe, taper(0.024, 0.024, 0.15, 0.15), { tubular: 24, radial: 10 }).geo, blue));
    bot.add(mesh(new THREE.CylinderGeometry(0.1, 0.13, 0.07, 24), joint, x, -1.59, 0.04));
    // 분사 불꽃
    const flame = mesh(new THREE.ConeGeometry(0.1, 0.62, 24, 1, true),
      new THREE.MeshBasicMaterial({ map: flameTex, transparent: true, blending: THREE.AdditiveBlending,
                                    depthWrite: false, side: THREE.DoubleSide }), x, -1.93, 0.04);
    flame.rotation.x = Math.PI;
    flame.userData.y0 = -1.93;
    flame.material.color.setScalar(1.8);
    bot.add(flame);
    flames.push(flame);
  }

  // ── 꼬리: 마디가 있는 관 끝에 흰 공 ──
  const tail = new THREE.Group();
  tail.position.set(0.1, -0.7, -0.42);
  const tailPts = [[0, 0, 0], [0.45, -0.36, -0.16], [0.95, -0.27, -0.08], [1.2, 0.14, 0.04], [1.13, 0.5, 0.12]];
  const tailSweep = sweep(tailPts, t => lerp(0.092, 0.058, t), { tubular: 48, radial: 16 });
  tail.add(mesh(tailSweep.geo, shell));
  const zAxis = new THREE.Vector3(0, 0, 1);
  for (const t of [0.14, 0.3, 0.46, 0.62, 0.78, 0.92]) {
    const band = mesh(new THREE.TorusGeometry(lerp(0.092, 0.058, t) + 0.012, 0.014, 8, 24), dark);
    band.position.copy(tailSweep.curve.getPointAt(t));
    band.quaternion.setFromUnitVectors(zAxis, tailSweep.curve.getTangentAt(t));
    tail.add(band);
  }
  tail.add(mesh(new THREE.SphereGeometry(0.21, 32, 24), white, 1.12, 0.62, 0.14));
  bot.add(tail);

  // 눈으로 보는 중심이 원점에 오게 맞춘다 (불꽃은 빼고 잰다)
  flames.forEach(f => { f.visible = false; });
  const box = new THREE.Box3().setFromObject(bot);
  flames.forEach(f => { f.visible = true; });
  const center = box.getCenter(new THREE.Vector3()), size = box.getSize(new THREE.Vector3());
  bot.position.sub(center);

  return { root, head, armL, armR, tail, horns, flames, faceMat, setMood,
           height: size.y, width: size.x,
           // 메뉴가 부딪히는 범위 (원 두 개: 머리와 몸)
           colliders: [{ x: -center.x, y: 0.3 + 0.84 - center.y, r: 1.28 }, { x: -center.x, y: -0.6 - center.y, r: 0.85 }] };
}

// ───────────────────────── 떠다니는 메뉴들 ─────────────────────────

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
  const wave = glow(0xffc93c, 1.9);
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
  g.addColorStop(0.35, 'rgba(255,255,255,0.45)');
  g.addColorStop(1, 'rgba(255,255,255,0)');
  c.fillStyle = g;
  c.fillRect(0, 0, w, w);
});

// ───────────────────────── 우주 ─────────────────────────

// 깊이가 제각각인 별 무리. 멀수록 작고, 저마다 다른 박자로 반짝인다
function makeStars(count) {
  const pos = new Float32Array(count * 3), size = new Float32Array(count),
        phase = new Float32Array(count), color = new Float32Array(count * 3);
  const tints = [[1, 1, 1], [0.75, 0.86, 1], [1, 0.9, 0.78], [0.82, 0.8, 1], [1, 1, 1]];
  for (let i = 0; i < count; i++) {
    const z = -8 - Math.pow(Math.random(), 0.7) * 150;
    const spread = (-z + 13) * 0.62;                        // 시야보다 조금 넓게
    pos[i * 3] = (Math.random() * 2 - 1) * spread * 1.9;
    pos[i * 3 + 1] = (Math.random() * 2 - 1) * spread;
    pos[i * 3 + 2] = z;
    size[i] = 0.07 + Math.pow(Math.random(), 7) * 0.5 + Math.random() * 0.08;   // 대부분 작고 몇 개만 크다
    phase[i] = Math.random();
    const t = tints[(Math.random() * tints.length) | 0], b = 0.3 + Math.pow(Math.random(), 2) * 0.75;
    color.set([t[0] * b, t[1] * b, t[2] * b], i * 3);
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  geo.setAttribute('aSize', new THREE.BufferAttribute(size, 1));
  geo.setAttribute('aPhase', new THREE.BufferAttribute(phase, 1));
  geo.setAttribute('aColor', new THREE.BufferAttribute(color, 3));
  const mat = new THREE.ShaderMaterial({
    uniforms: { uTime: { value: 0 }, uScale: { value: 1 } },
    transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
    vertexShader: `
      attribute float aSize; attribute float aPhase; attribute vec3 aColor;
      uniform float uTime; uniform float uScale;
      varying vec3 vColor; varying float vTw;
      void main() {
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        float tw = 0.7 + 0.3 * sin(uTime * (0.5 + fract(aPhase * 7.13) * 2.4) + aPhase * 6.2831);
        tw += 0.9 * pow(max(0.0, sin(uTime * 0.31 + aPhase * 43.0)), 30.0);   // 가끔 한 번씩 크게 반짝
        vTw = tw; vColor = aColor;
        gl_PointSize = max(1.2, aSize * uScale * (0.75 + 0.25 * tw) / -mv.z);
        gl_Position = projectionMatrix * mv;
      }`,
    fragmentShader: `
      varying vec3 vColor; varying float vTw;
      void main() {
        float d = length(gl_PointCoord - 0.5);
        float core = smoothstep(0.5, 0.0, d);
        gl_FragColor = vec4(vColor * vTw * (0.5 + 1.5 * pow(core, 5.0)), pow(core, 2.0));
      }`,
  });
  return new THREE.Points(geo, mat);
}

// 십자로 빛이 갈라지는 밝은 별
const flareTex = () => canvasTex(128, 128, (c, w) => {
  const m = w / 2;
  const g = c.createRadialGradient(m, m, 0, m, m, m);
  g.addColorStop(0, 'rgba(255,255,255,1)');
  g.addColorStop(0.12, 'rgba(200,225,255,0.55)');
  g.addColorStop(0.5, 'rgba(120,170,255,0.06)');
  g.addColorStop(1, 'rgba(0,0,0,0)');
  c.fillStyle = g; c.fillRect(0, 0, w, w);
  for (const horizontal of [true, false]) {
    const l = c.createLinearGradient(horizontal ? 0 : m, horizontal ? m : 0, horizontal ? w : m, horizontal ? m : w);
    l.addColorStop(0, 'rgba(255,255,255,0)');
    l.addColorStop(0.5, 'rgba(255,255,255,0.9)');
    l.addColorStop(1, 'rgba(255,255,255,0)');
    c.fillStyle = l;
    horizontal ? c.fillRect(0, m - 1.2, w, 2.4) : c.fillRect(m - 1.2, 0, 2.4, w);
  }
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
  const coarse = window.matchMedia?.('(pointer: coarse)').matches;
  const DPR = Math.min(window.devicePixelRatio || 1, coarse ? 1.5 : 2);
  const renderer = new THREE.WebGLRenderer({ antialias: false, powerPreference: 'high-performance' });
  renderer.setPixelRatio(DPR);
  renderer.setClearColor(0x000000, 1);
  renderer.toneMapping = THREE.NeutralToneMapping;   // 색이 물 빠지지 않는 톤매핑
  renderer.toneMappingExposure = 1.0;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  stage.prepend(renderer.domElement);

  const scene = new THREE.Scene();
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = 0.5;
  // 정면의 주광 + 뒤에서 비추는 푸른빛·분홍빛 (검은 우주에서 윤곽이 살아나게)
  const key = new THREE.DirectionalLight(0xffffff, 1.35);
  key.position.set(3.5, 6, 8);
  const rimBlue = new THREE.DirectionalLight(0x4aa8ff, 2.4);
  rimBlue.position.set(-7, 3, -5);
  const rimPink = new THREE.DirectionalLight(0xff5fa8, 1.8);
  rimPink.position.set(7, 1.5, -5);
  scene.add(key, rimBlue, rimPink, new THREE.HemisphereLight(0xcfe0ff, 0x10142a, 0.35));

  const FOV = 32, CAM_Z = 13;
  const camera = new THREE.PerspectiveCamera(FOV, 1, 0.1, 400);
  camera.position.set(0, 0.4, CAM_Z);

  // 후처리: 빛나는 부분이 번지게 (네온·별·불꽃)
  const composer = new EffectComposer(renderer, new THREE.WebGLRenderTarget(4, 4, {
    type: THREE.HalfFloatType, samples: 4 }));
  composer.setPixelRatio(DPR);
  composer.addPass(new RenderPass(scene, camera));
  const bloom = new UnrealBloomPass(new THREE.Vector2(256, 256), 0.42, 0.5, 1.25);
  composer.addPass(bloom);
  composer.addPass(new OutputPass());

  // ── 우주 ──
  const space = new THREE.Group();
  scene.add(space);
  const stars = makeStars(coarse ? 800 : 1300);
  space.add(stars);
  const flare = flareTex();
  const flares = [[-15, 8.5, -40, 1.5], [18, 6, -48, 1.9], [-21, -7, -54, 2.0], [7, -11, -44, 1.3], [27, -4, -72, 2.2]]
    .map(([x, y, z, s], i) => {
      const sp = new THREE.Sprite(new THREE.SpriteMaterial({
        map: flare, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
        color: new THREE.Color().setHSL(0.58 + (i % 3) * 0.05, 0.6, 0.8) }));
      sp.position.set(x, y, z);
      sp.userData = { s, p: i * 1.9 };
      space.add(sp);
      return sp;
    });
  // 별똥별: 가끔 한 줄기
  const streak = new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({
    map: canvasTex(256, 8, (c, w, h) => {
      const g = c.createLinearGradient(0, 0, w, 0);
      g.addColorStop(0, 'rgba(255,255,255,0)');
      g.addColorStop(0.85, 'rgba(190,220,255,0.7)');
      g.addColorStop(1, 'rgba(255,255,255,1)');
      c.fillStyle = g; c.fillRect(0, 0, w, h);
    }), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
  streak.visible = false;
  scene.add(streak);
  const shoot = { next: 3.5, t: 0, dur: 0.9, from: new THREE.Vector3(), to: new THREE.Vector3() };

  const world = new THREE.Group();        // 로고 자리를 피해 통째로 살짝 내린다
  scene.add(world);

  // ── 곽봇 ──
  const bot = buildBot();
  const rig = new THREE.Group();          // 자리·크기는 rig 에, 회전은 bot.root 에 (몸을 돌려도 둘레의 고리는 그대로)
  world.add(rig);
  const ACCENT = 0x4fb4ff;
  const ring = mesh(new THREE.TorusGeometry(2.55, 0.011, 8, 160), glow(ACCENT, 1.25));
  const ring2 = mesh(new THREE.TorusGeometry(2.95, 0.007, 8, 160), glow(ACCENT, 0.7));
  const moon = mesh(new THREE.SphereGeometry(0.06, 16, 12), glow(0xbfe6ff, 2.4), 2.55, 0, 0);   // 고리를 도는 작은 빛
  ring.add(moon);
  rig.add(bot.root, ring, ring2);
  const dot = softDot();

  // ── 메뉴들 ──
  const items = ITEMS.map((def, i) => {
    const obj = normalize(def.make());
    world.add(obj);
    return { ...def, obj, x: 0, y: 0, vx: 0, vy: 0, r: 0.5, size: 1, z: (i % 2 ? -0.35 : 0.35),
             hover: 0, lift: 0, spin: 0, spinTo: 0, punch: 0, cool: 0, phase: i * 1.7 + 0.6, appear: 0 };
  });

  // 가까이 떠다니는 먼지 (앞뒤 깊이감을 더한다)
  const N = 60, dust = new Float32Array(N * 3), speed = new Float32Array(N);
  for (let i = 0; i < N; i++) {
    dust[i * 3] = (Math.random() - 0.5) * 18;
    dust[i * 3 + 1] = (Math.random() - 0.5) * 10;
    dust[i * 3 + 2] = (Math.random() - 0.5) * 8;
    speed[i] = 0.08 + Math.random() * 0.2;
  }
  const dustGeo = new THREE.BufferGeometry();
  dustGeo.setAttribute('position', new THREE.BufferAttribute(dust, 3));
  scene.add(new THREE.Points(dustGeo, new THREE.PointsMaterial({
    map: dot, color: 0x6fb6ff, size: 0.11, transparent: true, opacity: 0.55, depthWrite: false,
    blending: THREE.AdditiveBlending })));

  // ── 부딪혔을 때의 효과: 불티와 퍼지는 고리 ──
  const sparks = Array.from({ length: 36 }, () => {
    const s = new THREE.Sprite(new THREE.SpriteMaterial({
      map: dot, transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending }));
    s.visible = false;
    world.add(s);
    return { s, vx: 0, vy: 0, life: 0 };
  });
  const shocks = Array.from({ length: 5 }, () => {
    const m = mesh(new THREE.RingGeometry(0.93, 1, 56), new THREE.MeshBasicMaterial({
      transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending, side: THREE.DoubleSide }));
    m.visible = false;
    world.add(m);
    return { m, life: 0, size: 1 };
  });
  let sparkAt = 0, shockAt = 0;
  function burst(x, y, power, hue) {
    const n = clamp(Math.round(4 + power * 0.8), 5, 10);
    for (let i = 0; i < n; i++) {
      const sp = sparks[sparkAt++ % sparks.length];
      const a = Math.random() * TAU, v = (1.5 + Math.random() * 3.5) * clamp(power / 4, 0.6, 1.8);
      sp.vx = Math.cos(a) * v; sp.vy = Math.sin(a) * v; sp.life = 1;
      sp.s.position.set(x, y, 0.8);
      sp.s.material.color.setHSL(hue + (Math.random() - 0.5) * 0.12, 0.9, 0.7).multiplyScalar(2);
      sp.s.visible = true;
    }
    const sh = shocks[shockAt++ % shocks.length];
    sh.life = 1; sh.size = clamp(0.4 + power * 0.05, 0.45, 0.85);
    sh.m.position.set(x, y, 0.7);
    sh.m.material.color.setHSL(hue, 0.7, 0.7).multiplyScalar(1.1);
    sh.m.visible = true;
  }

  // ── 배치와 크기 ──
  let W = 1, H = 1, viewW = 1, viewH = 1, botScale = 1, centerY = 0, placed = false;
  const bounds = { x0: -1, x1: 1, y0: -1, y1: 1 };
  function layout() {
    const w = stage.clientWidth, h = stage.clientHeight;
    if (!w || !h) return;                       // 홈이 가려져 있다
    const prevW = viewW, prevH = viewH;
    W = w; H = h;
    renderer.setSize(W, H, false);
    composer.setSize(W, H);
    camera.aspect = W / H;
    camera.updateProjectionMatrix();
    viewH = 2 * CAM_Z * Math.tan(THREE.MathUtils.degToRad(FOV / 2));
    viewW = viewH * camera.aspect;
    stars.material.uniforms.uScale.value = H * DPR / (2 * Math.tan(THREE.MathUtils.degToRad(FOV / 2)));

    const top = clamp(((topInset?.() || 0) + 10) / H, 0, 0.3) * viewH, bottom = 0.05 * viewH;
    const useH = viewH - top - bottom;
    centerY = (bottom - top) / 2;
    world.position.y = centerY;
    bounds.x0 = -viewW / 2; bounds.x1 = viewW / 2;
    bounds.y0 = -viewH / 2 - centerY; bounds.y1 = viewH / 2 - centerY;

    const portrait = viewW < useH * 0.95;
    botScale = Math.min(useH * (portrait ? 0.42 : 0.68) / bot.height, viewW * (portrait ? 0.46 : 0.3) / bot.width);
    const size = Math.min(useH * (portrait ? 0.16 : 0.21), viewW * (portrait ? 0.24 : 0.12));
    for (const it of items) { it.size = size; it.r = size * 0.5; }

    if (!placed) {
      // 처음엔 곽봇 둘레에 놓는다. ITEMS 순서대로: 식단, 공지, 학사일정, 학생회관 식당, 자주 가는 곳, 지도
      const spots = portrait
        ? [[0, 1], [0.87, 0.5], [-0.87, 0.5], [0, -1], [-0.87, -0.5], [0.87, -0.5]]       // 위·아래로 셋씩
        : [[-0.55, 0.74], [0.55, 0.74], [-1, 0], [-0.55, -0.74], [0.55, -0.74], [1, 0]];  // 양옆으로 셋씩
      const rx = portrait ? viewW * 0.34 : Math.min(viewW * 0.4, useH * 1.2);
      const ry = portrait ? useH * 0.38 : useH * 0.36;
      items.forEach((it, i) => { it.x = spots[i][0] * rx; it.y = spots[i][1] * ry; });
      placed = true;
    } else {
      // 창 크기가 바뀌면 옮겨 둔 자리도 같은 비율로 따라간다
      for (const it of items) { it.x *= viewW / prevW; it.y *= viewH / prevH; }
    }
  }

  // ── 화면 좌표 ↔ 무대 좌표 ──
  const pointer = { x: 0, y: 0, px: -1e4, py: -1e4, inside: false };
  const v = new THREE.Vector3(), dir = new THREE.Vector3();
  const toScreen = obj => {
    obj.getWorldPosition(v).project(camera);
    return [(v.x * 0.5 + 0.5) * W, (-v.y * 0.5 + 0.5) * H];
  };
  // 마우스가 가리키는 무대 평면(z=0) 위의 점
  const pointerWorld = () => {
    dir.set(pointer.x, pointer.y, 0.5).unproject(camera).sub(camera.position).normalize();
    const k = -camera.position.z / dir.z;
    return [camera.position.x + dir.x * k, camera.position.y + dir.y * k - world.position.y];
  };
  const pxPerUnit = () => H / viewH;

  function pick(reach = 0.6) {
    if (!pointer.inside) return null;
    let best = null, bestD = Infinity;
    for (const it of items) {
      const [sx, sy] = toScreen(it.obj);
      const d = Math.hypot(pointer.px - sx, pointer.py - sy);
      if (d < it.size * reach * pxPerUnit() && d < bestD) { best = it.key; bestD = d; }
    }
    if (best) return best;
    const [bx, by] = toScreen(bot.root);
    const u = pxPerUnit() * botScale;
    const nx = (pointer.px - bx) / (bot.width * 0.5 * u), ny = (pointer.py - by) / (bot.height * 0.5 * u);
    return nx * nx + ny * ny < 1 ? 'bot' : null;
  }

  // ── 누르기·끌기 ──
  let hovered = null, drag = null, down = null;
  const grab = { dx: 0, dy: 0, x: 0, y: 0 };
  // 곽봇은 끌면 몸이 돈다 (좌우로 빙글, 위아래로는 살짝 기울기만)
  const turn = { on: false, yaw: 0, pitch: 0, v: 0, rest: 0, x: 0, y: 0, at: 0 };

  function setHover(key) {
    if (key === hovered) return;
    hovered = key;
    const it = items.find(x => x.key === key);
    const held = drag || turn.on;
    if (it && !held) it.spinTo += TAU;          // 올리면 한 바퀴 돈다
    tip.textContent = key === 'bot' ? '누르면 대화 💬 · 끌면 돌아가요' : (it ? it.label : '');
    tip.classList.toggle('show', !!key && !held);
    stage.style.cursor = held ? 'grabbing' : key === 'bot' ? 'pointer' : key ? 'grab' : '';
  }
  const track = e => {
    const r = stage.getBoundingClientRect();
    pointer.px = e.clientX - r.left;
    pointer.py = e.clientY - r.top;
    pointer.x = (pointer.px / r.width) * 2 - 1;
    pointer.y = -((pointer.py / r.height) * 2 - 1);
    pointer.inside = true;
  };
  stage.addEventListener('pointermove', e => {
    if (down && e.pointerId !== down.id) return;      // 누르고 있는 손가락만 따라간다
    track(e);
    if (down && Math.hypot(e.clientX - down.x, e.clientY - down.y) > down.slop) down.moved = true;
    if (drag) {
      const [wx, wy] = pointerWorld();
      grab.x = wx + grab.dx; grab.y = wy + grab.dy;
    } else if (turn.on) {
      const k = Math.PI / Math.max(70, bot.width * botScale * pxPerUnit());   // 몸 너비만큼 끌면 반 바퀴
      const now = performance.now(), dx = e.clientX - turn.x, dy = e.clientY - turn.y;
      turn.yaw += dx * k;
      turn.pitch = clamp(turn.pitch + dy * k * 0.5, -0.5, 0.5);
      turn.v = lerp(turn.v, dx * k / (Math.max(4, now - turn.at) / 1000), 0.45);
      turn.x = e.clientX; turn.y = e.clientY; turn.at = now;
    } else if (e.pointerType !== 'touch') setHover(pick());
  });
  stage.addEventListener('pointerdown', e => {
    if (e.button > 0) return;
    track(e);
    const touch = e.pointerType === 'touch';
    const key = pick(touch ? 0.75 : 0.6);            // 손가락은 넉넉하게 잡아 준다
    if (!key) return;
    // 손가락은 가만히 눌러도 조금씩 미끄러진다. 그만큼은 끌기가 아니라 누르기로 본다
    down = { key, id: e.pointerId, x: e.clientX, y: e.clientY, moved: false, slop: touch ? 14 : 6 };
    drag = null; turn.on = false;
    const it = items.find(x => x.key === key);
    if (it) {
      const [wx, wy] = pointerWorld();
      drag = it;
      grab.dx = it.x - wx; grab.dy = it.y - wy;
      grab.x = it.x; grab.y = it.y;
    } else {
      turn.on = true; turn.v = 0;
      turn.x = e.clientX; turn.y = e.clientY; turn.at = performance.now();
    }
    try { stage.setPointerCapture(e.pointerId); } catch (err) { /* 놓쳐도 끌기는 된다 */ }
    tip.classList.remove('show');
    stage.style.cursor = 'grabbing';
    e.preventDefault();
  });

  // 손을 떼면 브라우저가 같은 자리에 click 을 한 번 더 보낸다. 그 사이에 정보 창이 떠 있으면
  // click 이 창 바깥(배경)에 떨어져 창이 뜨자마자 닫힌다 — 모바일에서 화면 가장자리 쪽 메뉴가
  // "눌러도 안 뜨던" 까닭. 우리가 누르기를 처리한 직후의 click 하나는 삼킨다.
  let swallow = 0;
  window.addEventListener('click', e => {
    if (performance.now() > swallow) return;
    swallow = 0;
    e.stopPropagation();
    e.preventDefault();
  }, true);

  const release = e => {
    if (down && e.pointerId !== down.id) return;
    const was = down, tapped = was && !was.moved && e.type === 'pointerup';
    if (turn.on) {
      // 멈췄다가 놓았거나 그냥 눌렀다 뗀 것이면 더 돌지 않는다
      if (tapped || performance.now() - turn.at > 90) turn.v = 0;
      turn.v = clamp(turn.v, -24, 24);
      turn.rest = 0;
    }
    drag = null; down = null; turn.on = false;
    if (e.pointerType === 'touch') { pointer.inside = false; setHover(null); }
    else { hovered = undefined; setHover(pick()); }
    if (tapped) {
      swallow = performance.now() + 500;
      onPick(was.key);                               // 끌지 않고 뗐으면 누른 것
    }
  };
  stage.addEventListener('pointerup', release);
  stage.addEventListener('pointercancel', release);
  stage.addEventListener('pointerleave', () => { if (!drag && !turn.on) { pointer.inside = false; setHover(null); } });

  // ── 물리: 원끼리 부딪히고 밀어낸다 ──
  let ouch = 0;
  function bump(a, b, x, y, power) {
    let fresh = false;                       // 방금 부딪힌 것끼리 계속 닿아 있을 때는 효과를 다시 내지 않는다
    for (const it of [a, b]) {
      if (!it || it.cool > 0) continue;
      it.punch = 1; it.cool = 0.35;
      it.spinTo += (Math.random() < 0.5 ? -1 : 1) * TAU;
      fresh = true;
    }
    if (fresh) burst(x, y, power, b ? 0.09 + Math.random() * 0.5 : 0.56);
  }
  function step(h) {
    for (const it of items) {
      if (it === drag) {                         // 손을 따라온다 (빠르게 끌면 그 속도로 남을 밀친다)
        it.vx = clamp((grab.x - it.x) * 18, -45, 45);
        it.vy = clamp((grab.y - it.y) * 18, -45, 45);
      } else {
        const d = Math.exp(-2.4 * h);            // 밀려난 뒤 스르르 멎는다
        it.vx *= d; it.vy *= d;
      }
      it.x += it.vx * h; it.y += it.vy * h;
    }
    // 메뉴끼리
    for (let i = 0; i < items.length; i++) {
      for (let j = i + 1; j < items.length; j++) {
        const a = items[i], b = items[j];
        const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || 1e-4, min = a.r + b.r;
        if (d >= min) continue;
        const nx = dx / d, ny = dy / d, wa = a === drag ? 0 : 1, wb = b === drag ? 0 : 1;
        if (!(wa + wb)) continue;
        const push = (min - d) / (wa + wb);
        a.x -= nx * push * wa; a.y -= ny * push * wa;
        b.x += nx * push * wb; b.y += ny * push * wb;
        const rel = (b.vx - a.vx) * nx + (b.vy - a.vy) * ny;
        if (rel < 0) {
          const jn = -(1.6) * rel / (wa + wb);
          a.vx -= jn * wa * nx; a.vy -= jn * wa * ny;
          b.vx += jn * wb * nx; b.vy += jn * wb * ny;
          if (-rel > 1.4) bump(a, b, a.x + nx * a.r, a.y + ny * a.r, -rel);
        }
      }
    }
    // 곽봇 (움직이지 않는 장애물)
    for (const it of items) {
      for (const c of bot.colliders) {
        const cx = c.x * botScale, cy = c.y * botScale, R = c.r * botScale;
        const dx = it.x - cx, dy = it.y - cy, d = Math.hypot(dx, dy) || 1e-4, min = it.r + R;
        if (d >= min) continue;
        const nx = dx / d, ny = dy / d;
        it.x = cx + nx * min; it.y = cy + ny * min;
        const vn = it.vx * nx + it.vy * ny;
        if (vn < 0) {
          if (it !== drag) { it.vx -= 1.55 * vn * nx; it.vy -= 1.55 * vn * ny; }
          if (-vn > 1.4 && it.cool <= 0) { bump(it, null, cx + nx * R, cy + ny * R, -vn); ouch = 0.8; }
        }
      }
    }
    // 화면 가장자리
    for (const it of items) {
      if (it !== drag) {
        const sp = Math.hypot(it.vx, it.vy);
        if (sp > 9) { it.vx *= 9 / sp; it.vy *= 9 / sp; }   // 세게 쳐도 화면 끝까지 날아가지 않게
      }
      const x0 = bounds.x0 + it.r, x1 = bounds.x1 - it.r, y0 = bounds.y0 + it.r, y1 = bounds.y1 - it.r;
      if (it.x < x0) { it.x = x0; if (it.vx < 0) it.vx *= -0.55; }
      if (it.x > x1) { it.x = x1; if (it.vx > 0) it.vx *= -0.55; }
      if (it.y < y0) { it.y = y0; if (it.vy < 0) it.vy *= -0.55; }
      if (it.y > y1) { it.y = y1; if (it.vy > 0) it.vy *= -0.55; }
    }
  }

  new ResizeObserver(layout).observe(stage);
  layout();

  // ── 움직임 ──
  const clock = new THREE.Clock();
  const still = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
  let t = 0, life = 0, camX = 0, camY = 0, headY = 0, headX = 0, botHover = 0, wave = 0, nextWave = 1.2;

  function frame() {
    requestAnimationFrame(frame);
    if (!isActive() || !placed) { clock.getDelta(); return; }
    const raw = clock.getDelta();
    const dt = Math.min(raw, 0.05);
    t += dt * (still ? 0.3 : 1);
    life += Math.min(raw, 0.3);     // 등장 연출은 실제 흐른 시간으로 (느린 기기에서도 제때 끝나게)

    step(dt / 2); step(dt / 2);

    // 시선: 마우스 쪽으로 카메라와 머리가 살짝 따라간다 (끄는 동안은 화면이 흔들리지 않게 멈춘다)
    const tx = pointer.inside ? pointer.x : 0, ty = pointer.inside ? pointer.y : 0;
    const held = drag || turn.on;
    if (!held) { camX = lerp(camX, tx * 1.1, 0.04); camY = lerp(camY, ty * 0.6, 0.04); }
    camera.position.set(camX, 0.4 + camY, CAM_Z);
    camera.lookAt(0, centerY * 0.5, 0);

    // 곽봇 돌리기: 놓으면 돌던 힘으로 더 돌다가 멎고, 잠시 뒤 스르르 앞을 본다
    if (!turn.on) {
      turn.yaw += turn.v * dt;
      turn.v *= Math.exp(-1.7 * dt);
      turn.pitch = lerp(turn.pitch, 0, 1 - Math.exp(-5 * dt));
      if (Math.abs(turn.v) < 0.4) {
        turn.rest += dt;
        if (turn.rest > 2.5) {
          const front = Math.round(turn.yaw / TAU) * TAU;
          turn.yaw = lerp(turn.yaw, front, 1 - Math.exp(-3.2 * dt));
          if (Math.abs(turn.yaw - front) < 1e-3) turn.yaw = 0;
        }
      } else turn.rest = 0;
    }
    const facing = turn.on ? 0 : Math.max(0, Math.cos(turn.yaw));   // 등을 보일 때는 마우스를 따라 고개를 돌리지 않는다
    headY = lerp(headY, tx * 0.45 * facing, 0.07);
    headX = lerp(headX, -ty * 0.24 * facing, 0.07);

    // 우주: 별이 반짝이고 아주 천천히 돈다
    stars.material.uniforms.uTime.value = t;
    space.rotation.z = t * 0.004;
    for (const f of flares) {
      const k = 0.75 + 0.25 * Math.sin(t * 0.9 + f.userData.p);
      f.scale.setScalar(f.userData.s * k);
      f.material.opacity = 0.3 + 0.4 * k;
    }
    shoot.next -= dt;
    if (shoot.next <= 0 && !streak.visible) {
      const x = (Math.random() * 2 - 1) * 26, y = 6 + Math.random() * 12, dx = (Math.random() < 0.5 ? -1 : 1) * (14 + Math.random() * 10);
      shoot.from.set(x, y, -42); shoot.to.set(x + dx, y - 7 - Math.random() * 5, -42);
      shoot.t = 0; streak.visible = true;
      streak.rotation.z = Math.atan2(shoot.to.y - shoot.from.y, shoot.to.x - shoot.from.x);
    }
    if (streak.visible) {
      shoot.t += dt / shoot.dur;
      streak.position.lerpVectors(shoot.from, shoot.to, shoot.t);
      streak.scale.set(7 * Math.sin(Math.min(1, shoot.t) * Math.PI) + 0.01, 0.09, 1);
      streak.material.opacity = Math.sin(Math.min(1, shoot.t) * Math.PI);
      if (shoot.t >= 1) { streak.visible = false; shoot.next = 6 + Math.random() * 9; }
    }

    // 곽봇: 둥실둥실, 가끔 손 흔들기, 부딪히면 움찔
    const intro = clamp(life / 0.9, 0, 1);
    botHover = lerp(botHover, hovered === 'bot' ? 1 : 0, 0.12);
    ouch = Math.max(0, ouch - dt);
    const dizzy = Math.abs(turn.v) > 11;        // 빙글빙글 세게 돌리면 어지럽다
    bot.setMood(ouch > 0 || dizzy ? 'ouch' : hovered === 'bot' || turn.on ? 'excited' : 'happy');
    nextWave -= dt;
    if (nextWave <= 0) { wave = 1; nextWave = 4.5 + Math.random() * 3; }
    wave = Math.max(hovered === 'bot' ? 1 : 0, wave - dt / 2.2);
    const waving = Math.min(1, wave * 3);
    const bob = Math.sin(t * 1.4) * 0.14;
    const shake = ouch > 0 ? Math.sin(ouch * 40) * 0.05 * ouch : 0;
    rig.position.set(shake * botScale, bob * botScale, 0);
    rig.scale.setScalar(botScale * easeOutBack(intro) * (1 + botHover * 0.05));
    bot.root.rotation.set(Math.sin(t * 0.7) * 0.03 + turn.pitch, Math.sin(t * 0.5) * 0.22 + headY * 0.4 + turn.yaw,
                          Math.sin(t * 0.9) * 0.035 + shake);
    bot.head.rotation.set(headX + Math.sin(t * 1.3) * 0.02, headY, Math.sin(t * 1.1) * 0.04);
    bot.armR.rotation.z = lerp(0.5, 2.3, waving) + Math.sin(t * (7 + botHover * 3)) * 0.26 * waving + Math.sin(t * 1.5) * 0.05;
    bot.armR.rotation.x = -0.25 * waving;
    bot.armL.rotation.z = -0.45 + Math.sin(t * 1.5 + 1) * 0.08;
    bot.armL.rotation.x = Math.sin(t * 1.2) * 0.1;
    bot.tail.rotation.set(0, Math.sin(t * 2.2) * 0.18, Math.sin(t * 1.7) * 0.08);
    bot.horns.forEach((h, i) => { h.rotation.x = Math.sin(t * 2.6 + i * 1.3) * 0.05; });
    bot.faceMat.emissiveIntensity = 1.6 + Math.sin(t * 2.4) * 0.18;
    bot.flames.forEach((f, i) => {
      const k = 0.85 + 0.25 * Math.sin(t * 31 + i * 2.1) * Math.sin(t * 17 + i) - bob * 0.9;
      f.scale.set(1, k, 1);
      f.position.y = f.userData.y0 - 0.31 * (k - 1);
    });
    ring.rotation.set(1.3, 0, t * 0.4);
    ring2.rotation.set(1.46, 0.35, -t * 0.25);

    // 메뉴들: 제자리에서 둥실거리고, 끌면 들려 올라온다
    for (let i = 0; i < items.length; i++) {
      const it = items[i], p = it.phase, held = it === drag ? 1 : 0;
      it.appear = clamp((life - 0.25 - i * 0.09) / 0.6, 0, 1);
      it.hover = lerp(it.hover, hovered === it.key || held ? 1 : 0, 0.14);
      it.lift = lerp(it.lift, held, 0.18);
      it.spin = lerp(it.spin, it.spinTo, 0.07);
      it.cool = Math.max(0, it.cool - dt);
      it.punch = Math.max(0, it.punch - dt * 2.4);
      const k = it.size * 0.07 * (1 - it.lift), spread = lerp(0.2, 1, easeOutBack(it.appear));
      it.obj.position.set(it.x * spread + Math.sin(t * 0.7 + p) * k * 1.6,
                          it.y * spread + Math.sin(t * 1.1 + p * 1.3) * k * 2.4,
                          it.z + Math.cos(t * 0.6 + p) * 0.25 * (1 - it.lift) + it.lift * 1.1);
      const squash = 1 + 0.24 * it.punch * Math.sin(it.punch * 15);
      it.obj.scale.setScalar(Math.max(1e-4, it.size * easeOutBack(it.appear) * (1 + it.hover * 0.16) * squash));
      it.obj.rotation.set(Math.sin(t * 0.5 + p * 2) * 0.13 + clamp(it.vy * 0.03, -0.5, 0.5),
                          Math.sin(t * 0.7 + p) * 0.42 * (1 - it.lift) + it.spin,
                          Math.sin(t * 0.6 + p * 3) * 0.07 - clamp(it.vx * 0.03, -0.5, 0.5));
    }

    // 불티와 고리
    for (const sp of sparks) {
      if (sp.life <= 0) continue;
      sp.life -= dt * 2.1;
      sp.s.position.x += sp.vx * dt; sp.s.position.y += sp.vy * dt;
      sp.vx *= 0.94; sp.vy *= 0.94;
      sp.s.scale.setScalar(0.26 * Math.max(0, sp.life));
      sp.s.material.opacity = Math.max(0, sp.life);
      if (sp.life <= 0) sp.s.visible = false;
    }
    for (const sh of shocks) {
      if (sh.life <= 0) continue;
      sh.life -= dt * 2.6;
      sh.m.scale.setScalar(sh.size * (0.25 + (1 - Math.max(0, sh.life)) * 1.3));
      sh.m.material.opacity = Math.max(0, sh.life) * 0.6;
      if (sh.life <= 0) sh.m.visible = false;
    }

    // 먼지는 천천히 위로
    const pos = dustGeo.attributes.position;
    for (let i = 0; i < N; i++) {
      let y = pos.getY(i) + speed[i] * dt;
      if (y > 5.2) y = -5.2;
      pos.setY(i, y);
    }
    pos.needsUpdate = true;

    // 이름표를 가리키는 것 위에 붙인다
    if (hovered && !held) {
      const it = items.find(x => x.key === hovered);
      const [sx, sy] = toScreen(it ? it.obj : bot.root);
      const lift = (it ? it.size * 0.7 : bot.height * 0.52 * botScale) * pxPerUnit();
      tip.style.transform = `translate(-50%, -100%) translate(${sx.toFixed(1)}px, ${(sy - lift).toFixed(1)}px)`;
    }

    composer.render();
  }
  frame();
}
