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

function getToolResultLines(): number {
  const val = process.env.ZAC_TOOL_RESULT_LINES;
  if (val !== undefined) {
    const parsed = parseInt(val, 10);
    if (!isNaN(parsed) && parsed >= 0) return parsed;
  }
  return 20; // default
}

function getShowThinking(): boolean {
  const val = process.env.ZAC_SHOW_THINKING;
  if (val !== undefined) {
    return val === "1";
  }
  return true; // default
}

const url = getGatewayUrl();
const toolResultLines = getToolResultLines();
const showThinking = getShowThinking();

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

chatUI = new ChatUI(connection, { toolResultLines, showThinking });
connection.connect();
chatUI.start();

process.on("SIGINT", () => {
  connection.disconnect();
  chatUI?.stop();
  process.exit(0);
});
