/* TransferAI - interfaz web.
 *
 * La página no decide nada del juego: muestra la pausa actual del grafo (su "tipo" elige la pantalla),
 * los eventos que emiten los agentes, y envía al servidor lo que escribe o elige el usuario.
 * Consulta /api/estado cada medio segundo mientras los agentes trabajan.
 */
"use strict";

// ---------------------------------------------------------------- UTILIDADES
const $ = (s) => document.querySelector(s);
const esc = (t) => String(t ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmt = (n) => (n === null || n === undefined || n === "" ? "-" : Number(n).toLocaleString("es-CL", { maximumFractionDigits: 2 }));
const IMG = {
  usuario: "img/director_usuario.png", club: "img/director_club.png", agente: "img/agente_jugador.png",
  manager: "img/manager.png", financiero: "img/financiero.png", fichaje: "img/fichaje.png", venta: "img/venta.png",
};
const POSICIONES = ["POR", "DFC", "LAT", "MED", "EXT", "DEL"];
const NOMBRE_POS = { POR: "Porteros", DFC: "Centrales", LAT: "Laterales", MED: "Mediocampistas", EXT: "Extremos", DEL: "Delanteros" };

const st = {
  desde: 0,              // cuántos eventos ya se recibieron
  generacion: 0,         // sube con cada respuesta enviada (descarta consultas viejas)
  esperando: false,      // se está enviando una respuesta
  ocupado: false,        // el grafo está trabajando
  rondaPendiente: false, // falta recibir la pausa que sigue a la última respuesta
  reproduciendo: false,  // al recargar la página: se reprocesan eventos sin mostrar ventanas
  pausa: null, juego: null, fin: false,
  vista: "menu", vistaPedida: null,
  eventosRonda: [], logAgentes: [], automaticas: [],
  escena: null, entrada: null, ultimaPausaEscena: null, asesor: null, notasConsejo: [],
  bandeja: [], mensajeSel: null, estadoClub: null, resumenFinal: null,
  cola: [], modalAbierto: false, cargandoTexto: "",
  verArbitro: true,
};

function aviso(texto, clase = "") {
  if (st.reproduciendo) return;
  const div = document.createElement("div");
  div.className = "aviso " + clase;
  div.textContent = texto;
  $("#avisos").appendChild(div);
  setTimeout(() => div.remove(), clase === "advertencia" || clase === "error" ? 7000 : 4500);
}

// ---------------------------------------------------------------- COMUNICACIÓN CON EL SERVIDOR
async function consultar() {
  const gen = st.generacion, enVuelo = st.esperando;
  try {
    const r = await fetch(`/api/estado?desde=${st.desde}`);
    const d = await r.json();
    st.desde = d.total;
    d.eventos.forEach(procesarEvento);
    st.ocupado = d.ocupado;
    if (d.juego) st.juego = d.juego;
    if (d.error) aviso(d.error, "error");
    if (!d.ocupado && !enVuelo && gen === st.generacion) {
      st.fin = d.fin;
      const cambio = JSON.stringify(d.pausa) !== JSON.stringify(st.pausa);
      if (st.rondaPendiente || cambio) {
        st.pausa = d.pausa;
        st.rondaPendiente = false;
        if (st.escena) st.escena.esperandoRival = false;
        alRecibirPausa();
      }
    }
    st.reproduciendo = false;
    actualizarBarra();
    actualizarCargando();
  } catch (e) { /* servidor ocupado o reiniciándose: se reintenta */ }
  setTimeout(consultar, st.ocupado || st.esperando || st.rondaPendiente ? 450 : 1500);
}

async function enviar(respuesta, cargando = "Procesando…") {
  if (st.esperando || st.ocupado) return;
  st.esperando = true;
  st.rondaPendiente = true;
  st.generacion++;
  st.eventosRonda = [];
  st.cargandoTexto = cargando;
  actualizarCargando();
  try {
    const r = await fetch("/api/responder", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ respuesta }),
    });
    if (!r.ok) aviso((await r.json()).error || "No se pudo enviar", "error");
  } finally {
    st.esperando = false;
    st.generacion++;
  }
}

async function nuevaPartida(club) {
  const r = await fetch("/api/nueva", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ club }),
  });
  if (!r.ok) { aviso((await r.json()).error, "error"); return; }
  Object.assign(st, { desde: 0, pausa: null, fin: false, vista: "menu", escena: null, rondaPendiente: true, generacion: st.generacion + 1 });
  st.cargandoTexto = `Cargando ${club}…`;
  document.body.classList.remove("sin-barra");
  $("#barra").classList.remove("oculto");
}

// ---------------------------------------------------------------- EVENTOS DE LOS AGENTES
function textoHerramienta(d) {
  const a = d.argumentos || {};
  if (d.herramienta === "buscar_jugadores") {
    const partes = [a.posicion || "jugadores"];
    if (a.edad_max) partes.push(`hasta ${a.edad_max} años`);
    if (a.valor_max) partes.push(`valor ≤ ${fmt(a.valor_max)} M€`);
    if (a.pie) partes.push(`pie ${a.pie}`);
    if (a.ordenar_por) partes.push(`ordenados por ${a.ordenar_por}`);
    return "🔎 Buscando " + partes.join(", ");
  }
  if (d.herramienta === "evaluar_encaje") return `📐 Evaluando encaje táctico (jugador ${a.id_jugador})`;
  return `🛠 ${d.herramienta}`;
}

function procesarEvento(e) {
  const { tipo, mensaje, datos } = e;
  st.eventosRonda.push(e);
  switch (tipo) {
    case "aviso":
      aviso(mensaje, "advertencia");
      if (st.escena && st.rondaPendiente) st.escena.rechazado = mensaje;
      break;
    case "error": aviso(mensaje, "error"); break;
    case "mensaje": aviso("📩 " + mensaje, "correo"); break;
    case "agente":
      st.logAgentes.push("▶ " + mensaje);
      st.cargandoTexto = mensaje + "…";
      break;
    case "herramienta":
      st.logAgentes.push(textoHerramienta(datos));
      st.cargandoTexto = textoHerramienta(datos);
      break;
    case "descarte": st.logAgentes.push("✖ " + mensaje); break;
    case "bandeja": st.bandeja = datos.mensajes || []; st.mensajeSel = null; break;
    case "estado_club": st.estadoClub = datos; break;
    case "resumen_ventana": st.resumenFinal = { titulo: mensaje, ...datos }; break;
    case "negociacion": st.entrada = { ultimo: datos.ultimo_mensaje || "", exigencia: datos.exigencia || "" }; break;
    case "interpretacion": if (st.escena) st.escena.entendido = mensaje; break;
    case "correccion_arbitro":
      if (datos.agente === "financiero") st.notasConsejo.push(mensaje);
      else if (st.escena) st.escena.notas.push(mensaje);
      break;
    case "mensaje_club":
      if (st.escena) {
        st.escena.rivalTexto = mensaje;
        st.escena.historial.push({ de: st.escena.rival, texto: mensaje });
        if (datos.contraoferta) st.escena.exigencia = datos.contraoferta;
      }
      break;
    case "consejo":
      if (st.reproduciendo) break;
      st.asesor = { agente: datos.agente, texto: mensaje, sugerencia: datos.sugerencia || "", notas: st.notasConsejo };
      st.notasConsejo = [];
      if (!st.reproduciendo) setTimeout(dibujarAsesor, 0);
      break;
    case "info":
      if (mensaje.startsWith("Mensaje enviado a")) ventana(`<h2>Mensaje enviado</h2><p>${esc(mensaje)}</p>`, "Volver al menú");
      else if (mensaje.includes("cerrada sin acuerdo")) ventana(`<h2>Sin acuerdo</h2>${ultimaFrase()}<p>${esc(mensaje)}</p>`);
      else if (!["Club cargado", "Diagnóstico listo"].some((x) => mensaje.startsWith(x))) aviso(mensaje);
      break;
    case "desempeno": ventanaDesempenoClub(datos); break;
    case "desempeno_jugador": if (datos.resultado !== "acuerdo") ventanaSinAcuerdoJugador(datos); break;
    case "fichaje": ventanaFichaje(mensaje, datos); break;
    case "venta": ventanaVenta(mensaje, datos); break;
  }
}

