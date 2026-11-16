// 3D 캠퍼스 지도.
//
// 학교 일러스트 지도를 두께가 있는 판 위에 올린 디오라마다. 건물 자리마다 일러스트를 살짝
// 돋워 올려 기울여 볼 때 입체감이 나게 하고, 그 위에 번호 핀을 세운다.
// 끌면 이동, 휠·핀치로 확대, 오른쪽 버튼(또는 두 손가락)으로 돌려 본다.
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const W = 10;                         // 지도 판의 가로 길이 (세로는 그림 비율대로)
const PIN_H = 0.34;
const ease = t => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

function numberTexture(text) {
  const c = document.createElement('canvas');
  c.width = c.height = 96;
  const x = c.getContext('2d');
  x.font = `800 ${text.length > 1 ? 50 : 58}px -apple-system, "Segoe UI", sans-serif`;
  x.textAlign = 'center';
  x.textBaseline = 'middle';
  x.fillStyle = '#fff';
  x.fillText(text, 48, 51);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return t;
}

function labelTexture(text) {
  const c = document.createElement('canvas');
  const x = c.getContext('2d');
  const font = '700 40px -apple-system, "Malgun Gothic", sans-serif';
  x.font = font;
  const w = Math.ceil(x.measureText(text).width) + 48;
  c.width = w; c.height = 72;
  x.font = font;
  x.fillStyle = 'rgba(20, 28, 46, .92)';
  x.beginPath();
  x.roundRect ? x.roundRect(0, 0, w, 72, 36) : x.rect(0, 0, w, 72);
  x.fill();
  x.fillStyle = '#fff';
  x.textAlign = 'center';
  x.textBaseline = 'middle';
  x.fillText(text, w / 2, 38);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  return { tex: t, aspect: w / 72 };
}

/**
 * @param host    캔버스를 넣을 요소
 * @param map     campus_buildings.json ({image, width, height, buildings:[{num,name,x,y}]})
 * @param onPick  건물 핀을 눌렀을 때 (building) => void
 * @param onHover 핀 위에 올렸을 때 (building | null, 화면 x, y) => void
 * @returns Promise — 일러스트를 못 불러오면 거부된다 (호출한 쪽이 평면 지도로 돌아간다)
 */
