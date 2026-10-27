// The demonstration 3D presenter: a stylised Sokokali in a Kenya-coloured jersey at a studio desk.
// Built from simple shapes so it needs no model files; a rigged character can replace
// <Presenter> later without touching the speech or animation logic.

import { Canvas, useFrame } from "@react-three/fiber";
import { useRef } from "react";
import type { Group, Mesh } from "three";

import type { LipSync } from "./lipSync";
import type { AvatarAnimation } from "./speech";

const SKIN = "#7a4a2a";
// Cosmetics unlocked by community milestones (never by gifts).
export const OUTFITS: Record<string, { jersey: string; band: string; trim: string }> = {
  home: { jersey: "#15803d", band: "#b91c1c", trim: "#f8fafc" },
  away: { jersey: "#e5e7eb", band: "#15803d", trim: "#b91c1c" },
  gold: { jersey: "#ca8a04", band: "#111827", trim: "#fef3c7" },
};
export const BACKGROUNDS: Record<string, { sky: string; ambient: number; left: string; right: string; floodlights: number }> = {
  studio: { sky: "#07130c", ambient: 0.55, left: "#22c55e", right: "#ef4444", floodlights: 3 },
  floodlights: { sky: "#0b1a12", ambient: 0.8, left: "#fef9c3", right: "#fef9c3", floodlights: 6 },
  derby_night: { sky: "#0b1026", ambient: 0.5, left: "#3b82f6", right: "#ef4444", floodlights: 6 },
};

interface Pose {
  bodyY: number;
  lean: number;
  leftArmX: number;
  leftArmZ: number;
  rightArmX: number;
  rightArmZ: number;
  brows: number;
  smile: number;
}

const REST: Pose = { bodyY: 0, lean: 0, leftArmX: 0, leftArmZ: -0.12, rightArmX: -1.55, rightArmZ: -0.35, brows: 0, smile: 0 };

function targetPose(animation: AvatarAnimation, t: number): Pose {
  switch (animation) {
    case "celebration":
      return {
        bodyY: Math.abs(Math.sin(t * 7)) * 0.07,
        lean: 0,
        leftArmX: 0,
        leftArmZ: -2.6 + 0.35 * Math.sin(t * 9),
        rightArmX: 0,
        rightArmZ: 2.5 + 0.25 * Math.sin(t * 9 + 1),
        brows: 1,
        smile: 1,
      };
    case "commentary":
      return {
        ...REST,
        lean: 0.06,
        leftArmX: -0.9 + 0.3 * Math.sin(t * 3.2),
        leftArmZ: -0.35 + 0.1 * Math.sin(t * 2.1),
        brows: 0.4 + 0.3 * Math.sin(t * 1.7),
        smile: 0.3,
      };
    case "speaking":
      return { ...REST, lean: 0.025, leftArmX: -0.3 + 0.15 * Math.sin(t * 2.4), brows: 0.2, smile: 0.4 };
    default:
      return { ...REST, bodyY: Math.sin(t * 1.6) * 0.006, smile: 0.25 };
  }
}