// ---------------------------------------------------------------- VENTANAS EMERGENTES
function ventana(html, textoBoton = "Continuar", clase = "") {
  if (st.reproduciendo) return;
  st.cola.push({ html: html + `<div class="acciones"><button class="boton" data-cerrar>${esc(textoBoton)}</button></div>`, clase });
  siguienteVentana();
}

function siguienteVentana() {
  if (st.modalAbierto || !st.cola.length) return;
  const { html, clase, alAbrir } = st.cola.shift();
  st.modalAbierto = true;
  const m = $("#modal");
  m.className = clase || "";
  m.innerHTML = html;
  $("#modal-fondo").classList.remove("oculto");
  m.querySelectorAll("[data-cerrar]").forEach((b) => b.addEventListener("click", cerrarVentana));
  if (alAbrir) alAbrir(m);
}

function cerrarVentana() {
  st.modalAbierto = false;
  $("#modal-fondo").classList.add("oculto");
  siguienteVentana();
}

/* Ventanas que dependen de una pausa del grafo (se responden con botones). */
function ventanaPausa(html, botones) {
  st.cola.unshift({
    html: html + `<div class="acciones">${botones.map((b, i) => `<button class="boton ${b.clase || ""}" data-i="${i}">${esc(b.texto)}</button>`).join("")}</div>`,
    alAbrir: (m) => m.querySelectorAll("[data-i]").forEach((el) => el.addEventListener("click", () => {
      cerrarVentana();
      botones[+el.dataset.i].accion();
    })),
  });
  siguienteVentana();
}

const ultimaFrase = () => (st.escena && st.escena.rivalTexto
  ? `<p><b>${esc(st.escena.rival)}:</b> “${esc(st.escena.rivalTexto)}”</p>` : "");

const bloqueDesempeno = (pct, texto) => `<div class="desempeno"><span class="pct">${fmt(pct)} %</span> del margen capturado<br>${texto}</div>`;

function ventanaDesempenoClub(d) {
  const rival = st.escena ? st.escena.rival : "el club";
  if (d.resultado === "acuerdo") {
    ventana(`<h2>🤝 ¡Acuerdo con ${esc(rival)}!</h2>
      <p><b>Traspaso:</b> ${esc(d.acuerdo)}</p>
      ${bloqueDesempeno(d.captura_pct, `El club pedía ${fmt(d.precio_pedido)} M€ y habría aceptado desde ${fmt(d.precio_minimo)} M€.
        Pagaste ${fmt(d.valor_pagado)} M€ en valor de hoy.`)}
      <p>Ahora negocia el contrato con el jugador desde <b>Fichajes</b>: tienes 5 días para empezar.</p>`);
  } else {
    ventana(`<h2>❌ Negociación rota con ${esc(rival)}</h2>${ultimaFrase()}
      <div class="desempeno">El club habría aceptado desde <b>${fmt(d.precio_minimo)} M€</b> (pedía ${fmt(d.precio_pedido)} M€).<br>
      Tu última oferta valía ${fmt(d.ultima_oferta_valor)} M€: faltaron ${fmt(d.faltaron)} M€.</div>`);
  }
}

function ventanaSinAcuerdoJugador(d) {
  ventana(`<h2>❌ Sin acuerdo con ${esc(d.jugador)}</h2>${ultimaFrase()}<p>El acuerdo con su club se cae.</p>
    <div class="desempeno">Ganaba ${fmt(d.salario_actual)} M€ y pedía ${fmt(d.salario_pedido)} M€ por temporada;
    habría aceptado desde ${fmt(d.salario_minimo)} M€. Tu última oferta valía ${fmt(d.ultima_oferta_valor)} M€.</div>`);
}

function ventanaFichaje(titulo, d) {
  const c = d.desempeno_club || {}, j = d.desempeno_jugador || {};
  ventana(`<img src="${IMG.fichaje}" alt="">
    <div><h2>${esc(titulo)}</h2>
      <p><b>Traspaso:</b> ${esc(d.traspaso)}<br><b>Contrato:</b> ${esc(d.contrato)}<br><b>Pago en esta ventana:</b> ${fmt(d.pago_esta_ventana)} M€</p>
      ${bloqueDesempeno(c.captura_pct, `Con el club: pedía ${fmt(c.precio_pedido)} M€, aceptaba desde ${fmt(c.precio_minimo)} M€; pagaste ${fmt(c.valor_pagado)} M€.`)}
      ${bloqueDesempeno(j.captura_pct, `Con el jugador: pedía ${fmt(j.salario_pedido)} M€, aceptaba desde ${fmt(j.salario_minimo)} M€; acordaste ${fmt(j.valor_anual_pagado)} M€ anuales.`)}
    </div>`, "¡Vamos!", "celebracion");
}

function ventanaVenta(titulo, d) {
  const x = d.desempeno || {};
  ventana(`<img src="${IMG.venta}" alt="">
    <div><h2>💰 ${esc(titulo)}</h2>
      <p><b>Traspaso:</b> ${esc(d.traspaso)}<br><b>Ingreso en esta ventana:</b> ${fmt(d.ingreso_esta_ventana)} M€</p>
      ${bloqueDesempeno(x.captura_pct, `Su primera oferta fue ${fmt(x.oferta_inicial)} M€ y habría pagado hasta ${fmt(x.precio_maximo)} M€.
        Cobraste ${fmt(x.valor_cobrado)} M€ en valor de hoy.`)}
    </div>`, "Continuar", "celebracion");
}

// ---------------------------------------------------------------- BARRA E INDICADOR DE ESPERA
function actualizarBarra() {
  const j = st.juego;
  if (!j) return;
  $("#barra").innerHTML = `
    <div class="club">${esc(j.club)}</div>
    <div class="dato"><small>Día</small><b>${j.dia} de 30</b><div class="progreso"><div style="width:${(j.dia / 30) * 100}%"></div></div></div>
    <div class="dato"><small>Presupuesto de fichajes</small><b>${fmt(j.resumen.presupuesto_fichajes)} M€</b></div>
    <div class="dato"><small>Margen salarial</small><b>${fmt(j.resumen.margen_salarial)} M€</b></div>
    <div class="dato"><small>Objetivos</small><b>${j.objetivos.length}</b></div>
    <div class="espacio"></div>
    <div class="dato"><small>Fichajes / ventas</small><b>${j.fichajes.length} / ${j.ventas.length}</b></div>`;
}

