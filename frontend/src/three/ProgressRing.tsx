import { useRef } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import * as THREE from 'three';

function Ring({ progress }: { progress: number }) {
  const fill = useRef<THREE.Mesh>(null);
  const halo = useRef<THREE.Mesh>(null);
  const current = useRef(0);

  useFrame((state, delta) => {
    current.current += (progress / 100 - current.current) * Math.min(1, delta * 4);
    const pct = THREE.MathUtils.clamp(current.current, 0.0001, 1);

    if (fill.current) {
      fill.current.geometry.dispose();
      fill.current.geometry = new THREE.RingGeometry(
        1.32,
        1.55,
        96,
        1,
        Math.PI / 2,
        -pct * Math.PI * 2,
      );
    }
    if (halo.current) {
      const t = state.clock.getElapsedTime();
      halo.current.rotation.z = -t * 0.35;
      const mat = halo.current.material as THREE.MeshBasicMaterial;
      mat.opacity = 0.18 + Math.sin(t * 2) * 0.06;
    }
  });

  return (
    <group>
      <mesh>
        <ringGeometry args={[1.32, 1.55, 96]} />
        <meshBasicMaterial color="#1b2333" side={THREE.DoubleSide} />
      </mesh>
      <mesh ref={fill}>
        <ringGeometry args={[1.32, 1.55, 96, 1, Math.PI / 2, -0.01]} />
        <meshBasicMaterial color="#38bdf8" side={THREE.DoubleSide} />
      </mesh>
      <mesh ref={halo}>
        <ringGeometry args={[1.62, 1.72, 64, 1, 0, Math.PI * 1.2]} />
        <meshBasicMaterial color="#7dd3fc" transparent opacity={0.2} side={THREE.DoubleSide} />
      </mesh>
    </group>
  );
}

export default function ProgressRing({
  progress,
  label = 'Analyzing',
  className = '',
}: {
  progress: number;
  label?: string;
  className?: string;
}) {
  return (
    <div className={`relative ${className}`}>
      <Canvas dpr={[1, 1.75]} camera={{ position: [0, 0, 5], fov: 45 }}>
        <ambientLight intensity={1} />
        <Ring progress={progress} />
      </Canvas>
      <div className="pointer-events-none absolute inset-0 grid place-items-center">
        <div className="text-center">
          <div className="font-mono text-4xl font-semibold text-slate-100">
            {Math.round(progress)}%
          </div>
          <div className="mt-1 text-[11px] uppercase tracking-[0.3em] text-slate-500">
            {label}
          </div>
        </div>
      </div>
    </div>
  );
}