function Presenter({ animation, lipSync, outfit }: { animation: AvatarAnimation; lipSync: LipSync; outfit: string }) {
  const colors = OUTFITS[outfit] ?? OUTFITS.home!;
  const body = useRef<Group>(null);
  const head = useRef<Group>(null);
  const leftArm = useRef<Group>(null);
  const rightArm = useRef<Group>(null);
  const eyes = useRef<Group>(null);
  const brows = useRef<Group>(null);
  const mouth = useRef<Mesh>(null);
  const pose = useRef<Pose>({ ...REST });
  const nextBlink = useRef(2);

  useFrame((state, delta) => {
    const t = state.clock.elapsedTime;
    const target = targetPose(animation, t);
    const k = 1 - Math.exp(-delta * 9); // frame-rate independent smoothing
    const p = pose.current;
    for (const key of Object.keys(p) as (keyof Pose)[]) p[key] += (target[key] - p[key]) * k;

    const mouthShape = lipSync.shape(performance.now());
    const talking = animation !== "idle";

    if (body.current) {
      body.current.position.y = p.bodyY;
      body.current.rotation.x = p.lean;
      body.current.scale.y = 1 + Math.sin(t * 1.6) * 0.008; // breathing
    }
    if (head.current) {
      head.current.rotation.y = Math.sin(t * 0.55) * 0.12;
      head.current.rotation.x = talking ? -0.04 + mouthShape.open * 0.06 : Math.sin(t * 0.8) * 0.02;
      head.current.rotation.z = Math.sin(t * 0.4) * 0.03;
    }
    if (leftArm.current) leftArm.current.rotation.set(p.leftArmX, 0, p.leftArmZ);
    if (rightArm.current) rightArm.current.rotation.set(p.rightArmX, 0, p.rightArmZ);
    if (brows.current) brows.current.position.y = 0.11 + p.brows * 0.02;

    // Blink every 2-5 seconds.
    if (eyes.current) {
      let open = 1;
      const sinceBlink = t - nextBlink.current;
      if (sinceBlink > 0) {
        open = sinceBlink < 0.15 ? Math.abs(Math.cos((sinceBlink / 0.15) * Math.PI)) : 1;
        if (sinceBlink >= 0.15) nextBlink.current = t + 2 + Math.random() * 3;
      }
      eyes.current.scale.y = Math.max(0.1, open);
    }

    if (mouth.current) {
      const smileOpen = animation === "celebration" ? 0.55 : 0;
      const open = Math.max(mouthShape.open, smileOpen);
      mouth.current.scale.set(0.9 + mouthShape.wide * 0.5 + p.smile * 0.3, 0.2 + open * 0.95, 0.35);
    }
  });

  return (
    <group ref={body}>
      {/* torso and jersey */}
      <mesh position={[0, 1.12, 0]} castShadow>
        <capsuleGeometry args={[0.27, 0.42, 8, 24]} />
        <meshStandardMaterial color={colors.jersey} roughness={0.7} />
      </mesh>
      <mesh position={[0, 1.2, 0.02]} rotation={[0, 0, 0]}>
        <cylinderGeometry args={[0.276, 0.276, 0.07, 32, 1, true]} />
        <meshStandardMaterial color={colors.band} roughness={0.7} />
      </mesh>
      <mesh position={[0, 1.245, 0.02]}>
        <cylinderGeometry args={[0.277, 0.277, 0.018, 32, 1, true]} />
        <meshStandardMaterial color={colors.trim} />
      </mesh>
      <mesh position={[0, 1.155, 0.02]}>
        <cylinderGeometry args={[0.277, 0.277, 0.018, 32, 1, true]} />
        <meshStandardMaterial color={colors.trim} />
      </mesh>

      {/* neck and head */}
      <mesh position={[0, 1.42, 0]}>
        <cylinderGeometry args={[0.07, 0.08, 0.12, 16]} />
        <meshStandardMaterial color={SKIN} roughness={0.6} />
      </mesh>
      <group ref={head} position={[0, 1.6, 0]}>
        <mesh castShadow>
          <sphereGeometry args={[0.2, 32, 32]} />
          <meshStandardMaterial color={SKIN} roughness={0.55} />
        </mesh>
        {/* short hair */}
        <mesh position={[0, 0.06, -0.01]} scale={[1.03, 0.82, 1.03]}>
          <sphereGeometry args={[0.2, 32, 16, 0, Math.PI * 2, 0, Math.PI / 2.1]} />
          <meshStandardMaterial color="#1c1917" roughness={0.9} />
        </mesh>
        {/* ears */}
        {[-1, 1].map((side) => (
          <mesh key={side} position={[side * 0.2, 0, 0]} scale={[0.5, 1, 0.8]}>
            <sphereGeometry args={[0.045, 16, 16]} />
            <meshStandardMaterial color={SKIN} />
          </mesh>
        ))}
        <group ref={eyes} position={[0, 0.035, 0.17]}>
          {[-1, 1].map((side) => (
            <group key={side} position={[side * 0.07, 0, 0]}>
              <mesh>
                <sphereGeometry args={[0.032, 16, 16]} />
                <meshStandardMaterial color="#ffffff" />
              </mesh>
              <mesh position={[0, 0, 0.026]}>
                <sphereGeometry args={[0.016, 16, 16]} />
                <meshStandardMaterial color="#111827" />
              </mesh>
            </group>
          ))}
        </group>
        <group ref={brows} position={[0, 0.11, 0.17]}>
          {[-1, 1].map((side) => (
            <mesh key={side} position={[side * 0.07, 0, 0]} rotation={[0, 0, side * -0.12]}>
              <boxGeometry args={[0.07, 0.014, 0.012]} />
              <meshStandardMaterial color="#1c1917" />
            </mesh>
          ))}
        </group>
        <mesh position={[0, -0.005, 0.2]}>
          <sphereGeometry args={[0.022, 12, 12]} />
          <meshStandardMaterial color="#6b3d22" />
        </mesh>
        <mesh ref={mouth} position={[0, -0.085, 0.19]}>
          <sphereGeometry args={[0.05, 24, 16]} />
          <meshStandardMaterial color="#3b0a0a" roughness={0.4} />
        </mesh>
      </group>

      {/* arms: each pivots at the shoulder */}
      <group ref={leftArm} position={[-0.33, 1.32, 0]}>
        <mesh position={[0, -0.24, 0]} castShadow>
          <capsuleGeometry args={[0.065, 0.36, 6, 16]} />
          <meshStandardMaterial color={colors.jersey} roughness={0.7} />
        </mesh>
        <mesh position={[0, -0.5, 0]}>
          <sphereGeometry args={[0.065, 16, 16]} />
          <meshStandardMaterial color={SKIN} />
        </mesh>
      </group>
      <group ref={rightArm} position={[0.33, 1.32, 0]}>
        <mesh position={[0, -0.24, 0]} castShadow>
          <capsuleGeometry args={[0.065, 0.36, 6, 16]} />
          <meshStandardMaterial color={colors.jersey} roughness={0.7} />
        </mesh>
        <mesh position={[0, -0.5, 0]}>
          <sphereGeometry args={[0.065, 16, 16]} />
          <meshStandardMaterial color={SKIN} />
        </mesh>
        {/* microphone in the right hand */}
        <group position={[0, -0.55, 0.02]}>
          <mesh position={[0, -0.02, 0]}>
            <cylinderGeometry args={[0.022, 0.016, 0.16, 16]} />
            <meshStandardMaterial color="#27272a" metalness={0.4} roughness={0.4} />
          </mesh>
          <mesh position={[0, -0.12, 0]}>
            <sphereGeometry args={[0.042, 16, 16]} />
            <meshStandardMaterial color="#a1a1aa" metalness={0.6} roughness={0.35} />
          </mesh>
        </group>
      </group>
    </group>
  );
}