function actualizarCargando() {
  const activo = st.esperando || st.ocupado || st.rondaPendiente;
  $("#cargando").classList.toggle("oculto", !activo || !st.juego && !st.rondaPendiente);
  $("#cargando-texto").textContent = st.cargandoTexto || "Procesando…";
  document.querySelectorAll("[data-bloquear]").forEach((el) => { el.disabled = activo; });
}

// ---------------------------------------------------------------- PANTALLAS
function alRecibirPausa() {
  const p = st.pausa;
  if (p && st.automaticas.length && st.automaticas[0].tipo === p.tipo) {
    const a = st.automaticas.shift();
    const resp = typeof a.respuesta === "function" ? a.respuesta(p) : a.respuesta;
    if (resp !== null && resp !== undefined) { enviar(resp); return; }
  }
  st.automaticas = [];
  if (p && p.tipo === "centro_de_mando") {
    st.ultimoPanel = p;
    st.vista = st.vistaPedida || "menu";
    st.vistaPedida = null;
    st.escena = null;
  }
  dibujar();
}

function dibujar() {
  const p = st.pausa;
  const borrador = $("#texto-oferta") ? $("#texto-oferta").value : "";
  if (st.fin) return dibujarFinal();
  if (!p) return;
  const pantallas = {
    centro_de_mando: () => ({ menu: dibujarMenu, plantilla: dibujarPlantilla, estado: dibujarEstado,
                              bandeja: dibujarBandeja, calendario: dibujarCalendario }[st.vista] || dibujarMenu)(p),
    confirmar_cierre: dibujarConfirmarCierre,
    confirmar_prioridades: dibujarPrioridades,
    elegir_objetivo: dibujarCandidatos,
    menu_fichajes: dibujarMenuFichajes,
    primer_contacto: (x) => dibujarEscena(x, "contacto"),
    negociacion_club: (x) => dibujarEscena(x, "club"),
    negociacion_jugador: (x) => dibujarEscena(x, "jugador"),
    negociacion_venta: (x) => dibujarEscena(x, "venta"),
    confirmar_interpretacion: dibujarConfirmarInterpretacion,
    menu_ventas: dibujarMenuVentas,
    elegir_transferible: dibujarTransferibles,
  };
  (pantallas[p.tipo] || (() => { $("#pantalla").innerHTML = `<div class="contenido">Pausa desconocida: ${esc(p.tipo)}</div>`; }))(p);
  if ($("#texto-oferta") && borrador && !$("#texto-oferta").value) $("#texto-oferta").value = borrador;
  actualizarCargando();
}

const botonVolver = (respuesta) => `<button class="boton secundario" data-bloquear data-volver="${esc(respuesta ?? "")}">← Volver al menú</button>`;

function activarVolver() {
  document.querySelectorAll("[data-volver]").forEach((b) => b.addEventListener("click", () => {
    if (b.dataset.volver) enviar(b.dataset.volver, "Volviendo al menú…");
    else { st.vista = "menu"; dibujar(); }
  }));
}

// ----- ELEGIR CLUB
async function dibujarPortada() {
  document.body.classList.add("sin-barra");
  const clubes = await (await fetch("/api/clubes")).json();
  $("#pantalla").innerHTML = `
    <div class="portada">
      <h1 class="logo">Transfer<span>AI</span></h1>
      <p>Simulador multiagente de un mercado de fichajes</p>
      <div class="tarjeta">
        <input id="club" list="lista-clubes" placeholder="Escribe tu club (ej: Newcastle)" autofocus>
        <datalist id="lista-clubes">${clubes.map((c) => `<option value="${esc(c)}">`).join("")}</datalist>
        <button class="boton" id="empezar">Empezar</button>
      </div>
    </div>`;
  const empezar = () => {
    const texto = $("#club").value.trim().toLowerCase();
    const club = clubes.find((c) => c.toLowerCase() === texto) || clubes.filter((c) => c.toLowerCase().includes(texto))[0];
    if (!texto || !club) return aviso("No encontré ese club", "advertencia");
    nuevaPartida(club);
  };
  $("#empezar").addEventListener("click", empezar);
  $("#club").addEventListener("keydown", (e) => { if (e.key === "Enter") empezar(); });
}

// ----- MENÚ PRINCIPAL
function dibujarMenu(p) {
  const opciones = [
    { n: 1, texto: "Ver plantilla", sub: "Jugadores y análisis del Manager", accion: () => pedir("1", "plantilla") },
    { n: 2, texto: "Estado del club", sub: "Objetivos, negociaciones y operaciones", accion: () => pedir("2", "estado") },
    { n: 3, texto: "Bandeja de entrada", sub: "Respuestas y ofertas", globito: p.mensajes_nuevos, accion: () => pedir("3", "bandeja") },
    { n: 4, texto: "Buscar refuerzos", sub: "Manager + Scouting + Financial", accion: () => { st.logAgentes = []; enviar("4", "El Manager Agent revisa la plantilla…"); } },
    { n: 5, texto: "Fichajes", sub: "Ofertar y negociar por tus objetivos", globito: p.negociaciones_abiertas, accion: () => enviar("5") },
    { n: 6, texto: "Ventas", sub: "Poner en venta y responder ofertas", globito: p.ofertas_recibidas, accion: () => enviar("6") },
    { n: 7, texto: "Avanzar días", sub: "Calendario de la ventana", accion: () => { st.eventosRonda = []; st.vista = "calendario"; dibujar(); } },
  ];
  const id = st.juego && st.juego.identidad;
  $("#pantalla").innerHTML = `
    <div class="menu">
      <div class="tabletas">
        ${opciones.map((o, i) => `<button class="tableta" data-bloquear data-op="${i}">
            <span class="num">${o.n}</span><span>${o.texto}<small>${o.sub}</small></span>
            ${o.globito ? `<span class="globito">${o.globito}</span>` : ""}</button>`).join("")}
      </div>
      <div class="menu-derecha">
        <h1 class="logo">Transfer<span>AI</span></h1>
        <p class="subtitulo">${esc(p.club)} · quedan ${p.dias_restantes} días de mercado${id ? `<br>${esc(id.entrenador)} · ${esc(id.descripcion)}` : ""}</p>
        <button class="boton peligro boton-cerrar-mercado" data-bloquear id="cerrar-mercado">8 · Cerrar el mercado</button>
      </div>
    </div>`;
  document.querySelectorAll("[data-op]").forEach((b) => b.addEventListener("click", () => opciones[+b.dataset.op].accion()));
  $("#cerrar-mercado").addEventListener("click", () => enviar("8"));
}

function pedir(respuesta, vista) {
  st.vistaPedida = vista;
  enviar(respuesta);
}

