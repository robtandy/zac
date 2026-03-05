import type { EditorTheme, ImageTheme, MarkdownTheme, SelectListTheme, SettingsListTheme } from "@mariozechner/pi-tui";
import { highlight, supportsLanguage } from "cli-highlight";

// Color functions - must be defined before use
const dim = (s: string) => `\x1b[2m${s}\x1b[22m`;
const bold = (s: string) => `\x1b[1m${s}\x1b[22m`;
const italic = (s: string) => `\x1b[3m${s}\x1b[23m`;
const underline = (s: string) => `\x1b[4m${s}\x1b[24m`;
const strikethrough = (s: string) => `\x1b[9m${s}\x1b[29m`;
const cyan = (s: string) => `\x1b[36m${s}\x1b[39m`;
const green = (s: string) => `\x1b[32m${s}\x1b[39m`;
const yellow = (s: string) => `\x1b[33m${s}\x1b[39m`;
const red = (s: string) => `\x1b[31m${s}\x1b[39m`;
const magenta = (s: string) => `\x1b[35m${s}\x1b[39m`;
const gray = (s: string) => `\x1b[90m${s}\x1b[39m`;
const white = (s: string) => `\x1b[37m${s}\x1b[39m`;
const black = (s: string) => `\x1b[30m${s}\x1b[39m`;
const bgGray = (s: string) => `\x1b[100m${s}\x1b[49m`;
const orange = (s: string) => `\x1b[38;5;208m${s}\x1b[39m`;
const purple = (s: string) => `\x1b[38;5;141m${s}\x1b[39m`;
const pink = (s: string) => `\x1b[38;5;213m${s}\x1b[39m`;
const blueColor = (s: string) => `\x1b[34m${s}\x1b[39m`;

// Syntax highlighting theme for cli-highlight
const cliHighlightTheme = {
  keyword: cyan,
  built_in: cyan,
  literal: magenta,
  number: magenta,
  string: green,
  comment: gray,
  function: blueColor,
  title: blueColor,
  class: yellow,
  type: orange,
  attr: orange,
  variable: white,
  params: white,
  operator: red,
  punctuation: white,
};

/**
 * Get language identifier from file path extension.
 */
export function getLanguageFromPath(filePath: string): string | undefined {
  const ext = filePath.split(".").pop()?.toLowerCase();
  if (!ext) return undefined;

  const extToLang: Record<string, string> = {
    ts: "typescript",
    tsx: "typescript",
    js: "javascript",
    jsx: "javascript",
    mjs: "javascript",
    cjs: "javascript",
    py: "python",
    rb: "ruby",
    rs: "rust",
    go: "go",
    java: "java",
    kt: "kotlin",
    swift: "swift",
    c: "c",
    h: "c",
    cpp: "cpp",
    cc: "cpp",
    cxx: "cpp",
    hpp: "cpp",
    cs: "csharp",
    php: "php",
    html: "html",
    htm: "html",
    css: "css",
    scss: "scss",
    less: "less",
    json: "json",
    yaml: "yaml",
    yml: "yaml",
    xml: "xml",
    sql: "sql",
    sh: "bash",
    bash: "bash",
    zsh: "bash",
    fish: "bash",
    md: "markdown",
    dockerfile: "dockerfile",
    toml: "toml",
    ini: "ini",
    conf: "ini",
    makefile: "makefile",
    mk: "makefile",
    r: "r",
    lua: "lua",
    pl: "perl",
    pm: "perl",
    hs: "haskell",
    ex: "elixir",
    exs: "elixir",
    erl: "erlang",
    clj: "clojure",
    scala: "scala",
    vue: "vue",
    svelte: "svelte",
    graphql: "graphql",
    proto: "protobuf",
    zig: "zig",
    nim: "nim",
    d: "d",
    f90: "fortran",
    f: "fortran",
    m: "objectivec",
    mm: "objectivec",
    sm: "assembly",
    asm: "assembly",
  };

  return extToLang[ext];
}

/**
 * Highlight code with syntax coloring based on file extension or language.
 * Returns array of highlighted lines.
 */
export function highlightCode(code: string, lang?: string): string[] {
  // Validate language before highlighting to avoid stderr spam from cli-highlight
  const validLang = lang && supportsLanguage(lang) ? lang : undefined;
  const opts = {
    language: validLang,
    ignoreIllegals: true,
    theme: cliHighlightTheme,
  };
  try {
    return highlight(code, opts).split("\n");
  } catch {
    return code.split("\n");
  }
}

const selectListTheme: SelectListTheme = {
  selectedPrefix: cyan,
  selectedText: white,
  description: gray,
  scrollInfo: gray,
  noMatch: gray,
};

export const editorTheme: EditorTheme = {
  borderColor: gray,
  selectList: selectListTheme,
};

export const settingsListTheme: SettingsListTheme = {
  label: (text: string, selected: boolean) =>
    selected ? bgGray(white(bold(text))) : white(text),
  value: (text: string, selected: boolean) =>
    selected ? bgGray(cyan(bold(text))) : cyan(text),
  description: (text: string) => gray(text),
  cursor: yellow("\u2033"),
  hint: gray,
};

export const markdownTheme: MarkdownTheme = {
  heading: bold,
  link: cyan,
  linkUrl: underline,
  code: yellow,
  codeBlock: white,
  codeBlockBorder: gray,
  quote: italic,
  quoteBorder: gray,
  hr: gray,
  listBullet: cyan,
  bold,
  italic,
  strikethrough,
  underline,
  highlightCode,
};

export const statusColor = gray;
export const statusBarColor = dim;
export const errorColor = red;
export const userMsgColor = green;
export const toolColor = yellow;
export const toolDimColor = dim;

// Context bar colors
export const blue = (s: string) => `\x1b[34m${s}\x1b[39m`;
export const contextSystemColor = cyan;
export const contextToolsColor = yellow;
export const contextUserColor = green;
export const contextAssistantColor = magenta;
export const contextToolResultsColor = blue;
export const contextFreeColor = gray;

export const compactionColor = cyan;

// Thinking message color (distinct from regular messages)
export const thinkingColor = purple;

export const imageTheme: ImageTheme = { fallbackColor: gray };

export { bgGray, white, black };
