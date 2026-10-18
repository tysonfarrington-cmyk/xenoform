/* Live tier. A WebGL1 raymarch of the liquid body, so it runs on integrated
   GPUs and on SwiftShader. WebGPU is probed and then ignored; the march is the
   picture that always exists. Edits are read from the desk every frame. */
(function () {
  const FORMS = ["sphere", "rocket", "bulb", "octopus", "tower", "scream", "ring", "tree", "coin", "lion"];
  const PALETTES = {
    violet: { flesh: [0.42, 0.16, 0.48], metal: [0.78, 0.72, 0.95], fog: [0.05, 0.03, 0.07] },
    "grey-green": { flesh: [0.22, 0.32, 0.26], metal: [0.72, 0.8, 0.74], fog: [0.03, 0.05, 0.04] },
    gold: { flesh: [0.48, 0.26, 0.08], metal: [0.96, 0.78, 0.38], fog: [0.06, 0.04, 0.02] },
    bronze: { flesh: [0.4, 0.18, 0.1], metal: [0.82, 0.52, 0.32], fog: [0.05, 0.03, 0.02] },
    neutral: { flesh: [0.34, 0.26, 0.24], metal: [0.8, 0.78, 0.74], fog: [0.03, 0.03, 0.035] },
  };

  const VERT = "attribute vec2 a;void main(){gl_Position=vec4(a,0.0,1.0);}";
  const FRAG = [
    "precision mediump float;",
    "uniform vec2 uRes;",
    "uniform vec4 uB0,uB1,uB2,uB3,uB4,uB5;",
    "uniform vec3 uFlesh,uMetal,uFog,uCam;",
    "uniform float uSpec,uNoise,uFlash,uTime;",
    "float sd(vec3 p){",
    "  float d=length(p-uB0.xyz)-uB0.w;",
    "  d=min(d,length(p-uB1.xyz)-uB1.w);",
    "  d=min(d,length(p-uB2.xyz)-uB2.w);",
    "  d=min(d,length(p-uB3.xyz)-uB3.w);",
    "  d=min(d,length(p-uB4.xyz)-uB4.w);",
    "  d=min(d,length(p-uB5.xyz)-uB5.w);",
    "  float n=sin(p.x*6.0+uTime)*sin(p.y*5.0)*sin(p.z*6.0);",
    "  return d-n*uNoise;",
    "}",
    "vec3 grad(vec3 p){",
    "  vec2 e=vec2(0.012,0.0);",
    "  return normalize(vec3(sd(p+e.xyy)-sd(p-e.xyy),sd(p+e.yxy)-sd(p-e.yxy),sd(p+e.yyx)-sd(p-e.yyx)));",
    "}",
    "void main(){",
    "  vec2 uv=(gl_FragCoord.xy/uRes)*2.0-1.0;",
    "  uv.x*=uRes.x/uRes.y;",
    "  float yaw=uCam.x,pitch=uCam.y,dist=uCam.z;",
    "  vec3 eye=vec3(sin(yaw)*dist,0.28+sin(pitch)*0.55,cos(yaw)*dist);",
    "  vec3 target=vec3(0.0,0.02,0.0);",
    "  vec3 forward=normalize(target-eye);",
    "  vec3 right=normalize(cross(forward,vec3(0.0,1.0,0.0)));",
    "  vec3 up=cross(right,forward);",
    "  vec3 rd=normalize(forward+right*uv.x*0.85+up*uv.y*0.85);",
    "  float t=0.02;",
    "  float hit=0.0;",
    "  vec3 p=eye;",
    "  for(int i=0;i<28;i++){",
    "    p=eye+rd*t;",
    "    float d=sd(p);",
    "    if(d<0.012){hit=1.0;break;}",
    "    t+=max(d,0.02);",
    "    if(t>8.0)break;",
    "  }",
    "  float horizon=smoothstep(0.05,0.85,gl_FragCoord.y/uRes.y);",
    "  vec3 bg=mix(uFog*0.7,uFog*2.4,horizon);",
    "  vec3 color=bg;",
    "  if(hit>0.5){",
    "    vec3 n=grad(p);",
    "    vec3 light=normalize(vec3(0.45,0.85,0.35));",
    "    float nd=clamp(dot(n,light),0.0,1.0);",
    "    float fill=clamp(dot(n,normalize(vec3(-0.35,0.25,0.7))),0.0,1.0);",
    "    float fres=pow(1.0-clamp(dot(n,-rd),0.0,1.0),2.2);",
    "    vec3 ref=reflect(rd,n);",
    "    float spec=pow(clamp(dot(ref,light),0.0,1.0),24.0)*uSpec;",
    "    vec3 body=mix(uFlesh,uMetal,fres);",
    "    color=body*(0.42+0.7*nd+0.28*fill)+uMetal*spec;",
    "    color=mix(color,bg,clamp(t/7.0,0.0,0.55));",
    "  }",
    "  color+=uFlash;",
    "  color*=1.0-0.18*dot(uv,uv);",
    "  gl_FragColor=vec4(clamp(color,0.0,1.0),1.0);",
    "}",
  ].join("");

  function layout(form) {
    const id = String(form || "sphere");
    const base = {
      sphere: [[0, 0.02, 0, 0.5], [0.38, 0.18, 0.05, 0.26], [-0.34, 0.12, 0.12, 0.24], [0.04, -0.32, 0, 0.22], [0.12, 0.36, -0.16, 0.16], [-0.1, -0.08, 0.32, 0.15]],
      rocket: [[0, 0.42, 0, 0.2], [0, 0.1, 0, 0.28], [0, -0.28, 0, 0.22], [0.22, -0.42, 0, 0.1], [-0.22, -0.42, 0, 0.1], [0, 0.68, 0, 0.1]],
      bulb: [[0, 0.12, 0, 0.46], [0, -0.42, 0, 0.1], [0.16, 0.28, 0.05, 0.14], [-0.16, 0.26, 0.08, 0.12], [0.05, -0.16, 0.2, 0.1], [0, 0.48, 0, 0.08]],
      octopus: [[0, 0, 0, 0.28], [0.46, 0.05, 0, 0.12], [-0.42, 0.08, 0.1, 0.12], [0.1, 0.4, -0.1, 0.12], [-0.08, -0.42, 0.12, 0.12], [0.05, 0.05, 0.46, 0.12]],
      tower: [[0, -0.4, 0, 0.34], [0, -0.05, 0, 0.26], [0, 0.28, 0, 0.2], [0, 0.52, 0, 0.12], [0.16, 0.16, 0.08, 0.08], [-0.14, -0.2, 0.1, 0.08]],
      scream: [[0, 0.05, 0, 0.22], [0.5, 0.1, 0, 0.16], [-0.48, 0.08, 0.05, 0.16], [0.2, 0.36, -0.1, 0.12], [-0.22, -0.28, 0.1, 0.14], [0, -0.08, 0.28, 0.1]],
      ring: [[0.42, 0, 0, 0.14], [-0.2, 0.36, 0, 0.14], [-0.34, -0.24, 0.05, 0.14], [0.16, -0.38, 0, 0.14], [0, 0, 0, 0.1], [0.05, 0.08, 0.2, 0.08]],
      tree: [[0, -0.35, 0, 0.16], [0, 0.05, 0, 0.28], [0.28, 0.22, 0, 0.16], [-0.26, 0.18, 0.08, 0.16], [0, 0.42, 0, 0.18], [0.05, 0.1, 0.22, 0.1]],
      coin: [[0, 0, 0, 0.42], [0, 0, 0.08, 0.3], [0.05, 0.02, -0.02, 0.12], [-0.2, 0.1, 0.12, 0.08], [0.18, -0.12, 0.1, 0.08], [0, 0.2, 0.16, 0.06]],
      lion: [[0, 0.05, 0, 0.32], [0.34, 0.2, 0, 0.18], [-0.32, 0.18, 0.06, 0.18], [0, 0.38, 0, 0.16], [0.12, -0.28, 0.08, 0.12], [-0.1, -0.26, 0.1, 0.12]],
    };
    if (base[id]) return base[id].map((row) => row.slice());
    const spin = (id.length * 0.7) % 6.28;
    return base.sphere.map((row, index) => {
      const c = Math.cos(spin + index);
      const s = Math.sin(spin + index * 0.5);
      return [row[0] * c - row[2] * s, row[1], row[0] * s + row[2] * c, row[3]];
    });
  }

  function mixBalls(a, b, blend, scatter, squash) {
    const out = [];
    for (let i = 0; i < 6; i++) {
      const left = a[i];
      const right = b[i];
      const k = blend;
      let x = left[0] * (1 - k) + right[0] * k;
      let y = left[1] * (1 - k) + right[1] * k;
      let z = left[2] * (1 - k) + right[2] * k;
      let r = left[3] * (1 - k) + right[3] * k;
      const dir = Math.hypot(x, y, z) || 1;
      x += (x / dir) * scatter;
      y += (y / dir) * scatter * 0.6;
      z += (z / dir) * scatter;
      y *= squash;
      r *= 0.85 + 0.2 * (1 - Math.min(scatter, 1));
      out.push([x, y, z, Math.max(0.05, r)]);
    }
    return out;
  }

  function createGate() {
    const times = [];
    return {
      allow(t, want) {
        for (let i = times.length - 1; i >= 0; i--) {
          if (t - times[i] >= 1) times.splice(i, 1);
        }
        if (!want) return false;
        if (times.length >= 3) return false;
        times.push(t);
        return true;
      },
    };
  }

  function sceneAt(scenes, t) {
    const list = scenes || [];
    if (!list.length) return { index: 0, start: 0, end: 1e9, form: "sphere", edit: "ribbon", shot: "wide", move: "orbit" };
    for (let i = 0; i < list.length; i++) {
      const scene = list[i];
      const last = i === list.length - 1;
      if ((scene.start <= t && t < scene.end) || (last && t >= scene.start)) return scene;
    }
    return list[0];
  }

  function blendAt(scene, next, t, beats) {
    if (!next) return 0;
    const span = Math.max(0.2, scene.end - scene.start);
    const fade = Math.min(0.55, span * 0.34);
    let cut = scene.end;
    const inside = (beats || []).filter((beat) => beat > scene.start && beat <= scene.end);
    if (inside.length) cut = inside[inside.length - 1];
    const anchors = scene.retime && scene.retime.anchors_s;
    if (anchors && anchors.length >= 2 && anchors[1].length >= 2) {
      const dst = Number(anchors[1][1]);
      if (dst > scene.start && dst <= scene.end) cut = dst;
    }
    const begin = Math.max(scene.start, cut - fade);
    if (t <= begin) return 0;
    if (t >= scene.end) return 1;
    return Math.max(0, Math.min(1, (t - begin) / Math.max(0.05, scene.end - begin)));
  }

  function transitionMods(name, blend) {
    const edit = String(name || "ribbon");
    let scatter = 0;
    let squash = 1;
    let dive = 0;
    let harden = 0;
    let step = blend;
    if (edit === "snap" || edit === "hard cut") step = blend > 0.5 ? 1 : 0;
    if (edit === "droplet-burst" || edit === "spike-burst") {
      const peak = Math.sin(Math.min(1, blend) * Math.PI);
      scatter = peak * (edit === "spike-burst" ? 0.55 : 0.42);
    }
    if (edit === "droplet-gather") scatter = (1 - blend) * 0.35;
    if (edit === "dive-splash") {
      dive = Math.sin(Math.min(1, blend) * Math.PI);
      squash = 1 - dive * 0.35;
      scatter = Math.max(0, blend - 0.45) * 0.5;
    }
    if (edit === "pour-harden" || edit === "dissolve") {
      harden = blend;
      step = blend * blend * (3 - 2 * blend);
    }
    if (edit === "grow-out") step = blend;
    if (edit === "fly-through") dive = blend;
    if (edit === "swim") step = blend * 0.65;
    if (edit === "bolt-strike") scatter = blend > 0.72 && blend < 0.9 ? 0.18 : 0;
    if (edit === "ribbon") scatter = Math.sin(blend * Math.PI) * 0.12;
    return { blend: step, scatter, squash, dive, harden };
  }

  function cameraFor(scene, t, energy, dive) {
    const shot = scene.shot || "wide";
    const move = scene.move || "orbit";
    let dist = shot === "macro" ? 1.15 : shot === "close" ? 1.45 : shot === "overhead" ? 1.75 : 1.95;
    let pitch = shot === "overhead" ? 1.15 : 0.15;
    let yaw = t * (0.25 + energy * 0.8);
    if (move === "hold") yaw = 0.4;
    if (move === "push in") dist -= Math.min(0.45, (t % 4) * 0.08);
    if (move === "pull back") dist += 0.25;
    if (move === "follow") yaw = Math.sin(t * 0.6) * 0.8;
    dist -= dive * 0.55;
    dist *= 1.15 - Math.min(0.35, energy * 0.25);
    return [yaw, pitch, Math.max(1.05, dist)];
  }

  function sampleDrive(drive, t) {
    if (!drive || !drive.bass || !drive.bass.length) {
      const pulse = 0.35 + 0.25 * Math.sin(t * 6);
      return { bass: pulse, mid: 0.3, high: 0.2, onset: Math.max(0, Math.sin(t * 8)) };
    }
    const fps = drive.fps || 20;
    const index = Math.max(0, Math.min(drive.bass.length - 1, Math.floor(t * fps)));
    return {
      bass: drive.bass[index] || 0,
      mid: (drive.mid && drive.mid[index]) || 0,
      high: (drive.high && drive.high[index]) || 0,
      onset: (drive.onset && drive.onset[index]) || 0,
    };
  }

  function slider(state, key, fallback) {
    const value = state && state.sliders ? state.sliders[key] : undefined;
    return value == null ? fallback : Number(value);
  }

  function compile(gl, type, source) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      const log = gl.getShaderInfoLog(shader);
      gl.deleteShader(shader);
      throw new Error(log || "shader");
    }
    return shader;
  }

  function create(canvas) {
    const gl = canvas.getContext("webgl", {
      alpha: false,
      antialias: false,
      preserveDrawingBuffer: true,
      powerPreference: "high-performance",
    });
    if (!gl) throw new Error("WebGL is missing");
    const program = gl.createProgram();
    gl.attachShader(program, compile(gl, gl.VERTEX_SHADER, VERT));
    gl.attachShader(program, compile(gl, gl.FRAGMENT_SHADER, FRAG));
    gl.linkProgram(program);
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
      throw new Error(gl.getProgramInfoLog(program) || "link");
    }
    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    const loc = (name) => gl.getUniformLocation(program, name);
    const uniforms = {
      res: loc("uRes"),
      balls: ["uB0", "uB1", "uB2", "uB3", "uB4", "uB5"].map(loc),
      flesh: loc("uFlesh"),
      metal: loc("uMetal"),
      fog: loc("uFog"),
      cam: loc("uCam"),
      spec: loc("uSpec"),
      noise: loc("uNoise"),
      flash: loc("uFlash"),
      time: loc("uTime"),
    };
    const gate = createGate();
    let webgpu = "unavailable";
    if (navigator.gpu) webgpu = "present, unused";

    function draw(t, frame) {
      const width = canvas.width;
      const height = canvas.height;
      gl.viewport(0, 0, width, height);
      gl.useProgram(program);
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      const attrib = gl.getAttribLocation(program, "a");
      gl.enableVertexAttribArray(attrib);
      gl.vertexAttribPointer(attrib, 2, gl.FLOAT, false, 0, 0);
      gl.uniform2f(uniforms.res, width, height);
      frame.balls.forEach((ball, index) => {
        gl.uniform4f(uniforms.balls[index], ball[0], ball[1], ball[2], ball[3]);
      });
      gl.uniform3fv(uniforms.flesh, frame.flesh);
      gl.uniform3fv(uniforms.metal, frame.metal);
      gl.uniform3fv(uniforms.fog, frame.fog);
      gl.uniform3fv(uniforms.cam, frame.cam);
      gl.uniform1f(uniforms.spec, frame.spec);
      gl.uniform1f(uniforms.noise, frame.noise);
      gl.uniform1f(uniforms.flash, frame.flash);
      gl.uniform1f(uniforms.time, t);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
    }

    function meanLuma() {
      const width = canvas.width;
      const height = canvas.height;
      const pixels = new Uint8Array(width * height * 4);
      gl.readPixels(0, 0, width, height, gl.RGBA, gl.UNSIGNED_BYTE, pixels);
      let sum = 0;
      let count = 0;
      const stride = Math.max(1, Math.floor((width * height) / 240)) * 4;
      for (let i = 0; i < pixels.length; i += stride) {
        sum += pixels[i] * 0.3 + pixels[i + 1] * 0.59 + pixels[i + 2] * 0.11;
        count += 1;
      }
      return sum / Math.max(1, count);
    }

    return { gl, draw, meanLuma, gate, webgpu };
  }

  function frameFor(state, t, gate) {
    const scenes = (state && state.scenes) || [];
    const beats = (state && state.beats) || [];
    const scene = sceneAt(scenes, t);
    const list = scenes.length ? scenes : [scene];
    const index = Math.max(0, list.indexOf(scene));
    const next = list[index + 1] || null;
    const raw = blendAt(scene, next, t, beats);
    const mods = transitionMods(scene.edit || scene.transition, raw);
    const env = sampleDrive(state && state.drive, t);
    const kick = slider(state, "kick", 0.5);
    const bass = slider(state, "bass", 0.5);
    const hats = slider(state, "hats", 0.5);
    const vocals = slider(state, "vocals", 0.5);
    const liquidity = slider(state, "liquidity", 0.5);
    const chaos = slider(state, "chaos", 0.5);
    const material = slider(state, "material", 0.5);
    const camera = slider(state, "camera", 0.5);
    const pulse = env.bass * (0.45 + bass) + env.onset * kick;
    let balls = mixBalls(layout(scene.form), layout(next ? next.form : scene.form), mods.blend, mods.scatter * (0.4 + chaos), mods.squash);
    const scale = 1.15 + pulse * 0.35;
    balls = balls.map((ball, i) => {
      const jiggle = chaos * 0.08 * Math.sin(t * 3 + i);
      return [ball[0] * scale + jiggle, ball[1] * scale, ball[2] * scale, ball[3] * scale];
    });
    const palette = PALETTES[(state && state.palette) || "violet"] || PALETTES.violet;
    const onBeat = (beats || []).some((beat) => Math.abs(beat - t) < 0.045);
    const flashMode = (state && state.flash) || "normal";
    const want = onBeat && flashMode !== "minimal";
    const allowed = gate ? gate.allow(t, want) : want;
    const flashScale = { soft: 0.04, normal: 0.08, hard: 0.14 }[flashMode] || 0.08;
    const bolt = String(scene.edit || "") === "bolt-strike";
    const flash = allowed ? Math.min(bolt ? 0.06 : 0.16, flashScale + (bolt ? 0 : env.high * 0.04)) : 0;
    return {
      balls,
      flesh: palette.flesh,
      metal: palette.metal,
      fog: palette.fog,
      cam: cameraFor(scene, t, camera, mods.dive + bass * 0.15),
      spec: 0.35 + material * 0.9 + hats * env.high * 0.4,
      noise: 0.012 + liquidity * 0.04 + vocals * env.mid * 0.02 + (1 - mods.harden) * 0.01,
      flash,
    };
  }

  const sessions = { current: null, raf: 0, audioCtx: null, record: null };

  function mount() {
    const canvas = document.getElementById("live-canvas");
    if (!canvas || !window.XENO_STATE) return null;
    if (sessions.current && sessions.current.canvas === canvas) return sessions.current;
    const engine = create(canvas);
    const session = { canvas, engine, started: performance.now(), playing: false };
    sessions.current = session;
    const loop = () => {
      if (sessions.current !== session) return;
      const state = window.XENO_STATE() || {};
      const audio = document.getElementById("live-audio");
      let t;
      if (audio && session.playing && !audio.paused) t = audio.currentTime || 0;
      else {
        const duration = Number(state.duration) || 12;
        t = ((performance.now() - session.started) / 1000) % duration;
      }
      const frame = frameFor(state, t, engine.gate);
      if (session.analyser) {
        const bins = new Uint8Array(session.analyser.frequencyBinCount);
        session.analyser.getByteFrequencyData(bins);
        const bass = bins.slice(0, 4).reduce((sum, value) => sum + value, 0) / (4 * 255);
        if (bass > 0.05) {
          frame.balls = frame.balls.map((ball) => [ball[0], ball[1], ball[2], ball[3] * (0.92 + bass * 0.2)]);
        }
      }
      engine.draw(t, frame);
      const note = document.getElementById("live-note");
      if (note && state.liveAiRequested && !state.liveAiPresent) {
        note.textContent = "Live+AI is not installed. Live is playing.";
      } else if (note && !note.dataset.lock) {
        note.textContent = session.recording ? "Recording." : "Live. Edits land on the next frame.";
      }
      sessions.raf = requestAnimationFrame(loop);
    };
    cancelAnimationFrame(sessions.raf);
    sessions.raf = requestAnimationFrame(loop);
    return session;
  }

  async function play() {
    const session = mount();
    const audio = document.getElementById("live-audio");
    if (!audio) return;
    const AudioCtx = window.AudioContext || window.webkitAudioContext;
    if (AudioCtx && !sessions.audioCtx) {
      const ctx = new AudioCtx();
      const source = ctx.createMediaElementSource(audio);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 64;
      const dest = ctx.createMediaStreamDestination();
      source.connect(analyser);
      analyser.connect(ctx.destination);
      analyser.connect(dest);
      sessions.audioCtx = ctx;
      sessions.dest = dest;
      if (session) session.analyser = analyser;
    }
    if (sessions.audioCtx && sessions.audioCtx.state === "suspended") await sessions.audioCtx.resume();
    await audio.play();
    if (session) session.playing = true;
  }

  function startRecord() {
    const session = sessions.current || mount();
    if (!session || !canvasStream(session)) return Promise.reject(new Error("This browser cannot record the canvas."));
    if (sessions.record) return Promise.resolve();
    const stream = session.canvas.captureStream(30);
    if (sessions.dest) {
      sessions.dest.stream.getAudioTracks().forEach((track) => stream.addTrack(track));
    }
    const type = MediaRecorder.isTypeSupported("video/webm;codecs=vp8") ? "video/webm;codecs=vp8" : "video/webm";
    const recorder = new MediaRecorder(stream, { mimeType: type });
    const chunks = [];
    recorder.ondataavailable = (event) => {
      if (event.data && event.data.size) chunks.push(event.data);
    };
    const done = new Promise((resolve) => {
      recorder.onstop = () => resolve(new Blob(chunks, { type: "video/webm" }));
    });
    recorder.start(200);
    sessions.record = { recorder, done };
    session.recording = true;
    return Promise.resolve();
  }

  function canvasStream(session) {
    return session && session.canvas && typeof session.canvas.captureStream === "function" && typeof MediaRecorder !== "undefined";
  }

  function stopRecord() {
    const current = sessions.record;
    sessions.record = null;
    if (sessions.current) sessions.current.recording = false;
    if (!current) return Promise.resolve(null);
    current.recorder.stop();
    return current.done;
  }

  function smoke(canvas) {
    const gate = createGate();
    const flashes = [0, 0.1, 0.2, 0.3].map((t) => gate.allow(t, true));
    const gateOk = flashes.filter(Boolean).length === 3 && flashes[3] === false;
    let engine;
    try {
      engine = create(canvas);
    } catch (error) {
      return { ok: false, error: String(error && error.message ? error.message : error), gateOk, webgpu: "unchecked" };
    }
    const samples = [];
    const state = {
      duration: 8,
      palette: "violet",
      flash: "normal",
      beats: [0.5, 1, 1.5, 2, 2.5],
      scenes: [
        { start: 0, end: 2, form: "sphere", edit: "pour-harden", shot: "wide", move: "orbit" },
        { start: 2, end: 4, form: "rocket", edit: "droplet-burst", shot: "close", move: "push in" },
        { start: 4, end: 8, form: "scream", edit: "dive-splash", shot: "macro", move: "follow" },
      ],
      sliders: { kick: 0.7, bass: 0.6, hats: 0.4, vocals: 0.5, liquidity: 0.7, chaos: 0.4, material: 0.8, camera: 0.6 },
      drive: { fps: 4, bass: [0.1, 0.8, 0.2, 0.9], mid: [0.2, 0.4, 0.5, 0.3], high: [0.1, 0.2, 0.6, 0.2], onset: [0, 1, 0, 1] },
    };
    for (let i = 0; i < 8; i++) {
      const time = i * 0.55;
      engine.draw(time, frameFor(state, time, engine.gate));
      samples.push(engine.meanLuma());
    }
    const luma = samples.reduce((sum, value) => sum + value, 0) / samples.length;
    const spread = Math.max.apply(null, samples) - Math.min.apply(null, samples);
    return {
      ok: luma > 14 && spread > 2 && gateOk,
      luma: Math.round(luma * 10) / 10,
      spread: Math.round(spread * 10) / 10,
      gateOk,
      webgpu: engine.webgpu,
      samples: samples.map((value) => Math.round(value)),
    };
  }

  window.XENO_LIVE = {
    mount,
    play,
    startRecord,
    stopRecord,
    recording: () => Boolean(sessions.record),
    smoke,
    createGate,
    frameFor,
    FORMS,
    PALETTES,
  };

  function bootSmoke() {
    if (!/liveSmoke=1/.test(location.search || "")) return;
    const canvas = document.createElement("canvas");
    canvas.width = 320;
    canvas.height = 180;
    canvas.id = "live-smoke-canvas";
    document.body.appendChild(canvas);
    const result = smoke(canvas);
    const pre = document.createElement("pre");
    pre.id = "live-smoke";
    pre.textContent = JSON.stringify(result);
    document.body.appendChild(pre);
    document.body.dataset.liveSmoke = result.ok ? "ok" : "fail";
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bootSmoke);
  else bootSmoke();
})();