function dibujarConfirmarCierre(p) {
  dibujarMenu(st.ultimoPanel || { club: st.juego.club, dias_restantes: 30 - p.dia });
  const extra = p.eventos_pendientes ? `<p>Quedan <b>${p.eventos_pendientes}</b> respuestas pendientes que se perderán.</p>` : "";
  ventanaPausa(`<h2>¿Cerrar el mercado en el día ${p.dia}?</h2><p>Esta acción no se puede deshacer.</p>${extra}`, [
    { texto: "Cancelar", clase: "secundario", accion: () => enviar("n") },
    { texto: "Sí, cerrar el mercado", clase: "peligro", accion: () => enviar("s", "Cerrando el mercado…") },
  ]);
}

// ----- PLANTILLA
function dibujarPlantilla() {
  const j = st.juego, d = j.diagnostico, fichados = new Set(j.fichajes.map((f) => f.id));
  const lista = (xs, f) => (xs && xs.length ? `<ul>${xs.map((x) => `<li>${f(x)}</li>`).join("")}</ul>` : `<p class="vacio">Sin datos</p>`);
  const analisis = d ? `
    ${j.diagnostico_vigente ? "" : `<p class="vacio">Este análisis es anterior a tus últimos movimientos; se actualiza al buscar refuerzos.</p>`}
    <div class="analisis">
      <div class="tarjeta"><h3 class="titulo-seccion">Fortalezas</h3>${lista(d.fortalezas, esc)}</div>
      <div class="tarjeta"><h3 class="titulo-seccion">Debilidades</h3>${lista(d.debilidades, esc)}</div>
      <div class="tarjeta"><h3 class="titulo-seccion">Prioridades</h3>${lista(d.posiciones_prioritarias, (x) =>
        `<span class="etiqueta ${esc(x.urgencia)}">${esc(x.posicion)} · ${esc(x.urgencia)}</span> ${esc(x.motivo)}`)}</div>
    </div>` : `<div class="tarjeta" style="margin-bottom:20px"><b>Análisis del Manager Agent:</b>
      <span class="vacio">todavía no analiza la plantilla. Lo hace al entrar a "Buscar refuerzos".</span></div>`;
  const tablas = POSICIONES.map((pos) => {
    const grupo = j.plantilla.filter((x) => x.posicion === pos).sort((a, b) => b.rating - a.rating);
    if (!grupo.length) return "";
    return `<div class="tarjeta"><h3 class="titulo-seccion">${NOMBRE_POS[pos]} (${grupo.length})</h3>
      <table class="tabla"><tr><th>Jugador</th><th>Perfil</th><th>Edad</th><th>Rating</th><th>Pot.</th><th>Rol</th><th>Contrato</th><th>Salario</th><th>Valor</th></tr>
      ${grupo.map((x) => `<tr class="${fichados.has(x.id) ? "nuevo-fichaje" : ""}">
        <td><b>${esc(x.nombre)}</b>${fichados.has(x.id) ? " 🆕" : ""}</td><td>${esc(x.perfil_tactico)}</td><td>${x.edad}</td>
        <td><span class="rating">${x.rating}</span></td><td>${x.potencial ?? "-"}</td><td>${x.titular === "si" ? "titular" : "suplente"}</td>
        <td>${x.anios_contrato} a</td><td>${fmt(x.salario_anual)}</td><td>${fmt(x.valor_mercado)}</td></tr>`).join("")}
      </table></div>`;
  }).join("");
  $("#pantalla").innerHTML = `<div class="contenido">
    <div class="encabezado"><h1>Plantilla de ${esc(j.club)}</h1>${botonVolver()}</div>
    ${j.identidad ? `<p><b>${esc(j.identidad.entrenador)}</b> · ${esc(j.identidad.descripcion)} ·
      Masa salarial ${fmt(j.resumen.masa_salarial_actual)} de ${fmt(j.resumen.tope_salarial)} M€ (montos en millones de euros)</p>` : ""}
    ${analisis}
    <div class="posiciones">${tablas}</div></div>`;
  activarVolver();
}

// ----- ESTADO DEL CLUB
function dibujarEstado() {
  const e = st.estadoClub || { panel: {}, fichajes: [], ventas: [], negociaciones: [], calendario: [] };
  const lista = (xs, f, vacio) => (xs.length ? `<ul>${xs.map((x) => `<li>${f(x)}</li>`).join("")}</ul>` : `<p class="vacio">${vacio}</p>`);
  $("#pantalla").innerHTML = `<div class="contenido">
    <div class="encabezado"><h1>Estado de ${esc(st.juego.club)}</h1>${botonVolver()}</div>
    <div class="grilla-2">
      <div class="tarjeta"><h3 class="titulo-seccion">Objetivos</h3>${lista(e.panel.objetivos || [], (o) => `${esc(o.nombre)} (${esc(o.club)})`, "Sin objetivos. Búscalos en Buscar refuerzos.")}</div>
      <div class="tarjeta"><h3 class="titulo-seccion">Negociaciones</h3>${lista(e.negociaciones, (n) => `<b>${esc(n.jugador)}</b> (${esc(n.club)}): ${esc(n.estado)}`, "Ninguna todavía.")}</div>
      <div class="tarjeta"><h3 class="titulo-seccion">Fichajes cerrados</h3>${lista(e.fichajes, (f) => `<b>${esc(f.nombre)}</b> desde ${esc(f.club_origen)}: ${esc(f.traspaso)}; ${esc(f.contrato)}`, "Ninguno.")}</div>
      <div class="tarjeta"><h3 class="titulo-seccion">Ventas cerradas</h3>${lista(e.ventas, (v) => `<b>${esc(v.nombre)}</b> a ${esc(v.club_destino)}: ${esc(v.traspaso)}`, "Ninguna.")}</div>
      <div class="tarjeta"><h3 class="titulo-seccion">Pendiente en el calendario</h3>${lista(e.calendario, (c) => `Día ${c.dia}: ${esc(c.asunto)}`, "Nada pendiente.")}</div>
      <div class="tarjeta"><h3 class="titulo-seccion">Finanzas</h3><ul>
        <li>Presupuesto de fichajes: <b>${fmt(st.juego.resumen.presupuesto_fichajes)} M€</b></li>
        <li>Margen salarial: <b>${fmt(st.juego.resumen.margen_salarial)} M€</b></li>
        <li>Masa salarial: ${fmt(st.juego.resumen.masa_salarial_actual)} de ${fmt(st.juego.resumen.tope_salarial)} M€</li></ul></div>
    </div></div>`;
  activarVolver();
}

// ----- BANDEJA
function remitente(m) {
  if (m.tipo === "respuesta_primer_contacto") return m.asunto.split(" responde sobre ")[0];
  if (m.tipo === "oferta_venta") return m.asunto.split(" ofrece ")[0];
  if (m.tipo === "plazo_vencido") return m.asunto.replace(" cierra la puerta", "");
  return "TransferAI (aviso del sistema)";
}

