// Centralized frontend constants.
// All hardcoded operational and display values should be defined here,
// not inline in component or hook files.

// --- API ---
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
export const API_ANALYZE_PATH = "/api/v1/analyze";

// --- Display limits ---
export const MAX_RECENT_EVENTS = 5;
export const MAX_HERO_IMAGES = 2;
export const MIN_UNIQUE_HERO_IMAGES = 2;

// --- Pipeline ---
export const DEFAULT_TOTAL_STEPS = 5;
export const STEP_LABELS = [
  "Iniciar",
  "Obter dados",
  "Classificar fotos",
  "Agrupar divisões",
  "Estimar custos",
  "Finalizar",
] as const;

// --- Locale & formatting ---
export const LOCALE = "pt-PT";
export const CURRENCY = "EUR";
export const HTML_LANG = "pt";

// --- Validation ---
export const IDEALISTA_DOMAIN = "idealista.pt";
export const IDEALISTA_PATH_SEGMENT = "/imovel/";

// --- SSE parsing ---
export const SSE_DATA_PREFIX = "data: ";
export const SSE_DATA_PREFIX_LENGTH = SSE_DATA_PREFIX.length;
