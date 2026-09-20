/** @type {import('next').NextConfig} */
const nextConfig = {
  // Type errors fail the build. v0 disables this, which is fine for a mockup
  // and wrong for an application talking to a real API: a mismatch between the
  // backend's types and the interface would ship rather than stop the build.
  // The project already type-checks clean, so this costs nothing today.
  images: {
    unoptimized: true,
  },
}

export default nextConfig