function dibujarBandeja() {
  const mensajes = [...st.bandeja].reverse();
  if (st.mensajeSel === null && mensajes.length) st.mensajeSel = mensajes[0].id;
  const sel = mensajes.find((m) => m.id === st.mensajeSel);
  const irA = sel && (sel.tipo === "respuesta_primer_contacto" || sel.tipo === "oferta_venta");
  $("#pantalla").innerHTML = `<div class="contenido">
    <div class="encabezado"><h1>Bandeja de entrada</h1>${botonVolver()}</div>
    ${mensajes.length ? `<div class="bandeja">
      <div class="tarjeta lista-mensajes">${mensajes.map((m) => `
        <div class="item-mensaje ${m.leido ? "" : "no-leido"} ${m.id === st.mensajeSel ? "activo" : ""}" data-id="${m.id}">
          <div class="de"><span>${esc(remitente(m))}</span><span>${m.leido ? "" : '<span class="etiqueta nuevo">NUEVO</span> '}día ${m.dia}</span></div>
          <div class="asunto">${esc(m.asunto)}</div></div>`).join("")}</div>
      <div class="tarjeta lector">${sel ? `
        <div class="cabecera-mail"><b>De:</b> ${esc(remitente(sel))}<br><b>Para:</b> Dirección deportiva, ${esc(st.juego.club)}<br>
          <b>Fecha:</b> día ${sel.dia} de la ventana<br><b>Asunto:</b> ${esc(sel.asunto)}</div>
        <div class="cuerpo">${esc((sel.datos && sel.datos.mensaje) || sel.asunto)}</div>
        ${irA ? `<p><button class="boton" data-bloquear id="ir-negociacion">Ir a la negociación →</button></p>` : ""}` : ""}</div>
    </div>` : `<div class="tarjeta"><p class="vacio">No hay mensajes todavía.</p></div>`}</div>`;
  document.querySelectorAll(".item-mensaje").forEach((el) => el.addEventListener("click", () => { st.mensajeSel = +el.dataset.id; dibujarBandeja(); }));
  if (irA) $("#ir-negociacion").addEventListener("click", () => irANegociacion(sel));
  activarVolver();
}

function irANegociacion(m) {
  if (m.tipo === "respuesta_primer_contacto") {
    st.automaticas = [{ tipo: "menu_fichajes", respuesta: String(m.datos.jugador_id) }];
    enviar("5");
  } else {
    const club = m.asunto.split(" ofrece ")[0], jugador = m.asunto.split(" por ").pop();
    st.automaticas = [{ tipo: "menu_ventas", respuesta: (p) => {
      const i = p.ofertas.findIndex((o) => o.club === club && o.jugador === jugador);
      if (i < 0) { aviso("Esa oferta ya no está vigente.", "advertencia"); return null; }
      return String(i + 1);
    } }];
    enviar("6");
  }
}

// ----- AVANZAR DÍAS (calendario)
function dibujarCalendario() {
  const j = st.juego, porDia = {};
  j.calendario.forEach((c) => (porDia[c.dia] = porDia[c.dia] || []).push({ texto: c.asunto, clase: "" }));
  j.plazos_jugador.forEach((x) => (porDia[x.dia] = porDia[x.dia] || []).push({ texto: `Plazo: ${x.jugador}`, clase: "plazo" }));
  const novedades = st.eventosRonda.filter((e) => e.tipo === "mensaje");
  const dias = Array.from({ length: 30 }, (_, i) => i + 1).map((d) => `
    <div class="dia ${d < j.dia ? "pasado" : ""} ${d === j.dia ? "hoy" : ""}"><div class="n">${d}</div>
      ${(porDia[d] || []).map((ev) => `<div class="evento ${ev.clase}" title="${esc(ev.texto)}">${esc(ev.texto.length > 34 ? ev.texto.slice(0, 32) + "…" : ev.texto)}</div>`).join("")}</div>`).join("");
  $("#pantalla").innerHTML = `<div class="contenido">
    <div class="encabezado"><h1>Calendario · día ${j.dia} de 30</h1>${botonVolver()}</div>
    <div class="calendario">${dias}</div>
    <div class="tarjeta barra-acciones"><b>Avanzar:</b>
      ${[1, 3, 5, 7].map((n) => `<button class="boton" data-bloquear data-dias="${n}">+${n} día${n > 1 ? "s" : ""}</button>`).join("")}
      <span class="vacio">Las respuestas de los clubes y las ofertas llegan a la bandeja al pasar los días.</span></div>
    ${novedades.length ? `<div class="tarjeta" style="margin-top:16px"><h3 class="titulo-seccion">Novedades</h3>
      <ul>${novedades.map((e) => `<li>Día ${e.datos.dia}: ${esc(e.mensaje)}</li>`).join("")}</ul></div>` : ""}</div>`;
  document.querySelectorAll("[data-dias]").forEach((b) => b.addEventListener("click", () => {
    const n = +b.dataset.dias;
    const avanzar = () => pedir(`7 ${n}`, "calendario");
    if (j.dia + n > 30) {
      ventanaPausa(`<h2>¿Avanzar ${n} días?</h2><p>Superarías el día 30 y el mercado se cerraría.</p>`,
        [{ texto: "Cancelar", clase: "secundario", accion: () => {} }, { texto: "Avanzar igual", clase: "peligro", accion: avanzar }]);
    } else avanzar();
  }));
  activarVolver();
}

// ----- SCOUTING
function dibujarPrioridades(p) {
  const propuestas = p.propuestas || [];
  const elegidas = new Set(propuestas.map((x) => x.posicion).filter((x) => POSICIONES.includes(x)));
  const d = st.juego && st.juego.diagnostico;
  $("#pantalla").innerHTML = `<div class="contenido">
    <div class="encabezado"><h1>Buscar refuerzos · prioridades del Manager</h1></div>
    <div class="grilla-2" style="grid-template-columns: 220px 1fr; align-items:end">
      <img src="${IMG.manager}" alt="Manager Agent" style="width:100%">
      <div>
        <div class="propuestas">${propuestas.map((x) => `<div class="tarjeta">
          <span class="etiqueta ${esc(x.urgencia)}">${esc(x.posicion)} · urgencia ${esc(x.urgencia)}</span>
          <p style="margin:8px 0 0">${esc(x.motivo)}</p></div>`).join("")}</div>
        ${d && d.restricciones ? `<p><b>Restricciones:</b> ${esc(d.restricciones)}</p>` : ""}
        <b>¿Qué posiciones quieres reforzar?</b>
        <div class="chips">${POSICIONES.map((x) => `<button class="chip ${elegidas.has(x) ? "activo" : ""}" data-pos="${x}">${x} · ${NOMBRE_POS[x]}</button>`).join("")}</div>
        <button class="boton" data-bloquear id="buscar">Buscar jugadores →</button>
      </div>
    </div></div>`;
  document.querySelectorAll("[data-pos]").forEach((b) => b.addEventListener("click", () => {
    elegidas.has(b.dataset.pos) ? elegidas.delete(b.dataset.pos) : elegidas.add(b.dataset.pos);
    b.classList.toggle("activo");
  }));
  $("#buscar").addEventListener("click", () => {
    if (!elegidas.size) return aviso("Elige al menos una posición", "advertencia");
    st.logAgentes = [];
    enviar([...elegidas].join(","), "El Scouting Agent está buscando candidatos…");
  });
}

