import { useMemo, useRef } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import * as THREE from 'three';
import type { DetectionItem } from '../api/types';

const CLASS_COLOR: Record<string, string> = {
  pothole: '#ef4444',
  crack: '#f1c40f',
  'alligator-cracking': '#9b5cb0',
  'alligator cracking': '#9b5cb0',
  alligator_cracking: '#9b5cb0',
};

function colorFor(name: string): string {
  return CLASS_COLOR[name.toLowerCase()] ?? '#38bdf8';
}

interface Bar {
  x: number;
  z: number;
  height: number;
  color: string;
}

function Bars({ bars }: { bars: Bar[] }) {
  const group = useRef<THREE.Group>(null);

  useFrame(({ clock }) => {
    if (!group.current) return;
    const t = clock.getElapsedTime();
    group.current.children.forEach((child, i) => {
      const target = bars[i]?.height ?? 0.1;
      const wobble = 1 + Math.sin(t * 1.4 + i * 0.5) * 0.04;
      child.scale.y = THREE.MathUtils.lerp(child.scale.y, target * wobble, 0.12);
      child.position.y = (child.scale.y * 1) / 2;
    });
  });

  return (
    <group ref={group}>
      {bars.map((bar, i) => (
        <mesh key={i} position={[bar.x, 0.05, bar.z]} scale={[1, 0.05, 1]} castShadow>
          <boxGeometry args={[0.34, 1, 0.34]} />
          <meshStandardMaterial
            color={bar.color}
            emissive={bar.color}
            emissiveIntensity={0.35}
            roughness={0.4}
            metalness={0.15}
          />
        </mesh>
      ))}
    </group>
  );
}

function Grid() {
  return (
    <>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.01, 0]} receiveShadow>
        <planeGeometry args={[14, 8]} />
        <meshStandardMaterial color="#0b0f17" roughness={1} />
      </mesh>
      <gridHelper args={[14, 28, '#1b2333', '#141b28']} position={[0, 0, 0]} />
    </>
  );
}

export default function SeverityField({
  detections,
  durationSec,
  className = '',
}: {
  detections: DetectionItem[];
  durationSec: number;
  className?: string;
}) {
  const bars = useMemo<Bar[]>(() => {
    if (detections.length === 0) return [];
    const columns = 24;
    const duration = Math.max(durationSec, 1);
    const classes = Array.from(new Set(detections.map((d) => d.class_name))).slice(0, 4);
    const grid = new Map<string, { sum: number; count: number; cls: string }>();

    for (const det of detections) {
      const col = Math.min(columns - 1, Math.floor((det.timestamp_sec / duration) * columns));
      const row = classes.indexOf(det.class_name);
      if (row < 0) continue;
      const key = `${col}:${row}`;
      const cell = grid.get(key) ?? { sum: 0, count: 0, cls: det.class_name };
      cell.sum += det.confidence;
      cell.count += 1;
      grid.set(key, cell);
    }

    const out: Bar[] = [];
    for (const [key, cell] of grid) {
      const [col, row] = key.split(':').map(Number);
      const intensity = (cell.sum / cell.count) * Math.min(3, cell.count);
      out.push({
        x: -6 + (col / (columns - 1 || 1)) * 12,
        z: -1.8 + row * 1.2,
        height: Math.max(0.15, intensity * 1.1),
        color: colorFor(cell.cls),
      });
    }
    return out;
  }, [detections, durationSec]);

  return (
    <div className={className}>
      {bars.length === 0 ? (
        <div className="grid h-full place-items-center text-sm text-slate-500">
          No detections to visualize.
        </div>
      ) : (
        <Canvas
          dpr={[1, 1.75]}
          shadows
          camera={{ position: [0, 5.5, 9], fov: 42 }}
          gl={{ antialias: true }}
        >
          <color attach="background" args={['#070a11']} />
          <ambientLight intensity={0.5} />
          <directionalLight position={[6, 9, 5]} intensity={1.2} castShadow />
          <pointLight position={[-6, 4, -4]} intensity={20} color="#38bdf8" distance={18} />
          <Grid />
          <Bars bars={bars} />
          <OrbitControls
            enablePan={false}
            minPolarAngle={0.2}
            maxPolarAngle={Math.PI / 2.4}
            minDistance={6}
            maxDistance={16}
            autoRotate
            autoRotateSpeed={0.6}
          />
        </Canvas>
      )}
    </div>
  );
}