function Studio({ background }: { background: string }) {
  const bg = BACKGROUNDS[background] ?? BACKGROUNDS.studio!;
  const lights = [-2.2, 0, 2.2, -3.4, 1.1, 3.4].slice(0, bg.floodlights);
  return (
    <>
      <color attach="background" args={[bg.sky]} />
      <fog attach="fog" args={[bg.sky, 4, 9]} />
      <ambientLight intensity={bg.ambient} />
      <directionalLight position={[2, 4, 3]} intensity={1.6} castShadow />
      <pointLight position={[-2.5, 3, -1]} intensity={8} color={bg.left} />
      <pointLight position={[2.5, 3, -1]} intensity={8} color={bg.right} />
      {/* floodlights */}
      {lights.map((x) => (
        <mesh key={x} position={[x, 3.1, -3]}>
          <sphereGeometry args={[0.12, 16, 16]} />
          <meshBasicMaterial color="#fef9c3" />
        </mesh>
      ))}
      {/* pitch floor */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <circleGeometry args={[5, 48]} />
        <meshStandardMaterial color="#14532d" roughness={1} />
      </mesh>
      {[-1.6, 0, 1.6].map((z) => (
        <mesh key={z} rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.002, z - 1]}>
          <planeGeometry args={[10, 0.8]} />
          <meshStandardMaterial color="#166534" roughness={1} />
        </mesh>
      ))}
      {/* presenter desk */}
      <mesh position={[0, 0.45, 0.45]} castShadow>
        <boxGeometry args={[1.7, 0.9, 0.55]} />
        <meshStandardMaterial color="#18181b" roughness={0.5} metalness={0.2} />
      </mesh>
      <mesh position={[0, 0.62, 0.726]}>
        <boxGeometry args={[1.7, 0.08, 0.01]} />
        <meshStandardMaterial color="#16a34a" emissive="#16a34a" emissiveIntensity={0.6} />
      </mesh>
      <mesh position={[0, 0.54, 0.726]}>
        <boxGeometry args={[1.7, 0.03, 0.01]} />
        <meshStandardMaterial color="#dc2626" emissive="#dc2626" emissiveIntensity={0.6} />
      </mesh>
    </>
  );
}

interface SceneProps {
  animation: AvatarAnimation;
  lipSync: LipSync;
  outfit?: string;
  background?: string;
  /** Tall 9:16 framing for portrait TikTok LIVE. */
  portrait?: boolean;
}

export default function PresenterScene({
  animation,
  lipSync,
  outfit = "home",
  background = "studio",
  portrait = false,
}: SceneProps) {
  // Portrait windows are narrow, so the camera steps back and widens to keep the shoulders and desk in frame.
  const camera = portrait
    ? { position: [0, 1.5, 3.4] as [number, number, number], fov: 46 }
    : { position: [0, 1.56, 2.3] as [number, number, number], fov: 30 };
  return (
    <Canvas
      key={portrait ? "portrait" : "landscape"}
      shadows
      dpr={[1, 2]}
      style={{ width: "100%", height: "100%" }}
      camera={camera}
      onCreated={({ camera: cam }) => cam.lookAt(0, portrait ? 1.3 : 1.45, 0)}
    >
      <Studio background={background} />
      <Presenter animation={animation} lipSync={lipSync} outfit={outfit} />
    </Canvas>
  );
}
