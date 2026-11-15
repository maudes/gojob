/** @type {import('next').NextConfig} */

// The browser still calls /api/... on this server. Every such call is handed to the Python
// backend (backend/), which does all the real work.
const API = process.env.GOJOB_API_URL || "http://127.0.0.1:8000";

const nextConfig = {
  rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
  },
  experimental: {
    // Research runs call the model for several minutes; the default proxy timeout is far shorter.
    proxyTimeout: 15 * 60 * 1000,
  },
};
export default nextConfig;