export function createMap3D({ host, map, onPick, onHover }) {
  return new Promise((resolve, reject) => {
    const D = W * map.height / map.width;
    new THREE.TextureLoader().setCrossOrigin('anonymous').load(
      // 평면 지도의 <img> 가 CORS 없이 캐시해 둔 응답을 다시 쓰지 않도록 주소를 구분한다
      map.image + (map.image.includes('?') ? '&' : '?') + 'gl=1',
      tex => resolve(build(tex, D)),
      undefined,
      () => reject(new Error('지도 그림을 불러오지 못했습니다')));

    function build(tex, D) {
      const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      renderer.outputColorSpace = THREE.SRGBColorSpace;
      renderer.shadowMap.enabled = true;
      renderer.shadowMap.type = THREE.PCFSoftShadowMap;
      host.prepend(renderer.domElement);

      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(38, 1.6, 0.1, 80);

      // 빛: 그림 본래 색이 거의 그대로 나오게 맞추고, 그림자만 살짝 진다
      scene.add(new THREE.AmbientLight(0xffffff, 2.05));
      const sun = new THREE.DirectionalLight(0xfff4e0, 1.55);
      sun.position.set(-5, 9, 5);
      sun.castShadow = true;
      sun.shadow.mapSize.set(2048, 2048);
      Object.assign(sun.shadow.camera, { left: -8, right: 8, top: 8, bottom: -8, near: 1, far: 30 });
      sun.shadow.bias = -0.0004;
      sun.shadow.normalBias = 0.02;
      sun.shadow.radius = 4;
      scene.add(sun);

      // ── 지도 판 ──
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.anisotropy = renderer.capabilities.getMaxAnisotropy();
      const toWorld = b => new THREE.Vector3((b.x / map.width - 0.5) * W, 0, (b.y / map.height - 0.5) * D);

      // 건물 자리를 살짝 돋운다. 그림이 남쪽에서 비스듬히 내려다본 구도라, 봉긋 솟은 면에
      // 건물 벽이 얹혀 기울여 볼 때 깊이가 생긴다 (정확한 건물 모양은 아니고 양감만 준다).
      const SEG_X = 220, SEG_Y = Math.round(220 * D / W);
      const ground = new THREE.PlaneGeometry(W, D, SEG_X, SEG_Y);
      ground.rotateX(-Math.PI / 2);
      const pos = ground.attributes.position;
      const spots = map.buildings.map(toWorld);
      const SIGMA = 0.2, BUMP = 0.13;
      const heightAt = (x, z) => {
        let h = 0;
        for (const s of spots) {
          const d2 = (x - s.x) ** 2 + ((z - s.z) * 1.25) ** 2;
          if (d2 < 0.5) h = Math.max(h, Math.exp(-d2 / (2 * SIGMA * SIGMA)));
        }
        // 가장자리는 판 옆면과 맞닿도록 평평하게
        const edge = Math.min(W / 2 - Math.abs(x), D / 2 - Math.abs(z));
        return h * BUMP * clamp(edge / 0.4, 0, 1);
      };
      for (let i = 0; i < pos.count; i++) pos.setY(i, heightAt(pos.getX(i), pos.getZ(i)));
      ground.computeVertexNormals();
      const top = new THREE.Mesh(ground, new THREE.MeshStandardMaterial({ map: tex, roughness: 1, metalness: 0 }));
      top.receiveShadow = true;
      scene.add(top);

      const soil = new THREE.MeshStandardMaterial({ color: 0x8b6b4a, roughness: 1 });
      const soilDark = new THREE.MeshStandardMaterial({ color: 0x5d4632, roughness: 1 });
      const slab = new THREE.Mesh(new THREE.BoxGeometry(W, 0.34, D), [soil, soil, soil, soilDark, soil, soil]);
      slab.position.y = -0.172;
      slab.receiveShadow = true;
      scene.add(slab);
      const grass = new THREE.Mesh(new THREE.BoxGeometry(W + 0.01, 0.05, D + 0.01),
                                   new THREE.MeshStandardMaterial({ color: 0x86b56a, roughness: 1 }));
      grass.position.y = -0.027;
      scene.add(grass);
      const stand = new THREE.Mesh(new THREE.BoxGeometry(W + 0.5, 0.12, D + 0.5),
                                   new THREE.MeshStandardMaterial({ color: 0x2c3447, roughness: 0.6 }));
      stand.position.y = -0.4;
      stand.receiveShadow = true;
      scene.add(stand);

      // ── 핀 ──
      const headGeo = new THREE.SphereGeometry(0.115, 28, 20);
      const stemGeo = new THREE.ConeGeometry(0.045, PIN_H, 14);
      stemGeo.rotateX(Math.PI);
      const red = new THREE.MeshStandardMaterial({ color: 0xea3f52, roughness: 0.28 });
      const blue = new THREE.MeshStandardMaterial({ color: 0x1f6feb, roughness: 0.28 });
      const pins = map.buildings.map(b => {
        const g = new THREE.Group();
        const p = toWorld(b);
        g.position.set(p.x, heightAt(p.x, p.z), p.z);
        const stem = new THREE.Mesh(stemGeo, red);
        stem.position.y = PIN_H / 2;
        const head = new THREE.Mesh(headGeo, red);
        head.position.y = PIN_H + 0.07;
        head.castShadow = stem.castShadow = true;
        const num = new THREE.Sprite(new THREE.SpriteMaterial({ map: numberTexture(String(b.num)), depthWrite: false }));
        num.scale.setScalar(0.19);
        g.add(stem, head, num);
        head.userData.pin = g;
        g.userData = { b, head, stem, num, mark: 0, hover: 0, label: null, pulse: null };
        scene.add(g);
        return g;
      });
      const heads = pins.map(g => g.userData.head);

      // ── 구름 (멀리서 볼 때만 보이고, 다가가면 걷힌다) ──
      const cloudMat = new THREE.MeshStandardMaterial({ color: 0xffffff, emissive: 0x8c97a8, roughness: 1,
                                                        transparent: true, opacity: 0.8, depthWrite: false });
      const puff = new THREE.SphereGeometry(0.3, 16, 12);
      // 앞쪽 건물을 가리지 않게 지도 뒤편 하늘에만 띄운다
      const clouds = [[-3.8, 1.7, -3.1, 1.2], [3.0, 2.0, -3.6, 0.95], [0.3, 2.3, -4.0, 1.05], [-6.2, 1.9, -3.4, 0.8]]
        .map(([x, y, z, s], i) => {
          const g = new THREE.Group();
          [[0, 0, 0, 1], [0.34, 0.03, 0.05, 0.8], [-0.34, -0.02, 0, 0.75], [0.1, 0.16, -0.08, 0.7], [-0.14, 0.1, 0.12, 0.6]]
            .forEach(([px, py, pz, ps]) => {
              const m = new THREE.Mesh(puff, cloudMat);
              m.position.set(px, py, pz);
              m.scale.set(ps * 1.25, ps * 0.8, ps);
              m.castShadow = true;
              g.add(m);
            });
          g.position.set(x, y, z);
          g.scale.setScalar(s);
          g.userData.speed = 0.05 + i * 0.012;
          scene.add(g);
          return g;
        });

      // ── 조작 ──
      const controls = new OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      controls.dampingFactor = 0.09;
      controls.screenSpacePanning = false;
      controls.zoomToCursor = true;
      controls.minDistance = 2.8;
      controls.maxDistance = 26;
      controls.minPolarAngle = 0.12;
      controls.maxPolarAngle = 1.2;
      // 그림이 남쪽에서 본 구도라, 너무 돌리면 건물이 누워 보인다
      controls.minAzimuthAngle = -1.0;
      controls.maxAzimuthAngle = 1.0;
      controls.mouseButtons = { LEFT: THREE.MOUSE.PAN, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.ROTATE };
      controls.touches = { ONE: THREE.TOUCH.PAN, TWO: THREE.TOUCH.DOLLY_ROTATE };

      // 처음 시점: 지도 전체가 화면에 들어오도록, 세로로 긴 화면일수록 더 물러선다
      const HOME = {
        target: new THREE.Vector3(0, 0, 0.5),
        get pos() {
          const f = Math.max(1, 1.9 / camera.aspect);
          return new THREE.Vector3(0, 7.3 * f, 9.3 * f + 0.5);
        },
      };
      let fly = null;
      function flyTo(target, position, seconds = 0.9) {
        fly = { t: 0, dur: seconds, t0: controls.target.clone(), p0: camera.position.clone(),
                t1: target.clone(), p1: position.clone() };
      }
      // 지금 보는 방향·거리를 유지한 채 중심만 옮긴다
      function focus(point, distance) {
        const offset = camera.position.clone().sub(controls.target);
        if (distance) offset.setLength(distance);
        flyTo(point, point.clone().add(offset));
      }

      // ── 핀 고르기 ──
      const ray = new THREE.Raycaster(), ndc = new THREE.Vector2();
      let hovered = null, downAt = null;
      const pinAt = e => {
        const r = renderer.domElement.getBoundingClientRect();
        ndc.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
        ray.setFromCamera(ndc, camera);
        const hit = ray.intersectObjects(heads, false)[0];
        return hit ? hit.object.userData.pin : null;
      };
      const el = renderer.domElement;
      el.addEventListener('pointermove', e => {
        if (e.pointerType === 'touch') return;
        hovered = pinAt(e);
        el.style.cursor = hovered ? 'pointer' : '';
        const r = host.getBoundingClientRect();
        onHover?.(hovered ? hovered.userData.b : null, e.clientX - r.left, e.clientY - r.top);
      });
      el.addEventListener('pointerleave', () => { hovered = null; onHover?.(null, 0, 0); });
      el.addEventListener('pointerdown', e => { downAt = [e.clientX, e.clientY]; fly = null; });
      el.addEventListener('pointerup', e => {
        if (!downAt || Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]) > 6) return;   // 끌기였다
        const pin = pinAt(e);
        if (!pin) return;
        onPick?.(pin.userData.b);
        focus(pin.position.clone().setY(0), Math.min(camera.position.distanceTo(controls.target), 6.5));
      });
      el.addEventListener('contextmenu', e => e.preventDefault());

      // ── 표시할 건물 (챗봇 답변에서 넘어온 경우) ──
      function setMarks(list) {
        const nums = new Set((list || []).map(b => b.num));
        for (const g of pins) {
          const u = g.userData, on = nums.has(u.b.num);
          u.mark = on ? 1 : 0;
          u.head.material = u.stem.material = on ? blue : red;
          if (u.label) { g.remove(u.label); u.label.material.map.dispose(); u.label = null; }
          if (u.pulse) { g.remove(u.pulse); u.pulse = null; }
          if (on) {
            const { tex: lt, aspect } = labelTexture(u.b.name);
            u.label = new THREE.Sprite(new THREE.SpriteMaterial({ map: lt, depthTest: false }));
            u.label.scale.set(0.22 * aspect, 0.22, 1);
            u.label.position.y = PIN_H + 0.42;
            u.label.renderOrder = 5;
            u.pulse = new THREE.Mesh(new THREE.RingGeometry(0.16, 0.2, 40),
              new THREE.MeshBasicMaterial({ color: 0x1f6feb, transparent: true, depthWrite: false }));
            u.pulse.rotation.x = -Math.PI / 2;
            u.pulse.position.y = 0.02;
            g.add(u.label, u.pulse);
          }
        }
        return pins.filter(g => g.userData.mark);
      }

      // ── 그리기 ──
      const clock = new THREE.Clock();
      const toCam = new THREE.Vector3();
      let running = false, t = 0;

      function resize() {
        const w = host.clientWidth || 1, h = host.clientHeight || 1;
        renderer.setSize(w, h, false);
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
      }
      new ResizeObserver(resize).observe(host);

      function frame() {
        if (!running) return;
        requestAnimationFrame(frame);
        const dt = Math.min(clock.getDelta(), 0.1);
        t += dt;

        if (fly) {
          fly.t = Math.min(1, fly.t + dt / fly.dur);
          const k = ease(fly.t);
          controls.target.lerpVectors(fly.t0, fly.t1, k);
          camera.position.lerpVectors(fly.p0, fly.p1, k);
          if (fly.t >= 1) fly = null;
        }
        controls.update();
        // 지도 밖으로 끌려 나가지 않게
        controls.target.x = clamp(controls.target.x, -W / 2, W / 2);
        controls.target.z = clamp(controls.target.z, -D / 2, D / 2);
        controls.target.y = 0;

        const dist = camera.position.distanceTo(controls.target);
        for (const g of pins) {
          const u = g.userData;
          u.hover += ((hovered === g ? 1 : 0) - u.hover) * 0.2;
          const bounce = u.mark ? Math.abs(Math.sin(t * 3.2)) * 0.12 : 0;
          g.scale.setScalar((1 + u.hover * 0.35 + u.mark * 0.3) * clamp(dist / 8, 0.62, 1.15));
          u.head.position.y = PIN_H + 0.07 + bounce;
          // 번호는 구슬 앞면에 붙어 보이도록 카메라 쪽으로 살짝 내민다
          toCam.copy(camera.position).sub(g.position).normalize();
          u.num.position.set(toCam.x * 0.125, u.head.position.y + toCam.y * 0.125, toCam.z * 0.125);
          if (u.pulse) {
            const k = (t * 0.9) % 1;
            u.pulse.scale.setScalar(1 + k * 2.2);
            u.pulse.material.opacity = (1 - k) * 0.8;
          }
        }
        cloudMat.opacity = clamp((dist - 6.5) / 4, 0, 1) * 0.85;
        for (const c of clouds) {
          c.visible = cloudMat.opacity > 0.01;
          c.position.x += c.userData.speed * dt;
          if (c.position.x > W / 2 + 1.5) c.position.x = -W / 2 - 1.5;
        }
        renderer.render(scene, camera);
      }

      return {
        /** 지도 창이 열릴 때. marks 가 있으면 그 건물들로 날아간다 */
        open(marks) {
          resize();
          const marked = setMarks(marks);
          // 위에서 내려다보다가 비스듬한 시점으로 내려앉는다
          camera.position.set(0, 15, 0.5);
          controls.target.copy(HOME.target);
          if (marked.length) {
            const c = marked.reduce((a, g) => a.add(g.position), new THREE.Vector3()).multiplyScalar(1 / marked.length).setY(0);
            flyTo(c, c.clone().add(new THREE.Vector3(0, 4.3, 5.5)), 1.5);
          } else {
            flyTo(HOME.target, HOME.pos, 1.4);
          }
          if (!running) { running = true; clock.getDelta(); frame(); }
        },
        close() { running = false; },
        zoom(factor) {
          const offset = camera.position.clone().sub(controls.target);
          offset.setLength(clamp(offset.length() * factor, controls.minDistance, controls.maxDistance));
          flyTo(controls.target, controls.target.clone().add(offset), 0.35);
        },
        rotate(angle) {
          const offset = camera.position.clone().sub(controls.target);
          const az = clamp(Math.atan2(offset.x, offset.z) + angle, controls.minAzimuthAngle, controls.maxAzimuthAngle);
          const flat = Math.hypot(offset.x, offset.z);
          offset.set(Math.sin(az) * flat, offset.y, Math.cos(az) * flat);
          flyTo(controls.target, controls.target.clone().add(offset), 0.45);
        },
        reset() { flyTo(HOME.target, HOME.pos, 0.8); },
      };
    }
  });
}