function dibujarCandidatos(p) {
  const fichas = (p.candidatos || []).map((c) => {
    const a = c.analisis || {}, encaje = c.encaje_tactico ?? 0;
    const color = c.nivel_encaje === "alto" ? "var(--verde)" : c.nivel_encaje === "medio" ? "var(--oro)" : "var(--naranja)";
    return `<div class="ficha">
      <h3>${esc(c.nombre)} <span class="rating">${c.rating}</span></h3>
      <div class="meta">${esc(c.posicion)} · ${c.edad} años · ${esc(c.club)}${c.potencial ? ` · potencial ${c.potencial}` : ""}</div>
      <div class="fila"><span class="etiqueta">${esc((c.tipo_de_fichaje || "").replace(/_/g, " "))}</span>
        <span class="etiqueta ${esc(a.veredicto)}">${esc((a.veredicto || "").toUpperCase())}</span></div>
      <div class="fila"><span>Traspaso estimado</span><b>${fmt(a.traspaso_estimado)} M€</b></div>
      <div class="fila"><span>Salario estimado</span><b>${fmt(a.salario_estimado_min)}–${fmt(a.salario_estimado_max)} M€</b></div>
      <div class="fila"><span>Presupuesto restante</span><b>${fmt(a.presupuesto_restante)} M€</b></div>
      ${c.perfil_tactico ? `<div class="fila"><span>${esc(c.perfil_tactico)}</span><b>encaje ${fmt(encaje)}/100</b></div>
        <div class="barra-encaje"><div style="width:${encaje}%;background:${color}"></div></div>
        <div class="fila" style="font-size:.8rem;color:var(--gris)"><span>Mejor actual: ${fmt(c.encaje_del_mejor_actual)}</span>
          <span>${esc((c.atributos_clave_para_el_estilo || []).join(", "))}</span></div>` : ""}
      <div class="nota"><b>Scouting Agent</b>${esc(c.justificacion)}</div>
      ${c.comentario ? `<div class="nota"><b>Financial Agent</b>${esc(c.comentario)}</div>` : ""}
      <button class="boton verde" data-bloquear data-id="${c.id}" style="width:100%">+ Agregar a objetivos</button>
    </div>`;
  }).join("");
  const otraRonda = p.intentos < p.max_rondas;
  $("#pantalla").innerHTML = `<div class="contenido">
    <div class="encabezado"><h1>Candidatos · ronda ${p.intentos} de ${p.max_rondas}</h1>${botonVolver("salir")}</div>
    ${fichas ? `<div class="fichas">${fichas}</div>` : `<div class="tarjeta" style="margin-bottom:18px"><p class="vacio">No hubo candidatos viables en esta ronda.</p></div>`}
    <div class="tarjeta barra-acciones" style="margin-bottom:16px">
      <input id="indicacion" placeholder="${otraRonda ? "Indicación para otra ronda (ej: más jóvenes, zurdo, más barato)" : "Ya no quedan rondas de scouting"}" ${otraRonda ? "" : "disabled"}>
      <button class="boton secundario" data-bloquear id="otra-ronda" ${otraRonda ? "" : "disabled"}>Nueva ronda</button>
    </div>
    ${st.logAgentes.length ? `<details><summary><b>Pasos de los agentes</b> (${st.logAgentes.length})</summary>
      <div class="registro-agentes">${st.logAgentes.map(esc).join("<br>")}</div></details>` : ""}</div>`;
  document.querySelectorAll("[data-id]").forEach((b) => b.addEventListener("click", () => enviar(b.dataset.id)));
  $("#otra-ronda").addEventListener("click", () => {
    st.logAgentes = [];
    enviar($("#indicacion").value.trim() || "nueva", "El Scouting Agent hace otra ronda…");
  });
  activarVolver();
}

// ----- FICHAJES Y VENTAS (menús)
function dibujarMenuFichajes(p) {
  const accion = { sin_oferta: "Primer contacto", abierta: "Negociar con el club", acuerdo_club: "Negociar con el jugador" };
  $("#pantalla").innerHTML = `<div class="contenido">
    <div class="encabezado"><h1>Fichajes · tus objetivos</h1>${botonVolver("volver")}</div>
    ${p.objetivos.length ? `<div class="lista-filas">${p.objetivos.map((o) => `
      <div class="tarjeta fila-item"><div class="info"><b>${esc(o.nombre)}</b> <span class="etiqueta">${esc(o.posicion)}</span>
        <div>${esc(o.club)} · ${esc(o.estado)}</div></div>
        ${accion[o.fase] ? `<button class="boton" data-bloquear data-obj="${o.id}">${accion[o.fase]} →</button>` : ""}</div>`).join("")}</div>`
      : `<div class="tarjeta"><p class="vacio">No tienes objetivos. Búscalos en "Buscar refuerzos".</p></div>`}</div>`;
  document.querySelectorAll("[data-obj]").forEach((b) => b.addEventListener("click", () => enviar(b.dataset.obj)));
  activarVolver();
}

