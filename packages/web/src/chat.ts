import { Marked } from "marked";
import { markedHighlight } from "marked-highlight";
import type { GatewayConnection } from "./connection.js";
import type { ServerEvent } from "./protocol.js";

const marked = new Marked(
  markedHighlight({
    emptyLangClass: "hljs",
    langPrefix: "hljs language-",
    highlight(code: string, lang: string) {
      // Simple escaping — no highlight.js dependency needed for now
      return escapeHtml(code);
    },
  })
);

marked.setOptions({
  breaks: true,
  gfm: true,
});

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export class ChatUI {
  private messagesEl: HTMLElement;
  private inputEl: HTMLTextAreaElement;
  private sendBtn: HTMLButtonElement;
  private statusIndicator: HTMLElement;
  private statusText: HTMLElement;
  private connection: GatewayConnection;

  private currentAssistantEl: HTMLElement | null = null;
  private currentBodyEl: HTMLElement | null = null;
  private currentText = "";
  private isStreaming = false;
  private renderRAF: number | null = null;
  private isCompacting = false;
  private inputQueuedDuringCompaction: string[] = [];
  private canvasFrame: HTMLIFrameElement | null = null;

  constructor(connection: GatewayConnection) {
    this.connection = connection;
    this.messagesEl = document.getElementById("messages")!;
    this.inputEl = document.getElementById("input") as HTMLTextAreaElement;
    this.sendBtn = document.getElementById("send-btn") as HTMLButtonElement;
    this.statusIndicator = document.getElementById("status-indicator")!;
    this.statusText = document.getElementById("status-text")!;

    this.inputEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        this.submit();
      }
    });

    this.inputEl.addEventListener("input", () => {
      this.autoResize();
    });

    this.sendBtn.addEventListener("click", () => {
      this.submit();
    });
  }

  private submit(): void {
    const text = this.inputEl.value.trim();
    if (!text) return;

    if (text === "/compact") {
      this.connection.send({ type: "steer", message: "/compact" });
      this.inputEl.value = "";
      this.autoResize();
      return;
    }

    if (text === "/context") {
      this.connection.send({ type: "context_request" });
      this.inputEl.value = "";
      this.autoResize();
      return;
    }

    if (text === "/reload") {
      this.connection.send({ type: "steer", message: "/reload" });
      this.inputEl.value = "";
      this.autoResize();
      return;
    }

    if (this.isCompacting) {
      this.inputQueuedDuringCompaction.push(text);
      this.addQueuedMessage(text);
      this.inputEl.value = "";
      this.autoResize();
      return;
    }

    this.connection.send({ type: "prompt", message: text });
    this.inputEl.value = "";
    this.autoResize();
  }

  private autoResize(): void {
    this.inputEl.style.height = "auto";
    this.inputEl.style.height = Math.min(this.inputEl.scrollHeight, 200) + "px";
  }

  setConnected(connected: boolean): void {
    this.statusIndicator.classList.toggle("connected", connected);
    this.statusText.textContent = connected ? "Connected" : "Disconnected — reconnecting...";
  }

  handleEvent(event: ServerEvent): void {
    switch (event.type) {
      case "user_message":
        this.addUserMessage(event.message);
        break;

      case "turn_start":
        this.currentText = "";
        this.startAssistantMessage();
        this.setStatus("Thinking...");
        break;

      case "text_delta":
        this.currentText += event.delta;
        this.scheduleRender();
        this.setStatus("Responding...");
        break;

      case "tool_start":
        this.flushAssistantText();
        this.addToolMessage(`Running ${event.tool_name}...`);
        this.setStatus(`Running tool: ${event.tool_name}`);
        break;

      case "tool_update":
        // Could update tool status, but skip for simplicity
        break;

      case "tool_end": {
        const status = event.is_error ? "error" : "done";
        this.addToolMessage(`${event.tool_name}: ${status}`, event.is_error);
        break;
      }

      case "turn_end":
      case "agent_end":
        this.finalizeAssistantMessage();
        this.setStatus("Ready");
        break;

      case "error":
        this.finalizeAssistantMessage();
        this.addErrorMessage(event.message);
        this.setStatus("Error");
        break;

      case "context_info":
        // Could render a context bar; for now just ignore
        break;

      case "compaction_start": {
        this.isCompacting = true;
        this.setStatus("Compacting context...");
        const indicator = document.createElement("div");
        indicator.className = "compaction-indicator";
        indicator.id = "compaction-indicator";
        indicator.innerHTML = '<div class="compaction-spinner"></div>Compacting context...';
        this.messagesEl.appendChild(indicator);
        this.scrollToBottom();
        break;
      }

      case "compaction_end": {
        this.isCompacting = false;
        // Clear all messages from the DOM
        this.messagesEl.innerHTML = "";
        // Show compaction banner with token count
        const banner = document.createElement("div");
        banner.className = "compaction-banner";
        const tokenInfo = event.tokens_before > 0
          ? `[Compacted from ${event.tokens_before.toLocaleString()} tokens]`
          : "[Compaction complete]";
        banner.textContent = tokenInfo;
        this.messagesEl.appendChild(banner);
        // Show summary text
        if (event.summary) {
          const summaryEl = this.createMessage("assistant");
          const body = summaryEl.querySelector(".message-body")!;
          const html = marked.parse(event.summary) as string;
          body.innerHTML = html;
          this.messagesEl.appendChild(summaryEl);
        }
        this.scrollToBottom();
        this.setStatus("Ready");
        // Flush queued input
        for (const msg of this.inputQueuedDuringCompaction) {
          this.connection.send({ type: "prompt", message: msg });
        }
        this.inputQueuedDuringCompaction = [];
        break;
      }

      case "reload_start": {
        this.setStatus("Reloading...");
        const indicator = document.createElement("div");
        indicator.className = "compaction-indicator";
        indicator.id = "reload-indicator";
        indicator.innerHTML = '<div class="compaction-spinner"></div>Reloading agent and web packages...';
        this.messagesEl.appendChild(indicator);
        this.scrollToBottom();
        break;
      }

      case "reload_end": {
        const existing = document.getElementById("reload-indicator");
        if (existing) existing.remove();
        const banner = document.createElement("div");
        banner.className = event.success ? "compaction-banner" : "compaction-banner reload-error";
        banner.textContent = event.message;
        this.messagesEl.appendChild(banner);
        this.scrollToBottom();
        this.setStatus("Ready");
        break;
      }

      case "canvas_update": {
        const frame = this.ensureCanvasFrame();
        if (event.url) {
          frame.src = event.url;
        } else if (event.html) {
          const send = () => frame.contentWindow?.postMessage(
            { type: "zac:render", html: event.html }, "*"
          );
          if (frame.src.includes("canvas-host")) {
            send();
          } else {
            frame.src = "/canvas-host.html";
            frame.onload = send;
          }
        }
        break;
      }

      case "canvas_screenshot": {
        const el = document.createElement("div");
        el.className = "message tool";
        const body = document.createElement("div");
        body.className = "message-body";
        const img = document.createElement("img");
        img.src = `data:image/png;base64,${event.image_data}`;
        img.style.maxWidth = "100%";
        body.appendChild(img);
        el.appendChild(body);
        this.messagesEl.appendChild(el);
        this.scrollToBottom();
        break;
      }

      case "canvas_dismiss": {
        if (this.canvasFrame) {
          this.canvasFrame.remove();
          this.canvasFrame = null;
          document.getElementById("app")!.classList.remove("with-canvas");
        }
        break;
      }
    }
  }

  private addUserMessage(text: string): void {
    const el = this.createMessage("user");
    const body = el.querySelector(".message-body")!;
    body.textContent = text;
    this.messagesEl.appendChild(el);
    this.scrollToBottom();
  }

  private startAssistantMessage(): void {
    this.currentAssistantEl = this.createMessage("assistant");
    this.currentBodyEl = this.currentAssistantEl.querySelector(".message-body")!;
    this.currentBodyEl.innerHTML = '<span class="streaming-cursor"></span>';
    this.messagesEl.appendChild(this.currentAssistantEl);
    this.isStreaming = true;
    this.scrollToBottom();
  }

  private scheduleRender(): void {
    if (this.renderRAF !== null) return;
    this.renderRAF = requestAnimationFrame(() => {
      this.renderRAF = null;
      this.renderAssistantText();
    });
  }

  private renderAssistantText(): void {
    if (!this.currentBodyEl || !this.currentText) return;
    const html = marked.parse(this.currentText) as string;
    this.currentBodyEl.innerHTML = html + '<span class="streaming-cursor"></span>';
    this.scrollToBottom();
  }

  private flushAssistantText(): void {
    if (this.currentBodyEl && this.currentText) {
      const html = marked.parse(this.currentText) as string;
      this.currentBodyEl.innerHTML = html;
    }
  }

  private finalizeAssistantMessage(): void {
    if (this.renderRAF !== null) {
      cancelAnimationFrame(this.renderRAF);
      this.renderRAF = null;
    }
    if (this.currentBodyEl && this.currentText) {
      const html = marked.parse(this.currentText) as string;
      this.currentBodyEl.innerHTML = html;
    } else if (this.currentBodyEl && !this.currentText) {
      // No text was streamed — remove the empty assistant message
      this.currentAssistantEl?.remove();
    }
    this.currentAssistantEl = null;
    this.currentBodyEl = null;
    this.currentText = "";
    this.isStreaming = false;
    this.scrollToBottom();
  }

  private addToolMessage(text: string, isError = false): void {
    const el = document.createElement("div");
    el.className = "message tool" + (isError ? " tool-error" : "");
    const body = document.createElement("div");
    body.className = "message-body";
    body.textContent = text;
    el.appendChild(body);
    this.messagesEl.appendChild(el);
    this.scrollToBottom();
  }

  private addErrorMessage(text: string): void {
    const el = this.createMessage("error");
    const body = el.querySelector(".message-body")!;
    body.textContent = text;
    this.messagesEl.appendChild(el);
    this.scrollToBottom();
  }

  private createMessage(role: "user" | "assistant" | "error"): HTMLElement {
    const el = document.createElement("div");
    el.className = `message ${role}`;

    const header = document.createElement("div");
    header.className = "message-header";
    header.textContent = role === "error" ? "Error" : role;
    el.appendChild(header);

    const body = document.createElement("div");
    body.className = "message-body";
    el.appendChild(body);

    return el;
  }

  private setStatus(text: string): void {
    this.statusText.textContent = text;
  }

  private addQueuedMessage(text: string): void {
    const el = document.createElement("div");
    el.className = "message queued";
    const body = document.createElement("div");
    body.className = "message-body";
    body.textContent = `[Queued] ${text}`;
    el.appendChild(body);
    this.messagesEl.appendChild(el);
    this.scrollToBottom();
  }

  private ensureCanvasFrame(): HTMLIFrameElement {
    if (!this.canvasFrame) {
      const app = document.getElementById("app")!;
      app.classList.add("with-canvas");
      const frame = document.createElement("iframe");
      frame.id = "canvas-frame";
      frame.src = "/canvas-host.html";
      app.appendChild(frame);
      this.canvasFrame = frame;
    }
    return this.canvasFrame;
  }

  private scrollToBottom(): void {
    requestAnimationFrame(() => {
      this.messagesEl.scrollTop = this.messagesEl.scrollHeight;
    });
  }
}
