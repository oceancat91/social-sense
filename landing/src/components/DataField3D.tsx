"use client";

import { useEffect, useRef } from "react";
import * as THREE from "three";

const PLATFORMS = ["微博", "抖音", "B站", "小红书", "知乎", "快手"];

const NODE_DATA = [
  { lat: 28, lon: -48, weight: 0.92 },
  { lat: -18, lon: -70, weight: 0.78 },
  { lat: 52, lon: 18, weight: 0.7 },
  { lat: -36, lon: 18, weight: 0.62 },
  { lat: 10, lon: 72, weight: 0.55 },
  { lat: 42, lon: 118, weight: 0.48 },
];

const ARC_PAIRS: [number, number][] = [
  [0, 1],
  [0, 2],
  [1, 3],
  [2, 4],
  [3, 5],
  [4, 5],
  [1, 4],
];

const FLOW_PER_ARC = 16;
const SPHERE_RADIUS = 1.62;
const FIELD_SCALE = 1.12;

/** 经纬规密度：纬度圈 + 经线数。刻意稀疏，追求仪器刻度般的克制。 */
const GRATICULE_LATITUDES = [-54, -27, 0, 27, 54];
const GRATICULE_MERIDIANS = 6;
const RING_SEGMENTS = 128;

/** 表面点阵密度：与经纬规同源，落在规则网格交叉处。 */
const LATTICE_LAT_STEP = 12;
const LATTICE_LON_STEP = 12;

const C_SOUTH = new THREE.Color(0x1d4ed8);
const C_NORTH = new THREE.Color(0x9dc4fb);
const C_ARC_HEAD = new THREE.Color(0x1d4ed8);
const C_ARC_TAIL = new THREE.Color(0x93c5fd);
const FOG_COLOR = 0xeff3fa;

function pointOnSphere(lat: number, lon: number, radius: number) {
  const phi = THREE.MathUtils.degToRad(90 - lat);
  const theta = THREE.MathUtils.degToRad(lon + 180);
  return new THREE.Vector3(
    -radius * Math.sin(phi) * Math.cos(theta),
    radius * Math.cos(phi),
    radius * Math.sin(phi) * Math.sin(theta),
  );
}

/**
 * 柔和径向渐变贴图。多段 stop 保证中心到边缘过渡无硬边，
 * 供点云、辉光、数据流粒子复用，全局只需一张纹理。
 */
function makeGlowTexture(): THREE.CanvasTexture {
  const size = 128;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  const gradient = ctx.createRadialGradient(
    size / 2,
    size / 2,
    0,
    size / 2,
    size / 2,
    size / 2,
  );
  gradient.addColorStop(0, "rgba(255,255,255,1)");
  gradient.addColorStop(0.14, "rgba(255,255,255,0.92)");
  gradient.addColorStop(0.32, "rgba(255,255,255,0.5)");
  gradient.addColorStop(0.55, "rgba(255,255,255,0.18)");
  gradient.addColorStop(0.78, "rgba(255,255,255,0.045)");
  gradient.addColorStop(1, "rgba(255,255,255,0)");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, size, size);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

/**
 * 写入 4 分量顶点色（RGB + A）。
 * Three.js 在 color 属性 itemSize 为 4 时启用 USE_COLOR_ALPHA，
 * 让线条 / 点云可以沿自身渐隐，比材质级统一 opacity 精细得多。
 */
function setVertexColors(
  geometry: THREE.BufferGeometry,
  colorFn: (point: THREE.Vector3, t: number) => [number, number, number, number],
) {
  const position = geometry.getAttribute("position");
  const colors: number[] = [];
  const vertex = new THREE.Vector3();
  for (let i = 0; i < position.count; i += 1) {
    vertex.fromBufferAttribute(position, i);
    const t = position.count > 1 ? i / (position.count - 1) : 0;
    const [r, g, b, a] = colorFn(vertex, t);
    colors.push(r, g, b, a);
  }
  geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 4));
}

/** 按纬度插值冷蓝到浅冰蓝，并按比例给出透明度。 */
function shadeByLatitude(y: number, alphaBase: number, alphaRange: number) {
  const t = THREE.MathUtils.clamp((y / SPHERE_RADIUS + 1) / 2, 0, 1);
  const color = C_SOUTH.clone().lerp(C_NORTH, t);
  return [color.r, color.g, color.b, alphaBase + alphaRange * t] as [
    number,
    number,
    number,
    number,
  ];
}

