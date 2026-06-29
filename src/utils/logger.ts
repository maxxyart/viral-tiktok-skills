import pino from "pino";
import { env } from "../config/env.js";

export const logger = pino({
  name: "social-scraper",
  level: env.NODE_ENV === "production" ? "info" : "debug",
});
