"""Optional moderngl raymarcher.

The CPU marcher is the reference. This shader repeats the same metaballs,
tendrils, and chrome-flesh lighting so a machine with EGL/OSMesa can skip the
numpy loop. If a context cannot be created, ``render.py`` falls back.
"""

from __future__ import annotations

import numpy as np

from xenoform.render_cpu import camera_distance

VERTEX = """
#version 330
in vec2 in_vert;
out vec2 v_uv;
void main() {
    v_uv = in_vert;
    gl_Position = vec4(in_vert, 0.0, 1.0);
}
"""

FRAGMENT = """
#version 330
uniform vec2 u_res;
uniform vec3 u_eye;
uniform vec3 u_forward;
uniform vec3 u_right;
uniform vec3 u_up;
uniform float u_bound;
uniform float u_noise_amp;
uniform float u_noise_freq;
uniform float u_phase;
uniform float u_spec;
uniform float u_hue;
uniform float u_mutate;
uniform float u_high;
uniform int u_steps;
uniform vec4 u_balls[6];
uniform vec4 u_tendril_a[6];
uniform vec4 u_tendril_b[6];
in vec2 v_uv;
out vec4 f_color;

float smin(float a, float b, float k) {
    float h = clamp(k - abs(a - b), 0.0, k) / k;
    return min(a, b) - h * h * k * 0.25;
}

float capsule(vec3 p, vec3 a, vec3 b, float r) {
    vec3 pa = p - a;
    vec3 ba = b - a;
    float h = clamp(dot(pa, ba) / dot(ba, ba), 0.0, 1.0);
    return length(pa - ba * h) - r;
}

float scene(vec3 p) {
    float d = 1e5;
    for (int i = 0; i < 6; i++) {
        d = smin(d, length(p - u_balls[i].xyz) - u_balls[i].w, 0.42);
    }
    for (int i = 0; i < 6; i++) {
        d = smin(d, capsule(p, u_tendril_a[i].xyz, u_tendril_b[i].xyz, u_tendril_b[i].w), 0.2);
    }
    float disp = sin(p.x * u_noise_freq + u_phase)
        * sin(p.y * u_noise_freq * 1.37 + u_phase * 1.7)
        * sin(p.z * u_noise_freq * 0.81 + 2.1);
    return d - u_noise_amp * disp;
}

vec3 normal_at(vec3 p) {
    float e = 0.003;
    return normalize(vec3(
        scene(p + vec3(e, 0, 0)) - scene(p - vec3(e, 0, 0)),
        scene(p + vec3(0, e, 0)) - scene(p - vec3(0, e, 0)),
        scene(p + vec3(0, 0, e)) - scene(p - vec3(0, 0, e))
    ));
}

void main() {
    vec2 uv = v_uv;
    float aspect = u_res.x / u_res.y;
    vec2 cam = vec2(uv.x * aspect * 0.82, uv.y * 0.82);
    vec3 rd = normalize(u_forward + u_right * cam.x + u_up * cam.y);
    float b = dot(rd, u_eye);
    float c = dot(u_eye, u_eye) - u_bound * u_bound;
    float disc = b * b - c;
    vec3 bg = mix(vec3(0.012, 0.013, 0.020), vec3(0.025, 0.016, 0.018), uv.y * 0.5 + 0.5);
    float vig = clamp(1.0 - 0.55 * dot(cam, cam), 0.25, 1.0);
    if (disc <= 0.0) {
        f_color = vec4(pow(bg * vig, vec3(1.0 / 2.2)), 0.0);
        return;
    }
    float tnear = max(-b - sqrt(disc), 0.0);
    float tfar = -b + sqrt(disc);
    float t = tnear;
    bool hit = false;
    for (int i = 0; i < 64; i++) {
        if (i >= u_steps) break;
        float d = scene(u_eye + rd * t);
        if (d < 0.012) { hit = true; break; }
        t += max(d, 0.008);
        if (t > tfar) break;
    }
    if (!hit) {
        f_color = vec4(pow(bg * vig, vec3(1.0 / 2.2)), 0.0);
        return;
    }
    vec3 p = u_eye + rd * t;
    vec3 n = normal_at(p);
    vec3 v = -rd;
    float ndotv = clamp(dot(n, v), 0.0, 1.0);
    float fres = pow(1.0 - ndotv, 2.3);
    vec3 key = normalize(vec3(0.32, 0.86, 0.38));
    float diff = pow(clamp(dot(n, key), 0.0, 1.0), 0.85);
    vec3 h = normalize(key + v);
    float spec = pow(clamp(dot(n, h), 0.0, 1.0), 40.0 + 70.0 * u_high);
    vec3 refl = reflect(rd, n);
    float tint_r = 0.55 + 0.45 * sin(u_hue * 6.28318);
    float tint_g = 0.48 + 0.35 * sin(u_hue * 6.28318 + 2.1);
    float tint_b = 0.58 + 0.40 * sin(u_hue * 6.28318 + 4.0);
    vec3 tint = vec3(tint_r, tint_g, tint_b) / max(max(tint_r, tint_g), tint_b);
    vec3 flesh = mix(vec3(0.62, 0.22, 0.24), vec3(0.28, 0.62, 0.30), u_mutate);
    vec3 env = mix(vec3(0.05, 0.035, 0.03), vec3(0.02, 0.03, 0.05), refl.y * 0.5 + 0.5);
    float irid = 0.5 + 0.5 * sin(refl.x * 4.2 + u_hue * 6.28318);
    vec3 chrome = env * (0.35 + 0.75 * tint) * (0.72 + 0.28 * irid);
    vec3 lit = flesh * (0.16 + 0.9 * diff);
    vec3 color = lit * (1.0 - fres) + chrome * (0.22 + 0.78 * fres);
    color += spec * vec3(1.0, 0.97, 0.92) * u_spec;
    color += fres * tint * (0.12 + 0.4 * u_mutate);
    color *= vig;
    color = pow(clamp(color, 0.0, 1.0), vec3(1.0 / 2.2));
    float depth = clamp(1.0 - (t - tnear) / max(tfar - tnear, 0.001), 0.0, 1.0);
    f_color = vec4(color, depth);
}
"""


