/* Portfolio IA — client de chat.
 *
 * Consomme POST /chat/stream en Server-Sent Events. EventSource ne sait pas
 * faire de POST, on lit donc le corps de la reponse avec fetch + ReadableStream
 * et on decoupe les evenements a la main. */

// Defini par src/config.js. Chaine vide = meme origine (cas Docker/nginx).
const API_BASE = window.PORTFOLIO_API_BASE ?? "";

const el = {
  thread: document.getElementById("thread"),
  threadInner: document.getElementById("thread-inner"),
  welcome: document.getElementById("welcome"),
  suggestions: document.getElementById("suggestions"),
  composer: document.getElementById("composer"),
  input: document.getElementById("input"),
  send: document.getElementById("send"),
  stop: document.getElementById("stop"),
  status: document.getElementById("status"),
  statusLabel: document.getElementById("status-label"),
  avatar: document.getElementById("avatar"),
  avatarImg: document.getElementById("avatar-img"),
  privacy: document.getElementById("privacy"),
};

let controller = null;
let stickToBottom = true;

/* ---------- utilitaires ---------- */

function node(tag, className, text) {
  const n = document.createElement(tag);
  if (className) n.className = className;
  if (text !== undefined) n.textContent = text;
  return n;
}

/* On ne recolle en bas que si l'utilisateur y etait deja : sinon on lui
   arracherait sa lecture a chaque token recu.
   Lire scrollHeight juste apres avoir modifie le DOM force un recalcul de mise
   en page synchrone. On le repousse dans la frame suivante, ou la mise en page
   a lieu de toute facon : au plus un recalcul par frame au lieu d'un par token. */
let scrollQueued = false;

function scrollIfPinned() {
  if (!stickToBottom || scrollQueued) return;
  scrollQueued = true;
  requestAnimationFrame(() => {
    scrollQueued = false;
    if (stickToBottom) el.thread.scrollTop = el.thread.scrollHeight;
  });
}

el.thread.addEventListener("scroll", () => {
  const distance = el.thread.scrollHeight - el.thread.scrollTop - el.thread.clientHeight;
  stickToBottom = distance < 60;
});

function setBusy(busy) {
  el.send.classList.toggle("is-hidden", busy);
  el.stop.classList.toggle("is-hidden", !busy);
  el.input.disabled = busy;
  if (!busy) el.input.focus();
}

function autoGrow() {
  el.input.style.height = "auto";
  el.input.style.height = `${el.input.scrollHeight}px`;
}

/* ---------- rendu des messages ---------- */

function addUserMessage(text) {
  const msg = node("div", "msg msg-user");
  msg.appendChild(node("div", "bubble", text));
  el.threadInner.appendChild(msg);
  stickToBottom = true;
  scrollIfPinned();
}

function addBotMessage() {
  const msg = node("div", "msg msg-bot");

  // Rappel permanent de la nature de l'interlocuteur, sur chaque reponse.
  msg.appendChild(node("div", "msg-label", "Assistant IA"));

  const phase = node("div", "phase");
  const phaseText = node("span", "phase-text", "Recherche dans le CV…");
  phase.appendChild(node("span", "phase-spinner"));
  phase.appendChild(phaseText);

  // La bulle reste masquee tant qu'aucun token n'est arrive : une boite vide
  // pendant les trois secondes de recherche fait desordre.
  const bubble = node("div", "bubble is-streaming is-hidden");
  const sources = node("div", "sources is-hidden");

  // Un noeud texte reutilise : "bubble.textContent += t" relirait puis
  // reecrirait toute la reponse a chaque token (cout quadratique), la ou
  // appendData n'ajoute que le fragment recu.
  const textNode = document.createTextNode("");
  bubble.appendChild(textNode);

  msg.append(phase, bubble, sources);
  el.threadInner.appendChild(msg);
  scrollIfPinned();

  return {
    setPhase(text) {
      phaseText.textContent = text;
    },
    hidePhase() {
      phase.remove();
    },
    appendToken(text) {
      bubble.classList.remove("is-hidden");
      textNode.appendData(text);
      scrollIfPinned();
    },
    setSources(list) {
      if (!list.length) return;
      sources.classList.remove("is-hidden");
      sources.appendChild(node("span", "sources-label", "Sources"));
      for (const s of list) {
        const chip = node("span", "source");
        chip.appendChild(node("span", null, s.section));
        chip.appendChild(node("span", "source-score", s.score.toFixed(2)));
        sources.appendChild(chip);
      }
      scrollIfPinned();
    },
    finish() {
      phase.remove();
      bubble.classList.remove("is-streaming");
      if (!textNode.data) textNode.data = "(aucune réponse reçue)";
      bubble.classList.remove("is-hidden");
      scrollIfPinned();
    },
    fail(text) {
      phase.remove();
      msg.classList.add("is-error");
      bubble.classList.remove("is-streaming", "is-hidden");
      textNode.data = text;
      scrollIfPinned();
    },
  };
}

