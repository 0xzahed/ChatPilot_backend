/**
 * ChatPilot Webchat Widget
 * Embeddable chat widget for external websites.
 *
 * Usage:
 *   <script src="https://chatpilot.devtosoft.tech/static/webchat/widget.js"
 *           data-workspace="WORKSPACE_ID" async></script>
 */
(function () {
  var scriptTag = document.currentScript || (function () {
    var scripts = document.getElementsByTagName("script");
    return scripts[scripts.length - 1];
  })();

  var workspaceId = scriptTag.getAttribute("data-workspace");
  if (!workspaceId) {
    console.error("[ChatPilot] Missing data-workspace attribute");
    return;
  }

  var API_BASE = "https://chatpilot.devtosoft.tech/api";
  var config = null;
  var sessionToken = localStorage.getItem("chatpilot_session_" + workspaceId);
  var isOpen = false;
  var messages = [];

  // Load config
  fetch(API_BASE + "/webchat/public/" + workspaceId + "/")
    .then(function (r) { return r.json(); })
    .then(function (data) {
      if (data.error) {
        console.error("[ChatPilot]", data.error);
        return;
      }
      config = data;
      renderWidget();
    })
    .catch(function (e) {
      console.error("[ChatPilot] Failed to load config:", e);
    });

  function renderWidget() {
    var pos = config.position === "bottom_left" ? { left: "20px" } : { right: "20px" };

    // Bubble button
    var bubble = document.createElement("div");
    bubble.id = "chatpilot-bubble";
    bubble.style.cssText = "position:fixed;bottom:20px;" +
      (pos.left ? "left:20px;" : "right:20px;") +
      "width:60px;height:60px;border-radius:50%;background:" +
      (config.primary_color || "#6366f1") +
      ";display:flex;align-items:center;justify-content:center;cursor:pointer;" +
      "box-shadow:0 4px 12px rgba(0,0,0,0.3);z-index:99999;transition:transform 0.2s;";
    bubble.innerHTML = '<svg width="28" height="28" viewBox="0 0 24 24" fill="white"><path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"/></svg>';
    bubble.onclick = toggleChat;
    document.body.appendChild(bubble);

    // Chat panel
    var panel = document.createElement("div");
    panel.id = "chatpilot-panel";
    panel.style.cssText = "position:fixed;bottom:90px;" +
      (pos.left ? "left:20px;" : "right:20px;") +
      "width:360px;height:500px;background:#fff;border-radius:12px;" +
      "box-shadow:0 8px 32px rgba(0,0,0,0.2);z-index:99999;display:none;" +
      "flex-direction:column;overflow:hidden;font-family:system-ui,-apple-system,sans-serif;";
    panel.innerHTML =
      '<div style="background:' + (config.primary_color || "#6366f1") +
      ';color:#fff;padding:14px 16px;display:flex;align-items:center;justify-content:space-between;">' +
      '<div style="display:flex;align-items:center;gap:10px;">' +
      (config.logo_url ? '<img src="' + config.logo_url + '" style="width:32px;height:32px;border-radius:50%;">' : "") +
      '<div><div style="font-weight:600;font-size:15px;">' + (config.title || "Chat with us") + '</div>' +
      '<div style="font-size:11px;opacity:0.8;">Online</div></div></div>' +
      '<button id="chatpilot-close" style="background:none;border:none;color:#fff;cursor:pointer;font-size:20px;padding:0 4px;">&times;</button>' +
      '</div>' +
      '<div id="chatpilot-messages" style="flex:1;overflow-y:auto;padding:16px;background:#f9fafb;"></div>' +
      '<div style="padding:12px;border-top:1px solid #e5e7eb;display:flex;gap:8px;">' +
      '<input id="chatpilot-input" type="text" placeholder="Type a message..." ' +
      'style="flex:1;padding:10px 12px;border:1px solid #d1d5db;border-radius:8px;font-size:14px;outline:none;">' +
      '<button id="chatpilot-send" style="background:' + (config.primary_color || "#6366f1") +
      ';color:#fff;border:none;border-radius:8px;padding:0 16px;cursor:pointer;font-size:14px;">Send</button>' +
      '</div>';
    document.body.appendChild(panel);

    document.getElementById("chatpilot-close").onclick = toggleChat;
    document.getElementById("chatpilot-send").onclick = sendMessage;
    var input = document.getElementById("chatpilot-input");
    input.addEventListener("keypress", function (e) {
      if (e.key === "Enter") sendMessage();
    });

    // Show welcome message
    addMessage("bot", config.welcome_message || "Hi! How can we help you today?");

    // Ensure session
    ensureSession();
  }

  function toggleChat() {
    var panel = document.getElementById("chatpilot-panel");
    var bubble = document.getElementById("chatpilot-bubble");
    isOpen = !isOpen;
    if (isOpen) {
      panel.style.display = "flex";
      bubble.style.transform = "scale(0.9)";
      document.getElementById("chatpilot-input").focus();
    } else {
      panel.style.display = "none";
      bubble.style.transform = "scale(1)";
    }
  }

  function addMessage(sender, text) {
    messages.push({ sender: sender, text: text });
    var container = document.getElementById("chatpilot-messages");
    if (!container) return;
    var div = document.createElement("div");
    div.style.cssText = "margin-bottom:10px;display:flex;" +
      (sender === "user" ? "justify-content:flex-end;" : "justify-content:flex-start;");
    var bubble = document.createElement("div");
    bubble.style.cssText = "max-width:75%;padding:10px 14px;border-radius:12px;font-size:14px;line-height:1.4;" +
      (sender === "user"
        ? "background:" + (config.primary_color || "#6366f1") + ";color:#fff;border-bottom-right-radius:4px;"
        : "background:#fff;border:1px solid #e5e7eb;color:#1f2937;border-bottom-left-radius:4px;");
    bubble.textContent = text;
    div.appendChild(bubble);
    container.appendChild(div);
    container.scrollTop = container.scrollHeight;
  }

  function ensureSession() {
    if (sessionToken) return;
    fetch(API_BASE + "/webchat/session/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workspace_id: workspaceId }),
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        sessionToken = data.session_token;
        localStorage.setItem("chatpilot_session_" + workspaceId, sessionToken);
      })
      .catch(function (e) {
        console.error("[ChatPilot] Session error:", e);
      });
  }

  function sendMessage() {
    var input = document.getElementById("chatpilot-input");
    var text = input.value.trim();
    if (!text) return;
    addMessage("user", text);
    input.value = "";

    // Send to backend (via conversation API — public endpoint)
    fetch(API_BASE + "/webchat/message/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        workspace_id: workspaceId,
        session_token: sessionToken,
        content: text,
      }),
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.auto_reply) {
          addMessage("bot", data.auto_reply);
        }
      })
      .catch(function (e) {
        console.error("[ChatPilot] Send error:", e);
        addMessage("bot", "Sorry, something went wrong. Please try again.");
      });
  }
})();
