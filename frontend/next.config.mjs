/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  env: { NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000" },
  // A self-hosted Docker deploy (as opposed to Render/Vercel's own build pipeline) wants
  // the standalone output: it traces exactly the node_modules files each route actually
  // needs into .next/standalone, instead of shipping the whole node_modules tree in the
  // image. No effect on `next dev` or a platform that does its own build.
  output: "standalone",
};
export default nextConfig;
