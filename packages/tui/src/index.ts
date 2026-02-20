import { GatewayConnection } from "./connection.js";
import { ChatUI } from "./chat.js";
import type { ServerEvent } from "./protocol.js";

const url = process.env.ZAC_GATEWAY_URL ?? "wss://localhost:8765";

let chatUI: ChatUI | null = null;

const connection = new GatewayConnection({
  url,
  onEvent: (event: ServerEvent) => {
    chatUI?.handleEvent(event);
  },
  onConnect: () => {
    chatUI?.setConnected(true);
  },
  onDisconnect: () => {
    chatUI?.setConnected(false);
  },
});

chatUI = new ChatUI(connection);
connection.connect();
chatUI.start();

process.on("SIGINT", () => {
  connection.disconnect();
  chatUI?.stop();
  process.exit(0);
});
