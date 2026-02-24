import { writeFileSync, appendFileSync, existsSync } from "fs";
import { join } from "path";

// Log levels
const LOG_LEVELS = {
  DEBUG: 0,
  INFO: 1,
  WARN: 2,
  ERROR: 3,
};

// Default to INFO if ZAC_LOG_LEVEL is not set
const logLevel = process.env.ZAC_LOG_LEVEL?.toUpperCase() || "INFO";
const currentLogLevel = LOG_LEVELS[logLevel] || LOG_LEVELS.INFO;

// Log file path
const logFilePath = join(__dirname, "..", "tui.log");

// Overwrite log file on startup
if (existsSync(logFilePath)) {
  writeFileSync(logFilePath, "", "utf-8");
}

/**
 * Log a message to the log file.
 * @param level - Log level (DEBUG, INFO, WARN, ERROR).
 * @param message - Message to log.
 */
export function log(level: keyof typeof LOG_LEVELS, message: string): void {
  if (LOG_LEVELS[level] < currentLogLevel) return;
  
  const timestamp = new Date().toISOString();
  const logMessage = `[${timestamp}] [${level}] ${message}\n`;
  
  appendFileSync(logFilePath, logMessage, "utf-8");
}

// Convenience methods
export const debug = (message: string) => log("DEBUG", message);
export const info = (message: string) => log("INFO", message);
export const warn = (message: string) => log("WARN", message);
export const error = (message: string) => log("ERROR", message);