interface FlowSystem {
  points: THREE.Points;
  positions: Float32Array;
  attribute: THREE.BufferAttribute;
  curve: THREE.QuadraticBezierCurve3;
  phase: number;
  speed: number;
}

/**
 * 六平台 3D 数据场。
 *
 * 视觉语言：精密数据仪器，不是"线框地球"。
 * 球体由经纬规（gratiule）构成，弧线是带渐隐端点的共振链路，
 * 光点沿链路循环流动表示跨平台数据在共振关系中持续传递。
 *
 * 深度：线性雾把远半球柔化进页面底色，近处清晰，形成真实体积感。
 * Three.js 隔离在该 Client 叶组件内，卸载时完整释放 GPU 资源。
 */
export default function DataField3D() {
  const hostRef = useRef<HTMLDivElement>(null);
  const labelRefs = useRef<(HTMLSpanElement | null)[]>([]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;

    const reduceMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;
    const scene = new THREE.Scene();
    scene.fog = new THREE.Fog(FOG_COLOR, 7.0, 13.5);

    const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 100);
    camera.position.set(0, 0.12, 7.6);

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({
        alpha: true,
        antialias: true,
        powerPreference: "high-performance",
      });
    } catch {
      host.dataset.webgl = "unavailable";
      return;
    }

    renderer.setClearColor(0x000000, 0);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    host.prepend(renderer.domElement);

    const glowTexture = makeGlowTexture();

    const field = new THREE.Group();
    field.rotation.set(-0.1, -0.45, 0.06);
    field.scale.setScalar(FIELD_SCALE);
    scene.add(field);

    /* ---------- 背光：冷蓝外扩氛围，无白色实心底 ---------- */
    const backdropWide = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: glowTexture,
        color: 0xc7dcfa,
        transparent: true,
        opacity: 0.26,
        depthTest: false,
        depthWrite: false,
      }),
    );
    backdropWide.scale.setScalar(6.4);
    backdropWide.renderOrder = -21;
    scene.add(backdropWide);

    /* ---------- 球体本身：极淡的乳白壳 ---------- */
    const shell = new THREE.Mesh(
      new THREE.SphereGeometry(SPHERE_RADIUS * 0.995, 48, 48),
      new THREE.MeshBasicMaterial({
        color: 0xc3dafb,
        transparent: true,
        opacity: 0.07,
        depthWrite: false,
      }),
    );
    field.add(shell);

    /* ---------- 经纬规：替代线框球，仪器刻度语言 ---------- */
    // 纬度圈
    GRATICULE_LATITUDES.forEach((lat) => {
      const latRad = THREE.MathUtils.degToRad(lat);
      const ringRadius = SPHERE_RADIUS * Math.cos(latRad);
      const y = SPHERE_RADIUS * Math.sin(latRad);
      const points: THREE.Vector3[] = [];
      for (let i = 0; i <= RING_SEGMENTS; i += 1) {
        const theta = (i / RING_SEGMENTS) * Math.PI * 2;
        points.push(
          new THREE.Vector3(
            Math.cos(theta) * ringRadius,
            y,
            Math.sin(theta) * ringRadius,
          ),
        );
      }
      const geometry = new THREE.BufferGeometry().setFromPoints(points);
      setVertexColors(geometry, (point) =>
        shadeByLatitude(point.y, 0.07, 0.1),
      );
      field.add(
        new THREE.LineLoop(
          geometry,
          new THREE.LineBasicMaterial({
            vertexColors: true,
            transparent: true,
            depthWrite: false,
          }),
        ),
      );
    });

    // 经线
    for (let m = 0; m < GRATICULE_MERIDIANS; m += 1) {
      const rotation = (m / GRATICULE_MERIDIANS) * Math.PI;
      const points: THREE.Vector3[] = [];
      for (let i = 0; i <= RING_SEGMENTS; i += 1) {
        const theta = (i / RING_SEGMENTS) * Math.PI * 2;
        const point = new THREE.Vector3(
          Math.sin(theta) * SPHERE_RADIUS,
          Math.cos(theta) * SPHERE_RADIUS,
          0,
        );
        point.applyAxisAngle(new THREE.Vector3(0, 1, 0), rotation);
        points.push(point);
      }
      const geometry = new THREE.BufferGeometry().setFromPoints(points);
      setVertexColors(geometry, (point) =>
        shadeByLatitude(point.y, 0.055, 0.075),
      );
      field.add(
        new THREE.LineLoop(
          geometry,
          new THREE.LineBasicMaterial({
            vertexColors: true,
            transparent: true,
            depthWrite: false,
          }),
        ),
      );
    }

    /* ---------- 悬浮尘埃：拉开景深，填充外层空间 ---------- */
    const dustCount = 200;
    const dustPositions: number[] = [];
    const dustColors: number[] = [];
    for (let i = 0; i < dustCount; i += 1) {
      const radius = 2.45 + Math.random() * 2.3;
      const phi = Math.acos(2 * Math.random() - 1);
      const theta = Math.random() * Math.PI * 2;
      const x = radius * Math.sin(phi) * Math.cos(theta);
      const y = radius * Math.cos(phi);
      const z = radius * Math.sin(phi) * Math.sin(theta);
      dustPositions.push(x, y, z);
      const shade = C_NORTH.clone().lerp(C_SOUTH, Math.random() * 0.6);
      const fade = 1 - (radius - 2.45) / 2.3;
      dustColors.push(
        shade.r,
        shade.g,
        shade.b,
        (0.07 + 0.16 * Math.random()) * fade + 0.025,
      );
    }
    const dustGeometry = new THREE.BufferGeometry();
    dustGeometry.setAttribute(
      "position",
      new THREE.Float32BufferAttribute(dustPositions, 3),
    );
    dustGeometry.setAttribute(
      "color",
      new THREE.Float32BufferAttribute(dustColors, 4),
    );
    const dust = new THREE.Points(
      dustGeometry,
      new THREE.PointsMaterial({
        size: 0.036,
        map: glowTexture,
        vertexColors: true,
        transparent: true,
        depthWrite: false,
      }),
    );
    field.add(dust);

    /* ---------- 表面点阵：经纬网格采样，精密而非随机散布 ---------- */
    // 与经纬规同源对齐：点阵落在经纬交叉的规则网格上，读作被采样的数据面。
    const pointPositions: number[] = [];
    const pointColors: number[] = [];
    for (let lat = -66; lat <= 66; lat += LATTICE_LAT_STEP) {
      const latRad = THREE.MathUtils.degToRad(lat);
      const ringRadius = SPHERE_RADIUS * Math.cos(latRad);
      const y = SPHERE_RADIUS * Math.sin(latRad);
      const polarFade = 1 - Math.abs(lat) / 78;
      for (let lon = -180; lon < 180; lon += LATTICE_LON_STEP) {
        const theta = THREE.MathUtils.degToRad(lon);
        pointPositions.push(
          Math.cos(theta) * ringRadius,
          y,
          Math.sin(theta) * ringRadius,
        );
        const color = C_SOUTH.clone().lerp(C_NORTH, (y / SPHERE_RADIUS + 1) / 2);
        pointColors.push(
          color.r,
          color.g,
          color.b,
          0.16 + 0.24 * polarFade,
        );
      }
    }
    const pointsGeometry = new THREE.BufferGeometry();
    pointsGeometry.setAttribute(
      "position",
      new THREE.Float32BufferAttribute(pointPositions, 3),
    );
    pointsGeometry.setAttribute(
      "color",
      new THREE.Float32BufferAttribute(pointColors, 4),
    );
    const pointCloud = new THREE.Points(
      pointsGeometry,
      new THREE.PointsMaterial({
        size: 0.03,
        map: glowTexture,
        vertexColors: true,
        transparent: true,
        depthWrite: false,
      }),
    );
    field.add(pointCloud);

    /* ---------- 球心氛围：冷蓝柔光，无实心白核 ---------- */
    const coreGlowWide = new THREE.Sprite(
      new THREE.SpriteMaterial({
        map: glowTexture,
        color: 0x6aa5f5,
        transparent: true,
        opacity: 0.16,
        depthWrite: false,
      }),
    );
    coreGlowWide.scale.setScalar(3.4);
    field.add(coreGlowWide);

    /* ---------- 轨道环：三条不同倾角的细环，读作数据轨道 ---------- */
    const haloSpecs = [
      { radius: 1.9, tube: 0.0075, tilt: [Math.PI / 2.7, 0.34, 0] },
      { radius: 2.0, tube: 0.0055, tilt: [Math.PI / 1.9, 0, -0.5] },
      { radius: 2.06, tube: 0.0045, tilt: [Math.PI / 3.6, -0.8, 0.22] },
    ];
    const haloMaterial = new THREE.MeshBasicMaterial({
      color: 0x3b82f6,
      transparent: true,
      opacity: 0.15,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const halos = haloSpecs.map((spec) => {
      const halo = new THREE.Mesh(
        new THREE.TorusGeometry(spec.radius, spec.tube, 6, 220),
        haloMaterial,
      );
      halo.rotation.set(spec.tilt[0], spec.tilt[1], spec.tilt[2]);
      field.add(halo);
      return halo;
    });

    /* ---------- 平台节点：核心 + 朝向外的标记环 + 柔光辉光 ---------- */
    const nodePositions = NODE_DATA.map((node) =>
      pointOnSphere(node.lat, node.lon, SPHERE_RADIUS * 1.025),
    );
    const nodeMeshes: THREE.Mesh[] = [];
    const nodeGlows: THREE.Sprite[] = [];
    const nodeRings: THREE.Mesh[] = [];

    nodePositions.forEach((position, index) => {
      const baseRadius = 0.05 + NODE_DATA[index].weight * 0.038;
      const normal = position.clone().normalize();

      const mesh = new THREE.Mesh(
        new THREE.SphereGeometry(baseRadius, 24, 24),
        new THREE.MeshBasicMaterial({
          color: index < 2 ? 0x1d4ed8 : 0x5b8def,
        }),
      );
      mesh.position.copy(position);
      mesh.userData.baseRadius = baseRadius;
      mesh.userData.phase = index * 0.86;
      field.add(mesh);
      nodeMeshes.push(mesh);

      // 标记环：法线朝球心外，形成仪器刻度感
      const ring = new THREE.Mesh(
        new THREE.TorusGeometry(baseRadius * 2.15, 0.0035, 6, 64),
        new THREE.MeshBasicMaterial({
          color: 0x2563eb,
          transparent: true,
          opacity: 0.42,
          depthWrite: false,
        }),
      );
      ring.position.copy(position);
      ring.quaternion.setFromUnitVectors(new THREE.Vector3(0, 0, 1), normal);
      ring.userData.phase = index * 0.86;
      field.add(ring);
      nodeRings.push(ring);

      const glow = new THREE.Sprite(
        new THREE.SpriteMaterial({
          map: glowTexture,
          color: 0x9dc4fb,
          transparent: true,
          opacity: 0.5,
          depthWrite: false,
        }),
      );
      glow.scale.setScalar(baseRadius * 7.4);
      glow.position.copy(position);
      glow.userData.baseScale = baseRadius * 7.4;
      glow.userData.phase = index * 0.86;
      field.add(glow);
      nodeGlows.push(glow);

      // 辐条：从球心到节点，向球心渐隐
      const spokeGeometry = new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(0, 0, 0),
        position.clone(),
      ]);
      setVertexColors(spokeGeometry, (_point, t) => [
        0x25 / 255,
        0x63 / 255,
        0xeb / 255,
        0.028 + 0.13 * t,
      ]);
      field.add(
        new THREE.Line(
          spokeGeometry,
          new THREE.LineBasicMaterial({
            vertexColors: true,
            transparent: true,
            depthWrite: false,
          }),
        ),
      );
    });

    /* ---------- 共振弧线：双层（柔晕管 + 渐隐线）+ 流动光点 ---------- */
    const flowSystems: FlowSystem[] = [];
    ARC_PAIRS.forEach(([a, b], index) => {
      const start = nodePositions[a];
      const end = nodePositions[b];
      const lift = 2.06 + (index % 3) * 0.14;
      const middle = start
        .clone()
        .add(end)
        .multiplyScalar(0.5)
        .normalize()
        .multiplyScalar(lift);
      const curve = new THREE.QuadraticBezierCurve3(start, middle, end);

      // 柔晕：细管，给弧线一层空气感
      const glowTube = new THREE.Mesh(
        new THREE.TubeGeometry(curve, 56, 0.016, 5, false),
        new THREE.MeshBasicMaterial({
          color: index < 2 ? 0x2563eb : 0x7aa2ef,
          transparent: true,
          opacity: 0.06,
          depthWrite: false,
        }),
      );
      field.add(glowTube);

      // 主弧线：端点渐隐，首尾色调递进
      const lineGeometry = new THREE.BufferGeometry().setFromPoints(
        curve.getPoints(72),
      );
      setVertexColors(lineGeometry, (_point, t) => {
        const color = C_ARC_HEAD.clone().lerp(C_ARC_TAIL, t);
        const fade = 0.16 + 0.84 * Math.pow(Math.sin(Math.PI * t), 0.55);
        return [color.r, color.g, color.b, 0.62 * fade];
      });
      field.add(
        new THREE.Line(
          lineGeometry,
          new THREE.LineBasicMaterial({
            vertexColors: true,
            transparent: true,
            depthWrite: false,
          }),
        ),
      );

      // 流动光点
      const positions = new Float32Array(FLOW_PER_ARC * 3);
      const flowGeometry = new THREE.BufferGeometry();
      const attribute = new THREE.BufferAttribute(positions, 3);
      flowGeometry.setAttribute("position", attribute);
      const flowPoints = new THREE.Points(
        flowGeometry,
        new THREE.PointsMaterial({
          color: 0x2f6ee9,
          size: 0.062,
          map: glowTexture,
          transparent: true,
          opacity: 0.9,
          depthWrite: false,
        }),
      );
      field.add(flowPoints);
      flowSystems.push({
        points: flowPoints,
        positions,
        attribute,
        curve,
        phase: index * 0.17,
        speed: 0.05 + (index % 3) * 0.015,
      });
    });

    const clock = new THREE.Clock();
    const pointer = new THREE.Vector2();
    let visible = true;
    let frame = 0;
    let motionTime = 0;

    const resize = () => {
      const { width, height } = host.getBoundingClientRect();
      if (!width || !height) return;
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    };

    const worldPosition = new THREE.Vector3();
    const normalVec = new THREE.Vector3();
    const toCamera = new THREE.Vector3();
    const projected = new THREE.Vector3();
    const labelSlots: { index: number; x: number; y: number; facing: number }[] =
      [];

    const updateLabels = () => {
      const width = host.clientWidth;
      const height = host.clientHeight;
      if (!width || !height) return;
      labelSlots.length = 0;

      nodeMeshes.forEach((mesh, index) => {
        mesh.getWorldPosition(worldPosition);
        normalVec.copy(worldPosition).normalize();
        toCamera.copy(camera.position).sub(worldPosition).normalize();
        const facing = normalVec.dot(toCamera);
        projected.copy(worldPosition).project(camera);
        labelSlots.push({
          index,
          x: (projected.x * 0.5 + 0.5) * width,
          y: (-projected.y * 0.5 + 0.5) * height,
          facing,
        });
      });

      // 纵向防重叠：按 y 排序后逐对推开，避免标签叠字
      labelSlots.sort((a, b) => a.y - b.y);
      for (let i = 1; i < labelSlots.length; i += 1) {
        const prev = labelSlots[i - 1];
        const cur = labelSlots[i];
        if (Math.abs(cur.x - prev.x) < 88 && cur.y - prev.y < 19) {
          cur.y = prev.y + 19;
        }
      }

      labelSlots.forEach((slot) => {
        const label = labelRefs.current[slot.index];
        if (!label) return;
        const x = Math.min(width - 48, Math.max(4, slot.x + 10));
        const y = Math.min(height - 11, Math.max(11, slot.y));
        // 背面节点标签降到 0.28 透明度，表达深度但保持信息完整
        const depth = THREE.MathUtils.clamp((slot.facing + 0.15) / 0.5, 0, 1);
        label.style.transform = `translate3d(${x.toFixed(1)}px, ${y.toFixed(1)}px, 0) translateY(-50%)`;
        label.style.opacity = (0.28 + 0.72 * depth).toFixed(3);
      });
    };

    const render = () => {
      if (!visible && !reduceMotion) return;
      const dt = Math.min(clock.getDelta(), 0.05);
      motionTime += dt;
      const elapsed = motionTime;

      const targetY = -0.45 + elapsed * 0.1 + pointer.x * 0.2;
      const targetX = -0.1 - pointer.y * 0.11 + Math.sin(elapsed * 0.32) * 0.03;
      field.rotation.y += (targetY - field.rotation.y) * 0.038;
      field.rotation.x += (targetX - field.rotation.x) * 0.034;

      if (!reduceMotion) {
        field.rotation.z = 0.06 + Math.sin(elapsed * 0.2) * 0.022;

        pointCloud.rotation.y = -elapsed * 0.05;
        pointCloud.rotation.x = Math.sin(elapsed * 0.26) * 0.042;
        dust.rotation.y = -elapsed * 0.028;
        dust.rotation.z = elapsed * 0.014;
        halos[0].rotation.z = elapsed * 0.11;
        halos[1].rotation.y = -elapsed * 0.085;
        halos[2].rotation.x = Math.PI / 3.6 + elapsed * 0.06;
        camera.position.z = 7.6 - Math.sin(elapsed * 0.4) * 0.05;

        coreGlowWide.scale.setScalar(3.4 + Math.sin(elapsed * 1.35) * 0.22);
        (coreGlowWide.material as THREE.SpriteMaterial).opacity =
          0.14 + Math.sin(elapsed * 1.35 + 0.6) * 0.035;

        nodeMeshes.forEach((mesh, index) => {
          const phase = mesh.userData.phase as number;
          mesh.scale.setScalar(1 + Math.sin(elapsed * 1.6 + phase) * 0.11);

          const ring = nodeRings[index];
          ring.scale.setScalar(1 + Math.sin(elapsed * 1.6 + phase) * 0.14);
          (ring.material as THREE.MeshBasicMaterial).opacity =
            0.3 + Math.sin(elapsed * 1.6 + phase) * 0.14;

          const glow = nodeGlows[index];
          const baseScale = glow.userData.baseScale as number;
          glow.scale.setScalar(
            baseScale + Math.sin(elapsed * 1.6 + phase) * 0.22,
          );
          (glow.material as THREE.SpriteMaterial).opacity =
            0.4 + Math.sin(elapsed * 1.6 + phase) * 0.14;
        });

        flowSystems.forEach((system) => {
          system.phase = (system.phase + system.speed * dt) % 1;
          for (let i = 0; i < FLOW_PER_ARC; i += 1) {
            const t = (i / FLOW_PER_ARC + system.phase) % 1;
            const point = system.curve.getPoint(t);
            system.positions[i * 3] = point.x;
            system.positions[i * 3 + 1] = point.y;
            system.positions[i * 3 + 2] = point.z;
          }
          system.attribute.needsUpdate = true;
          (system.points.material as THREE.PointsMaterial).opacity =
            0.72 + Math.sin(elapsed * 1.1 + system.phase * 6.2) * 0.2;
        });
      }

      renderer.render(scene, camera);
      updateLabels();
      if (!reduceMotion) {
        frame = window.requestAnimationFrame(render);
      }
    };

    const onPointerMove = (event: PointerEvent) => {
      const rect = host.getBoundingClientRect();
      pointer.set(
        ((event.clientX - rect.left) / rect.width) * 2 - 1,
        -(((event.clientY - rect.top) / rect.height) * 2 - 1),
      );
    };
    const onPointerLeave = () => pointer.set(0, 0);

    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(host);
    const visibilityObserver = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      if (visible && !frame) {
        clock.start();
        render();
      }
      if (!visible && frame) {
        window.cancelAnimationFrame(frame);
        frame = 0;
        clock.stop();
      }
    });
    visibilityObserver.observe(host);
    host.addEventListener("pointermove", onPointerMove, { passive: true });
    host.addEventListener("pointerleave", onPointerLeave);

    resize();
    render();

    return () => {
      window.cancelAnimationFrame(frame);
      resizeObserver.disconnect();
      visibilityObserver.disconnect();
      host.removeEventListener("pointermove", onPointerMove);
      host.removeEventListener("pointerleave", onPointerLeave);
      scene.traverse((object) => {
        if (
          object instanceof THREE.Mesh ||
          object instanceof THREE.Points ||
          object instanceof THREE.Line
        ) {
          object.geometry.dispose();
        }
        if (
          object instanceof THREE.Mesh ||
          object instanceof THREE.Points ||
          object instanceof THREE.Line ||
          object instanceof THREE.Sprite
        ) {
          const material = object.material;
          if (Array.isArray(material)) {
            material.forEach((item) => item.dispose());
          } else {
            material.dispose();
          }
        }
      });
      // 共享纹理只释放一次；Sprite 使用内置共享几何体，不单独释放
      glowTexture.dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, []);

  return (
    <div className="data-field" ref={hostRef}>
      <div className="data-field__fallback" aria-hidden="true" />
      <div className="data-field__labels" aria-hidden="true">
        {PLATFORMS.map((platform, index) => (
          <span
            key={platform}
            ref={(node) => {
              labelRefs.current[index] = node;
            }}
            className="data-field__label"
          >
            {platform}
          </span>
        ))}
      </div>
    </div>
  );
}