function dibujarMenuVentas(p) {
  $("#pantalla").innerHTML = `<div class="contenido">
    <div class="encabezado"><h1>Ventas</h1>${botonVolver("volver")}</div>
    <div class="grilla-2">
      <div class="tarjeta"><h3 class="titulo-seccion">Jugadores en venta</h3>
        ${p.transferibles.length ? `<ul>${p.transferibles.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>` : `<p class="vacio">Ningún jugador en venta.</p>`}
        <button class="boton" data-bloquear id="poner-venta">+ Poner un jugador en venta</button>
        <p class="vacio">Las ofertas por jugadores en venta llegan sobre todo en los primeros 20 días. También pueden llegar ofertas espontáneas.</p></div>
      <div class="tarjeta"><h3 class="titulo-seccion">Ofertas recibidas</h3>
        ${p.ofertas.length ? `<div class="lista-filas">${p.ofertas.map((o, i) => `<div class="fila-item">
          <div class="info"><b>${esc(o.club)}</b> ofrece ${esc(o.oferta)} por <b>${esc(o.jugador)}</b>
            <div>día ${o.dia} · ${o.motivo === "espontanea" ? "oferta espontánea" : "por jugador en venta"}</div></div>
          <button class="boton" data-bloquear data-oferta="${i + 1}">Responder →</button></div>`).join("")}</div>`
          : `<p class="vacio">No hay ofertas pendientes.</p>`}</div>
    </div></div>`;
  $("#poner-venta").addEventListener("click", () => enviar("vender"));
  document.querySelectorAll("[data-oferta]").forEach((b) => b.addEventListener("click", () => enviar(b.dataset.oferta)));
  activarVolver();
}

function dibujarTransferibles(p) {
  $("#pantalla").innerHTML = `<div class="contenido">
    <div class="encabezado"><h1>Poner un jugador en venta</h1>${botonVolver("volver")}</div>
    ${p.jugadores.length ? `<div class="tarjeta"><table class="tabla">
      <tr><th>Jugador</th><th>Posición</th><th>Edad</th><th>Rating</th><th>Valor</th><th></th></tr>
      ${p.jugadores.map((j, i) => `<tr><td><b>${esc(j.nombre)}</b></td><td>${esc(j.posicion)}</td><td>${j.edad}</td>
        <td><span class="rating">${j.rating}</span></td><td>${fmt(j.valor_mercado)} M€</td>
        <td><button class="boton chico" data-bloquear data-j="${i + 1}">Poner en venta</button></td></tr>`).join("")}
    </table></div>` : `<div class="tarjeta"><p class="vacio">No hay jugadores disponibles (la plantilla mínima es de 18).</p></div>`}</div>`;
  document.querySelectorAll("[data-j]").forEach((b) => b.addEventListener("click", () => enviar(b.dataset.j)));
  activarVolver();
}

// ----- ESCENA DE NEGOCIACIÓN
function datosEscena(p, modo) {
  if (modo === "club") return { clave: `club|${p.jugador}|${p.club_vendedor}`, rival: p.club_vendedor, img: IMG.club,
    titulo: `Negociación con ${p.club_vendedor} por ${p.jugador}`, exigenciaPausa: p.exigencia, etiqueta: "Exigencia",
    datos: `Ronda ${p.ronda} de ${p.max_rondas} · presupuesto ${fmt(p.presupuesto)} M€ · valor de mercado ${fmt(p.valor_mercado)} M€` };
  if (modo === "jugador") return { clave: `jug|${p.jugador}`, rival: `Agente de ${p.jugador}`, img: IMG.agente,
    titulo: `Contrato de ${p.jugador}`, exigenciaPausa: p.exigencia, etiqueta: "Exigencia",
    datos: `Ronda ${p.ronda} de ${p.max_rondas} · margen salarial ${fmt(p.margen_salarial)} M€ · gana hoy ${esc(p.salario_estimado)} M€` };
  if (modo === "venta") return { clave: `venta|${p.jugador}|${p.club}`, rival: p.club, img: IMG.club,
    titulo: `${p.club} quiere a ${p.jugador}`, exigenciaPausa: p.oferta, etiqueta: "Su oferta", ultimo: p.ultimo_mensaje,
    datos: `Ronda ${p.ronda} de ${p.max_rondas} · valor de mercado ${fmt(p.valor_mercado)} M€` };
  return { clave: `contacto|${p.jugador}|${p.club_vendedor}|${p.intento}`, rival: p.club_vendedor, img: IMG.club,
    titulo: `Primer contacto con ${p.club_vendedor} por ${p.jugador} (intento ${p.intento} de 2)`, exigenciaPausa: "", etiqueta: "",
    datos: `Valor de mercado ${fmt(p.valor_mercado)} M€ · cláusula ${p.clausula ? fmt(p.clausula) + " M€" : "no tiene"} · presupuesto ${fmt(p.presupuesto)} M€` };
}

function dibujarEscena(p, modo, bloqueada = false) {
  const info = datosEscena(p, modo);
  if (!st.escena || st.escena.clave !== info.clave) {
    const entrada = st.entrada || {};
    st.escena = { clave: info.clave, rival: info.rival, modo, rivalTexto: info.ultimo || entrada.ultimo || "", miTexto: "",
                  entendido: "", notas: [], exigencia: "", esperandoRival: false,
                  historial: (info.ultimo || entrada.ultimo) ? [{ de: info.rival, texto: info.ultimo || entrada.ultimo }] : [] };
    st.entrada = null;
  }
  st.ultimaPausaEscena = { p, modo };
  const e = st.escena;
  const exigencia = info.exigenciaPausa || e.exigencia;
  const rivalHtml = e.esperandoRival
    ? `<span class="escribiendo">${esc(e.rival)} está escribiendo <span>.</span><span>.</span><span>.</span></span>`
    : esc(e.rivalTexto);
  const consejos = modo === "club" || modo === "jugador";
  const ayuda = { contacto: "Muestra interés sin cifras, haz una oferta (fijos, variables, % de reventa, recompra, cuotas) o paga la cláusula.",
                  club: "Escribe tu oferta como a un club real, acepta sus condiciones o retírate.",
                  jugador: "Ofrece salario, años (o años + 1 opcional), bonos y prima; o acepta sus condiciones.",
                  venta: "Escribe cuánto pides (ej: 30 millones y un 10 % de una futura venta), o acepta / rechaza su oferta." }[modo];
  $("#pantalla").innerHTML = `<div class="negociacion">
    <div class="escena">
      <div class="titulo-escena"><div class="tarjeta"><h2>${esc(info.titulo)}</h2><div>${info.datos}</div>
        ${exigencia ? `<div class="exigencia">${info.etiqueta}: <span class="etiqueta">${esc(exigencia)}</span></div>` : ""}</div></div>
      <div class="consejos">
        ${e.historial.length ? `<button class="boton secundario chico" id="ver-historial">Historial</button>` : ""}
        <label class="etiqueta" style="cursor:pointer"><input type="checkbox" id="ver-arbitro" ${st.verArbitro ? "checked" : ""}> árbitro</label>
        ${consejos ? `<button class="boton chico" data-bloquear data-consejo="consejo m">Consejo Manager</button>
                      <button class="boton chico" data-bloquear data-consejo="consejo f">Consejo Financial</button>` : ""}
      </div>
      <img class="personaje izq" src="${IMG.usuario}" alt="Tú">
      <img class="personaje der" src="${info.img}" alt="${esc(info.rival)}">
      ${e.miTexto ? `<div class="globo izq"><span class="quien">Tú</span>${esc(e.miTexto)}
        ${e.entendido ? `<div class="entendido">Entendido: ${esc(e.entendido)}</div>` : ""}
        ${e.rechazado ? `<div class="rechazado">No se envió: ${esc(e.rechazado)}</div>` : ""}</div>` : ""}
      ${e.rivalTexto || e.esperandoRival ? `<div class="globo der"><span class="quien">${esc(e.rival)}</span>${rivalHtml}
        ${st.verArbitro && !e.esperandoRival ? e.notas.map((n) => `<div class="arbitro">⚖ Árbitro: ${esc(n)}</div>`).join("") : ""}</div>` : ""}
      <div id="capa-asesor"></div>
    </div>
    <div class="tablero">
      <div style="flex:1;display:flex;flex-direction:column">
        <textarea id="texto-oferta" data-bloquear placeholder="Escribe tu mensaje…"></textarea>
        <div class="ayuda">${ayuda} (Enter para enviar)</div>
      </div>
      <div class="botones">
        <button class="boton" data-bloquear id="enviar-oferta">Enviar</button>
        ${modo === "venta" ? `<button class="boton verde chico" data-bloquear data-rapido="aceptar">Aceptar oferta</button>
                              <button class="boton peligro chico" data-bloquear data-rapido="rechazar">Rechazar</button>` : ""}
        ${modo === "club" || modo === "jugador" ? `<button class="boton verde chico" data-bloquear data-rapido="Aceptamos sus condiciones.">Aceptar sus condiciones</button>
                              <button class="boton peligro chico" data-bloquear data-rapido="Nos retiramos de la negociación.">Retirarme</button>` : ""}
        ${modo === "contacto" ? botonVolver("volver") : ""}
      </div>
    </div></div>`;

  const enviarTexto = (texto) => {
    texto = texto.trim();
    if (!texto) return;
    e.miTexto = texto; e.entendido = ""; e.notas = []; e.rechazado = "";
    e.historial.push({ de: "Tú", texto });
    e.esperandoRival = modo !== "contacto";
    dibujarEscena(p, modo);
    enviar(texto, modo === "contacto" ? "Enviando tu mensaje…" : `${e.rival} está pensando su respuesta…`);
  };
  const area = $("#texto-oferta");
  $("#enviar-oferta").addEventListener("click", () => enviarTexto(area.value));
  area.addEventListener("keydown", (ev) => { if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); enviarTexto(area.value); } });
  document.querySelectorAll("[data-rapido]").forEach((b) => b.addEventListener("click", () => {
    const texto = b.dataset.rapido;
    const esFinal = /rechazar|retiramos/i.test(texto);
    if (esFinal) {
      ventanaPausa(`<h2>¿Seguro?</h2><p>${modo === "venta" ? "Rechazar cierra esta oferta." : "Retirarte cierra esta negociación."}</p>`,
        [{ texto: "Cancelar", clase: "secundario", accion: () => {} }, { texto: "Sí", clase: "peligro", accion: () => enviarTexto(texto) }]);
    } else enviarTexto(texto);
  }));
  document.querySelectorAll("[data-consejo]").forEach((b) => b.addEventListener("click", () =>
    enviar(b.dataset.consejo, b.dataset.consejo === "consejo m" ? "El Manager Agent está pensando…" : "El Financial Agent está haciendo números…")));
  $("#ver-arbitro").addEventListener("change", (ev) => { st.verArbitro = ev.target.checked; dibujarEscena(p, modo); });
  if ($("#ver-historial")) $("#ver-historial").addEventListener("click", () => ventana(`<h2>Historial</h2>
    ${e.historial.map((h) => `<p><b>${esc(h.de)}:</b> ${esc(h.texto)}</p>`).join("")}`, "Cerrar"));
  activarVolver();
  if (!bloqueada) area.focus();
  dibujarAsesor();
}

