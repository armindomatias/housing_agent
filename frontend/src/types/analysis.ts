/**
 * Types for property analysis
 * These mirror the backend Pydantic models
 */

export type RoomType =
  | "cozinha"
  | "sala"
  | "quarto"
  | "casa_de_banho"
  | "corredor"
  | "varanda"
  | "exterior"
  | "garagem"
  | "arrecadacao"
  | "outro";

export type RoomCondition =
  | "excelente"
  | "bom"
  | "razoavel"
  | "mau"
  | "necessita_remodelacao_total";

export interface RenovationItem {
  item: string;
  cost_min: number;
  cost_max: number;
  priority: "alta" | "media" | "baixa";
  notes: string;
}

export interface RoomAnalysis {
  room_type: RoomType;
  room_number: number;
  room_label: string;
  images: string[];
  condition: RoomCondition;
  condition_notes: string;
  renovation_items: RenovationItem[];
  cost_min: number;
  cost_max: number;
  confidence: number;
}

export interface PropertyData {
  url: string;
  title: string;
  price: number;
  area_m2: number;
  num_rooms: number;
  num_bathrooms: number;
  floor: string;
  location: string;
  description: string;
  image_urls: string[];
}

export interface RenovationEstimate {
  property_url: string;
  property_data: PropertyData | null;
  room_analyses: RoomAnalysis[];
  total_cost_min: number;
  total_cost_max: number;
  overall_confidence: number;
  summary: string;
  disclaimer: string;
}

export interface StreamEvent {
  type: "status" | "progress" | "result" | "error";
  message: string;
  step: number;
  total_steps: number;
  data?: {
    estimate?: RenovationEstimate;
    [key: string]: unknown;
  };
}
