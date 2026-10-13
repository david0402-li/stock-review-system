// scripts/worker.js
// Cloudflare Worker: 提供动态 API 和 R2 数据读取

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    };

    if (request.method === "OPTIONS") {
      return new Response(null, { headers: corsHeaders });
    }

    // GET /api/health
    if (url.pathname === "/api/health") {
      return new Response(JSON.stringify({ status: "ok" }), {
        headers: { ...corsHeaders, "Content-Type": "application/json" },
      });
    }

    // GET /api/data/:date - 从 R2 读取数据
    const match = url.pathname.match(/^\/api\/data\/(\d{8})$/);
    if (match) {
      const date = match[1];
      try {
        const obj = await env.R2_BUCKET.get(`data/${date}.json`);
        if (!obj) {
          return new Response(JSON.stringify({ error: "not found" }), {
            status: 404,
            headers: { ...corsHeaders, "Content-Type": "application/json" },
          });
        }
        const data = await obj.text();
        return new Response(data, {
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        });
      } catch (e) {
        return new Response(JSON.stringify({ error: e.message }), {
          status: 500,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        });
      }
    }

    // GET /api/latest - 获取最新数据
    if (url.pathname === "/api/latest") {
      try {
        const list = await env.R2_BUCKET.list({ prefix: "data/" });
        const keys = list.objects.map(o => o.key).sort().reverse();
        if (keys.length === 0) {
          return new Response(JSON.stringify({ error: "no data" }), {
            status: 404,
            headers: { ...corsHeaders, "Content-Type": "application/json" },
          });
        }
        const obj = await env.R2_BUCKET.get(keys[0]);
        const data = await obj.text();
        return new Response(data, {
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        });
      } catch (e) {
        return new Response(JSON.stringify({ error: e.message }), {
          status: 500,
          headers: { ...corsHeaders, "Content-Type": "application/json" },
        });
      }
    }

    return new Response("Not Found", { status: 404, headers: corsHeaders });
  },
};
