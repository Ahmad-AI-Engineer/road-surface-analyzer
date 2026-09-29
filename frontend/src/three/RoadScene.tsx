import { useMemo, useRef } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { Float } from '@react-three/drei';
import * as THREE from 'three';

function LowPolyTerrain() {
  const geometry = useMemo(() => {
    const geo = new THREE.PlaneGeometry(14, 14, 28, 28);
    const pos = geo.attributes.position as THREE.BufferAttribute;
    for (let i = 0; i < pos.count; i += 1) {
      const x = pos.getX(i);
      const y = pos.getY(i);
      const road = Math.exp(-(x * x) / 3.2); // flat strip down the middle
      const noise =
        Math.sin(x * 0.9) * Math.cos(y * 0.7) * 0.55 +
        Math.sin(x * 2.3 + y * 1.7) * 0.18;
      pos.setZ(i, noise * (1 - road) - road * 0.04);
    }
    geo.computeVertexNormals();
    return geo;
  }, []);

  return (
    <group rotation={[-Math.PI / 2.35, 0, 0]}>
      <mesh geometry={geometry} receiveShadow>
        <meshStandardMaterial
          color="#1a2233"
          flatShading
          roughness={0.95}
          metalness={0.05}
        />
      </mesh>
      <mesh geometry={geometry} position={[0, 0, 0.005]}>
        <meshBasicMaterial color="#38bdf8" wireframe transparent opacity={0.12} />
      </mesh>
    </group>
  );
}

function RoadMarkings() {
  const dashes = useMemo(() => Array.from({ length: 9 }, (_, i) => i), []);
  const group = useRef<THREE.Group>(null);

  useFrame((_, delta) => {
    if (!group.current) return;
    group.current.children.forEach((child) => {
      child.position.z += delta * 1.6;
      if (child.position.z > 6.5) child.position.z = -6.5;
    });
  });

  return (
    <group ref={group}>
      {dashes.map((i) => (
        <mesh
          key={i}
          position={[0, -0.34, -6.5 + i * 1.6]}
          rotation={[-Math.PI / 2, 0, 0]}
        >
          <planeGeometry args={[0.16, 0.8]} />
          <meshBasicMaterial color="#e2e8f0" transparent opacity={0.55} />
        </mesh>
      ))}
    </group>
  );
}

function DamageMarker({
  position,
  color,
  scale = 1,
}: {
  position: [number, number, number];
  color: string;
  scale?: number;
}) {
  const ref = useRef<THREE.Mesh>(null);
  useFrame(({ clock }) => {
    if (!ref.current) return;
    const t = clock.getElapsedTime();
    const pulse = 1 + Math.sin(t * 2 + position[0]) * 0.12;
    ref.current.scale.setScalar(scale * pulse);
  });

  return (
    <mesh ref={ref} position={position} rotation={[-Math.PI / 2, 0, 0]}>
      <ringGeometry args={[0.18, 0.26, 24]} />
      <meshBasicMaterial color={color} transparent opacity={0.85} side={THREE.DoubleSide} />
    </mesh>
  );
}

function SceneContents() {
  const group = useRef<THREE.Group>(null);
  useFrame((_, delta) => {
    if (group.current) group.current.rotation.y += delta * 0.06;
  });

  return (
    <>
      <ambientLight intensity={0.45} />
      <directionalLight position={[5, 8, 4]} intensity={1.1} color="#cfe8ff" />
      <pointLight position={[-4, 2, -3]} intensity={18} color="#9b5cb0" distance={14} />
      <fog attach="fog" args={['#07090f', 8, 20]} />

      <group ref={group} position={[0, -1.2, 0]}>
        <Float speed={1.1} rotationIntensity={0.15} floatIntensity={0.4}>
          <LowPolyTerrain />
          <RoadMarkings />
          <DamageMarker position={[-0.6, -0.32, 1.4]} color="#ef4444" scale={1.15} />
          <DamageMarker position={[0.7, -0.32, -1.1]} color="#f1c40f" />
          <DamageMarker position={[0.1, -0.32, 3.2]} color="#9b5cb0" scale={0.85} />
        </Float>
      </group>
    </>
  );
}

export default function RoadScene({ className = '' }: { className?: string }) {
  return (
    <div className={className}>
      <Canvas
        dpr={[1, 1.75]}
        camera={{ position: [0, 3.2, 7.5], fov: 45 }}
        gl={{ antialias: true, powerPreference: 'high-performance' }}
      >
        <color attach="background" args={['#07090f']} />
        <SceneContents />
      </Canvas>
    </div>
  );
}