/* ---------- lecture du flux SSE ---------- */

async function* readEvents(response) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let split;
    while ((split = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, split);
      buffer = buffer.slice(split + 2);

      let event = "message";
      let data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) event = line.slice(7);
        else if (line.startsWith("data: ")) data += line.slice(6);
      }
      if (data) yield { event, data: JSON.parse(data) };
    }
  }
}

/* ---------- envoi ---------- */

async function ask(question) {
  el.welcome?.remove();
  el.suggestions.classList.add("is-hidden");

  addUserMessage(question);
  const bot = addBotMessage();

  controller = new AbortController();
  setBusy(true);

  try {
    const response = await fetch(`${API_BASE}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question }),
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new Error(`Le serveur a répondu ${response.status}.`);
    }

    let started = false;

    for await (const { event, data } of readEvents(response)) {
      if (event === "sources") {
        // Les sources arrivent avant le premier mot : la recherche est finie,
        // le modele commence a rediger.
        bot.setPhase("Rédaction de la réponse…");
        bot.setSources(data.sources || []);
      } else if (event === "token") {
        if (!started) {
          bot.hidePhase();
          started = true;
        }
        bot.appendToken(data.text);
      } else if (event === "done") {
        bot.finish();
      }
    }

    bot.finish();
    setStatus("up");
  } catch (error) {
    if (error.name === "AbortError") {
      bot.finish();
    } else {
      bot.fail(explain(error));
      setStatus("down");
    }
  } finally {
    controller = null;
    setBusy(false);
  }
}

function explain(error) {
  if (error instanceof TypeError) {
    return (
      "Impossible de joindre l'API. Vérifiez que le backend tourne :\n" +
      "docker compose up   —   ou en local :\n" +
      "uvicorn --app-dir backend app.main:app --port 8000"
    );
  }
  return `Une erreur est survenue. ${error.message}`;
}

/* ---------- etat du backend ---------- */

function setStatus(state) {
  const labels = { up: "En ligne", down: "Hors ligne", unknown: "Connexion…" };
  el.status.dataset.state = state;
  el.statusLabel.textContent = labels[state];
}

async function checkHealth() {
  try {
    const response = await fetch(`${API_BASE}/health`, { cache: "no-store" });
    setStatus(response.ok ? "up" : "down");
  } catch {
    setStatus("down");
  }
}

/* ---------- evenements ---------- */

el.composer.addEventListener("submit", (event) => {
  event.preventDefault();
  const question = el.input.value.trim();
  if (question.length < 3 || controller) return;
  el.input.value = "";
  autoGrow();
  ask(question);
});

el.input.addEventListener("input", autoGrow);

el.input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    el.composer.requestSubmit();
  }
});

el.suggestions.addEventListener("click", (event) => {
  const chip = event.target.closest(".chip");
  if (!chip || controller) return;
  ask(chip.dataset.q);
});

el.stop.addEventListener("click", () => controller?.abort());

/* ---------- avatar ---------- */

// Si src/assets/avatar.jpeg ne se charge pas, on retombe sur les initiales
// plutot que d'afficher l'icone d'image cassee du navigateur. Le test
// "complete" couvre le cas ou l'image a deja echoue avant l'execution du script.
if (el.avatarImg.complete && el.avatarImg.naturalWidth === 0) {
  el.avatar.dataset.fallback = "true";
}
el.avatarImg.addEventListener("error", () => {
  el.avatar.dataset.fallback = "true";
});

/* ---------- confidentialite ---------- */

// Tous les liens ".link-button" ouvrent la feuille : pas d'id a inventer pour
// chaque nouveau point d'entree.
for (const button of document.querySelectorAll(".link-button")) {
  button.addEventListener("click", () => el.privacy.showModal());
}

// Clic sur le fond translucide : fermeture, comme une feuille iOS.
// Tester "event.target === el.privacy" ne suffit pas : les marges internes du
// <dialog> appartiennent au dialog lui-meme, donc un clic dedans fermait la
// feuille alors que le pointeur etait visuellement a l'interieur. On compare
// donc les coordonnees au rectangle reel.
el.privacy.addEventListener("click", (event) => {
  const box = el.privacy.getBoundingClientRect();
  const outside =
    event.clientX < box.left ||
    event.clientX > box.right ||
    event.clientY < box.top ||
    event.clientY > box.bottom;
  if (outside) el.privacy.close();
});

checkHealth();
el.input.focus();
