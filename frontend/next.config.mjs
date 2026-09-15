/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  env: { NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000" },
  // A self-hosted Docker deploy (as opposed to Render/Vercel's own build pipeline) wants
  // the standalone output: it traces exactly the node_modules files each route actually
  // needs into .next/standalone, instead of shipping the whole node_modules tree in the
  // image. No effect on `next dev` or a platform that does its own build.
  output: "standalone",
  // next build's own "Linting and checking validity of types" pass loads the whole
  // TypeScript program a second time and is the single heaviest, slowest step of the
  // whole build -- on a small self-hosted VM (limited RAM/CPU, no build cache between
  // deploys) it can run long enough, or swap hard enough, to look exactly like the build
  // hung. `npm run typecheck` (tsc --noEmit) and `npm run lint` already gate every push
  // before it reaches this branch, so redoing both again here, on the weakest machine in
  // the whole pipeline, buys nothing but that multi-minute stall.
  typescript: { ignoreBuildErrors: true },
  eslint: { ignoreDuringBuilds: true },
};
export default nextConfig;