function dibujarAsesor() {
  const capa = $("#capa-asesor");
  if (!capa || !st.asesor) return;
  const a = st.asesor;
  const nombre = a.agente === "manager" ? "Manager Agent" : "Financial Agent";
  const sugerencia = (a.sugerencia || "").replace(/\s*\(.*\)\s*$/, "");
  capa.innerHTML = `<div class="asesor">
    <img src="${a.agente === "manager" ? IMG.manager : IMG.financiero}" alt="${nombre}">
    <div class="globo"><span class="quien">${nombre}</span>${esc(a.texto)}
      ${a.sugerencia ? `<div class="sugerencia">Oferta sugerida: ${esc(a.sugerencia)}</div>` : ""}
      ${st.verArbitro ? a.notas.map((n) => `<div class="arbitro">⚖ ${esc(n)}</div>`).join("") : ""}
      <div class="acciones">
        ${sugerencia ? `<button class="boton chico" id="usar-sugerencia">Usar esta oferta</button>` : ""}
        <button class="boton secundario chico" id="cerrar-asesor">Gracias</button></div></div></div>`;
  const cerrar = () => { st.asesor = null; capa.innerHTML = ""; };
  $("#cerrar-asesor").addEventListener("click", cerrar);
  if (sugerencia) $("#usar-sugerencia").addEventListener("click", () => { $("#texto-oferta").value = sugerencia; cerrar(); $("#texto-oferta").focus(); });
}

function dibujarConfirmarInterpretacion(p) {
  if (st.escena) st.escena.esperandoRival = false;
  if (st.ultimaPausaEscena) dibujarEscena(st.ultimaPausaEscena.p, st.ultimaPausaEscena.modo, true);
  ventanaPausa(`<h2>Antes de enviar…</h2>
    ${p.duda ? `<p>${esc(p.duda)}</p>` : ""}
    <div class="desempeno"><b>Entendí:</b> ${esc(p.oferta)}</div>`, [
    { texto: "No, la reescribo", clase: "secundario", accion: () => enviar("n") },
    { texto: "Sí, envíala así", accion: () => {
      if (st.escena) { st.escena.esperandoRival = st.escena.modo !== "contacto"; dibujarEscena(st.ultimaPausaEscena.p, st.ultimaPausaEscena.modo, true); }
      enviar("s", "Enviando…");
    } },
  ]);
}

// ----- FIN DEL MERCADO
function dibujarFinal() {
  const r = st.resumenFinal;
  if (!r) { $("#pantalla").innerHTML = `<div class="contenido"><h1>Mercado cerrado</h1></div>`; return; }
  const lista = (xs, f, vacio) => (xs.length ? `<ul>${xs.map((x) => `<li>${f(x)}</li>`).join("")}</ul>` : `<p class="vacio">${vacio}</p>`);
  $("#pantalla").innerHTML = `<div class="contenido">
    <div class="encabezado"><h1>🏁 ${esc(r.titulo)} · ${esc(r.club)}</h1>
      <button class="boton" id="nueva-partida">Nueva partida</button></div>
    <div class="grilla-2">
      <div class="tarjeta"><h3 class="titulo-seccion">Fichajes</h3>${lista(r.fichajes, (f) => `<b>${esc(f.nombre)}</b>: ${esc(f.traspaso)}; ${esc(f.contrato)}
        <br><small>Captura con el club ${fmt(f.desempeno_club && f.desempeno_club.captura_pct)} % · con el jugador ${fmt(f.desempeno_jugador && f.desempeno_jugador.captura_pct)} %</small>`, "Ninguno")}</div>
      <div class="tarjeta"><h3 class="titulo-seccion">Ventas</h3>${lista(r.ventas, (v) => `<b>${esc(v.nombre)}</b> a ${esc(v.club_destino)}: ${esc(v.traspaso)}
        <br><small>Captura ${fmt(v.desempeno && v.desempeno.captura_pct)} %</small>`, "Ninguna")}</div>
      <div class="tarjeta"><h3 class="titulo-seccion">Finanzas finales</h3><ul>
        <li>Presupuesto final: <b>${fmt(r.presupuesto_final)} M€</b></li><li>Margen salarial final: <b>${fmt(r.margen_salarial_final)} M€</b></li>
        ${(r.compromisos || []).map((c) => `<li>Por pagar: ${esc(c.jugador)} ${fmt(c.monto)} M€ (temporada +${c.temporada})</li>`).join("")}
        ${(r.ingresos_futuros || []).map((c) => `<li>Por cobrar: ${esc(c.jugador)} ${fmt(c.monto)} M€ (temporada +${c.temporada})</li>`).join("")}</ul></div>
      <div class="tarjeta"><h3 class="titulo-seccion">Objetivos sin concretar</h3>${lista(r.objetivos_sin_cerrar || [], (o) => esc(o.nombre), "Ninguno")}</div>
    </div></div>`;
  $("#nueva-partida").addEventListener("click", volverAPortada);
}

function volverAPortada() {
  Object.assign(st, { fin: false, pausa: null, juego: null, escena: null, resumenFinal: null, cola: [] });
  $("#barra").classList.add("oculto");
  dibujarPortada();
}

// ---------------------------------------------------------------- INICIO
async function iniciar() {
  const d = await (await fetch("/api/estado?desde=0")).json();
  if (d.pausa || d.ocupado) {
    // Hay una partida en curso (por ejemplo, se recargó la página): se retoma sin repetir ventanas
    st.reproduciendo = true;
    st.rondaPendiente = true;
    document.body.classList.remove("sin-barra");
    $("#barra").classList.remove("oculto");
  } else {
    await dibujarPortada();
  }
  consultar();
}

iniciar();
