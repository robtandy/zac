import { GatewayConnection } from "./connection.js";
import { ChatUI } from "./chat.js";

// Determine WebSocket URL: same host as the page, or override with query param
function getWsUrl(): string {
  const params = new URLSearchParams(window.location.search);
  const override = params.get("ws");
  if (override) return override;

  // Default: WebSocket on same host/port as the page
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}`;
}

const wsUrl = getWsUrl();

const connection = new GatewayConnection({
  url: wsUrl,
  onEvent: (event) => {
    chatUI.handleEvent(event);
  },
  onConnect: () => {
    chatUI.setConnected(true);
  },
  onDisconnect: () => {
    chatUI.setConnected(false);
  },
});

const chatUI = new ChatUI(connection);
connection.connect();
