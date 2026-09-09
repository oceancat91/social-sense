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

function pointOnSphere(lat: number, lon: number, radius: number) {
  const phi = THREE.MathUtils.degToRad(90 - lat);
  const theta = THREE.MathUtils.degToRad(lon + 180);
  return new THREE.Vector3(
    -radius * Math.sin(phi) * Math.cos(theta),
    radius * Math.cos(phi),
    radius * Math.sin(phi) * Math.sin(theta),
  );
}

function makeArc(
  start: THREE.Vector3,
  end: THREE.Vector3,
  lift: number,
  color: number,
) {
  const middle = start
    .clone()
    .add(end)
    .multiplyScalar(0.5)
    .normalize()
    .multiplyScalar(lift);
  const curve = new THREE.QuadraticBezierCurve3(start, middle, end);
  const geometry = new THREE.BufferGeometry().setFromPoints(curve.getPoints(48));
  const material = new THREE.LineBasicMaterial({
    color,
    transparent: true,
    opacity: 0.34,
  });
  return new THREE.Line(geometry, material);
}

/**
 * 六平台 3D 数据场。
 * 节点大小映射示意声量，弧线表达跨平台共振关系。
 * Three.js 被隔离在该 Client 叶组件内，卸载时完整释放 GPU 资源。
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
    const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 100);
    camera.position.set(0, 0.1, 6.2);

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
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    host.prepend(renderer.domElement);

    const field = new THREE.Group();
    field.rotation.set(-0.12, -0.45, 0.08);
    scene.add(field);

    const shellGeometry = new THREE.IcosahedronGeometry(1.58, 3);
    const shellMaterial = new THREE.MeshBasicMaterial({
      color: 0x6f9cf4,
      wireframe: true,
      transparent: true,
      opacity: 0.11,
      depthWrite: false,
    });
    const shell = new THREE.Mesh(shellGeometry, shellMaterial);
    field.add(shell);

    const pointPositions: number[] = [];
    const pointCount = 420;
    const goldenAngle = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < pointCount; i += 1) {
      const y = 1 - (i / (pointCount - 1)) * 2;
      const radius = Math.sqrt(1 - y * y);
      const theta = goldenAngle * i;
      pointPositions.push(
        Math.cos(theta) * radius * 1.62,
        y * 1.62,
        Math.sin(theta) * radius * 1.62,
      );
    }
    const pointsGeometry = new THREE.BufferGeometry();
    pointsGeometry.setAttribute(
      "position",
      new THREE.Float32BufferAttribute(pointPositions, 3),
    );
    const pointsMaterial = new THREE.PointsMaterial({
      color: 0x2f6ee9,
      size: 0.018,
      transparent: true,
      opacity: 0.38,
      depthWrite: false,
    });
    const pointCloud = new THREE.Points(pointsGeometry, pointsMaterial);
    field.add(pointCloud);

    const coreGeometry = new THREE.SphereGeometry(0.34, 40, 40);
    const coreMaterial = new THREE.MeshBasicMaterial({
      color: 0xdbeafe,
      transparent: true,
      opacity: 0.72,
    });
    field.add(new THREE.Mesh(coreGeometry, coreMaterial));

    const haloMaterial = new THREE.MeshBasicMaterial({
      color: 0x2563eb,
      transparent: true,
      opacity: 0.14,
      side: THREE.DoubleSide,
      depthWrite: false,
    });
    const haloA = new THREE.Mesh(
      new THREE.TorusGeometry(1.88, 0.008, 8, 160),
      haloMaterial,
    );
    haloA.rotation.x = Math.PI / 2.7;
    haloA.rotation.y = 0.34;
    field.add(haloA);

    const haloB = new THREE.Mesh(
      new THREE.TorusGeometry(1.98, 0.006, 8, 160),
      haloMaterial.clone(),
    );
    haloB.rotation.x = Math.PI / 1.9;
    haloB.rotation.z = -0.5;
    field.add(haloB);

    const nodePositions = NODE_DATA.map((node) =>
      pointOnSphere(node.lat, node.lon, 1.66),
    );
    const nodeMeshes: THREE.Mesh[] = [];
    const spokeMaterial = new THREE.LineBasicMaterial({
      color: 0x2563eb,
      transparent: true,
      opacity: 0.14,
    });

    nodePositions.forEach((position, index) => {
      const radius = 0.055 + NODE_DATA[index].weight * 0.04;
      const geometry = new THREE.SphereGeometry(radius, 24, 24);
      const material = new THREE.MeshBasicMaterial({
        color: index < 2 ? 0x1d4ed8 : 0x5b8def,
      });
      const mesh = new THREE.Mesh(geometry, material);
      mesh.position.copy(position);
      mesh.userData.baseScale = 1;
      field.add(mesh);
      nodeMeshes.push(mesh);

      const spokeGeometry = new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(0, 0, 0),
        position,
      ]);
      field.add(new THREE.Line(spokeGeometry, spokeMaterial));
    });

    const arcPairs = [
      [0, 1],
      [0, 2],
      [1, 3],
      [2, 4],
      [3, 5],
      [4, 5],
      [1, 4],
    ];
    arcPairs.forEach(([a, b], index) => {
      field.add(
        makeArc(
          nodePositions[a],
          nodePositions[b],
          2.08 + (index % 3) * 0.12,
          index < 2 ? 0x2563eb : 0x7aa2ef,
        ),
      );
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

    const updateLabels = () => {
      const width = host.clientWidth;
      const height = host.clientHeight;
      nodeMeshes.forEach((mesh, index) => {
        const label = labelRefs.current[index];
        if (!label) return;
        const world = new THREE.Vector3();
        mesh.getWorldPosition(world);
        world.project(camera);
        const x = (world.x * 0.5 + 0.5) * width;
        const y = (-world.y * 0.5 + 0.5) * height;
        const safeX = Math.min(width - 52, Math.max(6, x + 8));
        const safeY = Math.min(height - 20, Math.max(12, y));
        label.style.transform = `translate3d(${safeX}px, ${safeY}px, 0) translateY(-50%)`;
        label.style.opacity = world.z < 1 ? "1" : "0";
      });
    };

    const render = () => {
      if (!visible && !reduceMotion) return;
      motionTime += Math.min(clock.getDelta(), 0.05);
      const elapsed = motionTime;
      if (!reduceMotion) {
        const targetY = -0.45 + elapsed * 0.12 + pointer.x * 0.18;
        const targetX =
          -0.12 - pointer.y * 0.1 + Math.sin(elapsed * 0.34) * 0.035;
        field.rotation.y +=
          (targetY - field.rotation.y) * 0.04;
        field.rotation.x += (targetX - field.rotation.x) * 0.035;
        field.rotation.z = 0.08 + Math.sin(elapsed * 0.22) * 0.025;
        shell.rotation.x = elapsed * 0.026;
        shell.rotation.z = -elapsed * 0.018;
        pointCloud.rotation.y = -elapsed * 0.055;
        pointCloud.rotation.x = Math.sin(elapsed * 0.28) * 0.045;
        haloA.rotation.z = elapsed * 0.12;
        haloB.rotation.y = -elapsed * 0.09;
        camera.position.z = 6.2 + Math.sin(elapsed * 0.42) * 0.06;
        nodeMeshes.forEach((mesh, index) => {
          const scale = 1 + Math.sin(elapsed * 1.7 + index * 0.9) * 0.12;
          mesh.scale.setScalar(scale);
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
          object instanceof THREE.Line
        ) {
          const material = object.material;
          if (Array.isArray(material)) {
            material.forEach((item) => item.dispose());
          } else {
            material.dispose();
          }
        }
      });
      spokeMaterial.dispose();
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
