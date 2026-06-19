import http from "node:http";
import fs from "node:fs";
import path from "node:path";

const root = path.resolve("dist");
const port = Number(process.env.PORT || 4173);
const types = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".svg": "image/svg+xml",
};

http
  .createServer((request, response) => {
    const url = new URL(request.url || "/", `http://127.0.0.1:${port}`);
    const requested = url.pathname === "/" ? "/index.html" : url.pathname;
    const file = path.join(root, path.normalize(requested).replace(/^(\.\.[/\\])+/, ""));
    const fallback = path.join(root, "index.html");
    const target = fs.existsSync(file) && fs.statSync(file).isFile() ? file : fallback;
    response.setHeader("Content-Type", types[path.extname(target)] || "application/octet-stream");
    fs.createReadStream(target).pipe(response);
  })
  .listen(port, "127.0.0.1", () => {
    console.log(`Serving ${root} at http://127.0.0.1:${port}`);
  });
