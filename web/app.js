(() => {
  "use strict";

  const config = window.PORTAL_CONFIG || {};
  const demo = config.demo === true;
  const $ = (id) => document.getElementById(id);
  const phases = {
    off: ["Apagado", "El mundo está descansando", "Enciéndelo cuando quieras jugar. Se apagará automáticamente cuando no quede nadie."],
    starting: ["Iniciando", "Una chispa para empezar", "La solicitud de encendido está en marcha. Puedes dejar esta página abierta."],
    booting: ["Iniciando", "La máquina está despertando", "Estamos esperando a que los servicios del servidor estén disponibles."],
    loading: ["Cargando", "El mundo está tomando forma", "Minecraft está cargando. El tiempo depende del mundo y de sus plugins."],
    ready: ["En línea", "La aventura te espera", "El servidor y Pelican están listos. Copia la dirección y entra desde Minecraft."],
    stopping: ["Apagando", "Guardando la última aventura", "Espera a que termine el apagado antes de volver a encenderlo."],
    blocked: ["En pausa", "Por ahora, toca descansar", "El encendido está temporalmente deshabilitado. Revisa el mensaje del servidor."],
    error: ["Revisar", "El servidor necesita atención", "No pudimos completar la operación. Puedes volver a consultar el estado."],
  };
  const stageOrder = ["starting", "booting", "loading", "ready"];
  let password = "";
  let authenticated = false;
  let snapshot = null;
  let pollTimer = null;
  let redirectTimer = null;
  let redirectDismissed = false;
  let requesting = false;
  let demoStartedAt = null;
  let demoStoppedAt = null;
  let gameTimer = null;
  let gameScore = 0;
  let gameEndsAt = 0;
  let litTile = -1;
  let pollingGeneration = 0;

  function notice(message, kind = "error") {
    $("notice").textContent = message;
    $("notice").dataset.kind = kind;
    $("notice").hidden = !message;
  }

  function normalizeBase(value) {
    const url = new URL(value || "/", window.location.href);
    const local = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
    if (url.protocol !== "https:" && !(url.protocol === "http:" && local)) {
      throw new Error("La API debe usar HTTPS. HTTP solo está permitido para desarrollo local.");
    }
    return url.href.replace(/\/$/, "");
  }

  function safePanelUrl(value) {
    try {
      const url = new URL(value);
      if (!["https:", "http:"].includes(url.protocol) || url.username || url.password) return null;
      return url.href;
    } catch { return null; }
  }

  function demoState() {
    const elapsed = demoStartedAt ? Date.now() - demoStartedAt : -1;
    const phase = demoStoppedAt ? (Date.now() - demoStoppedAt < 5000 ? "stopping" : "off") : elapsed < 0 ? "off" : elapsed < 4000 ? "starting" : elapsed < 9000 ? "booting" : elapsed < 22000 ? "loading" : "ready";
    return {
      phase,
      players: 0,
      usedHours: 12.4,
      maxHours: 180,
      minecraftAddress: "servidor-de-ejemplo:25565",
      panelUrl: "",
      message: "",
      updatedAt: new Date().toISOString(),
    };
  }

  async function api(path, method = "GET", payload = null) {
    if (demo) {
      if (path === "start" && (!demoStartedAt || demoStoppedAt)) { demoStartedAt = Date.now(); demoStoppedAt = null; }
      if (path === "stop" && !demoStoppedAt) demoStoppedAt = Date.now();
      return demoState();
    }
    const base = normalizeBase(config.apiBaseUrl);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch(`${base}/api/${path}`, {
        method,
        body: payload ? JSON.stringify(payload) : undefined,
        headers: { "X-Portal-Password": password, "Accept": "application/json", "Content-Type": "application/json" },
        cache: "no-store",
        credentials: "omit",
        signal: controller.signal,
      });
      let body;
      try { body = await response.json(); } catch { body = {}; }
      if (response.status === 401) {
        const error = new Error("La contraseña no es válida o cambió. Vuelve a entrar.");
        error.unauthorized = true;
        throw error;
      }
      if (!response.ok) {
        if (body.phase && phases[body.phase]) render(body);
        const fallback = response.status === 429 ? "Hay un límite activo. Espera antes de volver a intentar." : response.status === 409 ? "El servidor está cambiando de estado. Espera un momento." : "No pudimos consultar el servidor. Inténtalo de nuevo.";
        throw new Error(typeof body.message === "string" ? body.message : fallback);
      }
      if (!phases[body.phase]) throw new Error("La API devolvió un estado desconocido. Revisa su configuración.");
      return body;
    } catch (error) {
      if (error.name === "AbortError") throw new Error("La consulta está tardando demasiado. Volveremos a consultar sin repetir la operación.");
      if (error instanceof TypeError) throw new Error("No hay conexión con la API. Revisa tu conexión o vuelve a intentarlo.");
      throw error;
    } finally { clearTimeout(timeout); }
  }

  function cancelRedirect(dismiss = true) {
    clearInterval(redirectTimer);
    redirectTimer = null;
    redirectDismissed = dismiss;
    $("redirect-notice").hidden = true;
  }

  function startRedirect(url) {
    if (redirectTimer || redirectDismissed) return;
    let remaining = 10;
    $("redirect-notice").hidden = false;
    const text = () => { $("redirect-text").textContent = demo ? `Demo: simulación de redirección en ${remaining} s.` : `Abriremos Pelican en ${remaining} s.`; };
    text();
    redirectTimer = setInterval(() => {
      remaining -= 1;
      text();
      if (remaining <= 0) {
        cancelRedirect();
        if (demo) notice("Demostración terminada. En el despliegue real se abriría Pelican.", "success");
        else window.location.assign(url);
      }
    }, 1000);
  }

  function render(state) {
    snapshot = state;
    const phase = phases[state.phase] ? state.phase : "error";
    const [label, title, description] = phases[phase];
    $("status-badge").textContent = demo ? `Demo · ${label}` : label;
    $("status-badge").dataset.phase = phase;
    $("state-title").textContent = title;
    $("state-copy").textContent = typeof state.message === "string" && state.message ? state.message : description;
    const choices = state.servers || [{ id: 'paper', name: 'Mundo habitual' }];
    const ids = choices.map(item => item.id).join(',');
    if ($("server-select").dataset.catalog !== ids) {
      $("server-select").replaceChildren(...choices.map(item => {
        const option = document.createElement('option');
        option.value = item.id; option.textContent = item.name; return option;
      }));
      $("server-select").dataset.catalog = ids;
      $("server-select").value = state.selectedServer || 'paper';
    }
    $("server-select").disabled = requesting || !['off', 'blocked'].includes(phase);
    if (phase !== 'off') $("server-select").value = state.selectedServer || 'paper';
    const current = stageOrder.indexOf(phase);
    document.querySelectorAll("[data-stage]").forEach((item, index) => {
      item.classList.toggle("done", current >= 0 && (index < current || phase === "ready"));
      item.classList.toggle("current", current === index && phase !== "ready");
      if (current === index) item.setAttribute("aria-current", "step");
      else item.removeAttribute("aria-current");
    });
    const waiting = ["starting", "booting", "loading"].includes(phase);
    $("start-button").hidden = phase === "ready";
    $("start-button").disabled = requesting || waiting || ["stopping", "blocked"].includes(phase);
    $("start-button").firstChild.textContent = waiting ? "Encendido en curso " : phase === "stopping" ? "Apagado en curso " : phase === "blocked" ? "Encendido deshabilitado " : "Encender servidor ";
    const canStop = ["ready", "starting", "booting", "loading", "error"].includes(phase);
    $("stop-button").hidden = !canStop;
    $("stop-button").disabled = requesting;
    $("confirm-stop").disabled = requesting;
    if (!canStop) $("stop-confirmation").hidden = true;
    const address = typeof state.minecraftAddress === "string" ? state.minecraftAddress : "";
    $("minecraft-address").textContent = address || "Disponible al iniciar";
    $("copy-address").hidden = !address;
    $("players").textContent = Number.isFinite(state.players) && phase === "ready" ? String(state.players) : "—";
    const hours = Number.isFinite(state.usedHours) ? state.usedHours.toLocaleString("es-CL", { maximumFractionDigits: 1 }) : "—";
    $("hours").textContent = `${hours}${Number.isFinite(state.maxHours) ? ` / ${state.maxHours}` : ""} h`;
    const date = new Date(typeof state.updatedAt === "number" ? state.updatedAt * 1000 : state.updatedAt);
    $("updated-at").textContent = Number.isNaN(date.getTime()) ? "Estado actualizado" : `Actualizado ${date.toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit" })}`;
    const panelUrl = safePanelUrl(state.panelUrl);
    $("panel-link").hidden = phase !== "ready" || !panelUrl || demo;
    if (panelUrl) $("panel-link").href = panelUrl;
    else $("panel-link").removeAttribute("href");
    if (phase === "ready" && (panelUrl || demo) && !$("games-accordion").open && $("stop-confirmation").hidden) startRedirect(panelUrl);
    else if (phase !== "ready") {
      cancelRedirect(false);

    }
  }

  function showLogin() {
    authenticated = false;
    password = "";
    pollingGeneration += 1;
    clearTimeout(pollTimer);
    cancelRedirect();
    stopGame();
    $("login-form").hidden = false;
    $("dashboard").hidden = true;
    $("stop-confirmation").hidden = true;
    $("status-badge").textContent = "Sin consultar";
    delete $("status-badge").dataset.phase;
    $("password").value = "";
    $("password").type = "password";
    $("reveal-password").textContent = "Ver";
    $("reveal-password").setAttribute("aria-label", "Mostrar contraseña");
    $("reveal-password").setAttribute("aria-pressed", "false");
    $("password").focus();
  }

  function handleError(error) {
    if (error.unauthorized) showLogin();
    notice(error.message || "Algo salió mal. Inténtalo nuevamente.");
  }

  function schedulePoll() {
    clearTimeout(pollTimer);
    if (!authenticated) return;
    const generation = pollingGeneration;
    pollTimer = setTimeout(async () => {
      try {
        const state = await api("status");
        if (!authenticated || generation !== pollingGeneration) return;
        render(state);
        notice("");
      } catch (error) {
        if (authenticated && generation === pollingGeneration) handleError(error);
      } finally { if (authenticated && generation === pollingGeneration) schedulePoll(); }
    }, demo ? 1500 : 12000);
  }

  $("login-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (requesting) return;
    password = $("password").value;
    if (!password) return;
    requesting = true;
    $("login-button").disabled = true;
    notice("");
    try {
      const state = await api("status");
      authenticated = true;
      pollingGeneration += 1;
      redirectDismissed = false;
      $("password").value = "";
      $("login-form").hidden = true;
      $("dashboard").hidden = false;
      requesting = false;
      render(state);
      schedulePoll();
      (state.phase === "ready" && !$("panel-link").hidden ? $("panel-link") : $("logout-button")).focus();
    } catch (error) { password = ""; handleError(error); }
    finally { requesting = false; $("login-button").disabled = false; }
  });

  $("start-button").addEventListener("click", async () => {
    if (requesting || !authenticated) return;
    requesting = true;
    const generation = ++pollingGeneration;
    clearTimeout(pollTimer);
    $("start-button").disabled = true;
    notice("");
    try {
      const state = await api("start", "POST", { server: $("server-select").value || "paper" });
      if (authenticated && generation === pollingGeneration) render(state);
    }
    catch (error) { if (authenticated && generation === pollingGeneration) handleError(error); }
    finally {
      requesting = false;
      if (authenticated && snapshot) render(snapshot);
      schedulePoll();
    }
  });

  $("stop-button").addEventListener("click", () => {
    if (!authenticated || requesting) return;
    cancelRedirect();
    const players = Number.isFinite(snapshot?.players) ? snapshot.players : 0;
    $("stop-warning").textContent = `${players > 0 ? `Hay ${players} jugador(es) en línea. Se desconectarán. ` : ""}Se guardará el mundo y se apagará la máquina. Pelican dejará de estar disponible.`;
    $("stop-confirmation").hidden = false;
    $("confirm-stop").focus();
  });
  $("cancel-stop").addEventListener("click", () => {
    $("stop-confirmation").hidden = true;
    $("stop-button").focus();
  });
  $("confirm-stop").addEventListener("click", async () => {
    if (requesting || !authenticated || $("stop-confirmation").hidden) return;
    requesting = true;
    const generation = ++pollingGeneration;
    clearTimeout(pollTimer);
    cancelRedirect();
    notice("");
    if (snapshot) render(snapshot);
    try {
      const state = await api("stop", "POST");
      if (authenticated && generation === pollingGeneration) {
        $("stop-confirmation").hidden = true;
        render(state);
      }
    } catch (error) { if (authenticated && generation === pollingGeneration) handleError(error); }
    finally {
      requesting = false;
      if (authenticated && snapshot) render(snapshot);
      schedulePoll();
    }
  });

  $("reveal-password").addEventListener("click", () => {
    const visible = $("password").type === "password";
    $("password").type = visible ? "text" : "password";
    $("reveal-password").textContent = visible ? "Ocultar" : "Ver";
    $("reveal-password").setAttribute("aria-label", visible ? "Ocultar contraseña" : "Mostrar contraseña");
    $("reveal-password").setAttribute("aria-pressed", String(visible));
  });
  $("logout-button").addEventListener("click", () => { notice(""); showLogin(); });
  $("cancel-redirect").addEventListener("click", () => cancelRedirect());
  $("copy-address").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(snapshot.minecraftAddress);
      notice("Dirección copiada. Pégala en Multijugador → Conexión directa.", "success");
    } catch { notice("No se pudo copiar automáticamente. Selecciona la dirección y cópiala."); }
  });

  const tiles = Array.from({ length: 9 }, (_, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "spark-tile";
    button.disabled = true;
    button.textContent = "✦";
    button.setAttribute("aria-label", `Bloque ${index + 1}`);
    button.addEventListener("click", () => {
      if (!gameTimer || index !== litTile) return;
      gameScore += 1;
      lightTile();
      updateScore();
    });
    $("game-grid").append(button);
    return button;
  });

  function lightTile() {
    const previous = litTile;
    do { litTile = Math.floor(Math.random() * tiles.length); } while (litTile === previous);
    tiles.forEach((tile, index) => {
      tile.classList.toggle("lit", index === litTile);
      tile.setAttribute("aria-label", `Bloque ${index + 1}${index === litTile ? ", chispa encendida" : ""}`);
    });
  }

  function updateScore() {
    const seconds = Math.max(0, Math.ceil((gameEndsAt - Date.now()) / 1000));
    $("game-score").textContent = `${gameScore} chispas · ${seconds} segundos`;
  }

  function stopGame() {
    clearInterval(gameTimer);
    gameTimer = null;
    litTile = -1;
    tiles.forEach((tile, index) => {
      tile.disabled = true;
      tile.classList.remove("lit");
      tile.setAttribute("aria-label", `Bloque ${index + 1}`);
    });
    $("game-button").textContent = "Jugar otra ronda";
    $("game-score").textContent = `${gameScore} chispas recogidas. La consulta del servidor continúa por separado.`;
  }

  $("game-button").addEventListener("click", () => {
    if (gameTimer) { stopGame(); return; }
    gameScore = 0;
    gameEndsAt = Date.now() + 25000;
    tiles.forEach((tile) => { tile.disabled = false; });
    $("game-button").textContent = "Terminar ronda";
    lightTile();
    updateScore();
    gameTimer = setInterval(() => {
      if (Date.now() >= gameEndsAt) stopGame();
      else updateScore();
    }, 1000);
  });

  let cpsRound = null;
  let cpsTimer = null;
  let runner = null;
  let runnerFrame = null;
  let lastFrame = 0;
  let fireTimer = null;

  function updateCps() {
    if (!cpsRound) return;
    const result = cpsRound.result(Date.now());
    $("cps-rate").textContent = `${result.cps.toLocaleString("es-CL", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} CPS`;
    $("cps-time").textContent = `${(result.remaining / 1000).toFixed(1).replace(".", ",")} s`;
    // Keep the live region quiet until the round ends.
    if (result.done) finishCps(false);
  }
  function finishCps(interrupted) {
    if (!cpsRound) return;
    const result = cpsRound.result(Date.now());
    clearInterval(cpsTimer);
    cpsTimer = null;
    cpsRound = null;
    $("cps-target").disabled = true;
    $("cps-start").disabled = false;
    $("cps-start").textContent = "Otra ronda de 15 segundos";
    $("cps-score").textContent = interrupted ? "Ronda interrumpida. Puedes empezar de nuevo cuando quieras." : `${result.clicks} clics en 15 segundos · ${(result.clicks / 15).toFixed(2).replace(".", ",")} CPS. ¡Esa llama está viva!`;
  }
  $("cps-start").addEventListener("click", () => {
    if (cpsRound) return;
    cancelRedirect();
    cpsRound = new window.FogataGameRules.ClickRound(Date.now());
    $("cps-start").disabled = true;
    $("cps-target").disabled = false;
    $("cps-score").textContent = "¡Ahora! Pulsa la llama tantas veces como puedas.";
    $("cps-target").focus();
    updateCps();
    cpsTimer = setInterval(updateCps, 50);
  });
  $("cps-target").addEventListener("click", () => {
    if (!cpsRound) return;
    cpsRound.click(Date.now());
    updateCps();
  });

  function drawRunner() {
    $("runner-hero").style.bottom = `${28 + runner.y}px`;
    $("runner-obstacle").style.left = `${runner.obstacle}%`;
    $("runner-distance").textContent = `${Math.floor(runner.distance)} m`;
  }
  function finishRunner(interrupted = false) {
    if (!runner) return;
    cancelAnimationFrame(runnerFrame);
    runnerFrame = null;
    $("runner-start").textContent = "Volver a saltar";
    $("runner-score").textContent = interrupted ? "Brasa en pausa. Empieza otra carrera cuando quieras." : `Llegaste a ${Math.floor(runner.distance)} m. ¡Un salto más la próxima vez!`;
    runner = null;
  }
  function animateRunner(now) {
    if (!runner) return;
    runner.step((now - lastFrame) / 1000);
    lastFrame = now;
    drawRunner();
    if (runner.over) finishRunner();
    else runnerFrame = requestAnimationFrame(animateRunner);
  }
  $("runner-start").addEventListener("click", () => {
    if (runner) { finishRunner(true); return; }
    cancelRedirect();
    runner = new window.FogataGameRules.Runner();
    lastFrame = performance.now();
    $("runner-start").textContent = "Terminar carrera";
    $("runner-score").textContent = "¡Salta los troncos!";
    $("runner-track").focus();
    drawRunner();
    runnerFrame = requestAnimationFrame(animateRunner);
  });
  $("runner-track").addEventListener("click", () => { if (runner) runner.jump(); });
  $("runner-track").addEventListener("keydown", (event) => {
    if (![" ", "ArrowUp"].includes(event.key)) return;
    event.preventDefault();
    if (!event.repeat && runner) runner.jump();
  });
  // Native buttons produce a click for Enter and touch, too.
  $("campfire").addEventListener("click", () => {
    clearTimeout(fireTimer);
    $("campfire").classList.add("stoked");
    $("fire-caption").textContent = "ASÍ SE MANTIENE VIVA UNA BUENA FOGATA";
    fireTimer = setTimeout(() => {
      $("campfire").classList.remove("stoked");
      $("fire-caption").textContent = "UN SOPLIDO PARA AVIVAR LA LLAMA · HAZ CLIC";
    }, 1200);
  });
  function pauseGames() {
    if (gameTimer) stopGame();
    finishCps(true);
    finishRunner(true);
  }
  $("games-accordion").addEventListener("toggle", () => {
    if ($("games-accordion").open) cancelRedirect();
    else pauseGames();
  });
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) pauseGames();
  });

  if (demo) {
    $("demo-banner").hidden = false;
    $("login-hint").textContent = "Demo local: usa cualquier contraseña. No se envía ni guarda.";
  } else if (!config.apiBaseUrl) {
    $("login-button").disabled = true;
    notice("Falta configurar apiBaseUrl. El despliegue debe generar config.js con la URL de la API.");
  }

  window.addEventListener("pagehide", () => {
    clearTimeout(pollTimer);
    cancelRedirect();
    pauseGames();
    clearTimeout(fireTimer);
    $("campfire").classList.remove("stoked");
    password = "";
    authenticated = false;
    pollingGeneration += 1;
  });
  window.addEventListener("pageshow", (event) => {
    if (event.persisted) showLogin();
  });
})();
