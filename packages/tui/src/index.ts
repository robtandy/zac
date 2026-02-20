import { GatewayConnection } from "./connection.js";
import { ChatUI } from "./chat.js";
import type { ServerEvent } from "./protocol.js";

function getGatewayUrl(): string {
  const args = process.argv.slice(2);
  for (let i = 0; i < args.length; i++) {
    if (args[i] === "--gateway" && args[i + 1]) return args[i + 1];
    if (args[i].startsWith("--gateway=")) return args[i].slice("--gateway=".length);
  }
  return process.env.ZAC_GATEWAY_URL ?? "wss://localhost:8765";
}

const url = getGatewayUrl();

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