class GpuRenderer:
    def __init__(self, width: int, height: int, max_steps: int) -> None:
        import moderngl

        self.width = width
        self.height = height
        self.max_steps = max_steps
        self.ctx = moderngl.create_context(standalone=True)
        self.prog = self.ctx.program(vertex_shader=VERTEX, fragment_shader=FRAGMENT)
        vertices = np.array([-1.0, -1.0, 1.0, -1.0, -1.0, 1.0, 1.0, 1.0], dtype="f4")
        self.vbo = self.ctx.buffer(vertices.tobytes())
        self.vao = self.ctx.simple_vertex_array(self.prog, self.vbo, "in_vert")
        self.fbo = self.ctx.framebuffer(
            color_attachments=[self.ctx.texture((width, height), 4, dtype="f1")]
        )

    def render(self, form: dict):
        import math

        balls = form["balls"].astype("f4")
        tendrils = form["tendrils"].astype("f4")
        spin = float(form["spin"]) * 0.35
        dist = camera_distance(form)
        eye = np.array(
            [
                math.sin(spin * 0.4) * dist,
                0.42 + 0.06 * math.sin(float(form["t"]) * 0.6),
                math.cos(spin * 0.4) * dist,
            ],
            dtype="f4",
        )
        target = np.array([0.0, 0.02, 0.0], dtype="f4")
        forward = target - eye
        forward /= np.linalg.norm(forward)
        right = np.cross(forward, np.array([0.0, 1.0, 0.0], dtype="f4"))
        right /= np.linalg.norm(right)
        up = np.cross(right, forward)
        self.prog["u_res"].value = (float(self.width), float(self.height))
        self.prog["u_eye"].value = tuple(float(v) for v in eye)
        self.prog["u_forward"].value = tuple(float(v) for v in forward)
        self.prog["u_right"].value = tuple(float(v) for v in right)
        self.prog["u_up"].value = tuple(float(v) for v in up)
        self.prog["u_bound"].value = float(form["bound"])
        self.prog["u_noise_amp"].value = float(form["noise_amp"])
        self.prog["u_noise_freq"].value = float(form["noise_freq"])
        self.prog["u_phase"].value = float(form["phase"])
        self.prog["u_spec"].value = float(form["spec"])
        self.prog["u_hue"].value = float(form["hue"])
        self.prog["u_mutate"].value = float(form["mutate"])
        self.prog["u_high"].value = float(form["high"])
        self.prog["u_steps"].value = int(self.max_steps)
        self.prog["u_balls"].value = balls.reshape(-1).tolist()
        a = np.zeros((6, 4), dtype="f4")
        b = np.zeros((6, 4), dtype="f4")
        a[:, :3] = tendrils[:, 0:3]
        b[:, :3] = tendrils[:, 3:6]
        b[:, 3] = tendrils[:, 6]
        self.prog["u_tendril_a"].value = a.reshape(-1).tolist()
        self.prog["u_tendril_b"].value = b.reshape(-1).tolist()
        self.fbo.use()
        self.ctx.clear(0.0, 0.0, 0.0, 0.0)
        self.vao.render(mode=self.ctx.TRIANGLE_STRIP)
        raw = np.frombuffer(self.fbo.read(components=4, dtype="f1"), dtype=np.uint8)
        raw = raw.reshape(self.height, self.width, 4)
        # OpenGL origin is bottom-left.
        raw = np.flipud(raw)
        rgb = raw[:, :, :3].copy()
        depth = raw[:, :, 3].copy()
        mask = np.where(depth > 0, 255, 0).astype(np.uint8)
        return rgb, depth, mask
